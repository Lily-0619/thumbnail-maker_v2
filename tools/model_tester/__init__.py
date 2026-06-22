"""
model_tester
A1111 風の X/Y/Z プロット比較ツール。X軸=列 / Y軸=行 / Z軸=複数グリッドに
Checkpoint / LoRA / Steps / CFG / Sampler / Seed / Prompt S/R などを割り当てて
一括生成し、ラベル付きグリッドで見比べる。LoRA重ねがけ・Hires/アップスケール・
clip skip・VAE上書き・img2img に対応。本体(ui/ core/ config/)は一切変更せず、
tools/ への追加のみ。ComfyUI バックエンド。

起動:
    python tools/model_tester/model_tester_app.py
"""
