"""
composer.py
画像合成エンジン。
レイヤーを順番に合成してサムネイルを生成する。
"""

import os

from PIL import Image

from core.text_renderer import render_all_text


# ──────────────────────────────────────────
#  ユーティリティ
# ──────────────────────────────────────────


def load_image_rgba(path: str) -> Image.Image | None:
    """画像をRGBAで読み込む。存在しなければNoneを返す。"""
    if not path or not os.path.exists(path):
        return None
    img = Image.open(path).convert("RGBA")
    return img


def resize_fit(img: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """キャンバスサイズに合わせてリサイズ（アスペクト比維持・クロップなし）。"""
    img_ratio = img.width / img.height
    canvas_ratio = canvas_w / canvas_h

    if img_ratio > canvas_ratio:
        new_w = canvas_w
        new_h = int(canvas_w / img_ratio)
    else:
        new_h = canvas_h
        new_w = int(canvas_h * img_ratio)

    return img.resize((new_w, new_h), Image.LANCZOS)


def resize_cover(img: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """キャンバス全体を覆うようにリサイズ（中央クロップ）。"""
    img_ratio = img.width / img.height
    canvas_ratio = canvas_w / canvas_h

    if img_ratio > canvas_ratio:
        new_h = canvas_h
        new_w = int(canvas_h * img_ratio)
    else:
        new_w = canvas_w
        new_h = int(canvas_w / img_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - canvas_w) // 2
    top = (new_h - canvas_h) // 2
    return img.crop((left, top, left + canvas_w, top + canvas_h))


def set_opacity(img: Image.Image, opacity: float) -> Image.Image:
    """RGBAイメージ全体の透明度を変更する（0.0〜1.0）。"""
    opacity = max(0.0, min(float(opacity), 1.0))
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * opacity))
    img.putalpha(a)
    return img


# ──────────────────────────────────────────
#  レイヤー合成
# ──────────────────────────────────────────


def add_dark_overlay(canvas: Image.Image, opacity: float = 0.3) -> Image.Image:
    """
    Layer 2: 暗色オーバーレイ。
    背景が明るすぎるときにキャラ・文字を映えさせる。
    """
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, int(255 * opacity)))
    canvas = Image.alpha_composite(canvas, overlay)
    return canvas


def place_effect(
    canvas: Image.Image,
    effect_path: str,
    opacity: float = 0.85,
    x: int = 0,
    y: int = 0,
    scale: float = 1.0,
) -> Image.Image:
    """
    Layer 3: 後方エフェクト画像を合成する。

    effect_pathで指定された透過PNGなどをキャンバス基準でcover配置し、
    UIから指定されたX/Y座標・拡大率・透明度で微調整する。
    """
    effect = load_image_rgba(effect_path)
    if effect is None:
        return canvas

    cw, ch = canvas.size
    effect = resize_cover(effect, cw, ch)

    effect_scale = max(float(scale), 0.01)
    if effect_scale != 1.0:
        new_size = (max(int(effect.width * effect_scale), 1), max(int(effect.height * effect_scale), 1))
        effect = effect.resize(new_size, Image.LANCZOS)

    effect = set_opacity(effect, opacity)

    tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    base_x = (cw - effect.width) // 2
    base_y = (ch - effect.height) // 2
    tmp.paste(effect, (base_x + int(x), base_y + int(y)), effect)

    canvas = Image.alpha_composite(canvas, tmp)
    return canvas


def place_character(
    canvas: Image.Image,
    char_path: str,
    position: str = "right",
    scale: float = 1.0,
    offset_x: int = 0,
    offset_y: int = 0,
) -> Image.Image:
    """
    Layer 4: キャラクター画像を配置する。
    元素材をそのまま使い、顔・体型・衣装は変更しない。

    position: "left" | "right" | "center"
    scale   : 拡縮倍率（1.0 = キャンバス縦幅に合わせる）
    """
    char = load_image_rgba(char_path)
    if char is None:
        return canvas

    cw, ch = canvas.size

    target_h = max(int(ch * float(scale)), 1)
    ratio = target_h / char.height
    target_w = max(int(char.width * ratio), 1)
    char = char.resize((target_w, target_h), Image.LANCZOS)

    if position == "right":
        x = cw - target_w - 80 + int(offset_x)
    elif position == "left":
        x = 80 + int(offset_x)
    else:
        x = (cw - target_w) // 2 + int(offset_x)

    y = ch - target_h + int(offset_y)

    tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    tmp.paste(char, (x, y), char)
    canvas = Image.alpha_composite(canvas, tmp)
    return canvas


# ──────────────────────────────────────────
#  メイン合成関数
# ──────────────────────────────────────────


def compose_thumbnail(
    bg_path: str,
    char_path: str,
    effect_path: str,
    date_str: str,
    node_name: str,
    guilds: list,
    template: dict,
    font_path: str,
    guild_font_paths: list | None = None,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
) -> Image.Image:
    """
    全レイヤーを合成してサムネイルを生成する。

    レイヤー順:
      1. 背景画像
      2. 暗色補正
      3. 後方エフェクト
      4. キャラクター画像
      5. 前景エフェクト（将来追加）
      6. 日付
      7. 拠点名
      8. ギルド名

    Returns:
        合成済み PIL Image（RGBモード, 1920x1080）
    """
    bg = load_image_rgba(bg_path)
    if bg:
        canvas = resize_cover(bg, canvas_w, canvas_h)
    else:
        canvas = _make_default_bg(canvas_w, canvas_h)

    overlay_opacity = template.get("background", {}).get("overlay_opacity", 0.3)
    canvas = add_dark_overlay(canvas, overlay_opacity)

    if effect_path:
        effect_cfg = template.get("back_effect", template.get("effect", {}))
        canvas = place_effect(
            canvas,
            effect_path,
            opacity=effect_cfg.get("opacity", 0.85),
            x=effect_cfg.get("x", 0),
            y=effect_cfg.get("y", 0),
            scale=effect_cfg.get("scale", 1.0),
        )

    if char_path:
        char_cfg = template.get("character", {})
        canvas = place_character(
            canvas,
            char_path,
            position=char_cfg.get("position", "right"),
            scale=char_cfg.get("scale", 1.0),
            offset_x=char_cfg.get("offset_x", 0),
            offset_y=char_cfg.get("offset_y", 0),
        )

    canvas = render_all_text(
        canvas,
        date_str,
        node_name,
        guilds,
        template,
        font_path,
        guild_font_paths=guild_font_paths,
    )

    return canvas.convert("RGB")


def _make_default_bg(w: int, h: int) -> Image.Image:
    """背景素材がない場合のフォールバック用グラデーション背景。"""
    image = Image.new("RGBA", (w, h))
    pixels = image.load()
    for y in range(h):
        ratio = y / h
        r = int(10 + 20 * ratio)
        g = int(5 + 10 * ratio)
        b = int(30 + 40 * ratio)
        for x in range(w):
            pixels[x, y] = (r, g, b, 255)
    return image
