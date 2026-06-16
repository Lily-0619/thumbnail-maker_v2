"""
paths.py
プロジェクトルートと各フォルダ・設定ファイルのパス解決。

誤作動防止の要。ドライブ文字やフォルダ名に依存せず、
このファイル(__file__)を起点にプロジェクトルートを確定する。

  tools/effect_sorter/paths.py  →  ルートは parents[2]
"""

from pathlib import Path

# このファイルは tools/effect_sorter/ の中にある。ルートは2階層上で確定。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 各フォルダ（すべて PROJECT_ROOT 起点）──
MATERIAL_DIR = PROJECT_ROOT / "material"
CLASS_BUTTON_DIR = MATERIAL_DIR / "class_button"
EFFECT_DIR = MATERIAL_DIR / "effect"
UNSORTED_DIR = EFFECT_DIR / "_unsorted"

CONFIG_DIR = PROJECT_ROOT / "config"
WORDS_JSON = CONFIG_DIR / "effect_sorter_words.json"
DICT_JSON = CONFIG_DIR / "effect_sorter_dict.json"


def ensure_dirs():
    """
    起動時に必要なフォルダを保証する。
    なければ作る・あっても壊さない（mkdir exist_ok=True）。
    """
    for d in (UNSORTED_DIR, CLASS_BUTTON_DIR, EFFECT_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def effect_target_dir(cls: str, position: str, effect1: str) -> Path:
    """
    保存先フォルダパスを組み立てる（effect① まで。effect② はフォルダに使わない）。

        material/effect/<クラス>/<位置>/<effect①>/
    """
    return EFFECT_DIR / cls / position / effect1
