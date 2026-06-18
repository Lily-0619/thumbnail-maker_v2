# BDM Thumbnail Maker

黒い砂漠モバイルのノードウォー用サムネイルを生成するアプリです。

- 起動: `python main.py`（Windowsは `起動.bat`）
- **使い方の総合マニュアル（操作＋設定＋AI）** → [docs/操作説明書.md](docs/操作説明書.md)
- **AI画像生成（背景＋後方エフェクト）のセットアップと使い方** → [docs/AI画像生成_やり方説明書.md](docs/AI画像生成_やり方説明書.md)
  - ローカルの **ComfyUI** を使用。APIキー不要・無料・全部ローカルで動く
  - sdwebui（AUTOMATIC1111）/ Stability AI / OpenAI への切り替えも可
- **LoRA学習（自分のキャラ・画風・エフェクトを覚えさせる）** → [docs/LoRA学習_やり方説明書.md](docs/LoRA学習_やり方説明書.md)
  - 無料ツール **kohya_ss** を使用。SD1.5 なら RTX 3060 Ti（8GB）でも学習可能
- AIの設定: `config/ai_config.json` / プロンプト調整: `config/ai_prompts.json`

## 各種ファイル情報

### main.py
アプリのエントリーポイント。`python main.py` で起動する。

### cli.py
GUIなしでコマンドラインからサムネイルを生成するスクリプト。動作確認やバッチ処理に使う。

### requirements.txt
使用しているPythonのライブラリ情報の設定ファイルです。

### config/ai_config.json
AIプロバイダー・画像サイズなどの設定。`provider` を `comfyui`（標準）/ `sdwebui` / `stability` / `openai` から選ぶ。

### config/ai_prompts.json
AI生成のプロンプト文。拠点ごとの背景描写ヒント・エフェクト種類などを自由に編集できる。

### templates/
サムネイルのレイアウト設定（テキスト位置・サイズ・キャラ配置など）をJSONで管理する。

### data/node_options.json
曜日ごとの拠点候補リスト。UIのドロップダウンに使われる。

### assets/
背景・エフェクト・フォント素材を格納するフォルダ。

### .github/workflows/
GitHub Actions による自動構文チェックの設定ファイルです。

### .gitignore
Git管理が不要なファイル/ディレクトリの設定ファイルです。

### LICENSE
このリポジトリのコードの権利情報です。MITライセンスの範囲でご自由にご利用ください。
