"""
bg_removal_panel.py
背景除去のコアUI。CTkFrame なので独立ウィンドウにもメインアプリのタブにも埋め込める。

  左: 処理する画像グリッド（base_image_sorter の仕分けグリッドを流用。D&Dで複数貯めて選択）
  右上: モデル複数選択（チェック）＋ 実行ボタン群 ＋ 進捗バー ＋ ステータス
  右下: 結果エリア（モデルごと or 画像ごとに分けてプレビュー。各右上に🔍拡大、💾保存/✏️編集）

2つの実行モードがある:
  ・single（従来）: 選択中の 1 枚を、チェックした複数モデルで処理して比較する。
  ・batch（一括）  : 取り込んだ全画像を、チェックした先頭 1 モデルでまとめて処理する。
                     画像ごとに結果パネルを並べ、💾全部保存で一気に保存できる。

処理は重いので threading で実行し、UI更新は after() 経由。
プレビュー差し替えは「新画像をラベルへ適用してから旧CTkImage参照を入れ替える」順序にして
2枚目以降が出ない CTkImage 不具合（image pyimageN doesn't exist）を防ぐ。
"""

import shutil
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

try:
    # パッケージとして import された場合（メインアプリ埋め込み等）
    from . import engine, paths
    from .widgets import IMAGE_EXTS, ImageGrid, ZoomWindow
    from .mask_editor import MaskEditorWindow
except ImportError:
    # 単体スクリプトから import された場合（独立ウィンドウ／汎用ツール配置）
    import engine
    import paths
    from widgets import IMAGE_EXTS, ImageGrid, ZoomWindow
    from mask_editor import MaskEditorWindow

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    DND_FILES = None

PINK = {
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
    "accent": "#c6b6e2",
    "accent_hover": "#b09cd4",
    "accent_text": "#3f2a44",
}

PANE_PREVIEW = (240, 190)

_ORIGINAL_KEY = "__original__"


class BgRemovalPanel(ctk.CTkFrame):
    def __init__(self, master, output_dir=None, on_status=None, **kwargs):
        super().__init__(master, **kwargs)
        self._output_dir = Path(output_dir) if output_dir else paths.OUTPUT_DIR
        # 出力ベースから振り分け先を導出（埋め込みで output_dir を変えても整合する）
        self._stage_dir = self._output_dir          # 取り込んだ画像の一時保存
        self._processed_dir = self._output_dir / "処理済み"  # 保存後の元画像
        self._png_dir = self._output_dir / "PNG"     # 背景除去PNG

        self._on_status = on_status

        self._image_list = []  # 処理対象（= STAGE_DIR 直下の画像）。フォルダを参照して作る
        self.current_image_path = None
        self.original_image = None  # PIL.Image（選択中の元画像）

        # single モード（1枚をモデル比較）用
        self._results = {}  # {model_name: PIL.Image} 選択中画像の結果
        self._active_models = []  # 今回処理対象のモデル

        # batch モード（全画像を1モデルで一括）用
        self._batch_results = {}   # {Path: PIL.Image} 画像ごとの結果
        self._batch_model = None   # 一括処理に使ったモデル名

        self._mode = "single"      # "single" | "batch"
        self._panes = {}  # key -> dict（pane widgets / refs）
        self._busy = False

        self._model_vars = {
            name: ctk.BooleanVar(value=(name == engine.MODEL_NAMES[0]))
            for name in engine.MODEL_NAMES
        }
        self.status = ctk.StringVar(value="画像をドラッグ&ドロップで追加してください")

        self._build()
        self._enable_dnd()
        # 起動時に STAGE_DIR（outputs/bg_removal）にある画像を読み込む
        self._refresh_inputs()
        if self._image_list:
            self._select_image(self._image_list[0])

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=0)  # 入力グリッド（固定幅）
        self.columnconfigure(1, weight=1)  # 設定＋結果
        self.rowconfigure(1, weight=1)

        # ── 左: 処理する画像グリッド ──
        left = ctk.CTkFrame(self, fg_color=PINK["panel"])
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(8, 4), pady=8)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self._grid = ImageGrid(left, on_select=self._select_image, width=230)
        self._grid.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))
        ctk.CTkButton(
            btns, text="＋ 画像を追加", command=self.on_browse,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btns, text="🔄 再読込", width=80, command=self.on_refresh,
            fg_color=PINK["accent"], hover_color=PINK["accent_hover"],
            text_color=PINK["accent_text"],
        ).pack(side="left", padx=2)
        self._dnd_hint = ctk.CTkLabel(
            left, text="", text_color="#a05050", font=ctk.CTkFont(size=11)
        )
        self._dnd_hint.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))

        # ── 右上: モデル選択＋実行＋進捗 ──
        ctrl = ctk.CTkFrame(self, fg_color=PINK["panel"])
        ctrl.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(8, 4))
        ctrl.columnconfigure(0, weight=1)

        ctk.CTkLabel(ctrl, text="モデル（複数選択で比較／一括は先頭1つを使用）", anchor="w").grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 0)
        )
        models_frame = ctk.CTkFrame(ctrl, fg_color="transparent")
        models_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        for idx, (name, label) in enumerate(engine.MODELS):
            r, c = divmod(idx, 2)
            models_frame.columnconfigure(c, weight=1)
            ctk.CTkCheckBox(
                models_frame, text=label, variable=self._model_vars[name],
            ).grid(row=r, column=c, sticky="w", padx=8, pady=4)

        run_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        run_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 6))
        run_row.columnconfigure(4, weight=1)
        self._run_btn = ctk.CTkButton(
            run_row, text="背景除去を実行", command=self.on_run, width=130,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        )
        self._run_btn.grid(row=0, column=0, padx=(2, 6), pady=4)
        self._batch_btn = ctk.CTkButton(
            run_row, text="🚀 一括処理（全画像）", command=self.on_run_batch, width=150,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        )
        self._batch_btn.grid(row=0, column=1, padx=6, pady=4)
        self._save_all_btn = ctk.CTkButton(
            run_row, text="💾 全部保存", command=self.on_save_all, width=100, state="disabled",
            fg_color=PINK["accent"], hover_color=PINK["accent_hover"], text_color=PINK["accent_text"],
        )
        self._save_all_btn.grid(row=0, column=2, padx=6, pady=4)
        ctk.CTkButton(
            run_row, text="🧹 リセット", command=self.on_reset_preview, width=100,
            fg_color=PINK["accent"], hover_color=PINK["accent_hover"], text_color=PINK["accent_text"],
        ).grid(row=0, column=3, padx=6, pady=4)
        self._progress = ctk.CTkProgressBar(run_row, mode="indeterminate")
        self._progress.grid(row=0, column=4, sticky="ew", padx=4, pady=4)
        self._progress.set(0)
        ctk.CTkLabel(
            ctrl, textvariable=self.status, text_color="#7a3b5a", anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        # ── 右下: 結果エリア（モデルごと／画像ごとに分けて表示）──
        self._results_area = ctk.CTkScrollableFrame(
            self, fg_color=PINK["panel"], label_text="結果（🔍で拡大・💾で保存）"
        )
        self._results_area.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
        self._results_area.columnconfigure((0, 1), weight=1)

    # ──────────────────────────────────────────
    #  D&D / 追加
    # ──────────────────────────────────────────

    def _enable_dnd(self):
        root = self.winfo_toplevel()
        if DND_FILES is None or not hasattr(root, "TkdndVersion"):
            self._dnd_hint.configure(text="D&D無効。「＋ 画像を追加」で取り込み")
            return
        targets = [self, self._grid]
        for attr in ("_parent_canvas", "_parent_frame"):
            w = getattr(self._grid, attr, None)
            if w is not None:
                targets.append(w)
        for target in targets:
            try:
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self._dnd_hint.configure(text="画像/フォルダをここへD&Dで追加")

    def _on_drop(self, event):
        self._add_paths(self._parse_dnd_paths(event.data))

    @staticmethod
    def _parse_dnd_paths(raw: str):
        out, token, in_brace = [], "", False
        for ch in raw:
            if ch == "{":
                in_brace, token = True, ""
            elif ch == "}":
                in_brace = False
                out.append(token)
                token = ""
            elif ch == " " and not in_brace:
                if token:
                    out.append(token)
                    token = ""
            else:
                token += ch
        if token:
            out.append(token)
        return out

    def on_browse(self):
        files = filedialog.askopenfilenames(
            title="処理する画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp *.bmp"), ("すべて", "*.*")],
        )
        if files:
            self._add_paths(files)

    def _scan_inputs(self):
        """STAGE_DIR（outputs/bg_removal）直下の画像を一覧する。
        PNG/処理済み等のサブフォルダはファイルでないので自然に除外される。"""
        d = self._stage_dir
        if not d.exists():
            return []
        return [
            p for p in sorted(d.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        ]

    def _refresh_inputs(self):
        """STAGE_DIR を読み直してグリッドを更新する（選択中は維持）。"""
        self._image_list = self._scan_inputs()
        self._grid.refresh(self._image_list)
        if self.current_image_path in self._image_list:
            self._grid.set_selected(self.current_image_path)

    def on_refresh(self):
        self._refresh_inputs()
        if self.current_image_path not in self._image_list and self._image_list:
            self._select_image(self._image_list[0])
        self._set_status(f"再読込（{len(self._image_list)} 枚）")

    def _add_paths(self, raw_paths):
        added = 0
        for f in raw_paths:
            p = Path(f)
            if p.is_dir():
                for q in sorted(p.iterdir()):
                    if q.is_file() and q.suffix.lower() in IMAGE_EXTS and self._stage(q):
                        added += 1
            elif p.is_file() and p.suffix.lower() in IMAGE_EXTS and self._stage(p):
                added += 1
        had = self.current_image_path is not None
        self._refresh_inputs()  # フォルダを参照し直す
        if not had and self._image_list:
            self._select_image(self._image_list[0])
        if added:
            self._set_status(
                f"{added} 枚を outputs/bg_removal に取り込み（計 {len(self._image_list)} 枚）"
            )
        else:
            self._set_status("追加なし（同名が既にあるか画像でない）")

    def _stage(self, src) -> bool:
        """取り込んだ画像を STAGE_DIR へコピー（一時保存）。同名が既にあれば取り込まない。"""
        src = Path(src)
        dest = self._stage_dir / src.name
        if dest.exists():
            return False  # 既に同名がある（フォルダ参照なので一覧には出る）
        try:
            self._stage_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"取り込み失敗: {src.name} ({e})")
            return False
        return True

    @staticmethod
    def _unique_dest(directory, name: str) -> Path:
        directory = Path(directory)
        dest = directory / name
        if not dest.exists():
            return dest
        stem, suffix = Path(name).stem, Path(name).suffix
        i = 1
        while (directory / f"{stem}_{i}{suffix}").exists():
            i += 1
        return directory / f"{stem}_{i}{suffix}"

    # ──────────────────────────────────────────
    #  画像選択
    # ──────────────────────────────────────────

    def _select_image(self, path):
        # 画像をクリックしたら single（1枚比較）モードへ戻る
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            self._set_status(f"画像を開けませんでした: {e}")
            return
        self._mode = "single"
        self.current_image_path = Path(path)
        self.original_image = img
        self._grid.set_selected(self.current_image_path)
        self._results = {}
        self._active_models = []
        self._save_all_btn.configure(state="disabled")
        self._rebuild_results()
        self._set_status(f"選択: {self.current_image_path.name}（モデルを選んで実行）")

    def _selected_models(self):
        return [name for name in engine.MODEL_NAMES if self._model_vars[name].get()]

    # ──────────────────────────────────────────
    #  実行（single: 1枚を複数モデルで比較・非同期）
    # ──────────────────────────────────────────

    def on_run(self):
        if self._busy:
            return
        if self.current_image_path is None or self.original_image is None:
            self._set_status("先に画像を追加・選択してください")
            return
        models = self._selected_models()
        if not models:
            self._set_status("モデルを1つ以上選んでください")
            return
        if not engine.rembg_available():
            self._set_status('rembg が未導入です。pip install "rembg[gpu,cli]" を実行してください')
            return
        self._mode = "single"
        self._begin_busy()
        self._results = {}
        self._active_models = models
        self._rebuild_results()  # 元画像＋各モデルの「処理待ち」ペインを並べる
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        path = self.current_image_path
        threading.Thread(target=self._run_worker, args=(path, models), daemon=True).start()

    def _run_worker(self, path, models):
        total = len(models)
        for i, model in enumerate(models, 1):
            label = engine.NAME_TO_LABEL.get(model, model)
            self.after(0, self._set_status, f"処理中: {label} ({i}/{total})…")
            try:
                result = engine.remove_background(path, model)
                self.after(0, self._model_done, path, model, result, None)
            except Exception as e:  # noqa: BLE001
                self.after(0, self._model_done, path, model, None, e)
        self.after(0, self._run_all_done)

    def _model_done(self, path, model, result, error):
        # 実行中に別画像へ切り替わっていたら無視（結果の取り違え防止）
        if self._mode != "single" or path != self.current_image_path:
            return
        pane = self._panes.get(model)
        if error is not None:
            if pane:
                pane["label"].configure(image=None, text=f"エラー:\n{error}")
            return
        self._results[model] = result
        if pane:
            self._show_result_in_pane(pane, result)

    def _run_all_done(self):
        self._end_busy()
        done = len(self._results)
        total = len(self._active_models)
        if done == total:
            self._set_status(f"完了（{done} モデル）。保存/手動編集できます")
        else:
            self._set_status(f"完了：成功 {done} / {total}（失敗あり）")

    # ──────────────────────────────────────────
    #  実行（batch: 全画像を先頭1モデルで一括・非同期）
    # ──────────────────────────────────────────

    def on_run_batch(self):
        if self._busy:
            return
        paths_to_do = list(self._image_list)
        if not paths_to_do:
            self._set_status("処理する画像がありません（先に追加してください）")
            return
        models = self._selected_models()
        if not models:
            self._set_status("モデルを1つ以上選んでください")
            return
        if not engine.rembg_available():
            self._set_status('rembg が未導入です。pip install "rembg[gpu,cli]" を実行してください')
            return
        model = models[0]  # 一括は先頭の1モデルだけ使う
        self._mode = "batch"
        self._batch_model = model
        self._batch_results = {}
        self.current_image_path = None
        self.original_image = None
        self._begin_busy()
        self._rebuild_results()  # 画像ごとの「処理待ち」ペインを並べる
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        label = engine.NAME_TO_LABEL.get(model, model)
        self._set_status(f"一括処理を開始（{len(paths_to_do)} 枚 / {label}）…")
        threading.Thread(
            target=self._run_batch_worker, args=(paths_to_do, model), daemon=True
        ).start()

    def _run_batch_worker(self, paths_to_do, model):
        total = len(paths_to_do)
        for i, path in enumerate(paths_to_do, 1):
            self.after(0, self._set_status, f"一括処理中: {path.name} ({i}/{total})…")
            try:
                result = engine.remove_background(path, model)
                self.after(0, self._batch_item_done, path, result, None, i, total)
            except Exception as e:  # noqa: BLE001
                self.after(0, self._batch_item_done, path, None, e, i, total)
        self.after(0, self._batch_all_done)

    def _batch_item_done(self, path, result, error, i, total):
        if self._mode != "batch":
            return
        self._progress.set(i / total)
        pane = self._panes.get(str(path))
        if error is not None:
            if pane:
                pane["label"].configure(image=None, text=f"エラー:\n{error}")
            return
        self._batch_results[path] = result
        if pane:
            self._show_result_in_pane(pane, result)

    def _batch_all_done(self):
        self._end_busy()
        done = len(self._batch_results)
        total = len(self._image_list)
        if done:
            self._save_all_btn.configure(state="normal")
        if done == total:
            self._set_status(f"一括処理 完了（{done} 枚）。💾全部保存 か 各💾で保存できます")
        else:
            self._set_status(f"一括処理 完了：成功 {done} / {total}（失敗あり）")

    def on_save_all(self):
        """batch の結果をまとめて保存（PNG→PNG\\ ／ 元画像→処理済み\\）。"""
        if self._mode != "batch" or not self._batch_results:
            self._set_status("保存できる一括結果がありません")
            return
        model = self._batch_model or ""
        saved = 0
        failed = 0
        for path, result in list(self._batch_results.items()):
            try:
                engine.save_png(result, path, self._png_dir, model)
                self._move_original_to_processed(path)
                saved += 1
            except Exception:  # noqa: BLE001
                failed += 1
        self._refresh_inputs()  # 元画像が移動したので一覧を更新（結果ペインは残す）
        if failed:
            self._set_status(f"全部保存：成功 {saved} 枚 / 失敗 {failed} 枚")
        else:
            self._set_status(f"全部保存 完了（{saved} 枚を PNG\\ へ・元画像は 処理済み\\ へ）")

    def _move_original_to_processed(self, src):
        """元画像がまだ STAGE_DIR にあれば 処理済み\\ へ移動する。"""
        if src is None or not Path(src).exists():
            return
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        dest = self._unique_dest(self._processed_dir, Path(src).name)
        shutil.move(str(src), str(dest))

    def on_reset_preview(self):
        """結果プレビューをリセット（実行前の状態に戻す）。"""
        self._results = {}
        self._active_models = []
        self._batch_results = {}
        self._save_all_btn.configure(state="disabled")
        if self._mode == "batch":
            # batch のリセットは single（元画像プレビュー）へ戻す
            self._mode = "single"
            if self._image_list:
                self._select_image(self._image_list[0])
                self._set_status("プレビューをリセットしました")
                return
        self._rebuild_results()
        self._set_status("プレビューをリセットしました")

    # ──────────────────────────────────────────
    #  実行状態の切り替え
    # ──────────────────────────────────────────

    def _begin_busy(self):
        self._busy = True
        self._run_btn.configure(state="disabled")
        self._batch_btn.configure(state="disabled")
        self._save_all_btn.configure(state="disabled")

    def _end_busy(self):
        self._busy = False
        self._run_btn.configure(state="normal")
        self._batch_btn.configure(state="normal")
        self._progress.stop()
        self._progress.set(0)

    # ──────────────────────────────────────────
    #  結果エリアの構築
    # ──────────────────────────────────────────

    def _rebuild_results(self):
        for child in self._results_area.winfo_children():
            child.destroy()
        self._panes = {}

        if self._mode == "batch":
            self._results_area.configure(label_text="一括結果（画像ごと・🔍拡大／💾保存）")
            if not self._image_list:
                ctk.CTkLabel(
                    self._results_area, text="画像を追加して「🚀 一括処理」",
                ).grid(row=0, column=0, padx=8, pady=8)
                return
            for idx, path in enumerate(self._image_list):
                r, c = divmod(idx, 2)
                self._build_pane(
                    r, c, key=str(path), title=path.name,
                    kind="batch", src=path, model=self._batch_model,
                )
            return

        # single モード
        self._results_area.configure(label_text="結果（モデルごと・🔍拡大／💾保存）")
        items = []
        if self.original_image is not None:
            items.append((_ORIGINAL_KEY, "元画像", "original"))
        for model in self._active_models:
            items.append((model, engine.NAME_TO_LABEL.get(model, model), "model"))

        if not items:
            ctk.CTkLabel(
                self._results_area,
                text="画像を選び、モデルを選んで「背景除去を実行」\nまたは「🚀 一括処理」で全画像をまとめて処理",
            ).grid(row=0, column=0, padx=8, pady=8)
            return

        for idx, (key, title, kind) in enumerate(items):
            r, c = divmod(idx, 2)
            self._build_pane(
                r, c, key=key, title=title, kind=kind,
                src=self.current_image_path, model=(key if kind == "model" else None),
            )

    def _build_pane(self, row, col, key, title, kind, src=None, model=None):
        savable = kind in ("model", "batch")
        frame = ctk.CTkFrame(self._results_area, fg_color="#fff3f9", border_width=1)
        frame.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        frame.columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        header.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=title, anchor="w", font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        zoom_btn = ctk.CTkButton(
            header, text="🔍 拡大", width=64, command=lambda k=key: self._zoom(k),
        )
        zoom_btn.grid(row=0, column=1, sticky="e")

        label = ctk.CTkLabel(
            frame, text="処理待ち…", width=PANE_PREVIEW[0], height=PANE_PREVIEW[1],
        )
        label.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        pane = {"frame": frame, "label": label, "zoom_btn": zoom_btn,
                "ref": None, "prev_ref": None, "full": None, "original": None,
                "kind": kind, "src": Path(src) if src else None, "model": model,
                "save_btn": None, "edit_btn": None}

        if savable:
            footer = ctk.CTkFrame(frame, fg_color="transparent")
            footer.grid(row=2, column=0, sticky="w", padx=6, pady=(0, 6))
            save_btn = ctk.CTkButton(
                footer, text="💾 保存", width=78, state="disabled",
                command=lambda k=key: self._save(k),
                fg_color=PINK["button"], hover_color=PINK["button_hover"],
            )
            save_btn.pack(side="left", padx=(0, 4))
            edit_btn = ctk.CTkButton(
                footer, text="✏️ 手動編集", width=100, state="disabled",
                command=lambda k=key: self._edit(k),
                fg_color=PINK["accent"], hover_color=PINK["accent_hover"],
                text_color=PINK["accent_text"],
            )
            edit_btn.pack(side="left", padx=4)
            pane["save_btn"] = save_btn
            pane["edit_btn"] = edit_btn

        self._panes[key] = pane

        # 元画像はすぐ表示。結果ペインは既に結果があれば表示。
        if kind == "original":
            pane["full"] = self.original_image
            pane["original"] = self.original_image
            self._set_pane_image(pane, self._fit(self.original_image, PANE_PREVIEW))
            zoom_btn.configure(state="normal")
        elif kind == "model" and key in self._results:
            self._show_result_in_pane(pane, self._results[key])
        elif kind == "batch" and pane["src"] in self._batch_results:
            self._show_result_in_pane(pane, self._batch_results[pane["src"]])
        else:
            zoom_btn.configure(state="disabled")

    def _show_result_in_pane(self, pane, result):
        """処理結果（RGBA）をペインに表示し、各ボタンを有効化する。"""
        pane["full"] = result
        preview = engine.composite_on_checker(self._fit(result, PANE_PREVIEW))
        self._set_pane_image(pane, preview)
        pane["zoom_btn"].configure(state="normal")
        if pane.get("save_btn") is not None:
            pane["save_btn"].configure(state="normal")
        if pane.get("edit_btn") is not None:
            pane["edit_btn"].configure(state="normal")

    # ──────────────────────────────────────────
    #  拡大・保存・編集（single / batch 共通。ペインの文脈を使う）
    # ──────────────────────────────────────────

    def _zoom(self, key):
        pane = self._panes.get(key)
        if pane is None:
            return
        if pane["kind"] == "original":
            img = pane["full"]
            name = pane["src"].name if pane["src"] else ""
            title = f"元画像 - {name}"
        else:
            result = pane["full"]
            img = engine.composite_on_checker(result) if result is not None else None
            model_label = engine.NAME_TO_LABEL.get(pane["model"], pane["model"] or "")
            name = pane["src"].name if pane["src"] else ""
            title = f"{name}｜{model_label}" if name else model_label
        if img is not None:
            ZoomWindow(self.winfo_toplevel(), img, title=title)

    def _save(self, key):
        pane = self._panes.get(key)
        if pane is None or pane["full"] is None:
            self._set_status("その結果がまだありません")
            return
        result = pane["full"]
        src = pane["src"]
        model = pane["model"] or ""
        # 1) 背景除去PNGを PNG フォルダへ保存
        try:
            saved = engine.save_png(result, src, self._png_dir, model)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"PNG保存に失敗: {e}")
            return
        # 2) 元画像（ステージング分）を処理済みへ移動。
        #    まだ残っているときだけ動かすので、同じ画像を複数回保存しても二重移動しない。
        moved = ""
        if src is not None and Path(src).exists():
            try:
                self._move_original_to_processed(src)
                self._refresh_inputs()  # フォルダから消えたので一覧を更新（結果ペインは残す）
                moved = " / 元画像→処理済み"
            except Exception as e:  # noqa: BLE001
                moved = f" / 元画像の移動に失敗({e})"
        self._set_status(f"PNG保存: {saved.name}{moved}")

    def _edit(self, key):
        pane = self._panes.get(key)
        if pane is None or pane["full"] is None:
            self._set_status("編集できる結果がありません")
            return
        original = pane.get("original")
        if original is None:
            # batch などで未ロードなら元画像をここで読み込む
            src = pane["src"]
            try:
                original = Image.open(src).convert("RGBA") if src else None
            except Exception:
                original = None
            pane["original"] = original
        if original is None:
            self._set_status("元画像を読み込めませんでした")
            return
        model_label = engine.NAME_TO_LABEL.get(pane["model"], pane["model"] or "")
        MaskEditorWindow(
            self.winfo_toplevel(),
            original=original,
            result=pane["full"],
            title=f"手動切り抜き - {model_label}",
            on_apply=lambda edited, k=key: self._apply_edited(k, edited),
        )

    def _apply_edited(self, key, edited):
        """エディタの編集結果をそのペインの結果として反映（保存は💾で）。"""
        pane = self._panes.get(key)
        if pane is None:
            return
        pane["full"] = edited
        self._set_pane_image(
            pane, engine.composite_on_checker(self._fit(edited, PANE_PREVIEW))
        )
        # 内部の結果辞書も同期（再構築時に反映されるように）
        if pane["kind"] == "model" and pane["model"] is not None:
            self._results[pane["model"]] = edited
        elif pane["kind"] == "batch" and pane["src"] is not None:
            self._batch_results[pane["src"]] = edited
        model_label = engine.NAME_TO_LABEL.get(pane["model"], pane["model"] or "")
        self._set_status(f"手動編集を反映: {model_label}（💾で保存）")

    # ──────────────────────────────────────────
    #  ヘルパー
    # ──────────────────────────────────────────

    @staticmethod
    def _fit(img: Image.Image, box) -> Image.Image:
        out = img.copy()
        out.thumbnail(box, Image.LANCZOS)
        return out

    def _set_pane_image(self, pane, pil_img):
        new_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
        pane["label"].configure(image=new_img, text="")  # 先に適用
        pane["prev_ref"] = pane.get("ref")  # 旧参照を1サイクル保持
        pane["ref"] = new_img

    def _set_status(self, text):
        self.status.set(text)
        if self._on_status:
            try:
                self._on_status(text)
            except Exception:
                pass
