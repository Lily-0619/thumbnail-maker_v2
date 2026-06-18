# LoRA学習 やり方説明書（初心者向け・全部ローカルで無料 / kohya_ss）

自分の好きなキャラ・画風・エフェクトを **AIに覚えさせる小さな追加データ＝LoRA** を、
自分のPCだけで（無料・APIキー不要で）作るための説明書です。

- できあがった LoRA（`.safetensors`）を ComfyUI に入れると、サムネアプリのAI生成や
  「🎨 モデル / LoRA 比較」ツールでそのまま使えます。
- プログラミングの知識がなくても、上から順にやれば進められます。

> あなたのPCは **NVIDIA GeForce RTX 3060 Ti（VRAM 8GB）**。
> **SD1.5 系の LoRA 学習なら十分に動きます👍**（SDXL の LoRA は重いので、まずは SD1.5 から）。

---

## 0. 全体の流れ（先に地図を見る）

```
[① kohya_ss を入れる] ── 最初の1回だけ（DL待ち中心）
        │
[② 学習素材を用意]   ── 画像10〜30枚 ＋ 各画像の説明文(.txt)
        │
[③ フォルダを作法どおり並べる]  例: train/10_mychar/ に画像と.txt
        │
[④ kohya_ss のGUIで設定 → 学習実行]  ── RTX 3060 Ti で数十分〜
        │
[⑤ 出来た .safetensors を ComfyUI\models\loras\ に置く]
        │
[⑥ サムネアプリ / モデル比較ツールで効きを確認]
```

---

## 1. LoRAって何？（ざっくり）

- **モデル本体（checkpoint）** は「絵を描く脳みそ」。サイズが大きい（数GB）。
- **LoRA** は「脳みそにかぶせる小さなメモ」。サイズが小さい（数MB〜200MB程度）。
- 「このキャラの顔」「この画風」「この光り方のエフェクト」などを**少ない枚数で追加学習**できます。
- 使うときは **checkpoint ＋ LoRA** の組み合わせ。LoRAは付け外し・強さ調整が自由です。

LoRAで作れるものの例（このアプリ向け）:
- 特定キャラの立ち絵スタイル
- 共通の画風（ダークファンタジー寄りの統一感）
- 後方エフェクトの作風（炎・魔法陣などの“あなたの好きな見た目”）

---

## 2. 必要なもの（チェックリスト）

| いつ | やること | 目安時間 |
|---|---|---|
| 最初に1回 | ① kohya_ss を導入（依存も自動で入る） | 20〜40分（DL待ち） |
| 最初に1回 | ベースの SD1.5 モデルを1個用意 | 既にあればスキップ |
| 毎回 | ② 学習素材（画像＋説明文）を用意 | 30分〜 |
| 毎回 | ④ 設定して学習を回す | 30分〜数時間 |

必要スペック:
- GPU: NVIDIA・VRAM 6GB以上（**8GBのあなたはOK**）
- 空きディスク: 10GB以上（学習中の一時ファイル含む）

---

## 3. 手順① kohya_ss を入れる

kohya_ss は LoRA 学習の定番ツールで、ブラウザGUIから操作できます。

1. 事前に **Git** と **Python 3.10** を入れておく（未導入なら）。
   - Git: https://git-scm.com/download/win
   - Python 3.10: https://www.python.org/downloads/release/python-31011/
     （インストール時 **「Add python.exe to PATH」にチェック**）
2. kohya_ss を取得する。コマンドプロンプトで、**日本語やスペースを含まない場所**へ:
   ```
   cd /d E:\AI
   git clone https://github.com/bmaltais/kohya_ss.git
   cd kohya_ss
   ```
3. セットアップを実行（依存ライブラリと専用の仮想環境を自動構築）:
   ```
   setup.bat
   ```
   - メニューが出たら通常はインストール（案内に従う）。数GBのDLがあるので待ちます。
4. 起動:
   ```
   gui.bat
   ```
   - 最後に `http://127.0.0.1:7860` のようなURLが出ます。ブラウザで開くとGUIが使えます。

> 💡 ベースモデル（SD1.5の checkpoint）は、サムネアプリで使っているものと同じでOK。
> 置き場所はどこでも良いですが、`E:\AI\ComfyUI-master\models\checkpoints\` のものを指定すれば使い回せます。

---

## 4. 手順② 学習素材を用意する（ここが一番大事）

LoRAの出来は**素材の質**でほぼ決まります。

### 画像
- 枚数: **10〜30枚**程度（まずは15枚前後が扱いやすい）
- 覚えさせたい対象（キャラ・画風・エフェクト）が**一貫**していること
- 背景・ポーズ・角度は**ほどよくバラける**と過学習しにくい
- 解像度は **512px以上**（SD1.5は512基準）。極端に小さい画像は避ける
- 形式: png / jpg

### 説明文（キャプション）
- 各画像と**同じ名前の .txt** を用意し、中身に英語タグで内容を書く
  ```
  mychar01.png  ←→  mychar01.txt
  ```
  例（.txt の中身）:
  ```
  mychar, 1girl, silver hair, red dress, looking at viewer, dark background
  ```
- 先頭に **トリガーワード**（呼び出し用の固有語、例 `mychar`）を入れるのがコツ。
- タグ付けが面倒なら、kohya_ss の **Utilities → Captioning（WD14 Captioning）** で自動付与できます。
  自動付与後、先頭にトリガーワードを足すと安定します。

---

## 5. 手順③ フォルダを作法どおりに並べる

kohya_ss は **フォルダ名で「繰り返し回数」と「概念名」** を読み取ります。

```
E:\AI\train\
└─ img\
   └─ 10_mychar\          ← 「10」=1枚あたりの繰り返し回数、「mychar」=概念名
        mychar01.png
        mychar01.txt
        mychar02.png
        mychar02.txt
        ...
```

- フォルダ名は **`<繰り返し回数>_<トリガーワード>`**。例 `10_mychar`。
- 目安: 総ステップ数 ≒ 画像枚数 × 繰り返し回数 × epoch ÷ batch size。
  - 例: 15枚 × 10 × 10epoch ÷ 1 = 1500ステップ（ちょうど良いくらい）
- （任意）`reg\`（正則化画像）フォルダも作れますが、最初は無しでOK。
- 出力用に `E:\AI\train\model\` も作っておく。

---

## 6. 手順④ kohya_ss で設定して学習する

`gui.bat` のGUIで、上のタブから **「LoRA」** を選びます。

### 基本設定（Source model / Folders）
- **Model Quick Pick / Pretrained model**: ベースの SD1.5 checkpoint を指定
- **Image folder**: `E:\AI\train\img`（※ `10_mychar` の**親**フォルダを指定）
- **Output folder**: `E:\AI\train\model`
- **Output name**: `mychar_v1`（出来上がるファイル名）

### パラメータ（RTX 3060 Ti / VRAM 8GB の目安）
| 項目 | 値 | メモ |
|---|---|---|
| Train batch size | 1 | 8GBなら基本1 |
| Epoch | 10 | 多すぎると過学習 |
| Mixed precision | fp16 | VRAM節約 |
| Save precision | fp16 | |
| Network Rank (dim) | 16〜32 | キャラなら16〜32 |
| Network Alpha | dimと同じか半分 | 例 dim16 / alpha16 |
| Learning rate | 1e-4 | まずは標準 |
| LR scheduler | cosine | |
| Optimizer | AdamW8bit | VRAM節約に有効 |
| Resolution | 512,512 | SD1.5基準 |
| Gradient checkpointing | ON | **8GBではほぼ必須** |
| xformers (cross attention) | ON | VRAM節約・高速化 |
| Cache latents | ON | 速くなる |

設定したら **「Start training」**。コマンド画面に進捗（ステップ/loss）が出ます。
RTX 3060 Ti なら 1000〜1500ステップで**数十分**が目安。

> 💡 **VRAM不足（CUDA out of memory）が出たら**: Resolution を 512→448、dim を下げる、
> Gradient checkpointing と xformers が ON か確認、他のGPUアプリ（ComfyUI/Ollama/ゲーム）を閉じる。

---

## 7. 手順⑤ 出来たLoRAをアプリで使う

1. `E:\AI\train\model\` に `mychar_v1.safetensors` ができます。
2. これを **ComfyUIのLoRAフォルダ**へコピー:
   ```
   E:\AI\ComfyUI-master\models\loras\
   （ポータブル版なら ComfyUI_windows_portable\ComfyUI\models\loras\）
   ```
3. **確認のしかた**:
   - ランチャーの **🎨 モデル / LoRA 比較** を起動 → 「接続 / 一覧更新」→ 一覧に出てくる
   - 「（LoRAなし）」列と並べて生成し、効き具合・最適な強度を見比べる
   - プロンプトには**トリガーワード**（例 `mychar`）を入れると効果が出ます
4. サムネ本体のAI生成でこのLoRAを常用したい場合は、ComfyUIワークフロー側でLoRAを使う形になります（本体は現状LoRA指定UIが無いため、比較ツールで詰めた設定を活用するのがおすすめ）。

---

## 8. うまくいかない時（よくある症状）

| 症状 | 原因 | 対処 |
|---|---|---|
| CUDA out of memory | VRAM不足 | 解像度/ dim を下げる、gradient checkpointing・xformers をON、他アプリを閉じる |
| 全然似ない | 学習不足・素材バラつき | epoch/繰り返しを増やす、素材を統一、トリガーワードを徹底 |
| 何を描いても同じ顔（過学習） | 学習しすぎ | epoch/ステップを減らす、lrを下げる、dimを下げる、素材を増やす |
| 色や構図が崩れる | alpha/lr が強い | alphaをdimの半分に、lrを 1e-4→5e-5 に |
| LoRAが一覧に出ない | 置き場所違い | `ComfyUI\models\loras\` に置く → 比較ツールで「接続/一覧更新」 |
| setup.bat でエラー | Python/Git未導入・版違い | Python 3.10 と Git を入れ直す（PATH付き） |

---

## 9. コツ（品質を上げる小ワザ）

- **素材ファースト**: 枚数より「対象が一貫して・背景がほどよく多様」が効く。
- **トリガーワードはユニークに**: 一般単語(`girl`等)でなく `mychar` のような造語に。
- **まず控えめに学習 → 比較ツールで強度を探る**: 学習を強くしすぎず、使用時に strength で調整。
- **段階保存**: epochごとに保存すると、過学習する前の“ちょうど良い”版を選べる。
- **エフェクトLoRA**: 後方エフェクト用なら、透過/黒背景の素材で「光り方・形」を一貫させる。

---

## 10. 参考リンク

- kohya_ss（学習ツール本体）: https://github.com/bmaltais/kohya_ss
- LoRAモデル配布の例（素材研究用）: https://civitai.com/
- 関連: [AI画像生成_やり方説明書.md](AI画像生成_やり方説明書.md) / [操作説明書.md](操作説明書.md)

> まとめ: **SD1.5・512解像度・dim16前後・gradient checkpointing ON** から始めれば、
> RTX 3060 Ti（8GB）でも安定して LoRA を作れます。最初の1本ができたら、
> 比較ツールで強度と組み合わせを詰めていきましょう。
