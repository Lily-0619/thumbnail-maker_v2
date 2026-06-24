"""
widgets.py
再利用するUI部品（effect_sorter の widgets を踏襲）。

  - load_thumbnail : Pillowで透過を保ったサムネ生成
  - ZoomWindow     : プレビュー拡大用の別ウィンドウ（CTkToplevel）
  - PreviewPanel   : 選択中画像を大きく表示（右上に拡大ボタン）
  - ImageGrid      : 入力フォルダ内のサムネ一覧（選択でコールバック）

CTkImage は参照を保持しないとサムネが消えるため self._thumb_refs に退避する。
"""

from pathlib import Path

import customtkinter as ctk
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def load_thumbnail(path: Path, size):
    """透過を保ったままサムネを生成して返す（失敗時 None）。"""
    try:
        with Image.open(path) as opened:
            img = opened.convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
        canvas.paste(img, offset)
        return canvas
    except Exception:
        return None


class ZoomWindow(ctk.CTkToplevel):
    """画像を大きく表示する別ウィンドウ。"""

    def __init__(self, parent, path: Path):
        super().__init__(parent)
        self.title(f"拡大表示 - {path.name}")
        self.geometry("900x900")
        self.grab_set()
        self._img_ref = None
        self._build(path)

    def _build(self, path):
        try:
            with Image.open(path) as opened:
                img = opened.convert("RGBA")
        except Exception:
            ctk.CTkLabel(self, text="画像を開けませんでした。").pack(pady=20)
            return
        max_side = 840
        w, h = img.size
        scale = min(max_side / w, max_side / h, 1.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        self._img_ref = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        ctk.CTkLabel(self, image=self._img_ref, text="").pack(
            expand=True, fill="both", padx=10, pady=10
        )


class PreviewPanel(ctk.CTkFrame):
    """選択中画像を大きく表示。右上に拡大ボタン。"""

    PREVIEW_SIZE = (440, 340)

    def __init__(self, parent):
        super().__init__(parent)
        self._current_path = None
        self._img_ref = None
        self._prev_img_ref = None  # 旧CTkImageを1サイクル保持してGCを遅延させる

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=6, pady=(6, 0))
        ctk.CTkLabel(header, text="プレビュー", anchor="w").pack(side="left")
        self._name_label = ctk.CTkLabel(
            header, text="", anchor="e", font=ctk.CTkFont(size=11)
        )
        self._name_label.pack(side="left", expand=True, fill="x", padx=6)
        self._zoom_btn = ctk.CTkButton(
            header, text="🔍 拡大", width=70, command=self._open_zoom
        )
        self._zoom_btn.pack(side="right")

        self._image_label = ctk.CTkLabel(
            self,
            text="入力画像を選択してください",
            width=self.PREVIEW_SIZE[0],
            height=self.PREVIEW_SIZE[1],
        )
        self._image_label.pack(expand=True, fill="both", padx=6, pady=6)

    def show(self, path):
        """指定パスの画像をプレビューに表示する。

        重要：必ず「ラベルへ新画像を適用してから旧参照を入れ替える」順序で行う。
        先に旧 CTkImage を捨てるとGCで内部 PhotoImage が破棄され、ラベル再描画時に
        "image pyimageN doesn't exist" となって2枚目以降が表示されない不具合が出る。
        """
        path = Path(path) if path else None
        self._current_path = path

        if path is None or not path.exists():
            self._name_label.configure(text="")
            self._image_label.configure(image=None, text="入力画像を選択してください")
            self._prev_img_ref, self._img_ref = self._img_ref, None
            return

        self._name_label.configure(text=path.name)
        thumb = load_thumbnail(path, self.PREVIEW_SIZE)
        if thumb is None:
            self._image_label.configure(image=None, text="画像を開けませんでした")
            self._prev_img_ref, self._img_ref = self._img_ref, None
            return

        new_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=self.PREVIEW_SIZE)
        # 1) 先にラベルへ新画像を適用（この間、旧 self._img_ref はまだ生きている）
        self._image_label.configure(image=new_img, text="")
        # 2) そのあとで参照を入れ替える（旧→prevで1サイクル保持してから解放）
        self._prev_img_ref, self._img_ref = self._img_ref, new_img

    def _open_zoom(self):
        if self._current_path and self._current_path.exists():
            ZoomWindow(self.winfo_toplevel(), self._current_path)


class ImageGrid(ctk.CTkScrollableFrame):
    """入力フォルダのサムネ一覧。クリックで on_select(path) を呼ぶ。"""

    THUMB_SIZE = (84, 84)
    COLS = 3

    def __init__(self, parent, on_select, label_text="入力画像（D&Dで追加）", **kwargs):
        super().__init__(parent, label_text=label_text, **kwargs)
        self._on_select = on_select
        self._thumb_refs = []
        self._selected = None
        self._buttons = {}

    def refresh(self, image_paths):
        """画像パスのリストを受け取りグリッドを作り直す。"""
        for child in self.winfo_children():
            child.destroy()
        self._thumb_refs.clear()
        self._buttons = {}

        if not image_paths:
            ctk.CTkLabel(
                self,
                text="ここに画像をドラッグ&ドロップ\nまたは「＋ 画像を追加」で取り込み",
            ).grid(row=0, column=0, padx=8, pady=8)
            return

        for idx, path in enumerate(image_paths):
            r, c = divmod(idx, self.COLS)
            thumb = load_thumbnail(path, self.THUMB_SIZE)
            if thumb is None:
                continue
            ctk_img = ctk.CTkImage(
                light_image=thumb, dark_image=thumb, size=self.THUMB_SIZE
            )
            self._thumb_refs.append(ctk_img)
            btn = ctk.CTkButton(
                self,
                image=ctk_img,
                text=path.name[:12],
                compound="top",
                width=104,
                height=116,
                command=lambda p=path: self._select(p),
            )
            btn.grid(row=r, column=c, padx=4, pady=4)
            self._buttons[path] = btn
            if path == self._selected:
                btn.configure(border_width=2)

    def set_selected(self, path):
        """選択中画像をプログラム的に設定し、枠線ハイライトを更新する。"""
        self._selected = path
        for p, b in self._buttons.items():
            b.configure(border_width=2 if p == path else 0)

    def _select(self, path):
        self.set_selected(path)
        self._on_select(path)
