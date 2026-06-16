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

## D&D（必須）

エクスプローラ / Finder から未分類エリアへ画像をドラッグ&ドロップするため、`tkinterdnd2` が必須です。

```
pip install -r tools/effect_sorter/requirements.txt
```

画面下の **「＋ 画像を追加」** ボタンも残していますが、D&D前提で使えるようにしています。

## Ollama（オラマ）翻訳

effect① / effect② の **「Ollamaで日本語→英語」** ボタンは、ローカルの Ollama を使います。

アプリ起動時に Ollama の接続確認を行い、起動していなければ `ollama serve` を自動実行します。

1. Ollama をインストールしておく
2. 使うモデルを入れる（例: `ollama pull llama3.1`）
3. 必要なら環境変数で変更する
   - `OLLAMA_URL`（標準: `http://127.0.0.1:11434`）
   - `OLLAMA_MODEL`（標準: `llama3.1`）
   - `OLLAMA_START_COMMAND`（標準: `ollama serve`）
   - `OLLAMA_AUTO_START`（`0` / `false` / `no` で自動起動しない）

## 連続仕分け（スキップ / 保留 / 削除）

未分類画像を1枚ずつ片付けていくための機能です。確定（✔）・保留・削除のいずれかで
1枚処理すると、**その位置にスライドしてくる次の未分類画像が自動で選択される**ので、
続けて仕分けできます。プレビュー右下に **「残り N 枚」** を表示します。

| ボタン | 動作 | 元画像 |
|---|---|---|
| ⏭ スキップ | 何もせず次の未分類画像へ進む（非破壊） | `_unsorted` に残る |
| 保留 | 後で処理する画像を `material/effect/_hold/` へ退避 | copy→検証後に移動。復元可 |
| 🗑 削除 | 確認のうえ `material/effect/_trash/` へ退避（**完全削除はしない**） | copy→検証後に移動。復元可 |

保留・削除は確定フローと同じく **copy→検証→元削除** で行い、検証に失敗した場合は
元画像を `_unsorted` に残します。`_hold` / `_trash` 内で同名が衝突したときは `_dup1`
等のサフィックスを付けて退避し、既存を上書きしません。不要になった画像は
`_trash` フォルダごとエクスプローラ等で手動削除してください。

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
