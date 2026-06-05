"""
text_renderer.py
日本語テキストの描画モジュール。
縁取り・発光（グロー）エフェクトを含む。
"""

import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


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
) -> Image.Image:
    """縁取り付きテキストを描画する。"""
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
    stroke_color: str = "#1a1208",
    stroke_width: int = 6,
    glow_color: str = "#ffaa00",
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


def _font_for_guild(guild_font_paths: list | None, index: int, default_font_path: str) -> str:
    if guild_font_paths and index < len(guild_font_paths) and guild_font_paths[index]:
        return guild_font_paths[index]
    return default_font_path


def render_all_text(
    image: Image.Image,
    date_str: str,
    node_name: str,
    guilds: list,
    template: dict,
    font_path: str,
    guild_font_paths: list | None = None,
) -> Image.Image:
    """
    テンプレートに従いすべてのテキストを一括描画する。

    日付と拠点名は同じフォントを使い、ギルド名はギルドごとに
    別フォントを指定できる。
    """
    t = template.get("text", {})

    if date_str and "date" in t:
        cfg = t["date"]
        font = load_font(font_path, cfg.get("font_size", 64))
        image = draw_text_with_stroke(
            image,
            date_str,
            cfg.get("x", 80),
            cfg.get("y", 60),
            font,
            cfg.get("color", "#ffffff"),
            cfg.get("stroke_color", "#000000"),
            cfg.get("stroke_width", 4),
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
                cfg.get("color", "#d8b15a"),
                cfg.get("stroke_color", "#1a1208"),
                cfg.get("stroke_width", 6),
            )
        else:
            image = draw_text_with_stroke(
                image,
                node_name,
                cfg.get("x", 80),
                cfg.get("y", 140),
                font,
                cfg.get("color", "#d8b15a"),
                cfg.get("stroke_color", "#1a1208"),
                cfg.get("stroke_width", 6),
            )

    if guilds and "guilds" in t:
        cfg = t["guilds"]
        base_y = cfg.get("y", 900)
        font_size = cfg.get("font_size", 64)
        line_spacing = cfg.get("line_spacing", 12)
        line_height = font_size + line_spacing
        clean_guilds = [guild.strip() for guild in guilds[:5] if guild.strip()]
        for i, guild in enumerate(clean_guilds):
            guild_font = load_font(_font_for_guild(guild_font_paths, i, font_path), font_size)
            image = draw_text_with_stroke(
                image,
                guild,
                cfg.get("x", 80),
                base_y + i * line_height,
                guild_font,
                cfg.get("color", "#ffffff"),
                cfg.get("stroke_color", "#000000"),
                cfg.get("stroke_width", 4),
            )

    return image
