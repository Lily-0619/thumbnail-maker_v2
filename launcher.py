"""
launcher.py
BDM ツールランチャー。

起動すると、作りたい作業を選んで各ツールを開ける小さな画面を出す。

  - 🖼️ サムネ作成         : main.py（本体）
  - 🎨 画像生成 / 比較      : tools/model_tester/model_tester_app.py
  - 🗂️ 素材仕分け          : tools/effect_sorter/effect_sorter_app.py
  - 🏰 拠点画像仕分け       : tools/base_image_sorter/base_image_sorter_app.py

起動:
    python launcher.py
（Windows ではルートの「ランチャー起動.bat」をダブルクリックしてもよい）

各ツールは「このランチャーを動かしている Python」で子プロセスとして起動するので、
依存（customtkinter など）はランチャーと同じ環境のものがそのまま使われる。
"""

import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import customtkinter as ctk  # noqa: E402

# ── Theme（本体に合わせる。pink_theme は config/ と assets/config/ 両方を探す）──
ctk.set_appearance_mode("light")
for _theme in (ROOT / "config" / "pink_theme.json", ROOT / "assets" / "config" / "pink_theme.json"):
    if _theme.exists():
        ctk.set_default_color_theme(str(_theme))
        break
else:
    ctk.set_default_color_theme("blue")

PINK = {
    "window": "#fdeaf3",
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
}

# (ボタン名, 説明, 起動するスクリプト)
TOOLS = [
    ("🖼 サムネ作成", "日付・拠点・ギルド・キャラからサムネを作る本体アプリ", "main.py"),
    ("🎨 画像生成 / 比較", "かんたん生成＋⚙️詳細はX/Y/Z比較（モデル/LoRA/Steps等）。アップスケール対応", "tools/model_tester/model_tester_app.py"),
    ("🗂 素材仕分け", "エフェクト素材を目視で仕分け・リネーム・移動する", "tools/effect_sorter/effect_sorter_app.py"),
    ("🏰 拠点画像仕分け", "拠点サムネを 拠点×時間帯 で仕分け・リネームして material/back へ移動する", "tools/base_image_sorter/base_image_sorter_app.py"),
]


class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BDM ツールランチャー")
        self.geometry("540x480")
        self.resizable(False, True)
        self.configure(fg_color=PINK["window"])
        self.status = ctk.StringVar(value="開きたいものを選んでね ✨")
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="BDM ツールランチャー", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 2))
        ctk.CTkLabel(self, text="(｡•ᴗ•｡)  どれにする？", text_color="#7a3b5a").pack(pady=(0, 12))

        for label, desc, script in TOOLS:
            card = ctk.CTkFrame(self, fg_color=PINK["panel"], corner_radius=12)
            card.pack(fill="x", padx=20, pady=8)
            ctk.CTkButton(
                card,
                text=label,
                height=52,
                font=ctk.CTkFont(size=16, weight="bold"),
                fg_color=PINK["button"],
                hover_color=PINK["button_hover"],
                command=lambda s=script, lbl=label: self._launch(s, lbl),
            ).pack(fill="x", padx=10, pady=(10, 2))
            ctk.CTkLabel(
                card, text=desc, text_color="#7a3b5a", font=ctk.CTkFont(size=12),
                wraplength=460, justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 10))

        ctk.CTkLabel(self, textvariable=self.status, text_color="#a05050").pack(pady=10)

    def _launch(self, rel_script: str, label: str):
        script = ROOT / rel_script
        if not script.exists():
            messagebox.showwarning("見つかりません", f"{rel_script} が見つかりませんでした。")
            return
        try:
            # このランチャーと同じ Python で、ルートをカレントにして起動する
            # （各アプリは cwd 相対パスで material/ や config/ を参照するため）。
            subprocess.Popen([sys.executable, str(script)], cwd=str(ROOT))
            self.status.set(f"{label.strip()} を起動しました ✨")
        except Exception as e:
            messagebox.showerror("起動失敗", f"{label.strip()} の起動に失敗しました。\n{e}")


def main():
    Launcher().mainloop()


if __name__ == "__main__":
    main()
