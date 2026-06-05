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
        "canvas": {"width": 1920, "height": 1080},
        "text": {
            "date": {
                "x": 80,
                "y": 60,
                "font_size": 64,
                "color": "#ffffff",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "glow": False,
            },
            "node_name": {
                "x": 80,
                "y": 140,
                "font_size": 96,
                "color": "#d8b15a",
                "stroke_color": "#1a1208",
                "stroke_width": 6,
                "glow": True,
            },
            "guilds": {
                "x": 80,
                "y": 820,
                "font_size": 56,
                "line_spacing": 10,
                "color": "#ffffff",
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
            "type": "blue_purple_magic",
            "x": 0,
            "y": 0,
            "scale": 1.0,
            "opacity": 0.85,
        },
        "foreground_effect": {
            "enabled": False
        },
        "background": {
            "type": "dark_castle",
            "overlay_opacity": 0.3,
        },
    }
