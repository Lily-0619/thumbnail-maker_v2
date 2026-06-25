"""
paths.py
出力先などのパス解決。配置場所に応じて自動で出力先を決める（移植性のため）。

  - プロジェクト（tools/bg_remover/ の2階層上に main.py / material がある）なら
    <プロジェクトルート>/outputs/bg_removal/ に出す（指示書どおり）。
  - それ以外（例: D:\\汎用ツール\\bg_remover\\）なら、ツール直下の outputs/ に出す。

この1ファイルで両方に自動対応するので、プロジェクト版と汎用版でコードを分けずに済む。
"""

from pathlib import Path

HERE = Path(__file__).resolve()
_root_candidate = HERE.parents[2]

if (_root_candidate / "main.py").exists() or (_root_candidate / "material").exists():
    # bdm-thumbnail_app_v02 等のプロジェクト配下に置かれている。
    PROJECT_ROOT = _root_candidate
    OUTPUT_DIR = PROJECT_ROOT / "outputs" / "bg_removal"
else:
    # 汎用ツールフォルダ等に単体で置かれている。
    PROJECT_ROOT = HERE.parent
    OUTPUT_DIR = HERE.parent / "outputs"

# 取り込んだ画像の一時保存先（ステージング）。OUTPUT_DIR 直下に置く。
STAGE_DIR = OUTPUT_DIR
# 背景除去できたら、元画像（ステージング分）を「処理済み」へ、PNGを「PNG」へ振り分ける。
PROCESSED_DIR = OUTPUT_DIR / "処理済み"
PNG_DIR = OUTPUT_DIR / "PNG"


def ensure_dirs():
    """出力先フォルダ一式を保証する（なければ作る・あっても壊さない）。"""
    for d in (OUTPUT_DIR, STAGE_DIR, PROCESSED_DIR, PNG_DIR):
        d.mkdir(parents=True, exist_ok=True)
