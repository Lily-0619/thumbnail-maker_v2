# AI画像生成 やり方説明書(初心者向け)

サムネイルの「**背景**」と「**キャラの後方エフェクト**」をAIで自動生成できるようになりました。
この説明書は、**プログラミングがわからなくても**進められるように書いています。
上から順番にやれば大丈夫です。

---

## 1. これは何?(できるようになること)

- アプリの **Node(拠点名)を入力 → ボタンを押すだけ** で、拠点名から連想される
  **リアルダークファンタジー調の背景** をAIが描いてくれます。
- 同時に、キャラの後ろに置く **後方エフェクト(炎・氷・雷など)** も
  **透過PNG** で生成され、自動でアプリにセットされます。
- 生成された画像はフォルダに保存されるので、あとから何度でも使い回せます。
  - 背景: `assets/backgrounds/ai/`
  - エフェクト: `assets/effects/ai/`

```
[拠点名を入力] ──→ [✨ Generate BG + Effect ボタン] ──→ AIが2枚同時に生成
                                                          │
                            背景 → assets/backgrounds/ai/ に保存 & 自動セット
                            効果 → assets/effects/ai/   に保存 & 自動セット
                                                          │
                                              プレビューに自動反映 → Export PNG
```

---

## 2. あなたが手作業でやること一覧(チェックリスト)

| いつ | やること | かかる時間 |
|---|---|---|
| 最初に1回だけ | ① OpenAIのアカウント登録とAPIキー取得 | 10分くらい |
| 最初に1回だけ | ② OpenAIに支払い方法を登録し、クレジットをチャージ($5〜でOK) | 5分くらい |
| 最初に1回だけ | ③ `.env` ファイルを作ってAPIキーを貼り付ける | 2分 |
| 最初に1回だけ | ④ 動作確認コマンドを1回実行 | 1分 |
| 任意 | ⑤ エフェクトの見本画像を `material/サンプル/` に置く(置くと見本に寄せてくれる) | 数分 |
| 毎回 | アプリで拠点名を入れてボタンを押す | 数秒 |

①〜④が終われば、あとは**普段はボタンを押すだけ**です。

---

## 3. 手順① OpenAIのAPIキーを取る

「APIキー」とは、AIを呼び出すための**あなた専用の合言葉**です。

1. ブラウザで https://platform.openai.com/ を開く
   (※ ChatGPTのアカウントと同じものでログインできます。なければ「Sign up」で新規登録)
2. ログイン後、https://platform.openai.com/api-keys を開く
3. 「**+ Create new secret key**」ボタンを押す
4. 名前は何でもOK(例: `thumbnail-maker`)→「Create secret key」
5. `sk-` から始まる長い文字列が表示されるので、**必ずこの画面でコピー**して
   メモ帳などに一時保存する
   ⚠️ **この画面を閉じると二度と表示されません**。コピーし忘れたら、作り直せばOKです。

### 手順② 支払い設定(これをしないと生成できません)

1. https://platform.openai.com/settings/organization/billing を開く
2. 「Add payment details」でクレジットカードを登録
3. クレジットを購入(**最低の$5で十分**。背景1枚あたり数円〜10円程度の目安なので、$5で数十〜数百枚作れます)
   ※ 正確な料金は https://platform.openai.com/docs/pricing で「gpt-image-1」を確認してください
   ※ 「Auto recharge(自動チャージ)」は**OFFのまま**にしておくと使いすぎ防止になります

> 🔐 **APIキーの注意(重要)**
> - APIキーは**絶対に人に教えない・SNSに貼らない・Gitにアップしない**
> - もし漏れたら https://platform.openai.com/api-keys でそのキーを削除(Revoke)すれば無効化できます

---

## 4. 手順③ `.env` ファイルを作る

APIキーをアプリに教えるためのファイルを作ります。

1. アプリのフォルダ(`main.py` がある場所)を開く
2. そこにある **`.env.example`** というファイルを**コピー**する
3. コピーしたファイルの名前を **`.env`** に変更する(ピリオドから始まる名前です)
   - Windowsで「拡張子を変更すると使えなくなる可能性が…」と出たら「はい」でOK
4. `.env` をメモ帳で開いて、こうなるようにAPIキーを貼り付ける:

```
OPENAI_API_KEY=sk-ここにコピーしたキーを貼る
```

5. 上書き保存して閉じる

> 💡 `.env` は `.gitignore` に登録済みなので、Gitにアップされる心配はありません。

---

## 5. 手順④ 動作確認

コマンドプロンプト(またはアプリのフォルダで `cmd`)で以下を実行します。
**この確認コマンドは無料**です(AIは呼び出しません)。

```bat
cd /d D:\bdm-thumbnail_app_v02
.\.venv\Scripts\python.exe -m core.ai_image check
```

「APIキー(.env) : OK」と出れば準備完了です。

試しに1枚生成してみたいときは(※ここからは数円かかります):

```bat
.\.venv\Scripts\python.exe -m core.ai_image bg "Ehwaz Hill"
.\.venv\Scripts\python.exe -m core.ai_image effect fire
```

`assets/backgrounds/ai/` と `assets/effects/ai/` にPNGが保存されたら成功です。

---

## 6. 普段の使い方(アプリ)

1. いつもどおり `起動.bat` でアプリを起動
2. **Node(拠点名)** を入力 or プルダウンから選ぶ
3. 左側の「**🤖 AI Generate**」セクションで:
   - **Effect type** でエフェクトの種類を選ぶ
     (fire / ice / lightning / dark / holy / flower / butterfly / blue_purple_magic)
   - 「**✨ Generate BG + Effect (AI)**」を押す → 背景とエフェクトが**同時に**生成されます
   - 片方だけ作り直したいときは「BG only」「Effect only」
4. 10〜60秒くらい待つと、生成された画像が自動でセットされてプレビューに反映されます
5. 気に入らなければもう一度ボタンを押せば**別の画像**が生成されます(毎回少しずつ違うものが出ます)
6. あとはいつもどおり「📤 Export PNG」

> 💡 過去に生成した画像は消えずに `assets/backgrounds/ai/`・`assets/effects/ai/` に
> たまっていくので、「Select Background」「Select Effect」で選び直すこともできます。

---

## 7. エフェクトの見本画像を参考にさせる(任意)

手持ちの後方エフェクトのサンプルを見本として渡すと、**その雰囲気に寄せて**生成してくれます。

1. `material/サンプル/` フォルダの中に、エフェクト種類と同じ名前のフォルダを作る
   ```
   material/サンプル/fire/見本1.png
   material/サンプル/ice/見本.png
   ```
   または、ファイル名を種類名で始めて直接置いてもOK:
   ```
   material/サンプル/fire_見本.png
   ```
2. あとは普通に「Effect only」などで生成するだけ。見本があれば自動で使われます。

- `material/sample/` や `material/samples/` という名前でも認識します
- 見本を使いたくないときは `config/ai_config.json` の `"use_sample_reference"` を `false` に

---

## 8. 生成される絵柄を調整したいとき

プロンプト(AIへの指示文)はコードとは別のファイルにまとめてあります。
**メモ帳で開いて文章を書き換えるだけ**で調整できます。

### `config/ai_prompts.json`

- `background.template` … 背景の基本指示文(「リアルダークファンタジー」の指定はここ)
- `background.node_hints` … **拠点ごとの追加描写**。全拠点ぶん登録済みですが、自由に書き換え・追加OK
  ```json
  "Ehwaz Hill": "A windswept grassy hill at dusk, ancient weathered runestones..."
  ```
- `effect.types` … エフェクト種類ごとの描写。**新しい種類をここに追加すると、アプリのドロップダウンにも自動で出ます**

### `config/ai_config.json`

- `"quality"` … `low`(安い・粗い)/ `medium`(おすすめ)/ `high`(きれい・高い)
- `"provider"` … 生成サービスの切り替え(下の章を参照)

※ JSONファイルは「`"` や `,` を消してしまう」と壊れるので、**文章の中身だけ**書き換えてください。

---

## 9. お金をかけたくない場合(上級者向け・任意)

OpenAI以外も使えるようにしてあります。`config/ai_config.json` の `"provider"` を書き換えます。

| provider | 必要なもの | 特徴 |
|---|---|---|
| `openai`(初期設定) | OpenAI APIキー | 一番簡単。エフェクトの透過PNGも直接生成できる。**おすすめ** |
| `stability` | Stability AI APIキー(`.env` の `STABILITY_API_KEY`) | Stable Diffusion公式API |
| `sdwebui` | 自分のPCにStable Diffusion WebUI(AUTOMATIC1111)導入済み | **無料**だが高性能GPUが必要 |

`sdwebui` を使う場合は、WebUI側の `webui-user.bat` の `COMMANDLINE_ARGS` に `--api` を追加して起動しておいてください。
※ stability / sdwebui ではエフェクトを「黒背景で生成 → 自動で透過変換」します。光り物(炎・雷など)はきれいに抜けますが、openaiの透過生成のほうが確実です。

---

## 10. よくあるエラーと対処法

| 出るメッセージ | 原因 | 対処 |
|---|---|---|
| APIキーが設定されていません | `.env` がない/中身が空 | 手順③をやり直す。ファイル名が `.env.txt` になっていないか確認 |
| OpenAI APIキーが無効です | キーの貼り間違い | `.env` を開いて `sk-` から最後までコピーされているか確認 |
| 利用制限に達しました (429) | クレジット残高切れ | Billingページで残高を確認してチャージ |
| 接続できません | ネット未接続 | Wi-Fi/LANを確認 |
| タイムアウトしました | 混雑 | 少し待ってもう一度ボタンを押す |
| WebUIに接続できません | sdwebui設定でWebUI未起動 | WebUIを `--api` 付きで起動。使わないなら provider を `openai` に戻す |

困ったら、まず確認コマンド(無料)を実行すると原因がわかりやすいです:
```bat
.\.venv\Scripts\python.exe -m core.ai_image check
```

---

## 11. 今回追加されたファイル(参考)

| ファイル | 役割 | 触ってOK? |
|---|---|---|
| `core/ai_image.py` | AI生成の本体プログラム | 触らない |
| `config/ai_config.json` | 画質・サービスの設定 | 触ってOK |
| `config/ai_prompts.json` | AIへの指示文(プロンプト) | 触ってOK |
| `.env.example` | APIキー設定の見本 | コピーして使う |
| `.env`(自分で作る) | APIキー本体 | **人に見せない** |
| `assets/backgrounds/ai/` | 生成された背景の保存先 | 不要なものは削除OK |
| `assets/effects/ai/` | 生成されたエフェクトの保存先 | 不要なものは削除OK |
