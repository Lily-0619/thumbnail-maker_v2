"""
xyz_plot.py
X/Y/Z プロットの軸定義・値の展開・ラベル付きグリッド画像の合成。

A1111 の「X/Y/Z plot」スクリプト相当の考え方:
  - X 軸 = グリッドの列、Y 軸 = グリッドの行、Z 軸 = グリッドそのものを複数枚に分ける。
  - 各軸に「種類（Checkpoint / Steps / CFG / Seed / Prompt S/R …）」と「値リスト」を割り当てる。
  - すべての組み合わせ（X × Y × Z）について GenParams を複製・適用して 1 枚ずつ生成し、
    Z 値ごとに 1 枚のラベル付きグリッド画像にまとめる。

このモジュールは ComfyUI に依存しない（GenParams を加工して並べるだけ）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.model_tester.comfy_client import (
    NO_LORA,
    GenParams,
    LoraSpec,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────
#  軸の種類
# ──────────────────────────────────────────

# 軸種別の内部キー
AXIS_NONE = "none"
AXIS_CKPT = "ckpt"
AXIS_LORA = "lora"
AXIS_LORA_WEIGHT = "lora_weight"
AXIS_STEPS = "steps"
AXIS_CFG = "cfg"
AXIS_SAMPLER = "sampler"
AXIS_SCHEDULER = "scheduler"
AXIS_SEED = "seed"
AXIS_CLIP_SKIP = "clip_skip"
AXIS_WIDTH = "width"
AXIS_HEIGHT = "height"
AXIS_HIRES_DENOISE = "hires_denoise"
AXIS_HIRES_SCALE = "hires_scale"
AXIS_PROMPT_SR = "prompt_sr"

# UI に出す表示名 → 内部キー
AXIS_LABELS: dict[str, str] = {
    "（なし）": AXIS_NONE,
    "Checkpoint": AXIS_CKPT,
    "LoRA": AXIS_LORA,
    "LoRA強度": AXIS_LORA_WEIGHT,
    "Steps": AXIS_STEPS,
    "CFG Scale": AXIS_CFG,
    "Sampler": AXIS_SAMPLER,
    "Scheduler": AXIS_SCHEDULER,
    "Seed": AXIS_SEED,
    "Clip skip": AXIS_CLIP_SKIP,
    "幅 Width": AXIS_WIDTH,
    "高さ Height": AXIS_HEIGHT,
    "Hires denoise": AXIS_HIRES_DENOISE,
    "Hires 倍率": AXIS_HIRES_SCALE,
    "Prompt S/R（置換）": AXIS_PROMPT_SR,
}

# 値を「リストから選ぶ（チェックボックス）」タイプの軸。それ以外はテキスト入力。
LIST_AXES = {AXIS_CKPT, AXIS_LORA, AXIS_SAMPLER, AXIS_SCHEDULER}


class AxisError(ValueError):
    """軸の値が不正なときに投げる（ユーザー向けメッセージ付き）。"""


@dataclass
class Axis:
    """1 つの軸（種類 + 値リスト）。"""

    kind: str
    values: list  # 表示・適用に使う生の値（型は軸種別による）

    @property
    def active(self) -> bool:
        return self.kind != AXIS_NONE and bool(self.values)


def parse_values(kind: str, raw: str) -> list:
    """テキスト入力の軸（数値・Seed・Prompt S/R）をパースして値リストにする。

    - 数値系: カンマ区切り（例 "20, 28, 35"）
    - Seed:   カンマ区切りの整数（例 "1, 2, 3"）。"-1" はランダム。
    - Prompt S/R: 1 個目を検索語、2 個目以降を置換語とする（A1111 と同じ）。
                  例 "knight, mage, archer" → "knight" を "knight"/"mage"/"archer" に置換。
    """
    items = [s.strip() for s in raw.split(",") if s.strip()]
    if not items:
        raise AxisError("値が空です。カンマ区切りで入力してください（例: 20, 28, 35）。")

    if kind in (AXIS_STEPS, AXIS_CLIP_SKIP, AXIS_WIDTH, AXIS_HEIGHT):
        try:
            return [int(float(s)) for s in items]
        except ValueError:
            raise AxisError(f"整数をカンマ区切りで入力してください。現在: {raw}")
    if kind in (AXIS_CFG, AXIS_LORA_WEIGHT, AXIS_HIRES_DENOISE, AXIS_HIRES_SCALE):
        try:
            return [float(s) for s in items]
        except ValueError:
            raise AxisError(f"数値をカンマ区切りで入力してください。現在: {raw}")
    if kind == AXIS_SEED:
        try:
            return [int(s) for s in items]
        except ValueError:
            raise AxisError(f"整数の seed をカンマ区切りで入力してください。現在: {raw}")
    if kind == AXIS_PROMPT_SR:
        if len(items) < 2:
            raise AxisError("Prompt S/R は『検索語, 置換1, 置換2…』のように2個以上入力してください。")
        return items  # [search, *replacements]
    # その他は文字列そのまま
    return items


def value_label(kind: str, value) -> str:
    """グリッドのヘッダー表示用に、軸の値を短い文字列にする。"""
    if kind == AXIS_CKPT or kind == AXIS_LORA:
        if value == NO_LORA:
            return value
        stem = Path(str(value)).name
        for ext in (".safetensors", ".ckpt", ".pt", ".pth"):
            if stem.lower().endswith(ext):
                stem = stem[: -len(ext)]
                break
        return stem
    if kind == AXIS_SEED:
        return "random" if value == -1 else str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def apply_axis(base: GenParams, kind: str, value, *, sr_search: str | None = None) -> GenParams:
    """GenParams を複製し、ある軸の 1 値を適用した新しい GenParams を返す。"""
    p = base.copy()
    if kind == AXIS_NONE:
        return p
    if kind == AXIS_CKPT:
        p.ckpt_name = str(value)
    elif kind == AXIS_LORA:
        if value == NO_LORA:
            p.loras = []
        else:
            # 既存スタックの先頭強度を引き継いで LoRA だけ差し替える
            w_model = p.loras[0].strength_model if p.loras else 1.0
            w_clip = p.loras[0].strength_clip if p.loras else 1.0
            p.loras = [LoraSpec(str(value), w_model, w_clip)]
    elif kind == AXIS_LORA_WEIGHT:
        if p.loras:
            p.loras = [replace(l, strength_model=float(value), strength_clip=float(value)) for l in p.loras]
    elif kind == AXIS_STEPS:
        p.steps = int(value)
    elif kind == AXIS_CFG:
        p.cfg_scale = float(value)
    elif kind == AXIS_SAMPLER:
        p.sampler_name = str(value)
    elif kind == AXIS_SCHEDULER:
        p.scheduler = str(value)
    elif kind == AXIS_SEED:
        p.seed = None if int(value) == -1 else int(value)
    elif kind == AXIS_CLIP_SKIP:
        p.clip_skip = int(value)
    elif kind == AXIS_WIDTH:
        p.width = int(value)
    elif kind == AXIS_HEIGHT:
        p.height = int(value)
    elif kind == AXIS_HIRES_DENOISE:
        p.hires_denoise = float(value)
    elif kind == AXIS_HIRES_SCALE:
        p.hires_scale = float(value)
    elif kind == AXIS_PROMPT_SR:
        if sr_search:
            p.prompt = p.prompt.replace(sr_search, str(value))
            p.negative = p.negative.replace(sr_search, str(value))
    return p


@dataclass
class Job:
    """生成 1 枚分のジョブ（グリッド上の位置 + パラメータ）。"""

    z_index: int
    y_index: int
    x_index: int
    params: GenParams


def build_jobs(base: GenParams, x: Axis, y: Axis, z: Axis) -> list[Job]:
    """3 軸の組み合わせを展開して、生成すべき全ジョブを作る。

    軸が「（なし）」の場合は 1 要素（適用なし）として扱う。
    """
    def axis_values(axis: Axis) -> list:
        return list(axis.values) if axis.active else [None]

    def sr_search(axis: Axis) -> str | None:
        return axis.values[0] if (axis.kind == AXIS_PROMPT_SR and axis.values) else None

    def sr_values(axis: Axis) -> list:
        # Prompt S/R は 1 個目が検索語、2 個目以降が実際の値
        if axis.kind == AXIS_PROMPT_SR and axis.active:
            return axis.values[1:]
        return axis_values(axis)

    x_vals, y_vals, z_vals = sr_values(x), sr_values(y), sr_values(z)
    x_sr, y_sr, z_sr = sr_search(x), sr_search(y), sr_search(z)

    jobs: list[Job] = []
    for zi, zv in enumerate(z_vals):
        pz = apply_axis(base, z.kind, zv, sr_search=z_sr) if z.active else base.copy()
        for yi, yv in enumerate(y_vals):
            py = apply_axis(pz, y.kind, yv, sr_search=y_sr) if y.active else pz.copy()
            for xi, xv in enumerate(x_vals):
                px = apply_axis(py, x.kind, xv, sr_search=x_sr) if x.active else py.copy()
                jobs.append(Job(zi, yi, xi, px))
    return jobs


# ──────────────────────────────────────────
#  グリッド画像の合成
# ──────────────────────────────────────────


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """日本語が出せるフォントを探して読む。無ければ既定フォント。"""
    candidates = [
        PROJECT_ROOT / "font" / "JP" / "NotoSansJP-VariableFont_wght.ttf",
        PROJECT_ROOT / "font" / "JP" / "KiwiMaru-Medium.ttf",
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("C:/Windows/Fonts/YuGothM.ttc"),
        Path("C:/Windows/Fonts/msgothic.ttc"),
    ]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except Exception:
            continue
    try:
        for jp in (PROJECT_ROOT / "font" / "JP").glob("*.[to][tt][fc]"):
            return ImageFont.truetype(str(jp), size)
    except Exception:
        pass
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def compose_grid(
    cell_images: dict[tuple[int, int], Image.Image],
    *,
    x_headers: list[str],
    y_headers: list[str],
    title: str = "",
    cell_size: tuple[int, int] = (320, 180),
    bg=(253, 234, 243),
    fg=(80, 40, 70),
) -> Image.Image:
    """セル画像（(row, col) → Image）と行・列ヘッダーから1枚のグリッド画像を作る。

    左端に行ヘッダー（Y 軸値）、上端に列ヘッダー（X 軸値）、最上部に任意のタイトル（Z 軸値）。
    """
    cols = max(1, len(x_headers))
    rows = max(1, len(y_headers))
    cw, ch = cell_size
    pad = 10
    font = _load_font(18)
    title_font = _load_font(22)

    tmp = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(tmp)

    # 行ヘッダーの幅・列ヘッダーの高さ・タイトル高さを文字量から決める
    row_head_w = 0
    for h in y_headers:
        w, _ = _text_size(draw, h, font)
        row_head_w = max(row_head_w, w)
    row_head_w = min(max(row_head_w + 2 * pad, 60), 360) if y_headers else pad

    col_head_h = 0
    for h in x_headers:
        _, hh = _text_size(draw, h, font)
        col_head_h = max(col_head_h, hh)
    col_head_h = (col_head_h + 2 * pad) if x_headers else pad

    title_h = 0
    if title:
        _, th = _text_size(draw, title, title_font)
        title_h = th + 2 * pad

    grid_w = row_head_w + cols * (cw + pad) + pad
    grid_h = title_h + col_head_h + rows * (ch + pad) + pad

    canvas = Image.new("RGB", (grid_w, grid_h), bg)
    draw = ImageDraw.Draw(canvas)

    if title:
        draw.text((pad, pad), title, fill=fg, font=title_font)

    y0 = title_h + col_head_h
    x0 = row_head_w

    # 列ヘッダー
    for ci, head in enumerate(x_headers):
        cx = x0 + ci * (cw + pad)
        w, _ = _text_size(draw, head, font)
        draw.text((cx + (cw - w) // 2, title_h + pad), _ellipsize(draw, head, font, cw), fill=fg, font=font)

    # 行ヘッダー
    for ri, head in enumerate(y_headers):
        cy = y0 + ri * (ch + pad)
        _, h = _text_size(draw, head, font)
        draw.text((pad, cy + (ch - h) // 2), _ellipsize(draw, head, font, row_head_w - 2 * pad), fill=fg, font=font)

    # セル
    for ri in range(rows):
        for ci in range(cols):
            cx = x0 + ci * (cw + pad)
            cy = y0 + ri * (ch + pad)
            img = cell_images.get((ri, ci))
            if img is None:
                draw.rectangle([cx, cy, cx + cw, cy + ch], outline=(200, 170, 190), width=1)
                continue
            thumb = _fit(img, cell_size)
            canvas.paste(thumb, (cx + (cw - thumb.width) // 2, cy + (ch - thumb.height) // 2))
    return canvas


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = image.convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    return img


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if max_w <= 0:
        return text
    w, _ = _text_size(draw, text, font)
    if w <= max_w:
        return text
    while text and _text_size(draw, text + "…", font)[0] > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"
