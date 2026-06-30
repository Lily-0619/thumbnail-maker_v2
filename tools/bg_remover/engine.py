"""
engine.py
背景除去のコアロジック（UIなし・他プロジェクトへ流用可能）。

rembg はインポートが重く・未導入のこともあるので、関数内で遅延インポートする。
（アプリ自体は rembg 未導入でも起動でき、実行時にだけ必要になる。）
"""

import io
from datetime import datetime
from pathlib import Path

from PIL import Image

# 対応モデル（rembg指定名, 画面表示ラベル）。並び順でもある。
MODELS = [
    ("birefnet-general", "birefnet-general（推奨・高精度）"),
    ("birefnet-massive", "birefnet-massive（最高精度・重い）"),
]
MODEL_NAMES = [name for name, _label in MODELS]
LABEL_TO_NAME = {label: name for name, label in MODELS}
NAME_TO_LABEL = {name: label for name, label in MODELS}

# モデルのセッションは生成が重いので使い回す（モデル別にキャッシュ）。
_session_cache = {}


def rembg_available() -> bool:
    """rembg が import 可能か（未導入なら False）。"""
    import importlib.util

    return importlib.util.find_spec("rembg") is not None


def _get_session(model_name: str):
    from rembg import new_session  # 遅延import（重い・未導入対策）

    if model_name not in _session_cache:
        _session_cache[model_name] = new_session(model_name)
    return _session_cache[model_name]


def remove_background(input_path, model_name: str) -> Image.Image:
    """指定モデルで背景除去を実行し、RGBA の PIL Image を返す。"""
    from rembg import remove  # 遅延import

    session = _get_session(model_name)
    with open(input_path, "rb") as f:
        input_data = f.read()
    output_data = remove(input_data, session=session)
    return Image.open(io.BytesIO(output_data)).convert("RGBA")


def make_checker(
    width: int,
    height: int,
    tile: int = 16,
    light=(255, 255, 255, 255),
    dark=(200, 200, 200, 255),
) -> Image.Image:
    """市松模様の背景を生成（2×2タイルを敷き詰める高速版）。"""
    width = max(1, int(width))
    height = max(1, int(height))
    cell = Image.new("RGBA", (tile * 2, tile * 2), light)
    dark_tile = Image.new("RGBA", (tile, tile), dark)
    cell.paste(dark_tile, (0, 0))
    cell.paste(dark_tile, (tile, tile))
    bg = Image.new("RGBA", (width, height), light)
    for y in range(0, height, tile * 2):
        for x in range(0, width, tile * 2):
            bg.paste(cell, (x, y))
    return bg


def composite_on_checker(fg: Image.Image, tile: int = 16) -> Image.Image:
    """透過画像をチェッカー背景に合成して、透過の見えるRGBA画像を返す。"""
    fg = fg.convert("RGBA")
    bg = make_checker(fg.width, fg.height, tile=tile)
    bg.paste(fg, (0, 0), mask=fg.split()[3])  # アルファをマスクに使う
    return bg


def save_png(image: Image.Image, original_path, out_dir, model_name: str = "") -> Path:
    """
    結果を out_dir に PNG(RGBA) 保存する。
    ファイル名：{元ファイル名}_{モデル名}_{YYYYmmdd_HHMMSS}_nobg.png
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(original_path).stem if original_path else "image"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"_{model_name}" if model_name else ""
    save_path = out_dir / f"{base}{tag}_{ts}_nobg.png"
    image.convert("RGBA").save(save_path, format="PNG")  # 必ずRGBAで透過維持
    return save_path
