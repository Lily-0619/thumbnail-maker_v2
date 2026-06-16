"""
widgets.py
再利用するUI部品。

  - load_thumbnail : Pillowで透過を保ったサムネ生成
  - ZoomWindow     : プレビュー拡大用の別ウィンドウ（CTkToplevel）
  - PreviewPanel   : 選択中画像を大きく表示（右上に拡大ボタン）
  - UnsortedGrid   : _unsorted のサムネ一覧（選択でコールバック）

本体 ui/app.py の CharacterPickerDialog（CTkScrollableFrame + CTkImage）の作法を踏襲。
CTkImage は参照を保持しないとサムネが消えるため self._thumb_refs に退避する。
"""

from pathlib import Path

import customtkinter as ctk
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def load_thumbnail(path: Path, size):
    """透過を保ったままサムネを生成して返す（失敗時 None）。"""
    try:
        img = Image.open(path).convert("RGBA")
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
            img = Image.open(path).convert("RGBA")
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

    PREVIEW_SIZE = (360, 270)

    def __init__(self, parent):
        super().__init__(parent)
        self._current_path = None
        self._img_ref = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=6, pady=(6, 0))
        ctk.CTkLabel(header, text="プレビュー", anchor="w").pack(side="left")
        self._zoom_btn = ctk.CTkButton(
            header, text="🔍 拡大", width=70, command=self._open_zoom
        )
        self._zoom_btn.pack(side="right")

        self._image_label = ctk.CTkLabel(
            self, text="未分類画像を選択してください", width=self.PREVIEW_SIZE[0],
            height=self.PREVIEW_SIZE[1],
        )
        self._image_label.pack(expand=True, fill="both", padx=6, pady=6)

    def show(self, path):
        """指定パスの画像をプレビューに表示する。"""
        path = Path(path) if path else None
        self._current_path = path
        if path is None or not path.exists():
            self._img_ref = None
            self._image_label.configure(image=None, text="未分類画像を選択してください")
            return
        thumb = load_thumbnail(path, self.PREVIEW_SIZE)
        if thumb is None:
            self._img_ref = None
            self._image_label.configure(image=None, text="画像を開けませんでした")
            return
        self._img_ref = ctk.CTkImage(
            light_image=thumb, dark_image=thumb, size=self.PREVIEW_SIZE
        )
        self._image_label.configure(image=self._img_ref, text="")

    def _open_zoom(self):
        if self._current_path and self._current_path.exists():
            ZoomWindow(self.winfo_toplevel(), self._current_path)


class UnsortedGrid(ctk.CTkScrollableFrame):
    """_unsorted のサムネ一覧。クリックで on_select(path) を呼ぶ。"""

    THUMB_SIZE = (84, 84)
    COLS = 3

    def __init__(self, parent, on_select, **kwargs):
        super().__init__(parent, label_text="未分類 (_unsorted)", **kwargs)
        self._on_select = on_select
        self._thumb_refs = []
        self._selected = None

    def refresh(self, image_paths):
        """画像パスのリストを受け取りグリッドを作り直す。"""
        for child in self.winfo_children():
            child.destroy()
        self._thumb_refs.clear()

        if not image_paths:
            ctk.CTkLabel(
                self, text="未分類画像がありません。\n「画像を追加」ボタンで追加してください。"
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
                command=lambda p=path: self._on_select(p),
            )
            btn.grid(row=r, column=c, padx=4, pady=4)
