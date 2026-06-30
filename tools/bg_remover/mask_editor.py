"""
mask_editor.py
手動切り抜き（透過消しゴム）エディタ。Canva風に、AIの背景除去結果を手で補正する。

  - 削除する：塗ったところを透過（alpha=0）にする
  - 復元する：塗ったところを元画像から復元（alpha=255）する
  - サイズ：ブラシの大きさ
  - 元の画像を表示：元画像を薄く重ねてガイド表示（復元の目安）
  - 編集をリセット：AI結果の状態に戻す
  - ✔ 適用：編集結果を呼び出し元へ返す

実体は「元画像(RGB) ＋ 編集可能なアルファマスク(L)」。消す=0／復元=255 をマスクに描く。
出力用フル解像度マスク(_mask_full)と表示用の縮小マスク(_mask_disp)を同時に塗って軽くする。
"""

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

try:
    from . import engine
except ImportError:
    import engine

DISP_BOX = (820, 620)

_PINK = {
    "button": "#db3b8f", "button_hover": "#c02e7b",
    "accent": "#c6b6e2", "accent_hover": "#b09cd4", "accent_text": "#3f2a44",
}


class MaskEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent, original, result, title="手動切り抜き", on_apply=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("1000x780")
        self.grab_set()
        self._on_apply = on_apply

        self._original = original.convert("RGBA")
        # 注意: self._w は Tk ウィジェットのパス名なので使わない（_iw/_ih を使う）
        self._iw, self._ih = self._original.size
        # 出力用フルのマスク（AI結果のアルファを初期値に）
        self._mask_full = result.convert("RGBA").split()[3]
        self._init_mask_full = self._mask_full.copy()

        scale = min(DISP_BOX[0] / self._iw, DISP_BOX[1] / self._ih, 1.0)
        self._scale = scale
        self._dw = max(1, int(self._iw * scale))
        self._dh = max(1, int(self._ih * scale))
        self._orig_disp = self._original.resize((self._dw, self._dh), Image.LANCZOS)
        self._checker_disp = engine.make_checker(self._dw, self._dh)
        self._mask_disp = self._mask_full.resize((self._dw, self._dh), Image.LANCZOS)

        self._mode = ctk.StringVar(value="削除する")
        self._brush = 20
        self._show_original = ctk.BooleanVar(value=False)
        self._photo = None
        self._cursor_id = None

        self._build()
        self._render()

    # ── UI ──
    def _build(self):
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(bar, text="タイプ").pack(side="left", padx=(8, 4))
        ctk.CTkSegmentedButton(
            bar, values=["削除する", "復元する"], variable=self._mode,
        ).pack(side="left", padx=4)

        ctk.CTkLabel(bar, text="サイズ").pack(side="left", padx=(16, 4))
        slider = ctk.CTkSlider(bar, from_=4, to=120, number_of_steps=116, command=self._on_size, width=140)
        slider.set(self._brush)
        slider.pack(side="left", padx=4)
        self._size_label = ctk.CTkLabel(bar, text=str(self._brush), width=32)
        self._size_label.pack(side="left", padx=2)

        ctk.CTkSwitch(
            bar, text="元の画像を表示", variable=self._show_original, command=self._render,
        ).pack(side="left", padx=16)

        ctk.CTkButton(
            bar, text="↺ 編集をリセット", width=120, command=self._reset,
            fg_color=_PINK["accent"], hover_color=_PINK["accent_hover"], text_color=_PINK["accent_text"],
        ).pack(side="left", padx=6)

        ctk.CTkButton(bar, text="閉じる", width=80, command=self.destroy,
                      fg_color=_PINK["accent"], hover_color=_PINK["accent_hover"],
                      text_color=_PINK["accent_text"]).pack(side="right", padx=(6, 8))
        ctk.CTkButton(bar, text="✔ 適用", width=90, command=self._apply,
                      fg_color=_PINK["button"], hover_color=_PINK["button_hover"]).pack(side="right", padx=6)

        wrap = ctk.CTkFrame(self)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._canvas = tk.Canvas(
            wrap, width=self._dw, height=self._dh, highlightthickness=0,
            bg="#e9e2ee", cursor="none",
        )
        self._canvas.pack(expand=True)
        self._img_id = self._canvas.create_image(0, 0, anchor="nw")
        self._canvas.bind("<Button-1>", self._paint)
        self._canvas.bind("<B1-Motion>", self._paint)
        self._canvas.bind("<Motion>", self._move_cursor)
        self._canvas.bind("<Leave>", lambda _e: self._hide_cursor())

    # ── 描画 ──
    def _render(self):
        res = self._orig_disp.copy()
        res.putalpha(self._mask_disp)
        disp = self._checker_disp.copy()
        disp.paste(res, (0, 0), res)
        if self._show_original.get():
            ghost = self._orig_disp.copy()
            ghost.putalpha(90)  # 元画像を薄く重ねてガイド表示
            disp.paste(ghost, (0, 0), ghost)
        self._photo = ImageTk.PhotoImage(disp)
        self._canvas.itemconfig(self._img_id, image=self._photo)

    def _on_size(self, v):
        self._brush = int(float(v))
        self._size_label.configure(text=str(self._brush))

    def _paint(self, event):
        x, y = event.x, event.y
        if x < 0 or y < 0 or x >= self._dw or y >= self._dh:
            return
        value = 0 if self._mode.get() == "削除する" else 255
        r = max(1, self._brush // 2)
        ImageDraw.Draw(self._mask_disp).ellipse([x - r, y - r, x + r, y + r], fill=value)
        fx, fy = x / self._scale, y / self._scale
        rf = max(1, r / self._scale)
        ImageDraw.Draw(self._mask_full).ellipse([fx - rf, fy - rf, fx + rf, fy + rf], fill=value)
        self._render()
        self._move_cursor(event)

    def _move_cursor(self, event):
        r = max(1, self._brush // 2)
        self._hide_cursor()
        self._cursor_id = self._canvas.create_oval(
            event.x - r, event.y - r, event.x + r, event.y + r, outline="#d63384", width=2,
        )

    def _hide_cursor(self):
        if self._cursor_id is not None:
            self._canvas.delete(self._cursor_id)
            self._cursor_id = None

    def _reset(self):
        self._mask_full = self._init_mask_full.copy()
        self._mask_disp = self._mask_full.resize((self._dw, self._dh), Image.LANCZOS)
        self._render()

    def _apply(self):
        result = self._original.copy()
        result.putalpha(self._mask_full)
        if self._on_apply:
            try:
                self._on_apply(result)
            except Exception:
                pass
        self.destroy()
