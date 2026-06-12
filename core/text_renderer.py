"""
text_renderer.py
日本語テキストの描画モジュール。
縁取り・発光（グロー）エフェクトを含む。
"""

import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

DEFAULT_COMMON_FONT_PATH = "font/EN/Allura-Regular.ttf"
DEFAULT_LANGUAGE_FONT_PATHS = {
    "ja": "font/JP/KiwiMaru-Medium.ttf",
    "ko": "font/KR/YeonSung-Regular.ttf",
    "zh": "font/CN/NotoSerifTC-VariableFont_wght.ttf",
    "en": "font/EN/Pacifico-Regular.ttf",
    "ru": "font/RU/Pacifico-Regular.ttf",
}

LANGUAGE_FONT_CATEGORIES = {
    "ja": {
        "label": "日本語（🇯🇵）",
        "fallbacks": [
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/yugothb.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ],
    },
    "ru": {
        "label": "キリル / ロシア語（🇷🇺）",
        "fallbacks": [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
    },
    "en": {
        "label": "アルファベット / 英語（🇺🇸）",
        "fallbacks": [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
    },
    "zh": {
        "label": "中国語（🇨🇳）",
        "fallbacks": [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ],
    },
    "ko": {
        "label": "ハングル / 韓国語（🇰🇷）",
        "fallbacks": [
            "C:/Windows/Fonts/malgun.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ],
    },
}


def detect_language_category(text: str) -> str:
    """ギルド名の文字からフォントカテゴリを推定する。"""
    has_han = False
    for char in text:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            return "ko"
        if 0x0400 <= code <= 0x052F:
            return "ru"
        if 0x3040 <= code <= 0x30FF:
            return "ja"
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            has_han = True
    if has_han:
        return "zh"
    return "en"


def _existing_path(paths: list[str]) -> str:
    for path in paths:
        if path and Path(path).exists():
            return path
    return ""


def resolve_language_font_path(category: str, language_font_paths: dict | None, default_font_path: str) -> str:
    """個別指定が空の場合、カテゴリ別既定フォントを優先して解決する。"""
    if language_font_paths and language_font_paths.get(category):
        return language_font_paths[category]

    default_category_font = DEFAULT_LANGUAGE_FONT_PATHS.get(category, "")
    if default_category_font and Path(default_category_font).exists():
        return default_category_font

    category_info = LANGUAGE_FONT_CATEGORIES.get(category, LANGUAGE_FONT_CATEGORIES["en"])
    fallback = _existing_path(category_info["fallbacks"])
    if fallback:
        return fallback

    return default_font_path


def load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """
    フォントを読み込む。
    指定パスが存在しなければ fallback フォントを試みる。
    """
    fallback_paths = [
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/yugothb.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]

    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)

    for fb in fallback_paths:
        if os.path.exists(fb):
            print(f"[警告] フォントが見つかりません。フォールバック使用: {fb}")
            return ImageFont.truetype(fb, size)

    print("[警告] 日本語フォントが見つかりません。デフォルトフォントを使用します。")
    return ImageFont.load_default()


def hex_to_rgb(hex_color: str) -> tuple:
    """#rrggbb → (r, g, b)"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def draw_text_with_stroke(
    image: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str = "#ffffff",
    stroke_color: str = "#000000",
    stroke_width: int = 4,
    shadow_color: str = "#06101f",
    shadow_offset: tuple[int, int] = (4, 4),
    shadow_blur: int = 3,
) -> Image.Image:
    """縁取り付きテキストを描画する。全テキストに薄い青黒い影も付ける。"""
    if shadow_blur > 0 and text:
        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.text(
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            font=font,
            fill=hex_to_rgb(shadow_color) + (150,),
            stroke_width=stroke_width,
            stroke_fill=hex_to_rgb(shadow_color) + (150,),
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
        image = Image.alpha_composite(image.convert("RGBA"), shadow_layer)

    draw = ImageDraw.Draw(image)
    rgb_color = hex_to_rgb(color)
    rgb_stroke = hex_to_rgb(stroke_color)

    draw.text(
        (x, y),
        text,
        font=font,
        fill=rgb_color,
        stroke_width=stroke_width,
        stroke_fill=rgb_stroke,
    )
    return image

def draw_text_with_glow(
    image: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str = "#d8b15a",
    stroke_color: str = "#000000",
    stroke_width: int = 6,
    glow_color: str = "#FFD76A",
    glow_radius: int = 18,
    glow_strength: float = 1.2,
) -> Image.Image:
    """縁取り + 発光（グロー）エフェクト付きテキストを描画する。"""
    w, h = image.size

    glow_layer = Image.new("L", (w, h), 0)
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.text(
        (x, y),
        text,
        font=font,
        fill=255,
        stroke_width=stroke_width + 4,
        stroke_fill=255,
    )

    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    glow_rgb = hex_to_rgb(glow_color)
    glow_colored = Image.new("RGB", (w, h), glow_rgb)

    if glow_strength != 1.0:
        glow_blurred = glow_blurred.point(lambda v: max(0, min(int(v * glow_strength), 255)))

    glow_overlay = Image.new("RGB", (w, h), (0, 0, 0))
    glow_overlay.paste(glow_colored, (0, 0), glow_blurred)
    result = ImageChops.add(image.convert("RGB"), glow_overlay)

    if image.mode == "RGBA":
        result = result.convert("RGBA")
        result.putalpha(image.split()[3])

    result = draw_text_with_stroke(result, text, x, y, font, color, stroke_color, stroke_width)

    return result


def _font_for_guild(
    guild: str,
    guild_font_paths: list | None,
    language_font_paths: dict | None,
    index: int,
    default_font_path: str,
) -> str:
    if guild_font_paths and index < len(guild_font_paths) and guild_font_paths[index]:
        return guild_font_paths[index]
    category = detect_language_category(guild)
    return resolve_language_font_path(category, language_font_paths, default_font_path)


TEXT_ELEMENT_LABELS = {
    "date": "Date",
    "node_name": "Node Name",
    "subtitle": "Node War",
    "guilds": "Guild Names",
    "branding": "Branding Text",
}


def _text_bbox(
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    stroke_width: int = 0,
) -> tuple[int, int, int, int]:
    """指定座標に描画した文字の当たり判定用矩形を返す。"""
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((int(x), int(y)), text, font=font, stroke_width=int(stroke_width))
    padding = max(int(stroke_width), 4)
    return (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)


def _text_size(text: str, font: ImageFont.FreeTypeFont, stroke_width: int = 0) -> tuple[int, int]:
    """描画位置に依存しないテキストサイズを返す。"""
    bbox = _text_bbox(text, 0, 0, font, stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _centered_subtitle_x(node_text: str, subtitle_text: str, text_cfg: dict, font_path: str) -> int:
    """Node Warを拠点名の描画幅の中央へ自動配置するX座標を返す。"""
    node_cfg = text_cfg.get("node_name", {})
    subtitle_cfg = text_cfg.get("subtitle", {})
    node_font = load_font(font_path, node_cfg.get("font_size", 96))
    subtitle_font = load_font(font_path, subtitle_cfg.get("font_size", 75))
    node_width, _ = _text_size(node_text, node_font, node_cfg.get("stroke_width", 6))
    subtitle_width, _ = _text_size(subtitle_text, subtitle_font, subtitle_cfg.get("stroke_width", 4))
    node_x = node_cfg.get("x", 80)
    return int(node_x + (node_width - subtitle_width) / 2)


def build_text_element_bounds(
    date_str: str,
    node_name: str,
    guilds: list,
    template: dict,
    font_path: str,
    guild_font_paths: list | None = None,
    language_font_paths: dict | None = None,
) -> list[dict]:
    """プレビュー上で文字を選択するための1920x1080基準の矩形を作る。"""
    elements = []
    t = template.get("text", {})

    if date_str and "date" in t:
        cfg = t["date"]
        font = load_font(font_path, cfg.get("font_size", 64))
        elements.append(
            {
                "key": "date",
                "label": TEXT_ELEMENT_LABELS["date"],
                "bbox": _text_bbox(
                    date_str,
                    cfg.get("x", 80),
                    cfg.get("y", 60),
                    font,
                    cfg.get("stroke_width", 4),
                ),
            }
        )

    if node_name and "node_name" in t:
        cfg = t["node_name"]
        font = load_font(font_path, cfg.get("font_size", 96))
        elements.append(
            {
                "key": "node_name",
                "label": TEXT_ELEMENT_LABELS["node_name"],
                "bbox": _text_bbox(
                    node_name,
                    cfg.get("x", 80),
                    cfg.get("y", 140),
                    font,
                    cfg.get("stroke_width", 6),
                ),
            }
        )

    if "subtitle" in t:
        cfg = t["subtitle"]
        subtitle_text = cfg.get("text", "Node War")
        if subtitle_text:
            font = load_font(font_path, cfg.get("font_size", 75))
            subtitle_x = (
                _centered_subtitle_x(node_name, subtitle_text, t, font_path)
                if node_name
                else cfg.get("x", 100)
            )
            elements.append(
                {
                    "key": "subtitle",
                    "label": TEXT_ELEMENT_LABELS["subtitle"],
                    "bbox": _text_bbox(
                        subtitle_text,
                        subtitle_x,
                        cfg.get("y", 550),
                        font,
                        cfg.get("stroke_width", 4),
                    ),
                }
            )

    if guilds and "guilds" in t:
        cfg = t["guilds"]
        base_y = cfg.get("y", 900)
        font_size = cfg.get("font_size", 64)
        line_spacing = cfg.get("line_spacing", 12)
        line_height = font_size + line_spacing
        clean_guilds = [guild.strip() for guild in guilds[:5] if guild.strip()]
        guild_boxes = []
        for i, guild in enumerate(clean_guilds):
            guild_font = load_font(
                _font_for_guild(guild, guild_font_paths, language_font_paths, i, font_path),
                font_size,
            )
            guild_boxes.append(
                _text_bbox(
                    guild,
                    cfg.get("x", 80),
                    base_y + i * line_height,
                    guild_font,
                    cfg.get("stroke_width", 4),
                )
            )
        if guild_boxes:
            elements.append(
                {
                    "key": "guilds",
                    "label": TEXT_ELEMENT_LABELS["guilds"],
                    "bbox": (
                        min(box[0] for box in guild_boxes),
                        min(box[1] for box in guild_boxes),
                        max(box[2] for box in guild_boxes),
                        max(box[3] for box in guild_boxes),
                    ),
                }
            )

    branding_cfg = template.get("branding", {})
    if branding_cfg.get("enabled", True) and branding_cfg.get("type", "text") == "text":
        branding_text = branding_cfg.get("text", "Black Desert Mobile")
        if branding_text:
            brand_font_path = branding_cfg.get("font_path") or font_path
            brand_font = load_font(brand_font_path, branding_cfg.get("font_size", 46))
            elements.append(
                {
                    "key": "branding",
                    "label": TEXT_ELEMENT_LABELS["branding"],
                    "bbox": _text_bbox(
                        branding_text,
                        branding_cfg.get("x", 1320),
                        branding_cfg.get("y", 980),
                        brand_font,
                        branding_cfg.get("stroke_width", 3),
                    ),
                }
            )

    return elements


def render_all_text(
    image: Image.Image,
    date_str: str,
    node_name: str,
    guilds: list,
    template: dict,
    font_path: str,
    guild_font_paths: list | None = None,
    language_font_paths: dict | None = None,
) -> Image.Image:
    """
    テンプレートに従いすべてのテキストを一括描画する。

    日付と拠点名、固定のNode Warは同じフォントを使い、ギルド名は
    個別フォントまたは言語カテゴリ別フォントで描画する。
    """
    t = template.get("text", {})
    shadow_cfg = t.get("shadow", {})
    shadow_color = shadow_cfg.get("color", "#06101f")
    shadow_offset = tuple(shadow_cfg.get("offset", [4, 4]))
    shadow_blur = shadow_cfg.get("blur", 3)

    if date_str and "date" in t:
        cfg = t["date"]
        font = load_font(font_path, cfg.get("font_size", 64))
        image = draw_text_with_stroke(
            image,
            date_str,
            cfg.get("x", 80),
            cfg.get("y", 60),
            font,
            cfg.get("color", "#F5F5F5"),
            cfg.get("stroke_color", "#000000"),
            cfg.get("stroke_width", 4),
            shadow_color,
            shadow_offset,
            shadow_blur,
        )

    if node_name and "node_name" in t:
        cfg = t["node_name"]
        font = load_font(font_path, cfg.get("font_size", 96))
        if cfg.get("glow", False):
            image = draw_text_with_glow(
                image,
                node_name,
                cfg.get("x", 80),
                cfg.get("y", 140),
                font,
                cfg.get("color", "#E7B93E"),
                cfg.get("stroke_color", "#000000"),
                cfg.get("stroke_width", 6),
                cfg.get("glow_color", "#FFD76A"),
                cfg.get("glow_radius", 18),
                cfg.get("glow_strength", 1.2),
            )
        else:
            image = draw_text_with_stroke(
                image,
                node_name,
                cfg.get("x", 80),
                cfg.get("y", 140),
                font,
                cfg.get("color", "#E7B93E"),
                cfg.get("stroke_color", "#000000"),
                cfg.get("stroke_width", 6),
                shadow_color,
                shadow_offset,
                shadow_blur,
            )

    if "subtitle" in t:
        cfg = t["subtitle"]
        subtitle_text = cfg.get("text", "Node War")
        if subtitle_text:
            font = load_font(font_path, cfg.get("font_size", 75))
            subtitle_x = (
                _centered_subtitle_x(node_name, subtitle_text, t, font_path)
                if node_name
                else cfg.get("x", 100)
            )
            if cfg.get("glow", True):
                image = draw_text_with_glow(
                    image,
                    subtitle_text,
                    subtitle_x,
                    cfg.get("y", 550),
                    font,
                    cfg.get("color", "#E7B93E"),
                    cfg.get("stroke_color", "#000000"),
                    cfg.get("stroke_width", 4),
                    cfg.get("glow_color", "#FFD76A"),
                    cfg.get("glow_radius", 12),
                    cfg.get("glow_strength", 0.8),
                )
            else:
                image = draw_text_with_stroke(
                    image,
                    subtitle_text,
                    subtitle_x,
                    cfg.get("y", 550),
                    font,
                    cfg.get("color", "#E7B93E"),
                    cfg.get("stroke_color", "#000000"),
                    cfg.get("stroke_width", 4),
                    shadow_color,
                    shadow_offset,
                    shadow_blur,
                )

    if guilds and "guilds" in t:
        cfg = t["guilds"]
        base_y = cfg.get("y", 900)
        font_size = cfg.get("font_size", 64)
        line_spacing = cfg.get("line_spacing", 12)
        line_height = font_size + line_spacing
        clean_guilds = [guild.strip() for guild in guilds[:5] if guild.strip()]
        for i, guild in enumerate(clean_guilds):
            guild_font = load_font(
                _font_for_guild(guild, guild_font_paths, language_font_paths, i, font_path),
                font_size,
            )
            image = draw_text_with_stroke(
                image,
                guild,
                cfg.get("x", 80),
                base_y + i * line_height,
                guild_font,
                cfg.get("color", "#F4F4F4"),
                cfg.get("stroke_color", "#000000"),
                cfg.get("stroke_width", 4),
                shadow_color,
                shadow_offset,
                shadow_blur,
            )

    branding_cfg = template.get("branding", {})
    if branding_cfg.get("enabled", True) and branding_cfg.get("type", "text") == "text":
        branding_text = branding_cfg.get("text", "Black Desert Mobile")
        if branding_text:
            brand_font_path = branding_cfg.get("font_path") or font_path
            brand_font = load_font(brand_font_path, branding_cfg.get("font_size", 46))
            image = draw_text_with_stroke(
                image,
                branding_text,
                branding_cfg.get("x", 1320),
                branding_cfg.get("y", 980),
                brand_font,
                branding_cfg.get("color", "#F4F4F4"),
                branding_cfg.get("stroke_color", "#000000"),
                branding_cfg.get("stroke_width", 3),
                shadow_color,
                shadow_offset,
                shadow_blur,
            )

    return image
