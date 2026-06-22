# AI画像生成 やり方説明書(初心者向け・全部ローカルで動く版 / ComfyUI)

サムネイルの「**背景**」と「**キャラの後方エフェクト**」をAIで自動生成できるようになりました。

- **APIキー不要・登録不要・料金は一切かかりません**(全部あなたのPCの中で動きます)
- 使うのは無料ソフト「**ComfyUI**」です(あなたのPCにはすでに `E:\AI\ComfyUI-master` がありますが、後述のとおり起動できる状態に整える必要があります)
- この説明書は、プログラミングがわからなくても進められるように書いています。上から順番にやれば大丈夫です

> あなたのPCは **NVIDIA GeForce RTX 3060 Ti(VRAM 8GB)** なので、生成はサクサク動きます👍

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
[アプリ起動時に ComfyUI 接続確認(ローカル / http://127.0.0.1:8188)]
                 ↑ 未起動なら設定に従って裏で自動起動
[拠点名を入力] ──→ [✨ Generate BG + Effect ボタン] ──→ AIが2枚同時に生成
                                                          │
                            背景 → assets/backgrounds/ai/ に保存 & 自動セット
                            効果 → assets/effects/ai/   に保存 & 自動セット
                                                          │
                                              プレビューに自動反映 → Export PNG
```

---

## 2. 必要なPCスペック(あなたのPCはOKです)

| 項目 | 目安 | あなたのPC |
|---|---|---|
| グラフィックボード(GPU) | NVIDIA製・VRAM 4GB以上で動作、8GB以上で快適 | RTX 3060 Ti 8GB ✅ |
| 空きディスク容量 | 10GB以上(本体+AIモデル) | 要確認 |

---

## 3. あなたが手作業でやること一覧(チェックリスト)

| いつ | やること | かかる時間 |
|---|---|---|
| 最初に1回だけ | ① ComfyUI(起動できる版)を用意する | 15〜30分(ほぼDL待ち) |
| 最初に1回だけ | ② ダークファンタジー向きのモデルを入れる | 15分(DL待ち) |
| 最初に1回だけ | ③ ComfyUIを起動して動作確認 | 5分 |
| 任意 | ④ エフェクトの見本画像を `material/サンプル/` に置く | 数分 |
| **毎回** | アプリを起動する(ComfyUIは必要に応じて自動起動) | 数秒の操作 |

> アプリ側のプログラムは**すでに完成しています**。あなたがやるのは「ComfyUIを動く状態にする」ことと、`config/ai_config.json` の起動パスを自分のPCに合わせることです。

---

## 4. 手順① ComfyUI(起動できる版)を用意する

いまPCにある `E:\AI\ComfyUI-master` は「プログラムを置いただけ」で、**そのままでは起動できません**(起動用の部品とAIモデルが入っていない状態です)。初心者の方は、起動ボタン付きの**公式ポータブル版**を入れるのが一番カンタンで確実です。

1. ブラウザで ComfyUI 公式の配布ページを開く:
   https://github.com/comfyanonymous/ComfyUI/releases
2. 一番上(最新)の **Assets** を開き、**`ComfyUI_windows_portable_nvidia.7z`**(NVIDIA用)をダウンロード
   - 数GBあります。ダウンロードに時間がかかります
3. ダウンロードした `.7z` ファイルを展開する
   - `.7z` は標準のWindowsでは開けないことがあります。開けない場合は無料ソフト **7-Zip**( https://7-zip.org/ )を入れてから右クリック→「7-Zip」→「ここに展開」
   - ⚠️ 展開先は**日本語やスペースを含まない場所**にしてください(例: `E:\AI\ComfyUI_windows_portable`)
4. 展開すると中に **`run_nvidia_gpu.bat`** というファイルがあります(これが起動ボタンです)

> 💡 すでにComfyUIを自分で起動できる方は、この手順①は飛ばして、いまの `E:\AI\ComfyUI-master` をそのまま使ってOKです(その場合は手順②でモデルだけ入れてください)。ポート番号を変えている場合だけ、`config/ai_config.json` の `comfyui.url` を合わせてください(標準は `http://127.0.0.1:8188`)。

---

## 5. 手順② ダークファンタジー向きのモデルを入れる

ComfyUIは**AIモデル(checkpoint)が無いと画像を1枚も作れません。** 1個だけ入れればOKです。

1. 無料サイト Civitai( https://civitai.com/ )で好みのモデルを探す(無料登録が必要な場合あり)
   - 初心者へのおすすめ: 「**DreamShaper**」(リアル寄りファンタジーが得意で軽い)
   - 検索して、`.safetensors` 形式のファイルをダウンロード
2. ダウンロードしたファイルを、ComfyUIの次のフォルダに入れる:
   ```
   （ポータブル版の場合）ComfyUI_windows_portable\ComfyUI\models\checkpoints\
   （E:\AI\ComfyUI-master を使う場合) E:\AI\ComfyUI-master\models\checkpoints\
   ```
3. これだけでOKです。どのモデルを使うかはアプリが自動で見つけます。
   - 複数入れて特定の1個を指定したいときは、`config/ai_config.json` の `comfyui.ckpt_name` にファイル名(例 `dreamshaper_8.safetensors`)を書きます。空のままなら自動で最初の1個を使います。

> 💡 「SDXL」と書かれたモデルは高画質ですが少し重いです。使う場合は
> `config/ai_config.json` の `comfyui` の `"width": 768, "height": 432` を `1344` と `768` に上げると効果的です(8GB VRAMなら動きます)。

---

## 6. 手順③ ComfyUIを起動して動作確認

1. **ComfyUIを起動する**
   - ポータブル版なら **`run_nvidia_gpu.bat`** をダブルクリック
   - 黒い画面が出て、最後に `To see the GUI go to: http://127.0.0.1:8188` のような表示が出れば起動成功です
   - **この黒い画面は閉じないでください**(閉じると連携が切れます)
2. サムネイルアプリのフォルダで、コマンドプロンプト(またはPowerShell)から動作確認:

```
cd /d E:\bdm-thumbnail_app_v02
.\.venv\Scripts\python.exe -m core.ai_image check
```

次のように全部OKになっていれば準備完了です:

```
・provider 設定           : comfyui
・ComfyUI接続(http://127.0.0.1:8188) : OK
・モデル(checkpoint)      : OK(あなたのモデル名)
```

試しに1枚生成してみる場合(無料です):

```
.\.venv\Scripts\python.exe -m core.ai_image bg "Ehwaz Hill"
.\.venv\Scripts\python.exe -m core.ai_image effect fire
```

`assets/backgrounds/ai/` と `assets/effects/ai/` にPNGが保存されたら成功です。

### アプリ起動時の自動起動設定

サムネイルアプリ起動時にComfyUIも自動起動したい場合は、`config/ai_config.json` の `comfyui` にある次の項目を確認してください。

```json
"auto_start": true,
"python_path": "E:/AI/ComfyUI-master/.venv/Scripts/python.exe",
"main_path": "E:/AI/ComfyUI-master/main.py",
"working_dir": "E:/AI/ComfyUI-master"
```

別の場所にComfyUIを置いている場合は、この3つのパスだけ自分のPCに合わせて変更します。

---

## 7. 普段の使い方(アプリ)

1. いつもどおり `起動.bat` でサムネイルアプリを起動
   - ComfyUIがすでに起動済みなら、そのまま使います
   - 起動していなければ、`config/ai_config.json` の設定に従って裏で起動します
   - 自動起動がうまくいかない場合は、手動でComfyUIを起動してからアプリを使ってください
2. **Node(拠点名)** を入力 or プルダウンから選ぶ
3. 左側の「**🤖 AI Generate**」セクションで:
   - **Effect type** でエフェクトの種類を選ぶ
     (fire / ice / lightning / dark / holy / flower / butterfly / blue_purple_magic)
   - 「**✨ Generate BG + Effect (AI)**」を押す → 背景とエフェクトが**同時に**生成されます
   - 片方だけ作り直したいときは「BG only」「Effect only」
4. 生成が終わると自動でセットされ、プレビューに反映されます
   (時間はGPU性能次第。目安: RTX 3060 Ti なら10〜30秒/枚)
5. 気に入らなければもう一度ボタンを押せば**別の画像**が出ます
6. あとはいつもどおり「📤 Export PNG」

> 💡 過去に生成した画像は `assets/backgrounds/ai/`・`assets/effects/ai/` にたまっていくので、
> 「Select Background」「Select Effect」で選び直すこともできます。

---

## 8. エフェクトの見本画像を参考にさせる(任意)

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

**見本にどれだけ寄せるか**は `config/ai_config.json` の `comfyui` 内 `"denoising_strength"` で調整できます:
- `0.6` … 見本にかなり近い
- `0.7` … 標準(見本の雰囲気を残しつつ変化)
- `0.8` … 見本から大きく変化

- `material/sample/` や `material/samples/` という名前でも認識します
- 見本を使いたくないときは `"use_sample_reference"` を `false` に

---

## 9. 生成される絵柄を調整したいとき

プロンプト(AIへの指示文)はコードとは別のファイルにまとめてあります。
**メモ帳で開いて文章を書き換えるだけ**で調整できます。

### `config/ai_prompts.json`

- `background.template` … 背景の基本指示文(「リアルダークファンタジー」の指定はここ)
- `background.node_hints` … **拠点ごとの追加描写**。全拠点ぶん登録済みですが、自由に書き換え・追加OK
  ```json
  "Ehwaz Hill": "A windswept grassy hill at dusk, ancient weathered runestones..."
  ```
- `effect.types` … エフェクト種類ごとの描写。**新しい種類をここに追加すると、アプリのドロップダウンにも自動で出ます**

### `config/ai_config.json`(画質・速度の調整 / `comfyui` の部分)

| 設定 | 意味 | 目安 |
|---|---|---|
| `ckpt_name` | 使うモデル名 | 空=自動 / 指定するならファイル名 |
| `width` / `height` | 生成サイズ | SD1.5系: 768×432 / SDXL系: 1344×768 |
| `steps` | 描き込み回数 | 20=速い 〜 35=丁寧 |
| `sampler_name` / `scheduler` | 生成アルゴリズム | 通常はそのままでOK |
| `auto_start` | アプリ起動時にComfyUIを自動起動するか | `true` |
| `python_path` / `main_path` / `working_dir` | 自動起動に使うComfyUIの場所 | 自分のPCのComfyUIに合わせる |
| `startup_timeout_seconds` | 自動起動後の接続待ち時間 | 初回起動が遅いなら増やす |
| `timeout_seconds` | 待ち時間の上限 | hiresで時間が倍増。遅いなら600などに増やす |
| `hires.enabled` | 背景の高解像度化（ぼやけ防止） | `true`=くっきり / `false`=従来・速い |
| `hires.target_width` | 仕上がりの横幅 | `1536`標準 / `1920`が理想 / 落ちるなら`1280` |
| `hires.mode` | 拡大方式 | `latent`=モデル不要・標準 / `model`=ESRGAN等が必要 |
| `hires.denoise` | 2パス目の描き直し量 | 0.3=元に忠実 〜 0.6=ディテール増 |

> **背景のぼやけ対策（hires）**：背景は `width/height`（例 768×432）で作られ、合成時に 1920×1080 へ
> 引き伸ばされるためぼやけます。`hires.enabled` を `true` にすると、生成側で `target_width` まで
> 描き直して大きく作るので、仕上がりがくっきりします（標準でON）。GPUメモリが足りずに落ちる場合は
> `target_width` を下げてください。

※ JSONファイルは「`"` や `,` を消してしまう」と壊れるので、**文章や数字の中身だけ**書き換えてください。

---

## 10. よくあるエラーと対処法

| 出るメッセージ・症状 | 原因 | 対処 |
|---|---|---|
| ComfyUIに接続できません | ComfyUIを起動していない / 自動起動パスが違う | 手動で起動するか、`config/ai_config.json` の `python_path` / `main_path` / `working_dir` を確認 |
| モデル(checkpoint)が見つかりません | モデル未配置 | 手順②で `models\checkpoints\` に `.safetensors` を入れる |
| CUDA out of memory(黒い画面に赤字) | GPUメモリ不足 | `width/height` または `hires.target_width` を下げる。SDXLなら軽いSD1.5系モデルに変える |
| AI背景がぼやける | 引き伸ばし（hiresが無効/目標が低い） | `comfyui.hires.enabled` を `true`、`target_width` を 1536〜1920 に |
| タイムアウトしました | 生成が遅い | `config/ai_config.json` の `comfyui` の `timeout_seconds` を 600 に増やす |
| エフェクトの抜けが汚い | 暗い色は透明扱いになるため | 炎・雷など発光系は得意。暗い色主体は `effect.types` の文に「bright」「glowing」を足す |
| ポートが違うと言われる/つながらない | ComfyUIを別ポートで起動している | 黒い画面に出るURLを見て、`config/ai_config.json` の `comfyui.url` をそれに合わせる |

困ったら、まず確認コマンドを実行すると原因がわかりやすいです:
```
.\.venv\Scripts\python.exe -m core.ai_image check
```

---

## 11. 今回のファイル(参考)

| ファイル | 役割 | 触ってOK? |
|---|---|---|
| `core/ai_image.py` | AI生成の本体プログラム | 触らない |
| `config/ai_config.json` | 接続先・画質などの設定 | 触ってOK |
| `config/ai_prompts.json` | AIへの指示文(プロンプト) | 触ってOK |
| `assets/backgrounds/ai/` | 生成された背景の保存先 | 不要なものは削除OK |
| `assets/effects/ai/` | 生成されたエフェクトの保存先 | 不要なものは削除OK |

> 補足: ComfyUI以外に、AUTOMATIC1111 / Stability AI / OpenAI にも対応しています。`config/ai_config.json` の
> `"provider"` を切り替えれば使えますが、普段は `comfyui` のままでOKです。
