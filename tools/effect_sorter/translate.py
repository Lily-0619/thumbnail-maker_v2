"""
translate.py
簡易日本語→英語変換。config/effect_sorter_dict.json を使う。

  - 辞書にあれば英語キーへ置換。
  - 未知語は変換せず、ユーザーに英語キーを入力させる（自動ローマ字化はしない＝事故防止）。
  - AI翻訳は使わない。辞書は運用者が手で増やせる前提。
  - 保存はアトミック（一時ファイル→os.replace）。
"""

import json
import os
import tempfile

from . import paths

# 無ければ生成する初期辞書（§8-1）
_INITIAL_DICT = {
    "蓮": "lotus",
    "蝶": "butterfly",
    "雷": "thunder",
    "氷": "ice",
    "花": "flower",
    "光": "light",
    "闇": "dark",
    "霧": "mist",
    "煙": "smoke",
}


def ensure_file():
    """辞書JSONが無い場合のみ初期辞書で生成する。既存は上書きしない。"""
    if not paths.DICT_JSON.exists():
        _atomic_write(paths.DICT_JSON, _INITIAL_DICT)


def load() -> dict:
    """辞書を読む。無ければ初期辞書を返す。"""
    if not paths.DICT_JSON.exists():
        return dict(_INITIAL_DICT)
    try:
        with open(paths.DICT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return dict(_INITIAL_DICT)


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def translate(text: str):
    """
    入力文字列を辞書で変換して返す。

    戻り値: (変換後文字列, 変換できたか bool)
      - 完全一致が最優先。
      - 一致しなければ、辞書の各日本語キーを順に部分置換する。
      - どの置換も起きなければ (元の文字列, False)。
    """
    if not text:
        return text, False
    d = load()
    if text in d:
        return d[text], True

    result = text
    changed = False
    # 長いキーから先に置換（誤分割を減らす）
    for jp in sorted(d.keys(), key=len, reverse=True):
        if jp in result:
            result = result.replace(jp, d[jp])
            changed = True
    return result, changed
