# エフェクト素材仕分けツール

画像を目視して **クラス / 位置 / effect① / effect②** を選び、命名ルールでリネームして
`material/effect/<クラス>/<位置>/<effect①>/` へ移動する補助デスクトップアプリ。
サムネ生成・AI自動分類はしない。

## 起動

リポジトリのルートから:

```
python tools/effect_sorter/effect_sorter_app.py
```

Windows ではルートの `素材仕分け起動.bat` をダブルクリックしてもよい。

## D&D（任意）

エクスプローラから未分類エリアへ画像をドラッグ&ドロップしたい場合のみ:

```
pip install -r tools/effect_sorter/requirements.txt
```

`tkinterdnd2` が無くても、画面下の **「＋ 画像を追加」** ボタンで取り込めるため
ツールは完全に動作する。

## 命名ルール

```
クラス__位置__effect①__effect②__連番.png
例: WS__back__lotus__glow__001.png
```

- 区切りは `__`（アンダースコア2個）。連番は3桁ゼロ詰め。
- 使用可能文字は半角英数字・`_`・`-` のみ。位置は `back` / `front` のみ。
- 連番は確定時に保存先フォルダを見て自動採番。既存があっても上書きしない。

## ファイル

| ファイル | 役割 |
|---|---|
| `effect_sorter_app.py` | エントリーポイント（GUI） |
| `paths.py` | ルート検出・各フォルダパス解決 |
| `naming.py` | ファイル名生成・バリデーション・連番取得 |
| `words_store.py` | effect①/② 履歴の JSON 読み書き |
| `translate.py` | 簡易日本語→英語変換 |
| `widgets.py` | 再利用UI部品（プレビュー・拡大・サムネ一覧） |

設定ファイルは `config/effect_sorter_words.json` / `config/effect_sorter_dict.json`
に自動生成される（既存は壊さない）。
