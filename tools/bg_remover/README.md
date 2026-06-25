# 背景除去ツール（bg_remover）

画像をD&D／ファイル選択で読み込み、複数のAIモデル（[rembg](https://github.com/danielgatis/rembg)）で
背景を除去して、チェッカー背景で透過を確認し、PNG（RGBA）で保存するツール。

`effect_sorter` / `base_image_sorter` と同じ独立ツール構成。コアUIは `BgRemovalPanel`
（CTkFrame）なので、独立ウィンドウにもメインアプリのタブにも埋め込める。

## セットアップ（rembg のインストール）

プロジェクトの `.venv` に入れる（GPU版・NVIDIA/CUDA前提）:

```
D:\bdm-thumbnail_app_v02\.venv\Scripts\python.exe -m pip install "rembg[gpu,cli]"
```

- CUDA が使えない環境では `rembg[cpu,cli]` にする（自動でCPUにフォールバックもする）。
- **モデルは初回実行時に自動DL**（`~/.u2net/` に数百MB〜1GB）。最初の1回だけ時間がかかる。

## 起動

```
python tools/bg_remover/bg_remover_app.py
```

Windows ではルートの `背景除去起動.bat` をダブルクリックしてもよい。

## 使い方

1. 左の **「処理する画像」エリアへ画像/フォルダをD&D**（または「＋ 画像を追加」）。サムネ一覧に貯まる
   （base_image_sorter の仕分けグリッドを流用）。
2. サムネを **クリックして対象を選択**（結果エリアに「元画像」プレビューが出る）。
3. **モデルをチェック**（複数選択でモデル比較ができる）。
4. **背景除去を実行**。進捗バーと「モデル名 (i/N)」で進行を可視化（別スレッド・初回はモデルDL待ち）。
5. **モデルごとに結果が分かれて並ぶ**（チェッカー背景で透過確認）。各プレビュー右上の **🔍 拡大** で大きく確認。
6. 気に入った結果の **💾 保存** を押すと `outputs/bg_removal/` に保存（**どのモデルを保存するか選べる**）。
   ファイル名：`{元名}_{モデル名}_{日時}_nobg.png`（必ず RGBA で透過維持）。

## 対応モデル

| rembg指定名 | 特徴 |
|---|---|
| `birefnet-general` | メイン推奨。精度◎ |
| `birefnet-massive` | 最高精度・重い |
| `isnet-general-use` | 安定系 |
| `u2net` | 軽量・速い |

## メインアプリのタブに埋め込む場合（将来）

コアは CTkFrame なので、そのまま `tabview.add(...)` に貼れる:

```python
from tools.bg_remover.bg_removal_panel import BgRemovalPanel

tab = tabview.add("背景除去")
BgRemovalPanel(tab, output_dir=...).pack(fill="both", expand=True)
```

> 注意：D&D（tkinterdnd2）は **ルートウィンドウが tkinterdnd2 対応のときだけ**有効。
> 既存メインアプリが素の `CTk()` の場合、埋め込み時はD&Dが無効になり、ドロップエリアの
> クリック→ファイル選択にフォールバックする（処理・保存は問題なく動く）。

## ファイル

| ファイル | 役割 |
|---|---|
| `bg_remover_app.py` | 独立ウィンドウ版エントリーポイント |
| `bg_removal_panel.py` | コアUI `BgRemovalPanel`（CTkFrame・埋め込み可能） |
| `widgets.py` | 再利用UI部品（処理画像グリッド・拡大ウィンドウ・サムネ生成） |
| `engine.py` | 背景除去・チェッカー合成・保存のロジック（UI非依存・流用可能） |
| `paths.py` | 出力先の解決（プロジェクト配下なら outputs/bg_removal、単体なら ./outputs） |

## 注意・ハマりどころ

| 項目 | 内容 |
|---|---|
| 初回モデルDL | 初回実行時にモデルを `~/.u2net/` にDL（数百MB〜1GB）。しばらく待つ |
| GPU認識 | `onnxruntime-gpu` があればGPU。無ければ自動でCPU |
| 透過PNG | 結果は必ず `RGBA` で保存（`RGB` だと透過が消える） |
| パスの空白 | D&Dのパスは `{}` 除去・空白対応済み |
| D&D無効時 | ドロップエリアをクリックすればファイル選択で読み込める |
