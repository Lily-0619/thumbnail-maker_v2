"""
widgets.py
bg_remover 用の再利用UI部品（base_image_sorter の仕分けグリッドの作法を流用）。

  - load_thumbnail : 透過を保ったサムネ生成
  - ZoomWindow     : PIL画像を大きく表示する別ウィンドウ（結果・元画像の拡大用）
  - ImageGrid      : 処理対象画像のサムネ一覧（D&Dで貯めてクリック選択）

CTkImage は参照を保持しないと消えるため _thumb_refs に退避する。
"""

from pathlib import Path

import customtkinter as ctk
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_thumbnail(path, size):
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
    """PIL画像を大きく表示する別ウィンドウ。"""

    def __init__(self, parent, pil_image: Image.Image, title="拡大表示"):
        super().__init__(parent)
        self.title(title)
        self.geometry("900x900")
        self.grab_set()
        self._ref = None
        self._build(pil_image)

    def _build(self, img):
        if img is None:
            ctk.CTkLabel(self, text="画像がありません。").pack(pady=20)
            return
        img = img.convert("RGBA")
        max_side = 840
        w, h = img.size
        scale = min(max_side / w, max_side / h, 1.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        self._ref = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        ctk.CTkLabel(self, image=self._ref, text="").pack(
            expand=True, fill="both", padx=10, pady=10
        )


class ImageGrid(ctk.CTkScrollableFrame):
    """処理対象画像のサムネ一覧。クリックで on_select(path) を呼ぶ。"""

    THUMB_SIZE = (84, 84)
    COLS = 2

    def __init__(self, parent, on_select, label_text="処理する画像", **kwargs):
        super().__init__(parent, label_text=label_text, **kwargs)
        self._on_select = on_select
        self._thumb_refs = []
        self._selected = None
        self._buttons = {}

    def refresh(self, image_paths):
        for child in self.winfo_children():
            child.destroy()
        self._thumb_refs.clear()
        self._buttons = {}
        if not image_paths:
            ctk.CTkLabel(
                self, text="ここに画像をドラッグ&ドロップ\nまたは「＋ 画像を追加」",
            ).grid(row=0, column=0, padx=8, pady=8)
            return
        for idx, path in enumerate(image_paths):
            r, c = divmod(idx, self.COLS)
            thumb = load_thumbnail(path, self.THUMB_SIZE)
            if thumb is None:
                continue
            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=self.THUMB_SIZE)
            self._thumb_refs.append(ctk_img)
            btn = ctk.CTkButton(
                self, image=ctk_img, text=path.name[:10], compound="top",
                width=104, height=116, command=lambda p=path: self._select(p),
            )
            btn.grid(row=r, column=c, padx=4, pady=4)
            self._buttons[path] = btn
            if path == self._selected:
                btn.configure(border_width=2)

    def set_selected(self, path):
        self._selected = path
        for p, b in self._buttons.items():
            b.configure(border_width=2 if p == path else 0)

    def _select(self, path):
        self.set_selected(path)
        self._on_select(path)
