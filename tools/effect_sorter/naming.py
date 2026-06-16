"""
naming.py
ファイル名生成・バリデーション・連番自動取得。

命名フォーマット:
    クラス__位置__effect①__effect②__連番.png
    例: WS__back__lotus__glow__001.png

  - 区切りは アンダースコア2個 "__"。要素は5つ。
  - 連番は3桁ゼロ詰め（001）。999超は桁上げ（1000）。
  - 拡張子は最終的に .png に統一。
"""

import re
from pathlib import Path

SEP = "__"
ALLOWED_POSITIONS = ("back", "front")

# 使用可能文字: 半角英数字・_・- のみ
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# 日本語（ひらがな・カタカナ・漢字）検出用
_JP_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


class ValidationError(Exception):
    """バリデーション失敗。message は日本語の警告文。"""


def _has_japanese(s: str) -> bool:
    return bool(_JP_RE.search(s))


def validate(cls, position, effect1, effect2):
    """
    保存前のバリデーション（§4-4）。
    1つでも失敗したら ValidationError を投げる。message は日本語警告文。

    順に:
      (A) 必須チェック
      (B) 文字チェック（半角英数字・_・- のみ）
      (C) 位置チェック（back / front のみ）
    """
    # (A) 必須チェック
    if not cls:
        raise ValidationError("クラスが未選択です。")
    if not position:
        raise ValidationError("位置が未選択です。")
    if not effect1:
        raise ValidationError("effect① が未入力です。")
    if not effect2:
        raise ValidationError("effect② が未入力です。")

    # (C) 位置チェック（back/front のみ。大文字NG）
    if position not in ALLOWED_POSITIONS:
        raise ValidationError(
            f"位置が不正です。使用できるのは back / front のみです。現在：{position}"
        )

    # (B) 文字チェック
    for label, value in (
        ("クラス", cls),
        ("位置", position),
        ("effect①", effect1),
        ("effect②", effect2),
    ):
        if " " in value or "\t" in value:
            raise ValidationError(
                f"{label} に空白が含まれています。現在：{value}  推奨：{value.replace(' ', '_')}"
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
    ファイル名末尾の連番（3桁以上）を整数で返す。マッチしなければ None。
    prefix は 'class__position__effect1__effect2' （末尾 SEP なし）。
    """
    expected = prefix + SEP
    if not name.startswith(expected):
        return None
    rest = name[len(expected):]
    m = re.match(r"^(\d+)\.png$", rest)
    if not m:
        return None
    return int(m.group(1))


def next_sequence(target_dir: Path, cls, position, effect1, effect2) -> int:
    """
    保存先フォルダを実際に見て次の連番を計算する（§4-3）。

      1. 同じ class__position__effect1__effect2 で始まる *.png の連番を全部読む
      2. 最大値を取得（無ければ 0）
      3. 新規連番 = 最大値 + 1
    """
    prefix = SEP.join((cls, position, effect1, effect2))
    max_seq = 0
    if target_dir.exists():
        for p in target_dir.glob("*.png"):
            seq = _seq_from_name(p.name, prefix)
            if seq is not None and seq > max_seq:
                max_seq = seq
    return max_seq + 1


def format_sequence(seq: int) -> str:
    """3桁ゼロ詰め。999超は自然な桁数（1000）。"""
    return f"{seq:03d}"


def build_filename(cls, position, effect1, effect2, seq: int) -> str:
    """最終ファイル名を組み立てる。"""
    return SEP.join((cls, position, effect1, effect2, format_sequence(seq))) + ".png"


def title_preview(cls, position, effect1, effect2, seq=None) -> str:
    """
    タイトル欄に出す候補文字列（§10）。
    未確定要素はプレースホルダで見せる。
    """
    c = cls or "クラス"
    p = position or "位置"
    e1 = effect1 or "effect①"
    e2 = effect2 or "effect②"
    s = format_sequence(seq) if seq is not None else "001"
    return SEP.join((c, p, e1, e2, s))
