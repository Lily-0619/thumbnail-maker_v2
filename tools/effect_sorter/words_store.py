"""
words_store.py
effect①(クラス別) / effect②(共通) の履歴を config/effect_sorter_words.json に読み書きする。

データ構造:
{
  "effect1": { "WS": ["lotus", "butterfly"], ... },   # クラス別
  "effect2": ["sparkle", "glow", ...]                  # 共通
}

  - 起動時に読み込み、無ければ空構造で新規生成。
  - 追記は重複を追加しない。
  - 保存はアトミック（一時ファイル→os.replace）。
  - 書き込み失敗してもアプリは落とさない（呼び出し側で握る方針／ここでは例外を投げる）。
"""

import json
import os
import tempfile

from . import paths

_EMPTY = {"effect1": {}, "effect2": []}


def load() -> dict:
    """履歴JSONを読む。無ければ空構造を返す（生成はしない）。"""
    if not paths.WORDS_JSON.exists():
        return {"effect1": {}, "effect2": []}
    try:
        with open(paths.WORDS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # 壊れていても落とさない。空構造で続行（既存は上書き初期化しない＝ここでは保存しない）。
        return {"effect1": {}, "effect2": []}
    # 構造を正規化（欠損キーを補う）
    if not isinstance(data, dict):
        return {"effect1": {}, "effect2": []}
    data.setdefault("effect1", {})
    data.setdefault("effect2", [])
    if not isinstance(data["effect1"], dict):
        data["effect1"] = {}
    if not isinstance(data["effect2"], list):
        data["effect2"] = []
    return data


def ensure_file():
    """JSONが無い場合のみ空構造で生成する。既存は絶対に上書きしない。"""
    if not paths.WORDS_JSON.exists():
        _atomic_write(paths.WORDS_JSON, _EMPTY)


def _atomic_write(path, data):
    """一時ファイルに書いてから os.replace で差し替え（壊れ防止）。"""
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


def add_effect1(cls: str, word: str):
    """effect① を指定クラスのリストへ追記（重複追加しない）→ 即保存。"""
    data = load()
    lst = data["effect1"].setdefault(cls, [])
    if word not in lst:
        lst.append(word)
    _atomic_write(paths.WORDS_JSON, data)


def add_effect2(word: str):
    """effect② を共通リストへ追記（重複追加しない）→ 即保存。"""
    data = load()
    if word not in data["effect2"]:
        data["effect2"].append(word)
    _atomic_write(paths.WORDS_JSON, data)


def effect1_for(cls: str):
    """指定クラスの effect① 履歴リストを返す。"""
    return list(load()["effect1"].get(cls, []))


def effect2_all():
    """共通の effect② 履歴リストを返す。"""
    return list(load()["effect2"])
