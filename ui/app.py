"""
app.py
customtkinter main UI window.
"""

import copy
import json
import re
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from core.composer import compose_thumbnail
from core.template import list_templates, load_template, save_template
from core.text_renderer import (
    DEFAULT_COMMON_FONT_PATH,
    DEFAULT_LANGUAGE_FONT_PATHS,
    LANGUAGE_FONT_CATEGORIES,
    TEXT_ELEMENT_LABELS,
    build_text_element_bounds,
)
from ui.preview import PreviewPanel


# ── Theme ──
ctk.set_appearance_mode("dark")
_THEME_PATH = Path("config/pink_theme.json")
if _THEME_PATH.exists():
    ctk.set_default_color_theme(str(_THEME_PATH))
else:
    ctk.set_default_color_theme("blue")


WEEKDAY_LABELS = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}
WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_BY_INDEX = WEEKDAY_ORDER
NODE_OPTIONS_PATH = Path("data/node_options.json")
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
LANGUAGE_FONT_DIRS = {
    "ja": [Path("font/JP"), Path("font/CN")],
    "ko": [Path("font/KR")],
    "zh": [Path("font/CN")],
    "en": [Path("font/EN"), Path("font/RU")],
    "ru": [Path("font/RU")],
}


class CharacterPickerDialog(ctk.CTkToplevel):
    """Grid thumbnail picker for character images."""

    CHAR_DIR = Path("material/character")
    THUMB_SIZE = (96, 96)
    COLS = 4

    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.title("Pick Character")
        self.geometry("520x560")
        self.resizable(True, True)
        self.grab_set()
        self._on_select = on_select
        self._thumb_refs = []

        self._build()

    def _build(self):
        images = sorted(self.CHAR_DIR.glob("*.png")) if self.CHAR_DIR.exists() else []

        if not images:
            ctk.CTkLabel(self, text="No images found in material/character/").pack(pady=20)
            return

        scroll = ctk.CTkScrollableFrame(self, label_text="Character Images")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        for idx, path in enumerate(images):
            row_idx = idx // self.COLS
            col_idx = idx % self.COLS
            self._add_thumb(scroll, path, row_idx, col_idx)

    def _add_thumb(self, parent, path, row_idx, col_idx):
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail(self.THUMB_SIZE, Image.LANCZOS)
            thumb = Image.new("RGBA", self.THUMB_SIZE, (0, 0, 0, 0))
            offset = (
                (self.THUMB_SIZE[0] - img.width) // 2,
                (self.THUMB_SIZE[1] - img.height) // 2,
            )
            thumb.paste(img, offset)

            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=self.THUMB_SIZE)
            self._thumb_refs.append(ctk_img)

            name = path.stem.replace("m_img_", "").replace("_", " ")
            btn = ctk.CTkButton(
                parent,
                image=ctk_img,
                text=name[:14],
                compound="top",
                width=116,
                height=128,
                command=lambda p=path: self._pick(p),
            )
            btn.grid(row=row_idx, column=col_idx, padx=4, pady=4)
        except Exception:
            pass

    def _pick(self, path):
        self._on_select(str(path))
        self.destroy()


class ThumbnailApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BDM Thumbnail Generator v0.2.5")
        self.geometry("1500x900")
        self.resizable(True, True)

        self.bg_path = ctk.StringVar()
        self.char_path = ctk.StringVar()
        self.effect_path = ctk.StringVar()
        self.font_path = ctk.StringVar(value=DEFAULT_COMMON_FONT_PATH)
        self.branding_font_path = ctk.StringVar(value="")
        self.branding_text = ctk.StringVar(value="Black Desert Mobile")
        self.current_template_name = "node_war_default"
        self.current_template = load_template(self.current_template_name)
        self.node_options = self._load_node_options()
        self._preview_image = None
        self._preview_text_elements = []
        self.selected_text_key = None
        self.selected_text_name = ctk.StringVar(value="Selected: none")
        self.options_visible = False

        self._build_layout()
        self._bind_auto_output_name()
        self._update_output_name()

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self, width=500, label_text="Settings")
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
        self.preview.set_callbacks(
            on_select=self._select_text_element,
            on_drag=self._drag_text_element,
            on_release=self._refresh_preview_after_text_edit,
        )
        ctk.CTkLabel(right, textvariable=self.selected_text_name, font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, sticky="n", pady=(0, 4)
        )
        ctk.CTkLabel(
            right,
            text="Click text in preview to select → Arrow keys to move / Shift+Arrow for 10px / Ctrl+Up/Down to resize / Drag to move",
            text_color="gray",
            wraplength=780,
            justify="center",
        ).grid(row=2, column=0, sticky="n", pady=(0, 10))
        self.bind("<KeyPress>", self._on_key_press)

    def _build_form(self, parent):
        pad = {"padx": 10, "pady": 4}

        ctk.CTkLabel(parent, text="📅 Date", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.date_entry = ctk.CTkEntry(parent, placeholder_text="2026.06.04")
        self.date_entry.insert(0, date.today().strftime("%Y.%m.%d"))
        self.date_entry.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🗓️ Day", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        current_weekday = WEEKDAY_BY_INDEX[date.today().weekday()]
        self.weekday_menu = ctk.CTkOptionMenu(
            parent,
            values=[WEEKDAY_LABELS[key] for key in WEEKDAY_ORDER],
            command=self._on_weekday_changed,
        )
        self.weekday_menu.set(WEEKDAY_LABELS[current_weekday])
        self.weekday_menu.pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🏰 Node", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.node_entry = ctk.CTkEntry(parent, placeholder_text="Node name")
        self.node_menu = ctk.CTkOptionMenu(parent, values=["N/A"], command=self._on_node_selected)
        self.node_menu.pack(fill="x", **pad)
        self.node_entry.pack(fill="x", **pad)
        self._set_node_menu_values(current_weekday)

        ctk.CTkLabel(parent, text="💾 Output Filename", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.output_name = ctk.CTkEntry(parent, placeholder_text="20260609_node")
        self.output_name.pack(fill="x", **pad)

        ctk.CTkLabel(
            parent,
            text="⚔️ Guild Names (up to 5)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", **pad)
        self.guild_entries = []
        self.guild_font_paths = []
        for i in range(5):
            row = ctk.CTkFrame(parent)
            row.pack(fill="x", **pad)
            entry = ctk.CTkEntry(row, placeholder_text=f"Guild {i + 1}")
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            font_var = ctk.StringVar(value="")
            ctk.CTkEntry(
                row,
                textvariable=font_var,
                placeholder_text="Font (optional)",
                width=150,
            ).pack(side="left", padx=(0, 6))
            ctk.CTkButton(
                row,
                text="Select",
                width=60,
                command=lambda v=font_var: self._select_font_var(v),
            ).pack(side="left")
            self.guild_entries.append(entry)
            self.guild_font_paths.append(font_var)

        ctk.CTkLabel(parent, text="🖼️ Background", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.bg_path, placeholder_text="Leave blank for random from folder").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="Select Background", command=self._select_bg).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="🧙 Character", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(parent, textvariable=self.char_path, placeholder_text="None selected").pack(fill="x", **pad)
        ctk.CTkButton(parent, text="Pick Character", command=self._select_char).pack(fill="x", **pad)

        ctk.CTkButton(
            parent,
            text="⚙️ Options",
            height=38,
            command=self._toggle_options,
        ).pack(fill="x", padx=10, pady=(12, 4))

        self.options_frame = ctk.CTkFrame(parent)
        self._build_options(self.options_frame)

        ctk.CTkLabel(parent, text="📋 Template", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        templates = list_templates() or ["node_war_default"]
        self.template_menu = ctk.CTkOptionMenu(parent, values=templates, command=self._load_template)
        self.template_menu.set(self.current_template_name if self.current_template_name in templates else templates[0])
        self.template_menu.pack(fill="x", **pad)
        ctk.CTkButton(parent, text="💾 Save as Template", command=self._save_current_template).pack(fill="x", **pad)

        ctk.CTkButton(
            parent,
            text="👁️  Preview",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._preview,
        ).pack(fill="x", padx=10, pady=(16, 4))

        ctk.CTkButton(
            parent,
            text="📤  Export PNG",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#7b1fa2",
            hover_color="#6a1590",
            command=self._export,
        ).pack(fill="x", padx=10, pady=4)

    def _build_options(self, parent):
        pad = {"padx": 10, "pady": 4}

        ctk.CTkLabel(parent, text="🌐 Guild Font by Language", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkLabel(
            parent,
            text="If per-guild font is empty, language is auto-detected from the guild name.",
            text_color="gray",
            wraplength=430,
            justify="left",
        ).pack(anchor="w", **pad)
        self.language_font_paths = {}
        self.language_font_menus = {}
        for key in ["ja", "ko", "zh", "en", "ru"]:
            row = ctk.CTkFrame(parent)
            row.pack(fill="x", **pad)
            ctk.CTkLabel(row, text=LANGUAGE_FONT_CATEGORIES[key]["label"], width=155, anchor="w").pack(
                side="left", padx=(0, 6)
            )
            font_values = self._font_options_for_language(key)
            font_var = ctk.StringVar(value=DEFAULT_LANGUAGE_FONT_PATHS[key])
            menu = ctk.CTkOptionMenu(row, values=font_values, variable=font_var)
            menu.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self.language_font_paths[key] = font_var
            self.language_font_menus[key] = menu

        ctk.CTkLabel(parent, text="🔤 Common Font / Branding", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        ctk.CTkEntry(
            parent,
            textvariable=self.font_path,
            placeholder_text="Font for date, node name, Node War",
        ).pack(fill="x", **pad)
        ctk.CTkButton(parent, text="Select Common Font", command=self._select_font).pack(fill="x", **pad)
        ctk.CTkEntry(parent, textvariable=self.branding_text, placeholder_text="Branding text").pack(fill="x", **pad)
        ctk.CTkEntry(
            parent,
            textvariable=self.branding_font_path,
            placeholder_text="Branding font (blank = common font)",
        ).pack(fill="x", **pad)
        ctk.CTkButton(
            parent,
            text="Select Branding Font",
            command=lambda: self._select_font_var(self.branding_font_path),
        ).pack(fill="x", **pad)

        ctk.CTkLabel(parent, text="📐 Character Scale", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.char_scale = self._build_number_row(parent, "Scale", "1.0")

        ctk.CTkLabel(parent, text="📝 Text Position & Size", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", **pad)
        self.date_x = self._build_number_row(parent, "Date X", "100")
        self.date_y = self._build_number_row(parent, "Date Y", "60")
        self.date_size = self._build_number_row(parent, "Date Size", "70")
        self.node_x = self._build_number_row(parent, "Node X", "100")
        self.node_y = self._build_number_row(parent, "Node Y", "300")
        self.node_size = self._build_number_row(parent, "Node Size", "170")
        self.subtitle_x = self._build_number_row(parent, "Node War X", "100")
        self.subtitle_y = self._build_number_row(parent, "Node War Y", "550")
        self.subtitle_size = self._build_number_row(parent, "Node War Size", "75")
        self.guild_x = self._build_number_row(parent, "Guild X", "100")
        self.guild_y = self._build_number_row(parent, "Guild Y", "600")
        self.guild_size = self._build_number_row(parent, "Guild Size", "75")
        self.guild_line_spacing = self._build_number_row(parent, "Guild Spacing", "10")
        self.branding_x = self._build_number_row(parent, "Branding X", "1320")
        self.branding_y = self._build_number_row(parent, "Branding Y", "980")
        self.branding_size = self._build_number_row(parent, "Branding Size", "46")

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

    def _relative_project_path(self, value: str | Path) -> str:
        try:
            path = Path(value).resolve()
            return path.relative_to(Path.cwd().resolve()).as_posix()
        except (OSError, ValueError):
            return str(value)

    def _font_options_for_language(self, key: str) -> list[str]:
        values = []
        seen = set()
        for font_dir in LANGUAGE_FONT_DIRS[key]:
            if not font_dir.exists():
                continue
            for path in sorted(font_dir.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file() or path.suffix.lower() not in FONT_EXTENSIONS:
                    continue
                rel_path = path.as_posix()
                if rel_path not in seen:
                    values.append(rel_path)
                    seen.add(rel_path)

        default_path = DEFAULT_LANGUAGE_FONT_PATHS[key]
        if default_path not in seen:
            values.insert(0, default_path)
        return values or [default_path]

    def _set_font_menu_value(self, key: str, value: str):
        value = value or DEFAULT_LANGUAGE_FONT_PATHS[key]
        menu = self.language_font_menus[key]
        current_values = list(menu.cget("values"))
        if value not in current_values:
            current_values.append(value)
            menu.configure(values=current_values)
        self.language_font_paths[key].set(value)

    # ──────────────────────────────────────────
    #  File selection
    # ──────────────────────────────────────────

    def _select_bg(self):
        p = filedialog.askopenfilename(
            title="Select Background Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if p:
            self.bg_path.set(p)

    def _select_char(self):
        CharacterPickerDialog(
            self,
            on_select=lambda p: self.char_path.set(self._relative_project_path(p)),
        )

    def _select_font(self):
        self._select_font_var(self.font_path)

    def _select_font_var(self, font_var):
        p = filedialog.askopenfilename(
            title="Select Font File",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
        )
        if p:
            font_var.set(p)

    # ──────────────────────────────────────────
    #  Node options / output name
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
        values = self.node_options.get(weekday_key) or ["N/A"]
        self.node_menu.configure(values=values)
        self.node_menu.set(values[0])
        if values[0] != "N/A":
            self.node_entry.delete(0, "end")
            self.node_entry.insert(0, values[0])

    def _on_weekday_changed(self, label: str):
        self._set_node_menu_values(self._weekday_key_from_label(label))
        self._update_output_name()

    def _on_node_selected(self, node_name: str):
        if node_name == "N/A":
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
    #  Template
    # ──────────────────────────────────────────

    def _load_template(self, name: str):
        self.current_template_name = name
        self.current_template = load_template(name)
        self._apply_template_to_controls()
        print(f"[Template] loaded: {name}")

    def _path_for_template(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        try:
            path = Path(value)
            if path.exists():
                return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except (OSError, ValueError):
            pass
        return value

    def _save_current_template(self):
        params = self._collect_params()
        template = params["template"]
        template["template_name"] = self.current_template_name
        template["font_path"] = self._path_for_template(params["font_path"])
        template["guild_font_paths"] = [
            self._path_for_template(font_var.get()) for font_var in self.guild_font_paths
        ]
        template["language_fonts"] = {
            key: self._path_for_template(font_var.get())
            for key, font_var in self.language_font_paths.items()
        }
        branding = template.setdefault("branding", {})
        branding["font_path"] = self._path_for_template(branding.get("font_path", ""))

        save_template(self.current_template_name, template)
        self.current_template = copy.deepcopy(template)
        messagebox.showinfo("Template Saved", f"Saved to: {self.current_template_name}")
        print(f"[Template] saved: {self.current_template_name}")

    def _apply_template_to_controls(self):
        self.font_path.set(self.current_template.get("font_path", DEFAULT_COMMON_FONT_PATH))
        self._set_entry(self.char_scale, self.current_template.get("character", {}).get("scale", 1.0))

        text_cfg = self.current_template.get("text", {})
        self._set_entry(self.date_x, text_cfg.get("date", {}).get("x", 100))
        self._set_entry(self.date_y, text_cfg.get("date", {}).get("y", 60))
        self._set_entry(self.date_size, text_cfg.get("date", {}).get("font_size", 70))
        self._set_entry(self.node_x, text_cfg.get("node_name", {}).get("x", 100))
        self._set_entry(self.node_y, text_cfg.get("node_name", {}).get("y", 300))
        self._set_entry(self.node_size, text_cfg.get("node_name", {}).get("font_size", 170))
        self._set_entry(self.subtitle_x, text_cfg.get("subtitle", {}).get("x", 100))
        self._set_entry(self.subtitle_y, text_cfg.get("subtitle", {}).get("y", 550))
        self._set_entry(self.subtitle_size, text_cfg.get("subtitle", {}).get("font_size", 75))
        self._set_entry(self.guild_x, text_cfg.get("guilds", {}).get("x", 100))
        self._set_entry(self.guild_y, text_cfg.get("guilds", {}).get("y", 600))
        self._set_entry(self.guild_size, text_cfg.get("guilds", {}).get("font_size", 75))
        self._set_entry(self.guild_line_spacing, text_cfg.get("guilds", {}).get("line_spacing", 10))

        branding_cfg = self.current_template.get("branding", {})
        self.branding_text.set(branding_cfg.get("text", "Black Desert Mobile"))
        self.branding_font_path.set(branding_cfg.get("font_path", ""))
        self._set_entry(self.branding_x, branding_cfg.get("x", 1320))
        self._set_entry(self.branding_y, branding_cfg.get("y", 980))
        self._set_entry(self.branding_size, branding_cfg.get("font_size", 46))

        language_fonts = self.current_template.get("language_fonts", {})
        for key in self.language_font_paths:
            self._set_font_menu_value(key, language_fonts.get(key, DEFAULT_LANGUAGE_FONT_PATHS[key]))

        guild_font_paths = self.current_template.get("guild_font_paths", [])
        for index, font_var in enumerate(self.guild_font_paths):
            font_var.set(guild_font_paths[index] if index < len(guild_font_paths) else "")

    # ──────────────────────────────────────────
    #  Params
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
        self.selected_text_key = key
        if key:
            self.selected_text_name.set(f"Selected: {TEXT_ELEMENT_LABELS.get(key, key)}")
        else:
            self.selected_text_name.set("Selected: none")
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
        self._select_text_element(key)
        self._move_text_element(key, dx, dy, refresh=False)
        for element in self._preview_text_elements:
            if element["key"] == key:
                x1, y1, x2, y2 = element["bbox"]
                element["bbox"] = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
                break
        self.preview.set_text_elements(self._preview_text_elements)
        self.preview.set_selected(key)

    def _on_key_press(self, event):
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

        self._move_text_element(self.selected_text_key, dx, dy, refresh=False)
        for element in self._preview_text_elements:
            if element["key"] == self.selected_text_key:
                x1, y1, x2, y2 = element["bbox"]
                element["bbox"] = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
                break
        self.preview.set_text_elements(self._preview_text_elements)
        self.preview.set_selected(self.selected_text_key)

        if hasattr(self, "_key_debounce_id"):
            self.after_cancel(self._key_debounce_id)
        self._key_debounce_id = self.after(120, self._refresh_preview_after_text_edit)

        return "break"

    def _refresh_preview_after_text_edit(self):
        self._preview()
        self.preview.set_selected(self.selected_text_key)

    def _collect_params(self) -> dict:
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
                "y": self._int_value(self.subtitle_y, 550),
                "font_size": self._int_value(self.subtitle_size, 75),
            }
        )
        text_cfg.setdefault("guilds", {}).update(
            {
                "x": self._int_value(self.guild_x, 100),
                "y": self._int_value(self.guild_y, 600),
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
        language_font_paths = {
            key: var.get().strip()
            for key, var in self.language_font_paths.items()
            if var.get().strip()
        }
        template["font_path"] = self.font_path.get().strip() or DEFAULT_COMMON_FONT_PATH
        template["guild_font_paths"] = guild_font_paths
        template["language_fonts"] = language_font_paths

        return {
            "bg_path": self.bg_path.get(),
            "char_path": self.char_path.get(),
            "effect_path": self.effect_path.get(),
            "date_str": self.date_entry.get(),
            "node_name": self.node_entry.get(),
            "guilds": guilds,
            "template": template,
            "font_path": self.font_path.get().strip() or DEFAULT_COMMON_FONT_PATH,
            "guild_font_paths": guild_font_paths,
            "language_font_paths": language_font_paths,
        }

    # ──────────────────────────────────────────
    #  Preview / Export
    # ──────────────────────────────────────────

    def _preview(self):
        params = self._collect_params()
        try:
            img = compose_thumbnail(**params)
            self._preview_image = img
            self.preview.show(img)
            elements = build_text_element_bounds(
                params["date_str"],
                params["node_name"],
                params["guilds"],
                params["template"],
                params["font_path"],
                guild_font_paths=params["guild_font_paths"],
                language_font_paths=params["language_font_paths"],
            )
            self._preview_text_elements = elements
            self.preview.set_text_elements(elements)
            self.preview.set_selected(self.selected_text_key)
        except Exception as e:
            messagebox.showerror("Error", f"Preview failed:\n{e}")

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
        messagebox.showinfo("Exported", f"Saved:\n{out_path.resolve()}")
        print(f"[Export] {out_path.resolve()}")
