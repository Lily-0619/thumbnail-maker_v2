"""
preview.py
PIL Image を customtkinter の CTkLabel で表示するプレビューパネル。
"""

import customtkinter as ctk
from PIL import Image


class PreviewPanel(ctk.CTkFrame):
    """合成済み画像をリサイズしてUIに表示するパネル。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._label = ctk.CTkLabel(
            self,
            text="[ プレビュー ]\nまず素材を選んで「プレビュー」を押してください",
            font=ctk.CTkFont(size=16),
            text_color="gray",
        )
        self._label.pack(expand=True, fill="both", padx=20, pady=20)
        self._current_pil = None

        self.bind("<Configure>", self._on_resize)

    def show(self, pil_image: Image.Image):
        """PIL Imageを受け取り、パネルに合わせてリサイズして表示する。"""
        self._current_pil = pil_image
        self._render()

    def _render(self):
        if self._current_pil is None:
            return

        panel_w = max(self.winfo_width() - 20, 100)
        panel_h = max(self.winfo_height() - 20, 100)

        img_w, img_h = self._current_pil.size
        ratio = min(panel_w / img_w, panel_h / img_h)
        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)

        resized = self._current_pil.resize((new_w, new_h), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(new_w, new_h))

        self._label.configure(image=ctk_img, text="")
        self._label.image = ctk_img

    def _on_resize(self, event):
        """ウィンドウリサイズ時にプレビューを再描画する。"""
        self._render()
