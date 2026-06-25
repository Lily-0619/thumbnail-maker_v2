"""
bg_removal_panel.py
背景除去のコアUI。CTkFrame なので独立ウィンドウにもメインアプリのタブにも埋め込める。

  上段: 入力（D&Dドロップ／クリックでファイル選択）＋ 元画像プレビュー
  中段: モデル選択（CTkOptionMenu）＋ 背景除去を実行
  下段: 結果プレビュー（チェッカー背景で透過確認）＋ PNG保存 ＋ ステータス

処理は重いので threading で実行し、UI更新は after() 経由でメインスレッドに戻す。
プレビューの画像差し替えは「新画像をラベルへ適用してから旧CTkImage参照を入れ替える」
順序にして、2枚目以降が出ない CTkImage 不具合（image pyimageN doesn't exist）を防ぐ。
"""

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

try:
    # パッケージとして import された場合（例: メインアプリへ埋め込み）
    from . import engine, paths
except ImportError:
    # 単体スクリプトから import された場合（独立ウィンドウ／汎用ツール配置）
    import engine
    import paths

try:
    from tkinterdnd2 import DND_FILES
except ImportError:
    DND_FILES = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

PINK = {
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
    "drop": "#c6b6e2",
    "drop_hover": "#b09cd4",
    "drop_text": "#3f2a44",
}

ORIG_PREVIEW = (260, 200)
RESULT_PREVIEW = (380, 300)


class BgRemovalPanel(ctk.CTkFrame):
    def __init__(self, master, output_dir=None, on_status=None, **kwargs):
        super().__init__(master, **kwargs)
        self._output_dir = Path(output_dir) if output_dir else paths.OUTPUT_DIR
        self._on_status = on_status

        self.current_image_path = None
        self.original_image = None  # PIL.Image
        self.result_image = None  # PIL.Image（背景除去後 RGBA）
        self._busy = False

        # CTkImage の参照保持（*_prev はGC遅延用）
        self._orig_ref = None
        self._orig_ref_prev = None
        self._result_ref = None
        self._result_ref_prev = None

        self.model_label = ctk.StringVar(value=engine.MODELS[0][1])
        self.status = ctk.StringVar(value="画像を読み込んでください")

        self._build()
        self._enable_dnd()

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── 上段: 入力 ──
        top = ctk.CTkFrame(self, fg_color=PINK["panel"])
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=0)

        self._drop_area = ctk.CTkButton(
            top,
            text="ここに画像をドラッグ&ドロップ\n（クリックでファイル選択）",
            height=140,
            font=ctk.CTkFont(size=14),
            fg_color=PINK["drop"], hover_color=PINK["drop_hover"],
            text_color=PINK["drop_text"],
            command=self.on_browse,
        )
        self._drop_area.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._orig_label = ctk.CTkLabel(
            top, text="元画像プレビュー",
            width=ORIG_PREVIEW[0], height=ORIG_PREVIEW[1],
        )
        self._orig_label.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)

        # ── 中段: 設定 ──
        mid = ctk.CTkFrame(self, fg_color=PINK["panel"])
        mid.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(mid, text="モデル：").pack(side="left", padx=(10, 4), pady=10)
        ctk.CTkOptionMenu(
            mid, variable=self.model_label,
            values=[label for _name, label in engine.MODELS],
            width=260,
        ).pack(side="left", padx=4, pady=10)
        self._run_btn = ctk.CTkButton(
            mid, text="背景除去を実行", command=self.on_run,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        )
        self._run_btn.pack(side="left", padx=10, pady=10)

        # ── 下段: 結果 ──
        bottom = ctk.CTkFrame(self, fg_color=PINK["panel"])
        bottom.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(1, weight=1)

        ctk.CTkLabel(bottom, text="結果（透過はチェッカー背景で確認）", anchor="w").grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 0)
        )
        self._result_label = ctk.CTkLabel(
            bottom, text="ここに結果が表示されます",
            width=RESULT_PREVIEW[0], height=RESULT_PREVIEW[1],
        )
        self._result_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=8)

        actions = ctk.CTkFrame(bottom, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        self._save_btn = ctk.CTkButton(
            actions, text="💾 PNG保存", command=self.on_save, state="disabled",
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        )
        self._save_btn.pack(side="left")
        ctk.CTkLabel(
            actions, textvariable=self.status, text_color="#7a3b5a", anchor="w",
        ).pack(side="left", padx=12)

        self._dnd_hint = ctk.CTkLabel(
            bottom, text="", text_color="#a05050", font=ctk.CTkFont(size=11), anchor="w"
        )
        self._dnd_hint.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

    # ──────────────────────────────────────────
    #  D&D（埋め込み先がDnD対応ルートのときだけ有効化）
    # ──────────────────────────────────────────

    def _enable_dnd(self):
        root = self.winfo_toplevel()
        if DND_FILES is None or not hasattr(root, "TkdndVersion"):
            self._dnd_hint.configure(
                text="D&Dは無効です。ドロップエリアのクリックで画像を選べます。"
            )
            return
        for target in (self._drop_area, self._orig_label, self):
            try:
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self._dnd_hint.configure(text="画像をドラッグ&ドロップで読み込めます。")

    def _on_drop(self, event):
        files = self._parse_dnd_paths(event.data)
        for f in files:
            p = Path(f)
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                self._load_image(p)
                return
        self._set_status("画像ファイルをドロップしてください")

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

    # ──────────────────────────────────────────
    #  読み込み
    # ──────────────────────────────────────────

    def on_browse(self):
        path = filedialog.askopenfilename(
            title="背景を除去する画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp *.bmp"), ("すべて", "*.*")],
        )
        if path:
            self._load_image(Path(path))

    def _load_image(self, path: Path):
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            self._set_status(f"画像を開けませんでした: {e}")
            return
        self.current_image_path = path
        self.original_image = img
        self._set_image(self._orig_label, self._fit(img, ORIG_PREVIEW), "_orig")
        # 結果はリセット
        self.result_image = None
        self._set_image(self._result_label, None, "_result")
        self._result_label.configure(text="ここに結果が表示されます")
        self._save_btn.configure(state="disabled")
        self._set_status(f"読み込み: {path.name}")

    # ──────────────────────────────────────────
    #  背景除去（非同期）
    # ──────────────────────────────────────────

    def on_run(self):
        if self._busy:
            return
        if self.current_image_path is None or self.original_image is None:
            self._set_status("先に画像を読み込んでください")
            return
        if not engine.rembg_available():
            self._set_status("rembg が未導入です。pip install \"rembg[gpu,cli]\" を実行してください")
            return
        model_name = engine.LABEL_TO_NAME.get(self.model_label.get(), engine.MODEL_NAMES[0])
        self._busy = True
        self._run_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._set_status("処理中…（初回はモデルDLで時間がかかります）")
        path = self.current_image_path
        threading.Thread(
            target=self._run_worker, args=(path, model_name), daemon=True
        ).start()

    def _run_worker(self, path, model_name):
        try:
            result = engine.remove_background(path, model_name)
            self.after(0, self._run_done, result, None)
        except Exception as e:  # noqa: BLE001  失敗内容をUIに出して落とさない
            self.after(0, self._run_done, None, e)

    def _run_done(self, result, error):
        self._busy = False
        self._run_btn.configure(state="normal")
        if error is not None:
            self._set_status(f"エラー: {error}")
            return
        self.result_image = result
        preview = engine.composite_on_checker(self._fit(result, RESULT_PREVIEW))
        self._set_image(self._result_label, preview, "_result")
        self._save_btn.configure(state="normal")
        self._set_status("完了。PNG保存できます")

    # ──────────────────────────────────────────
    #  保存
    # ──────────────────────────────────────────

    def on_save(self):
        if self.result_image is None:
            self._set_status("先に背景除去を実行してください")
            return
        model_name = engine.LABEL_TO_NAME.get(self.model_label.get(), "")
        try:
            saved = engine.save_png(
                self.result_image, self.current_image_path, self._output_dir, model_name
            )
        except Exception as e:  # noqa: BLE001
            self._set_status(f"保存に失敗: {e}")
            return
        self._set_status(f"保存しました: {saved}")

    # ──────────────────────────────────────────
    #  ヘルパー
    # ──────────────────────────────────────────

    @staticmethod
    def _fit(img: Image.Image, box) -> Image.Image:
        out = img.copy()
        out.thumbnail(box, Image.LANCZOS)
        return out

    def _set_image(self, label, pil_img, ref_attr):
        """ラベルへ画像を安全に差し替える（旧参照は1サイクル保持してGCを遅延）。"""
        if pil_img is None:
            label.configure(image=None)
            setattr(self, ref_attr + "_ref_prev", getattr(self, ref_attr + "_ref", None))
            setattr(self, ref_attr + "_ref", None)
            return
        new_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
        label.configure(image=new_img, text="")  # 先に適用（この間 旧参照は生存）
        setattr(self, ref_attr + "_ref_prev", getattr(self, ref_attr + "_ref", None))
        setattr(self, ref_attr + "_ref", new_img)

    def _set_status(self, text):
        self.status.set(text)
        if self._on_status:
            try:
                self._on_status(text)
            except Exception:
                pass
