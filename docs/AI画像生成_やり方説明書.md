# AI画像生成 やり方説明書(初心者向け・全部ローカルで動く版)

サムネイルの「**背景**」と「**キャラの後方エフェクト**」をAIで自動生成できるようになりました。

- **APIキー不要・登録不要・料金は一切かかりません**(全部あなたのPCの中で動きます)
- 使うのは無料ソフト「**Stable Diffusion WebUI(AUTOMATIC1111)**」です
- この説明書は、プログラミングがわからなくても進められるように書いています。上から順番にやれば大丈夫です

---

## 1. これは何?(できるようになること)

- アプリの **Node(拠点名)を入力 → ボタンを押すだけ** で、拠点名から連想される
  **リアルダークファンタジー調の背景** をAIが描いてくれます。
- 同時に、キャラの後ろに置く **後方エフェクト(炎・氷・雷など)** も
  **透過PNG** で生成され、自動でアプリにセットされます。
- `material/サンプル/` に見本のエフェクト画像を置いておくと、**その見本の雰囲気に寄せて**生成します。
- 生成された画像はフォルダに保存されるので、あとから何度でも使い回せます。
  - 背景: `assets/backgrounds/ai/`
  - エフェクト: `assets/effects/ai/`

```
[Stable Diffusion WebUI を起動しておく(ローカル)]
                 ↑ ここにアプリが自動でお願いしに行く
[拠点名を入力] ──→ [✨ Generate BG + Effect ボタン] ──→ AIが2枚同時に生成
                                                          │
                            背景 → assets/backgrounds/ai/ に保存 & 自動セット
                            効果 → assets/effects/ai/   に保存 & 自動セット
                                                          │
                                              プレビューに自動反映 → Export PNG
```

---

## 2. 必要なPCスペック

| 項目 | 目安 |
|---|---|
| グラフィックボード(GPU) | **NVIDIA製を推奨**。VRAM 4GB以上で動作、8GB以上で快適 |
| 空きディスク容量 | 15GB以上(本体+AIモデル) |
| GPUがない場合 | CPUだけでも動きますが、1枚に数分〜十数分かかります |

---

## 3. あなたが手作業でやること一覧(チェックリスト)

| いつ | やること | かかる時間 |
|---|---|---|
| 最初に1回だけ | ① Stable Diffusion WebUI をインストール | 30分〜1時間(ほぼ待ち時間) |
| 最初に1回だけ | ② 起動設定に `--api` を追加 | 2分 |
| 最初に1回だけ | ③ (おすすめ)ダークファンタジー向きのモデルを入れる | 15分 |
| 最初に1回だけ | ④ 動作確認コマンドを1回実行 | 1分 |
| 任意 | ⑤ エフェクトの見本画像を `material/サンプル/` に置く | 数分 |
| **毎回** | **WebUIを起動してから**、アプリで拠点名を入れてボタンを押す | 数秒の操作 |

---

## 4. 手順① Stable Diffusion WebUI をインストールする

1. ブラウザでこのアドレスを開いてZIPをダウンロード:
   https://github.com/AUTOMATIC1111/stable-diffusion-webui/releases/download/v1.0.0-pre/sd.webui.zip
2. ダウンロードした `sd.webui.zip` を**右クリック→すべて展開**する
   - ⚠️ 展開先は**日本語やスペースを含まない場所**にしてください(例: `D:\sd.webui`)
3. 展開したフォルダの中の **`update.bat`** をダブルクリック
   - 黒い画面が出て最新版への更新が始まります。終わったら何かキーを押して閉じる
   - 「WindowsによってPCが保護されました」と出たら「詳細情報」→「実行」
4. 続けて **`run.bat`** をダブルクリック
   - **初回は必要なファイル(数GB)を自動ダウンロードするので、かなり時間がかかります。気長に待ってください**
   - AIモデルを持っていない場合は標準モデル(Stable Diffusion 1.5)も自動で入ります
5. 自動でブラウザに `http://127.0.0.1:7860` という画面が開いたらインストール成功です
6. いったん黒い画面を閉じて(×ボタンでOK)、次の手順へ

---

## 5. 手順② 起動設定に `--api` を追加する

サムネイルアプリがWebUIと会話できるようにするスイッチです。**これを忘れると連携できません。**

1. `sd.webui\webui\` フォルダの中の **`webui-user.bat`** を右クリック → 「メモ帳で編集」(または「編集」)
2. `set COMMANDLINE_ARGS=` と書かれた行を探して、こう書き換える:

   ```bat
   set COMMANDLINE_ARGS=--api
   ```

   - GPUのVRAMが4〜6GBなら、こうするとメモリ不足エラーが出にくくなります:

   ```bat
   set COMMANDLINE_ARGS=--api --medvram
   ```

3. 上書き保存して閉じる

---

## 6. 手順③ (おすすめ)ダークファンタジー向きのモデルを入れる

標準モデルでも動きますが、**モデルを変えると絵のクオリティが大きく上がります。**

1. 無料サイト Civitai( https://civitai.com/ )で好みのモデルを探す(無料登録が必要な場合あり)
   - 初心者へのおすすめ: 「**DreamShaper**」(リアル寄りファンタジーが得意で軽い)
   - 検索して、`.safetensors` 形式のファイルをダウンロード
2. ダウンロードしたファイルを次のフォルダに入れる:
   ```
   sd.webui\webui\models\Stable-diffusion\
   ```
3. `run.bat` でWebUIを起動し、画面**左上の「Stable Diffusion checkpoint」**欄で入れたモデルを選ぶ
   - 一度選べば次回からもそのモデルが使われます

> 💡 「SDXL」と書かれたモデルは高画質ですがVRAM 8GB以上推奨です。使う場合は
> `config/ai_config.json` の `"width": 960, "height": 540` を `1344` と `768` に上げると効果的です。

---

## 7. 手順④ 動作確認

1. **WebUIを起動しておく**(`run.bat` をダブルクリックして、ブラウザ画面が開くまで待つ)
2. コマンドプロンプトで以下を実行(サムネイルアプリのフォルダで):

```bat
cd /d D:\bdm-thumbnail_app_v02
.\.venv\Scripts\python.exe -m core.ai_image check
```

「WebUI接続(http://127.0.0.1:7860) : OK」と出れば準備完了です。

試しに1枚生成してみる場合(無料です):

```bat
.\.venv\Scripts\python.exe -m core.ai_image bg "Ehwaz Hill"
.\.venv\Scripts\python.exe -m core.ai_image effect fire
```

`assets/backgrounds/ai/` と `assets/effects/ai/` にPNGが保存されたら成功です。

---

## 8. 普段の使い方(アプリ)

1. **先に `run.bat` でWebUIを起動しておく**(黒い画面とブラウザは開いたままにする。ブラウザの画面は閉じてもOK、黒い画面は閉じない)
2. いつもどおり `起動.bat` でサムネイルアプリを起動
3. **Node(拠点名)** を入力 or プルダウンから選ぶ
4. 左側の「**🤖 AI Generate**」セクションで:
   - **Effect type** でエフェクトの種類を選ぶ
     (fire / ice / lightning / dark / holy / flower / butterfly / blue_purple_magic)
   - 「**✨ Generate BG + Effect (AI)**」を押す → 背景とエフェクトが**同時に**生成されます
   - 片方だけ作り直したいときは「BG only」「Effect only」
5. 生成が終わると自動でセットされ、プレビューに反映されます
   (時間はGPU性能次第。目安: RTX系なら10〜30秒/枚)
6. 気に入らなければもう一度ボタンを押せば**別の画像**が出ます
7. あとはいつもどおり「📤 Export PNG」

> 💡 過去に生成した画像は `assets/backgrounds/ai/`・`assets/effects/ai/` にたまっていくので、
> 「Select Background」「Select Effect」で選び直すこともできます。

---

## 9. エフェクトの見本画像を参考にさせる(任意)

手持ちの後方エフェクトのサンプルを見本として渡すと、**その雰囲気に寄せて**生成してくれます(img2imgという仕組みを使います)。

1. `material/サンプル/` フォルダの中に、エフェクト種類と同じ名前のフォルダを作って画像を入れる:
   ```
   material/サンプル/fire/見本1.png
   material/サンプル/ice/見本.png
   ```
   または、ファイル名を種類名で始めて直接置いてもOK:
   ```
   material/サンプル/fire_見本.png
   ```
2. あとは普通に「Effect only」などで生成するだけ。見本があれば自動で使われます。

**見本にどれだけ寄せるか**は `config/ai_config.json` の `"denoising_strength"` で調整できます:
- `0.6` … 見本にかなり近い
- `0.7` … 標準(見本の雰囲気を残しつつ変化)
- `0.8` … 見本から大きく変化

- `material/sample/` や `material/samples/` という名前でも認識します
- 見本を使いたくないときは `"use_sample_reference"` を `false` に

---

## 10. 生成される絵柄を調整したいとき

プロンプト(AIへの指示文)はコードとは別のファイルにまとめてあります。
**メモ帳で開いて文章を書き換えるだけ**で調整できます。

### `config/ai_prompts.json`

- `background.template` … 背景の基本指示文(「リアルダークファンタジー」の指定はここ)
- `background.node_hints` … **拠点ごとの追加描写**。全拠点ぶん登録済みですが、自由に書き換え・追加OK
  ```json
  "Ehwaz Hill": "A windswept grassy hill at dusk, ancient weathered runestones..."
  ```
- `effect.types` … エフェクト種類ごとの描写。**新しい種類をここに追加すると、アプリのドロップダウンにも自動で出ます**

### `config/ai_config.json`(画質・速度の調整)

| 設定 | 意味 | 目安 |
|---|---|---|
| `width` / `height` | 生成サイズ | SD1.5系: 960×540 / SDXL系: 1344×768 |
| `steps` | 描き込み回数 | 20=速い 〜 35=丁寧 |
| `timeout_seconds` | 待ち時間の上限 | GPUが遅いなら600などに増やす |

※ JSONファイルは「`"` や `,` を消してしまう」と壊れるので、**文章や数字の中身だけ**書き換えてください。

---

## 11. よくあるエラーと対処法

| 出るメッセージ・症状 | 原因 | 対処 |
|---|---|---|
| WebUIに接続できません | WebUIを起動していない / `--api` を付けていない | `run.bat` で起動する。手順②の `--api` 設定を確認 |
| CUDA out of memory(黒い画面に赤字) | GPUメモリ不足 | `--medvram`(それでもダメなら `--lowvram`)を追加。`width/height` を下げる |
| タイムアウトしました | 生成が遅い | `config/ai_config.json` の `timeout_seconds` を 600 に増やす |
| 1枚に何分もかかる | CPUで動いている | NVIDIA GPUドライバを最新にする。GPUがない場合は仕様です |
| 真っ黒な画像が出る | モデルとの相性 | `webui-user.bat` の COMMANDLINE_ARGS に `--no-half-vae` を追加 |
| エフェクトの抜けが汚い | 暗い色は透明扱いになるため | 炎・雷など発光系は得意。暗い色主体のエフェクトは `effect.types` の文に「bright」「glowing」を足す |

困ったら、まず確認コマンドを実行すると原因がわかりやすいです:
```bat
.\.venv\Scripts\python.exe -m core.ai_image check
```

---

## 12. 今回追加されたファイル(参考)

| ファイル | 役割 | 触ってOK? |
|---|---|---|
| `core/ai_image.py` | AI生成の本体プログラム | 触らない |
| `config/ai_config.json` | 接続先・画質などの設定 | 触ってOK |
| `config/ai_prompts.json` | AIへの指示文(プロンプト) | 触ってOK |
| `assets/backgrounds/ai/` | 生成された背景の保存先 | 不要なものは削除OK |
| `assets/effects/ai/` | 生成されたエフェクトの保存先 | 不要なものは削除OK |
| `.env.example` | クラウドAPI用の設定見本 | **ローカル運用では不要。無視してOK** |

> 補足: 将来クラウドAPI(Stability AI)を使いたくなったら、`config/ai_config.json` の
> `"provider"` を `"stability"` に変えて `.env` にキーを書けば切り替わります。普段は気にしなくてOKです。
