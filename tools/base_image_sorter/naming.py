"""
naming.py
ファイル名生成・バリデーション・連番自動取得。

命名フォーマット:
    {拠点名}_{時間帯}_{連番}.png
    例: Forest_of_Seclusion_day_001.png
        Ehwaz_Hill_night_003.png

  - 区切りはアンダースコア1個 "_"。
    （拠点名自体にも "_" を含むため、分割ではなく前方一致で連番を読む）
  - 連番は3桁ゼロ詰め（001）。999超は桁上げ（1000）。
  - 拡張子は最終的に .png に統一。
"""

import re
from pathlib import Path

# 時間帯として許可するキー（bases.TIME_KEYS と一致させる）。
ALLOWED_TIMES = ("day", "morning", "evening", "night")

# 使用可能文字: 半角英数字・_・- のみ（拠点名のハイフン Anti-troll も許可）。
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# 日本語（ひらがな・カタカナ・漢字）検出用。
_JP_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


class ValidationError(Exception):
    """バリデーション失敗。message は日本語の警告文。"""


def _has_japanese(s: str) -> bool:
    return bool(_JP_RE.search(s))


def validate(base: str, time_of_day: str):
    """
    保存前のバリデーション。1つでも失敗したら ValidationError を投げる。

    順に:
      (A) 必須チェック（拠点・時間帯）
      (B) 時間帯チェック（day/morning/evening/night のみ）
      (C) 文字チェック（半角英数字・_・- のみ）
    """
    # (A) 必須チェック
    if not base:
        raise ValidationError("拠点が未選択です。")
    if not time_of_day:
        raise ValidationError("時間帯が未選択です。")

    # (B) 時間帯チェック
    if time_of_day not in ALLOWED_TIMES:
        raise ValidationError(
            "時間帯が不正です。使用できるのは "
            "day / morning / evening / night のみです。"
            f"現在：{time_of_day}"
        )

    # (C) 文字チェック
    for label, value in (("拠点", base), ("時間帯", time_of_day)):
        if " " in value or "\t" in value:
            raise ValidationError(
                f"{label} に空白が含まれています。現在：{value}  "
                f"推奨：{value.replace(' ', '_')}"
            )
        if not _TOKEN_RE.match(value):
            if _has_japanese(value):
                raise ValidationError(
                    f"{label} に日本語が含まれています。現在：{value}\n"
                    "LoRA学習で使いにくいため、英語に変換してください。\n"
                    "使用可能：半角英数字、_、-"
                )
            raise ValidationError(
                f"{label} に使用できない文字があります。現在：{value}  "
                "使用可能：半角英数字、_、-"
            )


def _seq_from_name(name: str, prefix: str):
    """
    ファイル名末尾の連番（数字）を整数で返す。マッチしなければ None。
    prefix は '{拠点名}_{時間帯}_'（末尾の "_" まで含む）。
    """
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    m = re.match(r"^(\d+)\.png$", rest)
    if not m:
        return None
    return int(m.group(1))


def next_sequence(target_dir: Path, base: str, time_of_day: str) -> int:
    """
    保存先フォルダを実際に見て次の連番を計算する。

      1. 同じ {拠点名}_{時間帯}_ で始まる *.png の連番を全部読む
      2. 最大値を取得（無ければ 0）
      3. 新規連番 = 最大値 + 1
    """
    prefix = f"{base}_{time_of_day}_"
    max_seq = 0
    target_dir = Path(target_dir)
    if target_dir.exists():
        for p in target_dir.glob("*.png"):
            seq = _seq_from_name(p.name, prefix)
            if seq is not None and seq > max_seq:
                max_seq = seq
    return max_seq + 1


def format_sequence(seq: int) -> str:
    """3桁ゼロ詰め。999超は自然な桁数（1000）。"""
    return f"{seq:03d}"


def build_filename(base: str, time_of_day: str, seq: int) -> str:
    """最終ファイル名を組み立てる。"""
    return f"{base}_{time_of_day}_{format_sequence(seq)}.png"


def title_preview(base: str, time_of_day: str, seq=None) -> str:
    """
    ファイル名プレビューに出す候補文字列。未確定要素はプレースホルダで見せる。
    """
    b = base or "拠点名"
    t = time_of_day or "時間帯"
    s = format_sequence(seq) if seq is not None else "001"
    return f"{b}_{t}_{s}.png"
