"""
cli.py
UIなしでコマンドラインからサムネイルを生成するスクリプト。
動作確認やバッチ処理に使う。

使い方:
    python cli.py \
        --bg assets/backgrounds/dark_castle/bg01.jpg \
        --char assets/characters/chara01.png \
        --effect assets/effects/blue_purple_magic/effect01.png \
        --branding "Black Desert Mobile" \
        --date "2026.06.04" \
        --node "リンチファーム遺跡" \
        --guilds "GuildA" "GuildB" "GuildC" \
        --font assets/fonts/NotoSansJP-Bold.ttf \
        --guild-fonts assets/fonts/NotoSansJP-Bold.ttf assets/fonts/NotoSansJP-Bold.ttf \
        --font-ja assets/fonts/NotoSansJP-Bold.ttf \
        --template node_war_default \
        --out outputs/test_output.png
"""

import argparse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="黒砂漠モバイル サムネイル生成CLI")
    parser.add_argument("--bg", default="", help="背景画像パス（未指定なら assets/backgrounds からランダム選択）")
    parser.add_argument("--char", default="", help="キャラクター画像パス")
    parser.add_argument("--effect", default="", help="後方エフェクト画像パス（将来はAI生成パスを想定）")
    parser.add_argument("--date", default="2026.06.04", help='日付文字列（例: "2026.06.04"）')
    parser.add_argument("--node", default="テスト拠点", help="拠点名")
    parser.add_argument("--guilds", nargs="*", default=[], help="ギルド名（スペース区切りで複数指定、最大5件）")
    parser.add_argument("--font", default="assets/fonts/NotoSansJP-Bold.ttf", help="日付・拠点名・Node Warフォントパス")
    parser.add_argument("--branding", default="Black Desert Mobile", help="右下に表示する文字")
    parser.add_argument("--branding-font", default="", help="右下表示用フォントパス（空なら--font）")
    parser.add_argument("--guild-fonts", nargs="*", default=[], help="ギルドごとの個別フォントパス（ギルド順、指定時は言語カテゴリより優先）")
    parser.add_argument("--font-ja", default="", help="日本語（🇯🇵）ギルド用フォントパス")
    parser.add_argument("--font-ru", default="", help="キリル / ロシア語（🇷🇺）ギルド用フォントパス")
    parser.add_argument("--font-en", default="", help="アルファベット / 英語（🇺🇸）ギルド用フォントパス")
    parser.add_argument("--font-zh", default="", help="中国語（🇨🇳）ギルド用フォントパス")
    parser.add_argument("--font-ko", default="", help="ハングル / 韓国語（🇰🇷）ギルド用フォントパス")
    parser.add_argument("--template", default="node_war_default", help="テンプレート名")
    parser.add_argument("--out", default="outputs/cli_output.png", help="出力ファイルパス")
    return parser.parse_args()


def main():
    args = parse_args()

    from core.composer import compose_thumbnail
    from core.template import load_template

    template = load_template(args.template)
    template.setdefault("branding", {}).update({"text": args.branding, "font_path": args.branding_font})
    guilds = [guild for guild in args.guilds[:5] if guild.strip()]
    language_font_paths = {
        "ja": args.font_ja,
        "ru": args.font_ru,
        "en": args.font_en,
        "zh": args.font_zh,
        "ko": args.font_ko,
    }

    print("[合成開始]")
    print(f"  背景          : {args.bg or '（なし）'}")
    print(f"  キャラ        : {args.char or '（なし）'}")
    print(f"  後方エフェクト: {args.effect or '（なし）'}")
    print(f"  日付          : {args.date}")
    print(f"  拠点名        : {args.node}")
    print(f"  ギルド        : {guilds}")

    img = compose_thumbnail(
        bg_path=args.bg,
        char_path=args.char,
        effect_path=args.effect,
        date_str=args.date,
        node_name=args.node,
        guilds=guilds,
        template=template,
        font_path=args.font,
        guild_font_paths=args.guild_fonts,
        language_font_paths=language_font_paths,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG")
    print(f"[完了] 出力: {out_path.resolve()}")


if __name__ == "__main__":
    main()
