"""
app.py
customtkinter を使ったメインUIウィンドウ。
"""

import json
from datetime import date
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

from core.composer import compose_thumbnail
from core.template import list_templates, load_template
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
        self.title("黒砂漠モバイル サムネイル自動生成アプリ")
        self.geometry("1500x900")
        self.resizable(True, True)

        # ── 内部状態 ──
        self.bg_path = ctk.StringVar()
        self.char_path = ctk.StringVar()
        self.effect_path = ctk.StringVar()
        self.font_path = ctk.StringVar(value="assets/fonts/NotoSansJP-Bold.ttf")
        self.text_color = ctk.StringVar(value="#d8b15a")
        self.stroke_color = ctk.StringVar(value="#1a1208")
        self.current_template = load_template("node_war_default")
        self.node_options = self._load_node_options()
        self._preview_image = None  # PIL Image キャッシュ

        self._build_layout()

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
        self.preview = PreviewPanel(right)
        self.preview.pack(fill="both", expand=True)

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
        ctk.CTkEntry(parent, textvariable=self.bg_path, placeholder_text="未選択").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="背景を選択", command=self._select_bg).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="✨ 後方エフェクト画像", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.effect_path, placeholder_text="未選択").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="後方エフェクトを選択", command=self._select_effect).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🧙 キャラクター画像", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.char_path, placeholder_text="未選択").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="キャラを選択", command=self._select_char).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="📐 キャラ配置", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.char_pos = ctk.CTkOptionMenu(parent, values=["right", "left", "center"])
        self.char_pos.set("right")
        self.char_pos.pack(fill="x", **pad)
        self.char_x = self._build_number_row(parent, "キャラX座標", "0")
        self.char_y = self._build_number_row(parent, "キャラY座標", "0")
        self.char_scale = self._build_number_row(parent, "キャラ拡大率", "1.0")

        ctk.CTkLabel(parent, text="✨ 後方エフェクト微調整", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.effect_x = self._build_number_row(parent, "後方エフェクトX座標", "0")
        self.effect_y = self._build_number_row(parent, "後方エフェクトY座標", "0")
        self.effect_scale = self._build_number_row(parent, "後方エフェクト拡大率", "1.0")
        self.effect_opacity = self._build_number_row(parent, "後方エフェクト透明度", "0.85")

        ctk.CTkLabel(parent, text="🔤 日付・拠点名フォント", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.font_path, placeholder_text="fonts/NotoSansJP-Bold.ttf").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="フォントを選択", command=self._select_font).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🎨 拠点名カラー", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        color_row = ctk.CTkFrame(parent)
        color_row.pack(fill="x", **pad)
        ctk.CTkEntry(color_row, textvariable=self.text_color, width=100).pack(side="left", padx=(0, 6))
        ctk.CTkButton(color_row, text="色を選ぶ", width=80, command=self._pick_text_color).pack(side="left")

        ctk.CTkLabel(parent, text="🖊️ 縁取りカラー", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        stroke_row = ctk.CTkFrame(parent)
        stroke_row.pack(fill="x", **pad)
        ctk.CTkEntry(stroke_row, textvariable=self.stroke_color, width=100).pack(side="left", padx=(0, 6))
        ctk.CTkButton(stroke_row, text="色を選ぶ", width=80, command=self._pick_stroke_color).pack(side="left")

        ctk.CTkLabel(parent, text="📝 文字位置・サイズ", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.date_x = self._build_number_row(parent, "日付X", "80")
        self.date_y = self._build_number_row(parent, "日付Y", "60")
        self.date_size = self._build_number_row(parent, "日付サイズ", "64")
        self.node_x = self._build_number_row(parent, "拠点名X", "80")
        self.node_y = self._build_number_row(parent, "拠点名Y", "140")
        self.node_size = self._build_number_row(parent, "拠点名サイズ", "96")
        self.guild_x = self._build_number_row(parent, "ギルド名X", "80")
        self.guild_y = self._build_number_row(parent, "ギルド名Y", "820")
        self.guild_size = self._build_number_row(parent, "ギルド名サイズ", "56")
        self.guild_line_spacing = self._build_number_row(parent, "ギルド名行間", "10")

        ctk.CTkLabel(parent, text="📋 テンプレート", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        templates = list_templates() or ["node_war_default"]
        self.template_menu = ctk.CTkOptionMenu(parent, values=templates, command=self._load_template)
        self.template_menu.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="💾 出力ファイル名", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.output_name = ctk.CTkEntry(parent, placeholder_text="20260604_LynchFarmRuins")
        self.output_name.pack(fill="x", **pad)

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

    def _build_number_row(self, parent, label: str, default: str) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=90)
        entry.insert(0, default)
        entry.pack(side="left", fill="x", expand=True)
        return entry

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

    def _select_effect(self):
        p = filedialog.askopenfilename(title="後方エフェクト画像を選択", filetypes=[("PNG画像（透過）", "*.png"), ("すべて", "*.*")])
        if p:
            self.effect_path.set(p)

    def _select_font(self):
        self._select_font_var(self.font_path)

    def _select_font_var(self, font_var):
        p = filedialog.askopenfilename(
            title="フォントファイルを選択",
            filetypes=[("フォント", "*.ttf *.otf *.ttc"), ("すべて", "*.*")],
        )
        if p:
            font_var.set(p)

    def _pick_text_color(self):
        color = colorchooser.askcolor(title="拠点名カラーを選択", color=self.text_color.get())
        if color[1]:
            self.text_color.set(color[1])

    def _pick_stroke_color(self):
        color = colorchooser.askcolor(title="縁取りカラーを選択", color=self.stroke_color.get())
        if color[1]:
            self.stroke_color.set(color[1])

    # ──────────────────────────────────────────
    #  曜日別拠点候補
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

    def _on_node_selected(self, node_name: str):
        if node_name == "未設定":
            return
        self.node_entry.delete(0, "end")
        self.node_entry.insert(0, node_name)

    # ──────────────────────────────────────────
    #  テンプレート読み込み
    # ──────────────────────────────────────────

    def _load_template(self, name: str):
        self.current_template = load_template(name)
        self._apply_template_to_controls()
        print(f"[テンプレート] {name} を読み込みました")

    def _apply_template_to_controls(self):
        self._set_entry(self.char_scale, self.current_template.get("character", {}).get("scale", 1.0))
        self._set_entry(self.char_x, self.current_template.get("character", {}).get("offset_x", 0))
        self._set_entry(self.char_y, self.current_template.get("character", {}).get("offset_y", 0))
        self.char_pos.set(self.current_template.get("character", {}).get("position", "right"))

        effect_cfg = self.current_template.get("back_effect", self.current_template.get("effect", {}))
        self._set_entry(self.effect_x, effect_cfg.get("x", 0))
        self._set_entry(self.effect_y, effect_cfg.get("y", 0))
        self._set_entry(self.effect_scale, effect_cfg.get("scale", 1.0))
        self._set_entry(self.effect_opacity, effect_cfg.get("opacity", 0.85))

        text_cfg = self.current_template.get("text", {})
        self._set_entry(self.date_x, text_cfg.get("date", {}).get("x", 80))
        self._set_entry(self.date_y, text_cfg.get("date", {}).get("y", 60))
        self._set_entry(self.date_size, text_cfg.get("date", {}).get("font_size", 64))
        self._set_entry(self.node_x, text_cfg.get("node_name", {}).get("x", 80))
        self._set_entry(self.node_y, text_cfg.get("node_name", {}).get("y", 140))
        self._set_entry(self.node_size, text_cfg.get("node_name", {}).get("font_size", 96))
        self._set_entry(self.guild_x, text_cfg.get("guilds", {}).get("x", 80))
        self._set_entry(self.guild_y, text_cfg.get("guilds", {}).get("y", 820))
        self._set_entry(self.guild_size, text_cfg.get("guilds", {}).get("font_size", 56))
        self._set_entry(self.guild_line_spacing, text_cfg.get("guilds", {}).get("line_spacing", 10))

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

    def _collect_params(self) -> dict:
        """UIの入力値をまとめてdictで返す。"""
        template = dict(self.current_template)
        text_cfg = template.setdefault("text", {})

        text_cfg.setdefault("date", {}).update(
            {
                "x": self._int_value(self.date_x, 80),
                "y": self._int_value(self.date_y, 60),
                "font_size": self._int_value(self.date_size, 64),
            }
        )
        text_cfg.setdefault("node_name", {}).update(
            {
                "x": self._int_value(self.node_x, 80),
                "y": self._int_value(self.node_y, 140),
                "font_size": self._int_value(self.node_size, 96),
                "color": self.text_color.get(),
                "stroke_color": self.stroke_color.get(),
            }
        )
        text_cfg.setdefault("guilds", {}).update(
            {
                "x": self._int_value(self.guild_x, 80),
                "y": self._int_value(self.guild_y, 820),
                "font_size": self._int_value(self.guild_size, 56),
                "line_spacing": self._int_value(self.guild_line_spacing, 10),
            }
        )

        template.setdefault("character", {}).update(
            {
                "position": self.char_pos.get(),
                "offset_x": self._int_value(self.char_x, 0),
                "offset_y": self._int_value(self.char_y, 0),
                "scale": self._float_value(self.char_scale, 1.0),
            }
        )
        template.setdefault("back_effect", {}).update(
            {
                "x": self._int_value(self.effect_x, 0),
                "y": self._int_value(self.effect_y, 0),
                "scale": self._float_value(self.effect_scale, 1.0),
                "opacity": self._float_value(self.effect_opacity, 0.85),
            }
        )

        guilds = [e.get().strip() for e in self.guild_entries if e.get().strip()]
        guild_font_paths = []
        for entry, font_var in zip(self.guild_entries, self.guild_font_paths):
            if entry.get().strip():
                guild_font_paths.append(font_var.get().strip())

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
        except Exception as e:
            messagebox.showerror("エラー", f"プレビュー生成に失敗しました:\n{e}")

    def _export(self):
        if self._preview_image is None:
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
