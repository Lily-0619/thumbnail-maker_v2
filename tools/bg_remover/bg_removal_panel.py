"""
bg_removal_panel.py
背景除去のコアUI。CTkFrame なので独立ウィンドウにもメインアプリのタブにも埋め込める。

  左: 処理する画像グリッド（base_image_sorter の仕分けグリッドを流用。D&Dで複数貯めて選択）
  右上: モデル複数選択（チェック）＋ 背景除去を実行 ＋ 進捗バー ＋ ステータス
  右下: 結果エリア（元画像＋選択モデルごとに分けてプレビュー。各右上に🔍拡大、モデルは💾保存）

処理は重いので threading で実行（選択モデルを順に処理）し、UI更新は after() 経由。
進捗はプログレスバー（処理中アニメ）＋「モデル名 (i/N)」表示で可視化する。
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
        self._results = {}  # {model_name: PIL.Image} 選択中画像の結果
        self._active_models = []  # 今回処理対象のモデル
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

        ctk.CTkLabel(ctrl, text="モデル（複数選択で比較）", anchor="w").grid(
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
        run_row.columnconfigure(2, weight=1)
        self._run_btn = ctk.CTkButton(
            run_row, text="背景除去を実行", command=self.on_run, width=140,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        )
        self._run_btn.grid(row=0, column=0, padx=(2, 6), pady=4)
        ctk.CTkButton(
            run_row, text="🧹 プレビューをリセット", command=self.on_reset_preview, width=170,
            fg_color=PINK["accent"], hover_color=PINK["accent_hover"], text_color=PINK["accent_text"],
        ).grid(row=0, column=1, padx=6, pady=4)
        self._progress = ctk.CTkProgressBar(run_row, mode="indeterminate")
        self._progress.grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        self._progress.set(0)
        ctk.CTkLabel(
            ctrl, textvariable=self.status, text_color="#7a3b5a", anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        # ── 右下: 結果エリア（モデルごとに分けて表示）──
        self._results_area = ctk.CTkScrollableFrame(
            self, fg_color=PINK["panel"], label_text="結果（モデルごと・🔍で拡大）"
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
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            self._set_status(f"画像を開けませんでした: {e}")
            return
        self.current_image_path = Path(path)
        self.original_image = img
        self._grid.set_selected(self.current_image_path)
        self._results = {}
        self._active_models = []
        self._rebuild_results()
        self._set_status(f"選択: {self.current_image_path.name}（モデルを選んで実行）")

    # ──────────────────────────────────────────
    #  実行（複数モデルを順に・非同期）
    # ──────────────────────────────────────────

    def on_run(self):
        if self._busy:
            return
        if self.current_image_path is None or self.original_image is None:
            self._set_status("先に画像を追加・選択してください")
            return
        models = [name for name in engine.MODEL_NAMES if self._model_vars[name].get()]
        if not models:
            self._set_status("モデルを1つ以上選んでください")
            return
        if not engine.rembg_available():
            self._set_status('rembg が未導入です。pip install "rembg[gpu,cli]" を実行してください')
            return
        self._busy = True
        self._run_btn.configure(state="disabled")
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
        if path != self.current_image_path:
            return
        pane = self._panes.get(model)
        if error is not None:
            if pane:
                pane["label"].configure(image=None, text=f"エラー:\n{error}")
            return
        self._results[model] = result
        if pane:
            preview = engine.composite_on_checker(self._fit(result, PANE_PREVIEW))
            self._set_pane_image(pane, preview)
            pane["full"] = result
            if pane.get("save_btn") is not None:
                pane["save_btn"].configure(state="normal")
            if pane.get("zoom_btn") is not None:
                pane["zoom_btn"].configure(state="normal")
            if pane.get("edit_btn") is not None:
                pane["edit_btn"].configure(state="normal")

    def _run_all_done(self):
        self._busy = False
        self._run_btn.configure(state="normal")
        self._progress.stop()
        self._progress.set(0)
        done = len(self._results)
        total = len(self._active_models)
        if done == total:
            self._set_status(f"完了（{done} モデル）。保存/手動編集できます")
        else:
            self._set_status(f"完了：成功 {done} / {total}（失敗あり）")

    def on_reset_preview(self):
        """結果プレビューをリセット（実行前の状態＝元画像ペインのみに戻す）。"""
        self._results = {}
        self._active_models = []
        self._rebuild_results()
        self._set_status("プレビューをリセットしました")

    # ──────────────────────────────────────────
    #  結果エリアの構築
    # ──────────────────────────────────────────

    def _rebuild_results(self):
        for child in self._results_area.winfo_children():
            child.destroy()
        self._panes = {}

        items = []
        if self.original_image is not None:
            items.append((_ORIGINAL_KEY, "元画像", False))
        for model in self._active_models:
            items.append((model, engine.NAME_TO_LABEL.get(model, model), True))

        if not items:
            ctk.CTkLabel(
                self._results_area,
                text="画像を選び、モデルを選んで「背景除去を実行」",
            ).grid(row=0, column=0, padx=8, pady=8)
            return

        for idx, (key, title, savable) in enumerate(items):
            r, c = divmod(idx, 2)
            self._build_pane(r, c, key, title, savable)

    def _build_pane(self, row, col, key, title, savable):
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
                "ref": None, "prev_ref": None, "full": None,
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

        # 元画像はすぐ表示。モデルは既に結果があれば表示。
        if key == _ORIGINAL_KEY:
            pane["full"] = self.original_image
            self._set_pane_image(pane, self._fit(self.original_image, PANE_PREVIEW))
            zoom_btn.configure(state="normal")
        elif key in self._results:
            result = self._results[key]
            pane["full"] = result
            self._set_pane_image(pane, engine.composite_on_checker(self._fit(result, PANE_PREVIEW)))
            zoom_btn.configure(state="normal")
            if pane["save_btn"] is not None:
                pane["save_btn"].configure(state="normal")
            if pane["edit_btn"] is not None:
                pane["edit_btn"].configure(state="normal")
        else:
            zoom_btn.configure(state="disabled")

    # ──────────────────────────────────────────
    #  拡大・保存
    # ──────────────────────────────────────────

    def _zoom(self, key):
        if key == _ORIGINAL_KEY:
            img = self.original_image
            title = f"元画像 - {self.current_image_path.name if self.current_image_path else ''}"
        else:
            result = self._results.get(key)
            img = engine.composite_on_checker(result) if result is not None else None
            title = f"{engine.NAME_TO_LABEL.get(key, key)}"
        if img is not None:
            ZoomWindow(self.winfo_toplevel(), img, title=title)

    def _save(self, model):
        result = self._results.get(model)
        if result is None:
            self._set_status("そのモデルの結果がまだありません")
            return
        src = self.current_image_path
        # 1) 背景除去PNGを PNG フォルダへ保存
        try:
            saved = engine.save_png(result, src, self._png_dir, model)
        except Exception as e:  # noqa: BLE001
            self._set_status(f"PNG保存に失敗: {e}")
            return
        # 2) 元画像（ステージング分）を処理済みへ移動。
        #    まだ残っているときだけ動かすので、同じ画像で複数モデルを保存しても二重移動しない。
        moved = ""
        if src is not None and Path(src).exists():
            try:
                self._processed_dir.mkdir(parents=True, exist_ok=True)
                dest = self._unique_dest(self._processed_dir, Path(src).name)
                shutil.move(str(src), str(dest))
                self._refresh_inputs()  # フォルダから消えたので一覧を更新（結果ペインは残す）
                moved = " / 元画像→処理済み"
            except Exception as e:  # noqa: BLE001
                moved = f" / 元画像の移動に失敗({e})"
        self._set_status(f"PNG保存: {saved.name}{moved}")

    def _edit(self, model):
        result = self._results.get(model)
        if result is None or self.original_image is None:
            self._set_status("編集できる結果がありません")
            return
        MaskEditorWindow(
            self.winfo_toplevel(),
            original=self.original_image,
            result=result,
            title=f"手動切り抜き - {engine.NAME_TO_LABEL.get(model, model)}",
            on_apply=lambda edited, m=model: self._apply_edited(m, edited),
        )

    def _apply_edited(self, model, edited):
        """エディタの編集結果をそのモデルの結果として反映（保存は💾で）。"""
        self._results[model] = edited
        pane = self._panes.get(model)
        if pane is not None:
            pane["full"] = edited
            self._set_pane_image(
                pane, engine.composite_on_checker(self._fit(edited, PANE_PREVIEW))
            )
        self._set_status(
            f"手動編集を反映: {engine.NAME_TO_LABEL.get(model, model)}（💾で保存）"
        )

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
