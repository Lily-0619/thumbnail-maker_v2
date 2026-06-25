"""
tools/bg_remover
背景除去ツール（rembg）。

画像をD&D／ファイル選択で読み込み、複数のAIモデル（rembg）で背景を除去して
チェッカー背景で透過を確認し、PNG（RGBA）で保存する。

コアUIは BgRemovalPanel（CTkFrame）として実装してあり、独立ウィンドウ
（bg_remover_app.py）にも、将来メインアプリのタブにも埋め込める。
処理ロジックは engine.py に分離（UI非依存・他プロジェクトへ流用可能）。
"""
