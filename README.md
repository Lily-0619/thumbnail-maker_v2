# BDM Thumbnail Maker

黒い砂漠モバイルのノードウォー用サムネイルを生成するアプリです。

- 起動: `python main.py`(Windowsは `起動.bat`)
- **AI画像生成(背景+後方エフェクト)のセットアップと使い方** → [docs/AI画像生成_やり方説明書.md](docs/AI画像生成_やり方説明書.md)
  - ローカルの Stable Diffusion WebUI(AUTOMATIC1111)を使用。APIキー不要・無料
- AIの設定: `config/ai_config.json` / プロンプト調整: `config/ai_prompts.json`

---

# discordpy-startup

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

- Herokuでdiscord.pyを始めるテンプレートです。
- Use Template からご利用ください。
- 使い方はこちら： [Discord Bot 最速チュートリアル【Python&Heroku&GitHub】 - Qiita](https://qiita.com/1ntegrale9/items/aa4b373e8895273875a8)

## 各種ファイル情報

### discordbot.py
PythonによるDiscordBotのアプリケーションファイルです。

### requirements.txt
使用しているPythonのライブラリ情報の設定ファイルです。

### Procfile
Herokuでのプロセス実行コマンドの設定ファイルです。

### runtime.txt
Herokuでの実行環境の設定ファイルです。

### app.json
Herokuデプロイボタンの設定ファイルです。

### .github/workflows/flake8.yaml
GitHub Actions による自動構文チェックの設定ファイルです。

### .gitignore
Git管理が不要なファイル/ディレクトリの設定ファイルです。

### LICENSE
このリポジトリのコードの権利情報です。MITライセンスの範囲でご自由にご利用ください。

### README.md
このドキュメントです。
