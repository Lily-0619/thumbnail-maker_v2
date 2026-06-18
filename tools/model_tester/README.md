# モデル / LoRA 比較ツール

同じプロンプト・同じシードを **「選んだ複数モデル(checkpoint) × 選んだ複数LoRA」** で
一括生成し、**行=モデル / 列=LoRA** のグリッドに並べて見比べるための独立ツールです。
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

1. **接続 / 一覧更新** … ComfyUI に接続し、利用可能なモデルと LoRA の一覧を取得します。
2. **プロンプト / ネガティブ** … 全セル共通で使う文を入力します。
3. **steps / cfg / 幅 / 高さ / seed / LoRA強度** … 生成パラメータ。
   - **「全セルで同じシードを使う（推奨）」** をオンにすると、全セルが同じ seed になり
     モデル・LoRA の違いだけを公平に比較できます。
4. **モデル** … 比較したい checkpoint をチェック（複数可）。
5. **LoRA** … 比較したい LoRA をチェック（複数可）。先頭の **「（LoRAなし）」** は
   LoRA を使わない基準列です。LoRA が未インストールでも、これだけでモデル比較ができます。
6. **▶ 一括生成** … 「モデル×LoRA」の全組み合わせを順に生成し、グリッドに並べます。
   各セルをクリックすると拡大表示。

生成画像は `outputs/model_tester/<実行日時>/` に
`モデル__LoRA__強度__seed.png` の名前で保存されます（**「保存先を開く」** ボタンで開けます）。

## モデル / LoRA を増やすには

ComfyUI の `models/checkpoints/`（モデル）や `models/loras/`（LoRA）に
`.safetensors` を置きます。

**重要：ComfyUI は「起動した時点」のフォルダしか見ません。** 起動したまま
ファイルを足しても、`接続 / 一覧更新` だけでは出てこないことがあります
（ComfyUI 側が一覧をキャッシュしているため）。

そこで、ファイルを足したら **「ComfyUI 再起動（モデル追加後）」** ボタンを
押してください。ComfyUI を一度落として起動し直し、フォルダを再スキャンして
最新の一覧に更新します（`auto_start` が有効な場合）。

- `auto_start` が無効な場合は、ComfyUI を手動で終了→起動してから
  `接続 / 一覧更新` を押してください。
- 再起動ボタンは、ポート（既定 `8188`）を使っている ComfyUI を停止して
  起動し直します。比較ツール自身を巻き込んで落とすことはありません。

## 仕組み（ComfyUI ワークフロー）

LoRA を選んだセルでは、`CheckpointLoaderSimple` と `CLIPTextEncode`/`KSampler` の間に
`LoraLoader` ノードを挿入し、`strength_model` / `strength_clip` に LoRA強度を渡しています。
「（LoRAなし）」のセルは素の checkpoint のみで生成します。

## ファイル

| ファイル | 役割 |
|---|---|
| `model_tester_app.py` | エントリーポイント（GUI・比較グリッド） |
| `comfy_client.py` | ComfyUI 接続・一覧取得・LoRA対応ワークフロー・生成 |
| `config_loader.py` | `ai_config.json` の探索・読み込み |

## 既知の制限（今後の拡張候補）

- 多数のモデル×LoRAを選ぶとグリッドが横に広がります（横スクロールは未対応）。
- LoRA強度は全LoRA共通の1値です（LoRAごとの強度比較は未対応）。
- img2img・複数LoRA重ねがけ・サンプラー比較は未対応（必要なら追加します）。
