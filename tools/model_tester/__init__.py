"""
model_tester
モデル(checkpoint)とLoRAを「同じプロンプトで一括生成して並べて見比べる」ための
独立ツール。本体(ui/ core/ config/)は一切変更せず、tools/ への追加のみ。

起動:
    python tools/model_tester/model_tester_app.py
"""
