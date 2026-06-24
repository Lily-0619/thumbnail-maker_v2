"""
bases.py
拠点名リスト（曜日別）と時間帯の定義。データだけを持つモジュール。

  - 拠点名のスペル・ハイフンはそのまま使用する（ファイル名にもこの英語名を使う）。
  - 画面表示は「英語名（日本語名）」の2行で出すが、ファイル名は英語名のみ。
  - 日本語名(BASE_JP)は表示専用。固有名詞は推定が混じるので、合わなければ
    この辞書を書き換えるだけで直せる（ファイル名には影響しない）。
  - 時間帯は day / morning / evening / night の4種。
"""

from collections import OrderedDict

# 曜日見出し付きの縦リストでそのまま描画する想定の順序。
BASES_BY_DAY = OrderedDict(
    [
        (
            "月曜日",
            [
                "Forest_of_Seclusion",
                "Ehwaz_Hill",
                "Highlands",
                "Rhutum_Outstation",
                "Kasula_Farm",
                "Kaia_Pier",
                "Castle_Ruins_Entrance",
                "Velia_Farmlands",
                "Quint_Hill",
                "Ahto_Farm",
            ],
        ),
        (
            "木曜日",
            [
                "Plains_of_Agris",
                "Bradie_Fortress",
                "Marnis_Second_Lab",
                "Treant_Forest",
                "Lynch_Farm_Ruins",
                "Northern_Plantation",
                "Hidden_Monastery",
                "Anti-troll_Fortification",
                "Crioville",
            ],
        ),
        (
            "金曜日",
            [
                "Orc_Camp",
                "Abandoned_Iron_Mine",
                "Bree_Tree_Forest",
                "Altar_of_Agris",
                "Northern_Quarry",
                "Harpy_Cliff",
                "Naga_Extraction_Mill",
                "Inner_Mansha_Forest",
            ],
        ),
        (
            "土曜日",
            [
                "Calpheon_Siege_War",
                "Valencian_Siege_War",
            ],
        ),
        (
            "日曜日",
            [
                "Forest_of_Plunder",
                "Naga_Swamplands",
                "Dernyl_Farm",
                "Forsaken_Lands",
                "Cursed_Lands",
                "Old_Dandelion",
                "Behr_River_Downstream",
                "Altinova_Entrance",
            ],
        ),
    ]
)

# 表示専用の日本語名（ファイル名には使わない）。ユーザー指定の正式名。
BASE_JP = {
    # 月曜日
    "Forest_of_Seclusion": "隠遁の森",
    "Ehwaz_Hill": "エワズの丘",
    "Highlands": "高原地帯",
    "Rhutum_Outstation": "ルツム族駐屯地",
    "Kasula_Farm": "カズラ農場",
    "Kaia_Pier": "カイア渡し場",
    "Castle_Ruins_Entrance": "廃城跡入り口",
    "Velia_Farmlands": "ベリア農場地帯",
    "Quint_Hill": "ギュントの丘",
    "Ahto_Farm": "アト農場",
    # 木曜日
    "Plains_of_Agris": "アグリス平原",
    "Bradie_Fortress": "ブレディー砦",
    "Marnis_Second_Lab": "マルニの第2実験場",
    "Treant_Forest": "エントの森",
    "Lynch_Farm_Ruins": "リンチ農場廃墟",
    "Northern_Plantation": "北部大農場",
    "Hidden_Monastery": "隠された修道院",
    "Anti-troll_Fortification": "トロル防御基地",
    "Crioville": "クリオ村",
    # 金曜日
    "Orc_Camp": "オークキャンプ",
    "Abandoned_Iron_Mine": "廃鉄鉱山採掘場",
    "Bree_Tree_Forest": "ブリの森",
    "Altar_of_Agris": "アグリス祭壇",
    "Northern_Quarry": "北部採石場",
    "Harpy_Cliff": "ハーピーの絶壁",
    "Naga_Extraction_Mill": "ナーガ抽出場",
    "Inner_Mansha_Forest": "マンシャの森の奥",
    # 土曜日
    "Calpheon_Siege_War": "カルフェオン攻城戦",
    "Valencian_Siege_War": "バレンシア攻城戦",
    # 日曜日
    "Forest_of_Plunder": "略奪の森",
    "Naga_Swamplands": "ナーガ沼地",
    "Dernyl_Farm": "デルニール農場",
    "Forsaken_Lands": "捨てられた地",
    "Cursed_Lands": "忘却の地",
    "Old_Dandelion": "旧ダンデリオン",
    "Behr_River_Downstream": "ベア川下流",
    "Altinova_Entrance": "アルティノ入口",
}

# 全拠点のフラットリスト（バリデーション等で使用）。
ALL_BASES = [name for names in BASES_BY_DAY.values() for name in names]

# 時間帯（ファイル名キー, 画面表示ラベル）。朝→昼→夕→夜の順で並べる。
TIMES_OF_DAY = [
    ("morning", "朝 morning"),
    ("day", "昼 day"),
    ("evening", "夕 evening"),
    ("night", "夜 night"),
]

# ファイル名・バリデーションで使う時間帯キーの集合。
TIME_KEYS = [key for key, _label in TIMES_OF_DAY]


def display_name(base: str) -> str:
    """ボタン表示用「英語名（日本語名）」。日本語名が無ければ英語名のみ。"""
    jp = BASE_JP.get(base)
    return f"{base}\n（{jp}）" if jp else base
