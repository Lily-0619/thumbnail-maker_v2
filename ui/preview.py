"""
preview.py
PIL Image を customtkinter 内の Canvas で表示するプレビューパネル。
"""

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk


class PreviewPanel(ctk.CTkFrame):
    """合成済み画像をリサイズしてUIに表示し、文字要素のクリック/ドラッグを扱うパネル。"""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._canvas = tk.Canvas(self, highlightthickness=0, bg="#1f1f1f", cursor="arrow")
        self._canvas.pack(expand=True, fill="both", padx=20, pady=20)
        self._current_pil = None
        self._photo = None
        self._image_item = None
        self._display = {"x": 0, "y": 0, "w": 0, "h": 0, "ratio": 1.0}
        self._text_elements = []
        self._selected_key = None
        self._select_callback = None
        self._drag_callback = None
        self._release_callback = None  # ドラッグ完了時に再合成を呼ぶ
        self._drag_key = None
        self._drag_last = None
        self._drag_occurred = False  # ドラッグが実際に発生したか記録

        self._canvas.create_text(
            10,
            10,
            anchor="nw",
            fill="#9a9a9a",
            font=("TkDefaultFont", 16),
            text="[ プレビュー ]\nまず素材を選んで「プレビュー」を押してください",
        )

        self.bind("<Configure>", self._on_resize)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

    def set_callbacks(self, on_select=None, on_drag=None, on_release=None):
        """クリック選択・ドラッグ移動・ドラッグ完了のコールバックを登録する。"""
        self._select_callback = on_select
        self._drag_callback = on_drag
        self._release_callback = on_release

    def set_text_elements(self, elements):
        """1920x1080基準の文字要素矩形をプレビューへ渡す。"""
        self._text_elements = elements or []
        self._draw_selection()

    def set_selected(self, key: str | None):
        """選択中の文字要素キーを更新し、プレビュー上に枠を描く。"""
        self._selected_key = key
        self._draw_selection()

    def show(self, pil_image: Image.Image):
        """PIL Imageを受け取り、パネルに合わせてリサイズして表示する。"""
        self._current_pil = pil_image
        self._render()

    def _render(self):
        self._canvas.delete("all")
        if self._current_pil is None:
            self._canvas.create_text(
                10,
                10,
                anchor="nw",
                fill="#9a9a9a",
                font=("TkDefaultFont", 16),
                text="[ プレビュー ]\nまず素材を選んで「プレビュー」を押してください",
            )
            return

        panel_w = max(self._canvas.winfo_width(), 100)
        panel_h = max(self._canvas.winfo_height(), 100)

        img_w, img_h = self._current_pil.size
        ratio = min(panel_w / img_w, panel_h / img_h)
        new_w = max(int(img_w * ratio), 1)
        new_h = max(int(img_h * ratio), 1)
        offset_x = (panel_w - new_w) // 2
        offset_y = (panel_h - new_h) // 2
        self._display = {"x": offset_x, "y": offset_y, "w": new_w, "h": new_h, "ratio": ratio}

        resized = self._current_pil.resize((new_w, new_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        self._image_item = self._canvas.create_image(offset_x, offset_y, anchor="nw", image=self._photo)
        self._draw_selection()

    def _on_resize(self, _event):
        """ウィンドウリサイズ時にプレビューを再描画する。"""
        self._render()

    def _canvas_to_image(self, event) -> tuple[int, int] | None:
        display = self._display
        if not display["w"] or not display["h"]:
            return None
        if not (display["x"] <= event.x <= display["x"] + display["w"]):
            return None
        if not (display["y"] <= event.y <= display["y"] + display["h"]):
            return None
        image_x = int((event.x - display["x"]) / display["ratio"])
        image_y = int((event.y - display["y"]) / display["ratio"])
        return image_x, image_y

    def _image_delta_from_canvas(self, dx: int, dy: int) -> tuple[int, int]:
        ratio = self._display.get("ratio") or 1.0
        return int(round(dx / ratio)), int(round(dy / ratio))

    def _hit_test(self, image_x: int, image_y: int) -> str | None:
        for element in reversed(self._text_elements):
            x1, y1, x2, y2 = element["bbox"]
            if x1 <= image_x <= x2 and y1 <= image_y <= y2:
                return element["key"]
        return None

    def _on_click(self, event):
        image_pos = self._canvas_to_image(event)
        key = self._hit_test(*image_pos) if image_pos else None
        self._drag_key = key
        self._drag_last = (event.x, event.y) if key else None
        self._drag_occurred = False
        self.set_selected(key)
        if self._select_callback:
            self._select_callback(key)
        self.focus_set()

    def _on_drag(self, event):
        if not self._drag_key or not self._drag_last or not self._drag_callback:
            return
        dx = event.x - self._drag_last[0]
        dy = event.y - self._drag_last[1]
        image_dx, image_dy = self._image_delta_from_canvas(dx, dy)
        if image_dx or image_dy:
            self._drag_occurred = True
            self._drag_callback(self._drag_key, image_dx, image_dy)
            self._drag_last = (event.x, event.y)

    def _on_release(self, _event):
        """マウスを離したとき、ドラッグが発生していれば再合成コールバックを呼ぶ。"""
        if self._drag_occurred and self._release_callback:
            self._release_callback()
        self._drag_key = None
        self._drag_last = None
        self._drag_occurred = False

    def _draw_selection(self):
        self._canvas.delete("selection")
        if not self._selected_key:
            return
        display = self._display
        ratio = display.get("ratio") or 1.0
        selected = next((element for element in self._text_elements if element["key"] == self._selected_key), None)
        if not selected:
            return
        x1, y1, x2, y2 = selected["bbox"]
        sx1 = display["x"] + x1 * ratio
        sy1 = display["y"] + y1 * ratio
        sx2 = display["x"] + x2 * ratio
        sy2 = display["y"] + y2 * ratio
        self._canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="#3BA5FF", width=2, tags="selection")
        self._canvas.create_text(
            sx1,
            max(sy1 - 18, 4),
            anchor="nw",
            fill="#3BA5FF",
            text=selected.get("label", "選択中"),
            tags="selection",
        )
