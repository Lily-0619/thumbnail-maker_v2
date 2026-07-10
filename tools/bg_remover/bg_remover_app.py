"""
bg_remover_app.py
背景除去ツール（独立ウィンドウ版）エントリーポイント。

起動:
    python tools/bg_remover/bg_remover_app.py

D&Dを使うため、ルートは tkinterdnd2 対応の CTk（DnDCTk）にする。
中身は BgRemovalPanel（CTkFrame）をそのまま貼るだけ。テーマ/フォントは
bdm-thumbnail_app_v02 の pink_theme / HachiMaruPop があれば使い、無ければ既定。
"""

import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path
import tkinter.font as tkfont

# 配置非依存にするため、このツール自身のフォルダを sys.path に入れて直接importする。
# （bdmの tools/bg_remover でも、D:\汎用ツール\bg_remover でもそのまま動く）
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# ── 依存(rembg等)の入った .venv で確実に起動する ─────────────────────
# .py を直接ダブルクリックしたり、システムの別Pythonから起動されると rembg が
# 見つからず「未導入」になる。その場合はプロジェクトの .venv の python を探して
# 自動で起動し直す（どんな起動方法でも“確実に動く”ようにするため）。
def _relaunch_in_project_venv() -> None:
    import importlib.util

    try:
        if importlib.util.find_spec("rembg") is not None:
            return  # すでに依存が揃った環境（= 正しい .venv 等）で動いている
    except Exception:
        pass
    if os.environ.get("BG_REMOVER_RELAUNCHED") == "1":
        return  # 再起動済み。ループ防止（.venv でも無ければ通常起動しメッセージ表示）

    exe_rels = ("Scripts/python.exe", "Scripts/pythonw.exe", "bin/python", "bin/python3")
    for parent in (HERE, *HERE.parents):
        venv = parent / ".venv"
        if not venv.is_dir():
            continue
        for rel in exe_rels:
            cand = venv / rel
            if not cand.exists():
                continue
            try:
                same = cand.resolve() == Path(sys.executable).resolve()
            except OSError:
                same = False
            if same:
                return  # 既に .venv の python。それでも無いなら諦めてメッセージ表示
            env = dict(os.environ, BG_REMOVER_RELAUNCHED="1")
            script = str(Path(__file__).resolve())
            subprocess.Popen([str(cand), script, *sys.argv[1:]], env=env)
            raise SystemExit(0)
        break  # .venv はあるが python 実行体が無い → これ以上探さない


_relaunch_in_project_venv()

import customtkinter as ctk  # noqa: E402

try:
    from tkinterdnd2 import TkinterDnD  # noqa: E402
except ImportError:
    TkinterDnD = None

import paths  # noqa: E402
from bg_removal_panel import BgRemovalPanel  # noqa: E402

# ── Theme（bdmのpink_themeがあれば使う。無ければblue）──
ctk.set_appearance_mode("light")
_THEME_CANDIDATES = (
    paths.PROJECT_ROOT / "config" / "pink_theme.json",
    paths.PROJECT_ROOT / "assets" / "config" / "pink_theme.json",
    Path("D:/bdm-thumbnail_app_v02/config/pink_theme.json"),
)
for _theme_path in _THEME_CANDIDATES:
    if _theme_path.exists():
        ctk.set_default_color_theme(str(_theme_path))
        break
else:
    ctk.set_default_color_theme("blue")

UI_FONT_FILE_NAME = "HachiMaruPop-Regular.ttf"
UI_FONT_FAMILY = "Hachi Maru Pop"
UI_FONT_CANDIDATES = (
    paths.PROJECT_ROOT / "font" / "JP" / UI_FONT_FILE_NAME,
    Path("D:/bdm-thumbnail_app_v02/font/JP") / UI_FONT_FILE_NAME,
)


def _register_ui_font() -> str:
    for font_path in UI_FONT_CANDIDATES:
        if not font_path.exists():
            continue
        if platform.system() == "Windows":
            try:
                ctypes.windll.gdi32.AddFontResourceExW(str(font_path.resolve()), 0x10, 0)
            except (AttributeError, OSError):
                pass
        ctk.ThemeManager.theme["CTkFont"]["family"] = UI_FONT_FAMILY
        return UI_FONT_FAMILY
    return ctk.ThemeManager.theme.get("CTkFont", {}).get("family", "Roboto")


def _apply_tk_default_font(family: str) -> None:
    for font_name in (
        "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
        "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
        "TkIconFont", "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(font_name).configure(family=family)
        except Exception:
            pass


if TkinterDnD is not None:
    class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        """CustomTkinterでtkinterdnd2を利用するためのルートクラス。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class DnDCTk(ctk.CTk):
        """tkinterdnd2が無い環境向け。クリックでファイル選択する。"""


class BgRemoverApp(DnDCTk):
    def __init__(self):
        super().__init__()
        self.title("背景除去ツール")
        family = _register_ui_font()
        _apply_tk_default_font(family)
        self.geometry("1240x900")
        self.minsize(1000, 720)
        self.configure(fg_color="#fdeaf3")

        paths.ensure_dirs()

        ctk.CTkLabel(
            self, text="背景除去（rembg）", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            self,
            text=f"出力：{paths.OUTPUT_DIR}　（複数枚は「🚀 一括処理」でまとめて／💾でPNGは PNG\\・元画像は 処理済み\\ へ）",
            font=ctk.CTkFont(size=11), text_color="#7a3b5a", anchor="w",
        ).pack(anchor="w", padx=16, pady=(0, 6))

        self.panel = BgRemovalPanel(self, output_dir=paths.OUTPUT_DIR)
        self.panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))


def main():
    app = BgRemoverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
