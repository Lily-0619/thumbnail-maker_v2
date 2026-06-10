"""
app.py
customtkinter を使ったメインUIウィンドウ。
"""

import copy
import json
import re
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.composer import compose_thumbnail
from core.template import list_templates, load_template
from core.text_renderer import (
    LANGUAGE_FONT_CATEGORIES,
    TEXT_ELEMENT_LABELS,
    build_text_element_bounds,
)
from ui.preview import PreviewPanel


# ── テーマ設定 ──
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


WEEKDAY_LABELS = {
    "monday": "月曜日",
    "tuesday": "火曜日",
    "wednesday": "水曜日",
    "thursday": "木曜日",
    "friday": "金曜日",
    "saturday": "土曜日",
    "sunday": "日曜日",
}
WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_BY_INDEX = WEEKDAY_ORDER
NODE_OPTIONS_PATH = Path("data/node_options.json")


class ThumbnailApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("黒砂漠モバイル サムネイル自動生成アプリ v0.2.4")
        self.geometry("1500x900")
        self.resizable(True, True)

        # ── 内部状態 ──
        self.bg_path = ctk.StringVar()
        self.char_path = ctk.StringVar()
        # 後方エフェクトはAI生成前提。将来の生成処理からここへパスを入れる想定。
        self.effect_path = ctk.StringVar()
        self.font_path = ctk.StringVar(value="assets/fonts/NotoSansJP-Bold.ttf")
        self.branding_font_path = ctk.StringVar(value="")
        self.branding_text = ctk.StringVar(value="Black Desert Mobile")
        self.current_template = load_template("node_war_default")
        self.node_options = self._load_node_options()
        self._preview_image = None  # PIL Image キャッシュ
        self.selected_text_key = None
        self.selected_text_name = ctk.StringVar(value="選択中: なし")
        self.options_visible = False

        self._build_layout()
        self._bind_auto_output_name()
        self._update_output_name()

    # ──────────────────────────────────────────
    #  レイアウト構築
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self, width=500, label_text="設定パネル")
        left.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self._build_form(left)

        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=0)
        right.rowconfigure(1, weight=0)
        right.rowconfigure(2, weight=1)
        self.preview = PreviewPanel(right, height=430)
        self.preview.grid(row=0, column=0, padx=10, pady=10, sticky="new")
        self.preview.set_callbacks(on_select=self._select_text_element, on_drag=self._drag_text_element)
        ctk.CTkLabel(right, textvariable=self.selected_text_name, font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, sticky="n", pady=(0, 4)
        )
        ctk.CTkLabel(
            right,
            text="プレビュー上の文字をクリックして選択 → 矢印キーで移動 / Shift+矢印で10px移動 / Ctrl+上下でサイズ変更 / ドラッグで移動",
            text_color="gray",
            wraplength=780,
            justify="center",
        ).grid(row=2, column=0, sticky="n", pady=(0, 10))
        self.bind("<KeyPress>", self._on_key_press)

    def _build_form(self, parent):
        pad = {"padx": 10, "pady": 4}

        ctk.CTkLabel(parent, text="📅 日付", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.date_entry = ctk.CTkEntry(parent, placeholder_text="2026.06.04")
        self.date_entry.insert(0, date.today().strftime("%Y.%m.%d"))
        self.date_entry.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🗓️ 曜日", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        current_weekday = WEEKDAY_BY_INDEX[date.today().weekday()]
        self.weekday_menu = ctk.CTkOptionMenu(
            parent,
            values=[WEEKDAY_LABELS[key] for key in WEEKDAY_ORDER],
            command=self._on_weekday_changed,
        )
        self.weekday_menu.set(WEEKDAY_LABELS[current_weekday])
        self.weekday_menu.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🏰 拠点候補", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.node_entry = ctk.CTkEntry(parent, placeholder_text="リンチファーム遺跡")
        self.node_menu = ctk.CTkOptionMenu(parent, values=["未設定"], command=self._on_node_selected)
        self.node_menu.pack(fill="x", **pad)
        self.node_entry.pack(fill="x", **pad)
        self._set_node_menu_values(current_weekday)

        # 出力ファイル名は、日付・拠点候補の下、ギルド名入力の上へ移動。
        ctk.CTkLabel(parent, text="💾 出力ファイル名", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.output_name = ctk.CTkEntry(parent, placeholder_text="20260609_node")
        self.output_name.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="⚔️ ギルド名（最大5つ・空欄は無視）", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.guild_entries = []
        self.guild_font_paths = []
        for i in range(5):
            row = ctk.CTkFrame(parent)
            row.pack(fill="x", **pad)
            entry = ctk.CTkEntry(row, placeholder_text=f"ギルド {i + 1}")
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            font_var = ctk.StringVar(value="")
            ctk.CTkEntry(row, textvariable=font_var, placeholder_text="個別フォント（任意）", width=150).pack(side="left", padx=(0, 6))
            ctk.CTkButton(row, text="選択", width=54, command=lambda v=font_var: self._select_font_var(v)).pack(side="left")
            self.guild_entries.append(entry)
            self.guild_font_paths.append(font_var)

        ctk.CTkLabel(parent, text="🖼️ 背景画像", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.bg_path, placeholder_text="未選択なら所定フォルダからランダム").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="背景を選択", command=self._select_bg).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🧙 キャラクター画像", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.char_path, placeholder_text="未選択").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="キャラを選択", command=self._select_char).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="✨ 後方エフェクト", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkLabel(
            parent,
            text="後方エフェクトは今後、背景生成開始時にキャラクターへ合わせてAI生成する想定です。位置・サイズ・透明度の手動調整はv0.2.2で削除しました。",
            text_color="gray",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", **pad)

        ctk.CTkButton(
            parent,
            text="⚙️ オプションを開く",
            height=38,
            command=self._toggle_options,
        ).pack(fill="x", padx=10, pady=(12, 4))

        self.options_frame = ctk.CTkFrame(parent)
        self._build_options(self.options_frame)

        ctk.CTkLabel(parent, text="📋 テンプレート", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        templates = list_templates() or ["node_war_default"]
        self.template_menu = ctk.CTkOptionMenu(parent, values=templates, command=self._load_template)
        self.template_menu.pack(fill="x", **pad)

        ctk.CTkButton(
            parent,
            text="👁️  プレビュー",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._preview,
        ).pack(fill="x", padx=10, pady=(16, 4))

        ctk.CTkButton(
            parent,
            text="📤  PNG出力",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1e6f3e",
            hover_color="#145a2e",
            command=self._export,
        ).pack(fill="x", padx=10, pady=4)

    def _build_options(self, parent):
        pad = {"padx": 10, "pady": 4}

        ctk.CTkLabel(parent, text="🌐 ギルド名カテゴリ別フォント", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkLabel(
            parent,
            text="個別フォント欄が空なら、ギルド名から言語カテゴリを自動判定して下のフォントを使います。",
            text_color="gray",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", **pad)
        self.language_font_paths = {}
        for key in ["ja", "ru", "en", "zh", "ko"]:
            row = ctk.CTkFrame(parent)
            row.pack(fill="x", **pad)
            ctk.CTkLabel(row, text=LANGUAGE_FONT_CATEGORIES[key]["label"], width=155, anchor="w").pack(side="left", padx=(0, 6))
            font_var = ctk.StringVar(value="")
            ctk.CTkEntry(row, textvariable=font_var, placeholder_text="未指定ならOS標準候補", width=170).pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkButton(row, text="選択", width=54, command=lambda v=font_var: self._select_font_var(v)).pack(side="left")
            self.language_font_paths[key] = font_var

        ctk.CTkLabel(parent, text="🔤 共通フォント / 右下表示", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.font_path, placeholder_text="日付・拠点名・Node War用フォント").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="共通フォントを選択", command=self._select_font).pack(fill="x", **pad)
        ctk.CTkEntry(parent, textvariable=self.branding_text, placeholder_text="右下表示テキスト").pack(fill="x", **pad)
        ctk.CTkEntry(parent, textvariable=self.branding_font_path, placeholder_text="右下表示フォント（空なら共通フォント）").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="右下表示フォントを選択", command=lambda: self._select_font_var(self.branding_font_path)).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="📐 キャラ拡大率（右側固定）", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.char_scale = self._build_number_row(parent, "キャラ拡大率", "1.0")

        ctk.CTkLabel(parent, text="📝 文字位置・サイズ", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.date_x = self._build_number_row(parent, "日付X", "100")
        self.date_y = self._build_number_row(parent, "日付Y", "60")
        self.date_size = self._build_number_row(parent, "日付サイズ", "70")
        self.node_x = self._build_number_row(parent, "拠点名X", "100")
        self.node_y = self._build_number_row(parent, "拠点名Y", "300")
        self.node_size = self._build_number_row(parent, "拠点名サイズ", "170")
        self.subtitle_x = self._build_number_row(parent, "Node War X", "100")
        self.subtitle_y = self._build_number_row(parent, "Node War Y", "470")
        self.subtitle_size = self._build_number_row(parent, "Node Warサイズ", "75")
        self.guild_x = self._build_number_row(parent, "ギルド名X", "100")
        self.guild_y = self._build_number_row(parent, "ギルド名Y", "300")
        self.guild_size = self._build_number_row(parent, "ギルド名サイズ", "75")
        self.guild_line_spacing = self._build_number_row(parent, "ギルド名行間", "10")
        self.branding_x = self._build_number_row(parent, "右下表示X", "1320")
        self.branding_y = self._build_number_row(parent, "右下表示Y", "980")
        self.branding_size = self._build_number_row(parent, "右下表示サイズ", "46")

    def _build_number_row(self, parent, label: str, default: str) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=90)
        entry.insert(0, default)
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def _toggle_options(self):
        self.options_visible = not self.options_visible
        if self.options_visible:
            self.options_frame.pack(fill="x", padx=10, pady=8)
        else:
            self.options_frame.pack_forget()

    # ──────────────────────────────────────────
    #  ファイル選択
    # ──────────────────────────────────────────

    def _select_bg(self):
        p = filedialog.askopenfilename(
            title="背景画像を選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.webp"), ("すべて", "*.*")],
        )
        if p:
            self.bg_path.set(p)

    def _select_char(self):
        p = filedialog.askopenfilename(title="キャラクター画像を選択", filetypes=[("PNG画像", "*.png"), ("すべて", "*.*")])
        if p:
            self.char_path.set(p)

    def _select_font(self):
        self._select_font_var(self.font_path)

    def _select_font_var(self, font_var):
        p = filedialog.askopenfilename(
            title="フォントファイルを選択",
            filetypes=[("フォント", "*.ttf *.otf *.ttc"), ("すべて", "*.*")],
        )
        if p:
            font_var.set(p)

    # ──────────────────────────────────────────
    #  曜日別拠点候補 / 出力名
    # ──────────────────────────────────────────

    def _load_node_options(self) -> dict:
        if NODE_OPTIONS_PATH.exists():
            with open(NODE_OPTIONS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {key: [] for key in WEEKDAY_ORDER}

    def _weekday_key_from_label(self, label: str) -> str:
        for key, value in WEEKDAY_LABELS.items():
            if value == label:
                return key
        return "monday"

    def _set_node_menu_values(self, weekday_key: str):
        values = self.node_options.get(weekday_key) or ["未設定"]
        self.node_menu.configure(values=values)
        self.node_menu.set(values[0])
        if values[0] != "未設定":
            self.node_entry.delete(0, "end")
            self.node_entry.insert(0, values[0])

    def _on_weekday_changed(self, label: str):
        self._set_node_menu_values(self._weekday_key_from_label(label))
        self._update_output_name()

    def _on_node_selected(self, node_name: str):
        if node_name == "未設定":
            return
        self.node_entry.delete(0, "end")
        self.node_entry.insert(0, node_name)
        self._update_output_name()

    def _bind_auto_output_name(self):
        self.date_entry.bind("<KeyRelease>", lambda _event: self._update_output_name())
        self.node_entry.bind("<KeyRelease>", lambda _event: self._update_output_name())

    def _safe_filename_part(self, value: str) -> str:
        value = value.strip().replace(" ", "_").replace("　", "_")
        value = re.sub(r'[\\/:*?"<>|]+', "_", value)
        return value or "thumbnail"

    def _update_output_name(self):
        date_part = self.date_entry.get().replace(".", "") or date.today().strftime("%Y%m%d")
        node_part = self._safe_filename_part(self.node_entry.get())
        self.output_name.delete(0, "end")
        self.output_name.insert(0, f"{date_part}_{node_part}")

    # ──────────────────────────────────────────
    #  テンプレート読み込み
    # ──────────────────────────────────────────

    def _load_template(self, name: str):
        self.current_template = load_template(name)
        self._apply_template_to_controls()
        print(f"[テンプレート] {name} を読み込みました")

    def _apply_template_to_controls(self):
        self._set_entry(self.char_scale, self.current_template.get("character", {}).get("scale", 1.0))

        text_cfg = self.current_template.get("text", {})
        self._set_entry(self.date_x, text_cfg.get("date", {}).get("x", 100))
        self._set_entry(self.date_y, text_cfg.get("date", {}).get("y", 60))
        self._set_entry(self.date_size, text_cfg.get("date", {}).get("font_size", 70))
        self._set_entry(self.node_x, text_cfg.get("node_name", {}).get("x", 100))
        self._set_entry(self.node_y, text_cfg.get("node_name", {}).get("y", 300))
        self._set_entry(self.node_size, text_cfg.get("node_name", {}).get("font_size", 170))
        self._set_entry(self.subtitle_x, text_cfg.get("subtitle", {}).get("x", 100))
        self._set_entry(self.subtitle_y, text_cfg.get("subtitle", {}).get("y", 470))
        self._set_entry(self.subtitle_size, text_cfg.get("subtitle", {}).get("font_size", 75))
        self._set_entry(self.guild_x, text_cfg.get("guilds", {}).get("x", 100))
        self._set_entry(self.guild_y, text_cfg.get("guilds", {}).get("y", 300))
        self._set_entry(self.guild_size, text_cfg.get("guilds", {}).get("font_size", 75))
        self._set_entry(self.guild_line_spacing, text_cfg.get("guilds", {}).get("line_spacing", 10))

        branding_cfg = self.current_template.get("branding", {})
        self.branding_text.set(branding_cfg.get("text", "Black Desert Mobile"))
        self.branding_font_path.set(branding_cfg.get("font_path", ""))
        self._set_entry(self.branding_x, branding_cfg.get("x", 1320))
        self._set_entry(self.branding_y, branding_cfg.get("y", 980))
        self._set_entry(self.branding_size, branding_cfg.get("font_size", 46))

        language_fonts = self.current_template.get("language_fonts", {})
        for key, font_var in self.language_font_paths.items():
            font_var.set(language_fonts.get(key, ""))

    # ──────────────────────────────────────────
    #  合成パラメータ収集
    # ──────────────────────────────────────────

    def _int_value(self, entry, default: int) -> int:
        try:
            return int(float(entry.get()))
        except ValueError:
            return default

    def _float_value(self, entry, default: float) -> float:
        try:
            return float(entry.get())
        except ValueError:
            return default

    def _set_entry(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value))


    def _text_control_map(self) -> dict:
        return {
            "date": {"x": self.date_x, "y": self.date_y, "size": self.date_size},
            "node_name": {"x": self.node_x, "y": self.node_y, "size": self.node_size},
            "subtitle": {"x": self.subtitle_x, "y": self.subtitle_y, "size": self.subtitle_size},
            "guilds": {"x": self.guild_x, "y": self.guild_y, "size": self.guild_size},
            "branding": {"x": self.branding_x, "y": self.branding_y, "size": self.branding_size},
        }

    def _select_text_element(self, key: str | None):
        """プレビューでクリックされた文字要素を選択状態にする。"""
        self.selected_text_key = key
        if key:
            self.selected_text_name.set(f"選択中: {TEXT_ELEMENT_LABELS.get(key, key)}")
        else:
            self.selected_text_name.set("選択中: なし")
        if hasattr(self, "preview"):
            self.preview.set_selected(key)

    def _move_text_element(self, key: str, dx: int, dy: int, refresh: bool = True):
        controls = self._text_control_map().get(key)
        if not controls:
            return
        self._set_entry(controls["x"], self._int_value(controls["x"], 0) + dx)
        self._set_entry(controls["y"], self._int_value(controls["y"], 0) + dy)
        if refresh:
            self._refresh_preview_after_text_edit()

    def _resize_text_element(self, key: str, delta: int):
        controls = self._text_control_map().get(key)
        if not controls:
            return
        current = self._int_value(controls["size"], 1)
        self._set_entry(controls["size"], max(1, current + delta))
        self._refresh_preview_after_text_edit()

    def _drag_text_element(self, key: str, dx: int, dy: int):
        """プレビュー上のドラッグ量を元画像座標として反映する。"""
        self._select_text_element(key)
        self._move_text_element(key, dx, dy)

    def _on_key_press(self, event):
        """選択中の文字要素を矢印キーで移動し、Ctrl+上下でサイズを変える。"""
        if not self.selected_text_key:
            return
        key_name = event.keysym
        if key_name not in {"Up", "Down", "Left", "Right"}:
            return

        is_shift = bool(event.state & 0x0001)
        is_ctrl = bool(event.state & 0x0004)
        if is_ctrl and key_name in {"Up", "Down"}:
            self._resize_text_element(self.selected_text_key, 1 if key_name == "Up" else -1)
            return "break"

        step = 10 if is_shift else 1
        dx = 0
        dy = 0
        if key_name == "Up":
            dy = -step
        elif key_name == "Down":
            dy = step
        elif key_name == "Left":
            dx = -step
        elif key_name == "Right":
            dx = step
        self._move_text_element(self.selected_text_key, dx, dy)
        return "break"

    def _refresh_preview_after_text_edit(self):
        self._preview()
        self.preview.set_selected(self.selected_text_key)

    def _collect_params(self) -> dict:
        """UIの入力値をまとめてdictで返す。"""
        template = copy.deepcopy(self.current_template)
        text_cfg = template.setdefault("text", {})

        text_cfg.setdefault("date", {}).update(
            {
                "x": self._int_value(self.date_x, 100),
                "y": self._int_value(self.date_y, 60),
                "font_size": self._int_value(self.date_size, 70),
            }
        )
        text_cfg.setdefault("node_name", {}).update(
            {
                "x": self._int_value(self.node_x, 100),
                "y": self._int_value(self.node_y, 300),
                "font_size": self._int_value(self.node_size, 170),
            }
        )
        text_cfg.setdefault("subtitle", {}).update(
            {
                "text": "Node War",
                "x": self._int_value(self.subtitle_x, 100),
                "y": self._int_value(self.subtitle_y, 470),
                "font_size": self._int_value(self.subtitle_size, 75),
            }
        )
        text_cfg.setdefault("guilds", {}).update(
            {
                "x": self._int_value(self.guild_x, 100),
                "y": self._int_value(self.guild_y, 300),
                "font_size": self._int_value(self.guild_size, 75),
                "line_spacing": self._int_value(self.guild_line_spacing, 10),
            }
        )

        template.setdefault("character", {}).update(
            {
                "position": "right",
                "offset_x": 0,
                "offset_y": 0,
                "scale": self._float_value(self.char_scale, 1.0),
            }
        )
        template.setdefault("branding", {}).update(
            {
                "type": "text",
                "text": self.branding_text.get().strip() or "Black Desert Mobile",
                "font_path": self.branding_font_path.get().strip(),
                "x": self._int_value(self.branding_x, 1320),
                "y": self._int_value(self.branding_y, 980),
                "font_size": self._int_value(self.branding_size, 46),
            }
        )

        guilds = [e.get().strip() for e in self.guild_entries if e.get().strip()]
        guild_font_paths = []
        for entry, font_var in zip(self.guild_entries, self.guild_font_paths):
            if entry.get().strip():
                guild_font_paths.append(font_var.get().strip())
        language_font_paths = {key: var.get().strip() for key, var in self.language_font_paths.items() if var.get().strip()}

        return {
            "bg_path": self.bg_path.get(),
            "char_path": self.char_path.get(),
            "effect_path": self.effect_path.get(),
            "date_str": self.date_entry.get(),
            "node_name": self.node_entry.get(),
            "guilds": guilds,
            "template": template,
            "font_path": self.font_path.get(),
            "guild_font_paths": guild_font_paths,
            "language_font_paths": language_font_paths,
        }

    # ──────────────────────────────────────────
    #  プレビュー / PNG出力
    # ──────────────────────────────────────────

    def _preview(self):
        params = self._collect_params()
        try:
            img = compose_thumbnail(**params)
            self._preview_image = img
            self.preview.show(img)
            self.preview.set_text_elements(
                build_text_element_bounds(
                    params["date_str"],
                    params["node_name"],
                    params["guilds"],
                    params["template"],
                    params["font_path"],
                    guild_font_paths=params["guild_font_paths"],
                    language_font_paths=params["language_font_paths"],
                )
            )
            self.preview.set_selected(self.selected_text_key)
        except Exception as e:
            messagebox.showerror("エラー", f"プレビュー生成に失敗しました:\n{e}")

    def _export(self):
        self._preview()
        if self._preview_image is None:
            return

        name = self.output_name.get().strip()
        if not name:
            date_str = self.date_entry.get().replace(".", "")
            node = self.node_entry.get().replace(" ", "_").replace("　", "_")
            name = f"{date_str}_{node}" if node else f"{date_str}_thumbnail"

        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{name}.png"

        counter = 1
        while out_path.exists():
            out_path = out_dir / f"{name}_{counter:02d}.png"
            counter += 1

        self._preview_image.save(str(out_path), "PNG")
        messagebox.showinfo("出力完了", f"保存しました:\n{out_path.resolve()}")
        print(f"[出力] {out_path.resolve()}")
