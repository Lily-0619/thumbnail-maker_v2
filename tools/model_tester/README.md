# X / Y / Z プロット比較ツール

AUTOMATIC1111 の「X/Y/Z plot」と同じ考え方で、**X 軸=列 / Y 軸=行 / Z 軸=グリッドを複数枚**に
割り当て、Checkpoint・LoRA・Steps・CFG・Sampler・Seed・Prompt S/R などを自由に組み合わせて
一括生成し、**ラベル付きの比較グリッド画像**にまとめる独立ツールです。
本体（`ui/` `core/` `config/`）は一切変更しません。`tools/` への追加のみ。

## 起動

リポジトリのルートから:

```
python tools/model_tester/model_tester_app.py
```

Windows ではルートの `モデル比較起動.bat` をダブルクリックしてもよい。

## 前提：ComfyUI

画像生成は本体と同じく **ローカルの ComfyUI** を使います（標準 `http://127.0.0.1:8188`）。

- 接続先や自動起動の設定は本体の `ai_config.json` を流用します
  （`config/ai_config.json` → 無ければ `assets/config/ai_config.json` の順で探します）。
- `comfyui.auto_start` が `true` で `python_path` / `main_path` / `working_dir` が
  正しく設定されていれば、起動時に ComfyUI を自動起動します。
- 自動起動を使わない場合は、先に ComfyUI を起動してから
  画面の **「接続 / 一覧更新」** を押してください。

## 使い方

1. **接続 / 一覧更新** … ComfyUI に接続し、checkpoint / LoRA / VAE / アップスケーラー /
   sampler / scheduler の一覧を取得します。
2. **プロンプト / ネガティブ** … 全セル共通の文を入力します。
3. **ベース設定** … steps / cfg / 幅 / 高さ / seed / clip skip と、モデル・Sampler・Scheduler・VAE。
   *軸にしない項目の既定値*として全セルに使われます。seed を空にすると、Seed 軸を使わない限り
   全セルで同じシードに固定され、条件の違いだけを公平に比較できます。
4. **LoRA スタック** … 複数の LoRA をそれぞれ強度付きで重ねがけできます。
5. **Hires fix / アップスケール**（任意）… 下記参照。
6. **img2img**（任意）… 元画像を選ぶと img2img になり、denoise で変化量を決めます。
7. **X / Y / Z 軸** … 各軸に「種類」を選び、値を指定します（下記）。
8. **▶ プロット生成** … 全組み合わせを順に生成し、生成済みセルから順に表示。
   完了すると Z 値ごとに**ラベル付きグリッド画像**を合成して並べます（クリックで拡大）。

生成物は `outputs/model_tester/<実行日時>/` に保存されます。

- 各セル画像：`z{n}_y{n}_x{n}_seed{値}.png`
- 合成グリッド：`grid_z{n}.png`（**「保存先を開く」** ボタンでフォルダを開けます）

## 軸の種類と値の書き方

各軸（X / Y / Z）に次のどれかを割り当てられます。**「（なし）」**にするとその軸は使いません。

| 種類 | 値の入力 | 例 |
|---|---|---|
| Checkpoint | 一覧からチェック | 比較したいモデルを複数選択 |
| LoRA | 一覧からチェック | `（LoRAなし）` を含めると基準列になる |
| LoRA強度 | カンマ区切りの数値 | `0.4, 0.7, 1.0` |
| Steps | カンマ区切りの整数 | `20, 28, 35` |
| CFG Scale | カンマ区切りの数値 | `4, 7, 10` |
| Sampler | 一覧からチェック | `euler`, `dpmpp_2m` など |
| Scheduler | 一覧からチェック | `normal`, `karras` など |
| Seed | カンマ区切りの整数 | `1, 2, 3`（`-1` でランダム） |
| Clip skip | カンマ区切りの整数 | `1, 2` |
| 幅 / 高さ | カンマ区切りの整数 | `768, 1024` |
| Hires denoise | カンマ区切りの数値 | `0.3, 0.5, 0.7` |
| Hires 倍率 | カンマ区切りの数値 | `1.5, 2.0` |
| Prompt S/R（置換） | `検索語, 置換1, 置換2 …` | `knight, mage, archer` |

> **Prompt S/R** は A1111 と同じく、1 個目を検索語、2 個目以降を置換語として
> プロンプト（とネガティブ）内の該当文字列を置き換えます。
> 上の例なら `knight` を `mage` / `archer` に差し替えた 2 パターンを比較します。

## LoRA スタック（重ねがけ）

「LoRA スタック」欄で、複数の LoRA をそれぞれ強度を付けて同時適用できます。
ComfyUI 上では `LoraLoader` を直列に挿入してチェーンします。
LoRA 軸を使うと、スタック先頭の LoRA を一覧の各 LoRA に差し替えて比較します
（強度はスタック先頭の値を引き継ぎます）。

## Hires fix / アップスケール

「方式」で選びます。

- **OFF** … 1 パスのみ。
- **latent（再サンプル）** … 1 パス目の latent を `LatentUpscaleBy` で拡大し、
  2 パス目の KSampler を `Hires steps` / `Hires denoise` で回します（A1111 の Hires fix 相当）。
- **アップスケーラーモデル** … 1 パス目をデコード → `Upscaler`（ESRGAN 等）で拡大 →
  目標倍率にリサイズ → 再エンコード → 2 パス目の KSampler。`Upscaler` は接続後に
  `models/upscale_models` の一覧から選びます。

`倍率` は最終解像度の倍率、`Hires steps` は 2 パス目のステップ数、
`Hires denoise` は 2 パス目の変化量です（0.3〜0.6 が目安）。

## VAE / clip skip / img2img

- **VAE** … `（モデル付属）` のままなら checkpoint 内蔵 VAE を使用。`models/vae` の VAE を選ぶと上書き。
- **clip skip** … A1111 流（`1`=なし、`2` 以上で `CLIPSetLastLayer` を挿入）。
- **img2img** … 元画像を選ぶと `LoadImage`→`VAEEncode` で img2img になり、`denoise` で変化量を決めます。

## LoRA / モデル / VAE / アップスケーラーを増やすには

ComfyUI の各フォルダにファイルを置き、ツールの **「接続 / 一覧更新」** を押すと反映されます。

- モデル: `models/checkpoints/*.safetensors`
- LoRA: `models/loras/*.safetensors`
- VAE: `models/vae/*`
- アップスケーラー: `models/upscale_models/*.pth`（ESRGAN 系など）

## ファイル

| ファイル | 役割 |
|---|---|
| `model_tester_app.py` | エントリーポイント（GUI・X/Y/Z 軸の設定・結果表示） |
| `comfy_client.py` | ComfyUI 接続・一覧取得・フル機能ワークフロー組み立て・生成 |
| `xyz_plot.py` | 軸定義・組み合わせ展開・ラベル付きグリッド画像の合成 |
| `config_loader.py` | `ai_config.json` の探索・読み込み |

## 補足・制限

- 多数の組み合わせ（X×Y×Z）を選ぶと生成枚数が増え時間がかかります。
  64 枚を超える場合は確認ダイアログを出します。
- 結果プレビューは合成済みグリッド画像を表示します（クリックで拡大）。
  個々の高解像度画像は保存先フォルダの各セル PNG を参照してください。
- img2img を使うと初期 latent が元画像になるため、`幅 / 高さ` 軸は効きません
  （元画像の解像度が基準になります）。
