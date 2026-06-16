"""
config_loader.py
ComfyUI 接続設定の読み込み。

本体の AI 設定 `ai_config.json` を流用する。リポジトリの整理状況により
`config/` と `assets/config/` のどちらにも置かれうるため、両方を順に探す。
見つからなくても標準値で動作する（ComfyUI が 127.0.0.1:8188 で起動している前提）。
"""

import json
from pathlib import Path

# このファイルは tools/model_tester/ の中にある。ルートは2階層上。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# config/ を優先し、無ければ assets/config/ を見る。
_CONFIG_CANDIDATES = (
    PROJECT_ROOT / "config" / "ai_config.json",
    PROJECT_ROOT / "assets" / "config" / "ai_config.json",
)

# 設定ファイルが全く無い場合のフォールバック。
_DEFAULT = {
    "comfyui": {
        "url": "http://127.0.0.1:8188",
        "auto_start": False,
        "width": 768,
        "height": 432,
        "steps": 28,
        "cfg_scale": 7,
        "sampler_name": "euler",
        "scheduler": "normal",
    },
    "timeout_seconds": 300,
}


def load_config() -> dict:
    """ai_config.json を探して読む。無ければ標準値を返す（落とさない）。"""
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
    return dict(_DEFAULT)
