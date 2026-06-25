"""
paths.py
プロジェクトルートと、仕分け先フォルダ（固定）のパス解決。

このファイル(__file__)を起点にプロジェクトルートを確定する。
仕分け先は material/back に固定（拠点ごとにサブフォルダを切る）。
入力はフォルダ選択ではなく、画面へのドラッグ&ドロップ／追加で受け取る。

  tools/base_image_sorter/paths.py  →  ルートは parents[2]
"""

from pathlib import Path

# このファイルは tools/base_image_sorter/ の中にある。ルートは2階層上で確定。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = PROJECT_ROOT / "config"
MATERIAL_DIR = PROJECT_ROOT / "material"

# 仕分け先（固定）。例: D:/bdm-thumbnail_app_v02/material/back
OUTPUT_DIR = MATERIAL_DIR / "back"

# 連続仕分け用（保留・ゴミ箱）。仕分け先の下に作り、完全削除はせず退避する。
HOLD_DIR = OUTPUT_DIR / "_hold"
TRASH_DIR = OUTPUT_DIR / "_trash"
# 拠点サブフォルダと混同しないための予約名。
RESERVED_DIRNAMES = {"_hold", "_trash"}


def ensure_dirs():
    """起動時に仕分け先フォルダを保証する（なければ作る・あっても壊さない）。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def output_target_dir(base: str) -> Path:
    """
    保存先フォルダパスを組み立てる（拠点ごとにサブフォルダ）。

        material/back/<拠点名>/
    """
    return OUTPUT_DIR / base
