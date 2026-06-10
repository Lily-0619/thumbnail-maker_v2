"""
template.py
テンプレートJSONの読み書き管理モジュール。
"""

import json
from pathlib import Path


TEMPLATES_DIR = Path("templates")


def load_template(template_name: str) -> dict:
    """テンプレートJSONを読み込む。存在しなければデフォルト値を返す。"""
    path = TEMPLATES_DIR / f"{template_name}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    print(f"[警告] テンプレートが見つかりません: {path}")
    return get_default_template()


def save_template(template_name: str, data: dict) -> None:
    """テンプレートをJSONに保存する。"""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMPLATES_DIR / f"{template_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[保存] テンプレート保存完了: {path}")


def list_templates() -> list:
    """利用可能なテンプレート名の一覧を返す。"""
    if not TEMPLATES_DIR.exists():
        return []
    return [p.stem for p in TEMPLATES_DIR.glob("*.json")]


def get_default_template() -> dict:
    """デフォルトテンプレートをdictで返す。"""
    return {
        "template_name": "default",
        "font_path": "font/EN/Allura-Regular.ttf",
        "guild_font_paths": [],
        "canvas": {"width": 1920, "height": 1080},
        "text": {
            "shadow": {"color": "#06101F", "offset": [4, 4], "blur": 3},
            "date": {
                "x": 100,
                "y": 60,
                "font_size": 70,
                "color": "#F5F5F5",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "glow": False,
            },
            "node_name": {
                "x": 100,
                "y": 300,
                "font_size": 170,
                "color": "#E7B93E",
                "stroke_color": "#000000",
                "stroke_width": 6,
                "glow": True,
                "glow_color": "#FFD76A",
                "glow_radius": 18,
                "glow_strength": 1.2,
            },
            "subtitle": {
                "text": "Node War",
                "x": 100,
                "y": 550,
                "font_size": 75,
                "color": "#E7B93E",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "glow": True,
                "glow_color": "#FFD76A",
                "glow_radius": 12,
                "glow_strength": 0.8,
            },
            "guilds": {
                "x": 100,
                "y": 600,
                "font_size": 75,
                "line_spacing": 10,
                "color": "#F4F4F4",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "glow": False,
            },
        },
        "character": {
            "position": "right",
            "scale": 1.0,
            "offset_x": 0,
            "offset_y": 0,
        },
        "back_effect": {
            "type": "ai_generated_with_background",
            "opacity": 0.85,
        },
        "foreground_effect": {"enabled": False},
        "branding": {
            "enabled": True,
            "type": "text",
            "text": "Black Desert Mobile",
            "font_path": "",
            "x": 1320,
            "y": 980,
            "font_size": 46,
            "color": "#F4F4F4",
            "stroke_color": "#000000",
            "stroke_width": 3,
            "logo_path": "",
        },
        "language_fonts": {
            "ja": "font/JP/KiwiMaru-Medium.ttf",
            "ru": "font/RU/Pacifico-Regular.ttf",
            "en": "font/EN/Pacifico-Regular.ttf",
            "zh": "font/CN/NotoSerifTC-VariableFont_wght.ttf",
            "ko": "font/KR/YeonSung-Regular.ttf",
        },
        "background": {
            "type": "dark_castle",
            "overlay_opacity": 0.3,
            "random_dir": "assets/backgrounds",
        },
    }
