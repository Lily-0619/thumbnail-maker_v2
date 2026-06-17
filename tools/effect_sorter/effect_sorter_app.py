"""
effect_sorter_app.py
エフェクト素材仕分けツール エントリーポイント。

起動:
    python tools/effect_sorter/effect_sorter_app.py

人間が画像を目視 → クラス/位置/effect①/effect② を選ぶ → 命名ルールでリネーム
→ 対応フォルダへ移動（copy→検証→delete）する補助デスクトップアプリ。
本体 ui/app.py と同じく CustomTkinter で書く。
"""

import os
import shutil
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

# ── プロジェクトルートを sys.path に追加（本体 main.py と同様）──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa: E402
except ImportError:  # D&Dが無い環境でも、仕分け本体は起動できるようにする。
    DND_FILES = None
    TkinterDnD = None

from tools.effect_sorter import naming, paths, translate, words_store  # noqa: E402
from tools.effect_sorter.naming import ValidationError  # noqa: E402
from tools.effect_sorter.widgets import (  # noqa: E402
    IMAGE_EXTS,
    PreviewPanel,
    UnsortedGrid,
)

# ── Theme（本体に合わせる）──
# pink_theme.json は config/ にも assets/config/ にも置かれうるため両方を探す。
ctk.set_appearance_mode("light")
_THEME_CANDIDATES = (
    paths.CONFIG_DIR / "pink_theme.json",
    paths.PROJECT_ROOT / "assets" / "config" / "pink_theme.json",
)
for _theme_path in _THEME_CANDIDATES:
    if _theme_path.exists():
        ctk.set_default_color_theme(str(_theme_path))
        break
else:
    ctk.set_default_color_theme("blue")

PINK = {
    "window": "#fdeaf3",
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
    "select": "#3f94d1",
    # 連続仕分け用アクションボタン
    "skip": "#7a8aa0",
    "skip_hover": "#5f6e85",
    "hold": "#c9a23b",
    "hold_hover": "#a8861f",
    "delete": "#b04a4a",
    "delete_hover": "#8f3838",
}


if TkinterDnD is not None:
    class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        """CustomTkinterでtkinterdnd2を利用するためのルートクラス。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class DnDCTk(ctk.CTk):
        """tkinterdnd2が無い環境向け。追加ボタンで画像を取り込む。"""


class EffectSorterApp(DnDCTk):
    def __init__(self):
        super().__init__()
        self.title("エフェクト素材仕分けツール")
        self.geometry("1200x780")
        self.resizable(True, True)
        self.configure(fg_color=PINK["window"])

        # 起動時にフォルダ・設定ファイルを保証（なければ作る・あっても壊さない）
        paths.ensure_dirs()
        words_store.ensure_file()
        translate.ensure_file()

        # 状態
        self.cls = ctk.StringVar(value="")
        self.position = ctk.StringVar(value="")
        self.effect1 = ctk.StringVar(value="")
        self.effect2 = ctk.StringVar(value="")
        self.title_text = ctk.StringVar(value="")
        self.ollama_status = ctk.StringVar(value="Ollama: 起動確認中...")
        self.remaining = ctk.StringVar(value="残り 0 枚")
        self.selected_image = None  # _unsorted 内の選択中画像 Path
        self._unsorted_list = []  # 現在表示中の未分類画像（連続仕分けのインデックス基準）

        self._class_buttons = []
        self._pos_buttons = {}

        self._build_layout()
        self._enable_dnd()
        self.refresh_unsorted()
        self.refresh_class_buttons()
        self.refresh_effect2_history()  # effect② 共通履歴は起動時から表示
        self._update_title()
        self._start_ollama_on_launch()

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self.rowconfigure(1, weight=1)

        # ── タイトル欄 + チェックボタン（上部） ──
        top = ctk.CTkFrame(self, fg_color=PINK["panel"])
        top.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(10, 6))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="素材仕分け", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 0)
        )
        self._title_entry = ctk.CTkEntry(
            top, textvariable=self.title_text, font=ctk.CTkFont(size=14)
        )
        self._title_entry.grid(row=1, column=0, sticky="ew", padx=(8, 6), pady=8)
        ctk.CTkButton(
            top, text="✔ 確定", width=90, command=self.on_confirm,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).grid(row=1, column=1, padx=(0, 8), pady=8)

        # ── 左カラム: class + 位置 ──
        left = ctk.CTkFrame(self, fg_color=PINK["panel"])
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=6)
        left.rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text="class", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self._class_frame = ctk.CTkFrame(left, fg_color="transparent", width=170)
        self._class_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        self._class_frame.grid_propagate(False)
        self._class_frame.columnconfigure((0, 1), weight=1)

        pos_frame = ctk.CTkFrame(left, fg_color="transparent")
        pos_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        ctk.CTkLabel(pos_frame, text="位置").pack(anchor="w")
        for pos in ("back", "front"):
            b = ctk.CTkButton(
                pos_frame, text=pos, command=lambda p=pos: self._select_position(p),
                fg_color=PINK["button"], hover_color=PINK["button_hover"],
            )
            b.pack(fill="x", pady=2)
            self._pos_buttons[pos] = b

        # ── effect① カラム ──
        e1col = ctk.CTkFrame(self, fg_color=PINK["panel"])
        e1col.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
        e1col.rowconfigure(4, weight=1)
        ctk.CTkLabel(e1col, text="effect①", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        e1entry = ctk.CTkEntry(e1col, textvariable=self.effect1)
        e1entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(
            e1col, text="Ollamaで日本語→英語", height=26,
            command=lambda: self._translate_field(self.effect1),
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        ctk.CTkLabel(
            e1col,
            textvariable=self.ollama_status,
            text_color="#a05050",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._e1_hist = ctk.CTkScrollableFrame(e1col, label_text="履歴（クラス別）")
        self._e1_hist.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        e1col.columnconfigure(0, weight=1)

        # ── effect② カラム ──
        e2col = ctk.CTkFrame(self, fg_color=PINK["panel"])
        e2col.grid(row=1, column=2, sticky="nsew", padx=6, pady=6)
        e2col.rowconfigure(4, weight=1)
        ctk.CTkLabel(e2col, text="effect②", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        e2entry = ctk.CTkEntry(e2col, textvariable=self.effect2)
        e2entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(
            e2col, text="Ollamaで日本語→英語", height=26,
            command=lambda: self._translate_field(self.effect2),
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        ctk.CTkLabel(
            e2col,
            textvariable=self.ollama_status,
            text_color="#a05050",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._e2_hist = ctk.CTkScrollableFrame(e2col, label_text="履歴（共通）")
        self._e2_hist.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        e2col.columnconfigure(0, weight=1)

        # ── 右カラム: プレビュー + アクション + 未分類 ──
        right = ctk.CTkFrame(self, fg_color=PINK["panel"])
        right.grid(row=1, column=3, sticky="nsew", padx=(6, 10), pady=6)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        self._preview = PreviewPanel(right)
        self._preview.grid(row=0, column=0, sticky="ew", padx=6, pady=6)

        # ── 連続仕分けのアクションバー（残り枚数 + スキップ/保留/削除） ──
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))
        ctk.CTkLabel(
            actions, textvariable=self.remaining,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(2, 8))
        ctk.CTkButton(
            actions, text="🗑 削除", width=72, command=self.on_delete,
            fg_color=PINK["delete"], hover_color=PINK["delete_hover"],
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            actions, text="保留", width=64, command=self.on_hold,
            fg_color=PINK["hold"], hover_color=PINK["hold_hover"],
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            actions, text="⏭ スキップ", width=84, command=self.on_skip,
            fg_color=PINK["skip"], hover_color=PINK["skip_hover"],
        ).pack(side="right", padx=2)

        unsorted_wrap = ctk.CTkFrame(right, fg_color="transparent")
        unsorted_wrap.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        unsorted_wrap.rowconfigure(0, weight=1)
        unsorted_wrap.columnconfigure(0, weight=1)
        self._unsorted_grid = UnsortedGrid(unsorted_wrap, on_select=self._select_image)
        self._unsorted_grid.grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(
            unsorted_wrap, text="＋ 画像を追加", command=self.on_add_images,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self._dnd_label = ctk.CTkLabel(
            unsorted_wrap, text="", text_color="#a05050", font=ctk.CTkFont(size=11)
        )
        self._dnd_label.grid(row=2, column=0, sticky="ew")

        # タイトル欄をライブ更新するため各 Var を監視
        for var in (self.cls, self.position, self.effect1, self.effect2):
            var.trace_add("write", lambda *_: self._update_title())

    # ──────────────────────────────────────────
    #  Ollama startup
    # ──────────────────────────────────────────

    def _start_ollama_on_launch(self):
        """アプリ起動と同時にOllamaの起動確認・自動起動を行う。"""
        threading.Thread(target=self._ollama_startup_worker, daemon=True).start()

    def _ollama_startup_worker(self):
        try:
            message = translate.ensure_ollama_ready(start_if_needed=True)
            self.after(0, self.ollama_status.set, f"✅ {message}")
        except translate.OllamaStartupError as e:
            self.after(0, self.ollama_status.set, "⚠️ Ollama起動に失敗")
            self.after(0, messagebox.showwarning, "Ollama Startup", str(e))

    # ──────────────────────────────────────────
    #  D&D
    # ──────────────────────────────────────────

    def _enable_dnd(self):
        """未分類グリッドとアプリ全体への画像ドロップを有効化する。"""
        if DND_FILES is None:
            self._dnd_label.configure(text="ドラッグ&ドロップは無効です。『＋ 画像を追加』を使ってください。")
            return
        target = self._unsorted_grid
        target.drop_target_register(DND_FILES)
        target.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop)
        self._dnd_label.configure(text="画像をここへドラッグ&ドロップできます。")

    def _on_drop(self, event):
        # event.data はスペース区切り。{} で囲まれたパス（空白入り）に対応。
        raw = event.data
        files = self._parse_dnd_paths(raw)
        self._import_files(files)

    @staticmethod
    def _parse_dnd_paths(raw: str):
        paths_out = []
        token = ""
        in_brace = False
        for ch in raw:
            if ch == "{":
                in_brace = True
                token = ""
            elif ch == "}":
                in_brace = False
                paths_out.append(token)
                token = ""
            elif ch == " " and not in_brace:
                if token:
                    paths_out.append(token)
                    token = ""
            else:
                token += ch
        if token:
            paths_out.append(token)
        return paths_out

    # ──────────────────────────────────────────
    #  取り込み（_unsorted へ）
    # ──────────────────────────────────────────

    def on_add_images(self):
        files = filedialog.askopenfilenames(
            title="追加する画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp"), ("すべて", "*.*")],
        )
        if files:
            self._import_files(files)

    def _import_files(self, files):
        added, skipped = 0, 0
        for f in files:
            src = Path(f)
            if not src.is_file() or src.suffix.lower() not in IMAGE_EXTS:
                skipped += 1
                continue
            try:
                self._import_one(src)
                added += 1
            except Exception as e:
                messagebox.showwarning(
                    "取り込み失敗",
                    f"{src.name} の取り込みに失敗しました。\n{e}\n"
                    "元ファイルはそのまま残っています。",
                )
        if skipped:
            messagebox.showinfo(
                "一部スキップ",
                f"{skipped} 件は画像でないためスキップしました。\n"
                "対応形式：png / jpg / jpeg / webp",
            )
        if added:
            self.refresh_unsorted()

    def _import_one(self, src: Path):
        """外部画像を _unsorted へ取り込む（同名は _dup で退避、上書きしない）。"""
        dest = paths.UNSORTED_DIR / src.name
        if dest.exists():
            stem, n = src.stem, 1
            while dest.exists():
                dest = paths.UNSORTED_DIR / f"{stem}_dup{n}{src.suffix}"
                n += 1
        shutil.copy2(src, dest)
        # 検証（サイズ一致）
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise OSError("コピー検証に失敗しました。")

    # ──────────────────────────────────────────
    #  選択系
    # ──────────────────────────────────────────

    def refresh_class_buttons(self):
        for child in self._class_frame.winfo_children():
            child.destroy()
        self._class_buttons.clear()

        pngs = (
            sorted(paths.CLASS_BUTTON_DIR.glob("*.png"))
            if paths.CLASS_BUTTON_DIR.exists()
            else []
        )
        if not pngs:
            ctk.CTkLabel(
                self._class_frame,
                text="クラスボタン用PNGがありません。\nmaterial/class_button/ に\nWS.png 等を置いてください。",
            ).grid(row=0, column=0, columnspan=2, padx=4, pady=4)
            return

        self._class_thumb_refs = []
        for idx, p in enumerate(pngs):
            name = p.stem  # WS.png → WS
            try:
                with Image.open(p) as opened:
                    img = opened.convert("RGBA")
                img.thumbnail((56, 56), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(56, 56))
                self._class_thumb_refs.append(ctk_img)
            except Exception:
                ctk_img = None
            b = ctk.CTkButton(
                self._class_frame,
                text="",
                image=ctk_img,
                width=72,
                height=68,
                fg_color=PINK["select"],
                hover_color=PINK["button_hover"],
                command=lambda n=name: self._select_class(n),
            )
            row, col = divmod(idx, 2)
            b.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            self._class_buttons.append((name, b))

    def _select_class(self, name):
        self.cls.set(name)
        self._highlight_class(name)
        self.refresh_effect1_history()

    def _highlight_class(self, name):
        for n, b in self._class_buttons:
            b.configure(border_width=2 if n == name else 0)

    def _select_position(self, pos):
        self.position.set(pos)
        for p, b in self._pos_buttons.items():
            b.configure(border_width=2 if p == pos else 0)

    def _select_image(self, path):
        self.selected_image = Path(path)
        self._unsorted_grid.set_selected(self.selected_image)
        self._preview.show(self.selected_image)

    # ──────────────────────────────────────────
    #  履歴ボタン
    # ──────────────────────────────────────────

    def refresh_effect1_history(self):
        for child in self._e1_hist.winfo_children():
            child.destroy()
        cls = self.cls.get()
        words = words_store.effect1_for(cls) if cls else []
        if not words:
            ctk.CTkLabel(self._e1_hist, text="（履歴なし）").pack(padx=4, pady=4)
            return
        for w in words:
            ctk.CTkButton(
                self._e1_hist, text=w, height=26,
                command=lambda x=w: self.effect1.set(x),
            ).pack(fill="x", pady=2)

    def refresh_effect2_history(self):
        for child in self._e2_hist.winfo_children():
            child.destroy()
        words = words_store.effect2_all()
        if not words:
            ctk.CTkLabel(self._e2_hist, text="（履歴なし）").pack(padx=4, pady=4)
            return
        for w in words:
            ctk.CTkButton(
                self._e2_hist, text=w, height=26,
                command=lambda x=w: self.effect2.set(x),
            ).pack(fill="x", pady=2)

    # ──────────────────────────────────────────
    #  翻訳
    # ──────────────────────────────────────────

    def _translate_field(self, var):
        text = var.get().strip()
        if not text:
            return
        try:
            result, changed = translate.translate(text)
        except translate.TranslationError as e:
            messagebox.showwarning("Ollama翻訳エラー", str(e))
            return
        if changed:
            var.set(result)
        else:
            messagebox.showinfo(
                "翻訳できませんでした",
                f"「{text}」をOllamaで翻訳できませんでした。\n"
                "Ollamaが起動しているか確認してください。",
            )

    # ──────────────────────────────────────────
    #  タイトル欄
    # ──────────────────────────────────────────

    def _update_title(self):
        cls = self.cls.get()
        pos = self.position.get()
        e1 = self.effect1.get().strip()
        e2 = self.effect2.get().strip()
        seq = None
        if cls and pos and e1 and e2:
            try:
                target = paths.effect_target_dir(cls, pos, e1)
                seq = naming.next_sequence(target, cls, pos, e1, e2)
            except Exception:
                seq = None
        self.title_text.set(naming.title_preview(cls, pos, e1, e2, seq))

    # ──────────────────────────────────────────
    #  確定フロー（copy → 検証 → delete）
    # ──────────────────────────────────────────

    def on_confirm(self):
        # 0. 画像が選択されているか
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return

        cls = self.cls.get()
        pos = self.position.get()
        e1 = self.effect1.get().strip()
        e2 = self.effect2.get().strip()
        old_index = self._index_of_selected()  # 連続仕分け: 確定後この位置へ次画像が来る

        # 1. バリデーション
        try:
            naming.validate(cls, pos, e1, e2)
        except ValidationError as e:
            messagebox.showwarning("入力エラー", f"{e}\n\n画像は _unsorted に残っています。")
            return

        src = self.selected_image

        try:
            # 2-3. 保存先フォルダを用意
            target_dir = paths.effect_target_dir(cls, pos, e1)
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showwarning(
                "フォルダ作成失敗",
                f"保存先フォルダを作成できませんでした。\n{e}\n\n画像は _unsorted に残っています。",
            )
            return

        try:
            # 4-5. 連番を再計算し、衝突する限り +1（多重起動の保険）
            seq = naming.next_sequence(target_dir, cls, pos, e1, e2)
            for _ in range(1000):
                final_name = naming.build_filename(cls, pos, e1, e2, seq)
                final_path = target_dir / final_name
                if not final_path.exists():
                    break
                seq += 1
            else:
                raise OSError("連番の空きが見つかりませんでした。")

            # 6. Pillow で中身ごとPNG変換して保存（jpg/webpも安全・透過保持）
            with Image.open(src) as im:
                im.save(final_path, "PNG")

            # 7. コピー検証
            if not final_path.exists() or final_path.stat().st_size == 0:
                if final_path.exists():
                    final_path.unlink(missing_ok=True)
                raise OSError("保存後の検証に失敗しました。")

        except Exception as e:
            # 作りかけがあれば消す。元画像は _unsorted に残す。
            try:
                if "final_path" in locals() and final_path.exists():
                    final_path.unlink(missing_ok=True)
            except Exception:
                pass
            messagebox.showwarning(
                "保存失敗",
                f"画像の保存に失敗しました。\n{e}\n\n画像は _unsorted に残っています。",
            )
            return

        # 8. 元画像（_unsorted）を削除
        try:
            src.unlink(missing_ok=True)
        except Exception as e:
            messagebox.showwarning(
                "元画像の削除に失敗",
                f"保存は成功しましたが、元画像を削除できませんでした。\n{e}\n"
                f"保存先：{final_path}\n手動で _unsorted の {src.name} を整理してください。",
            )

        # 9. 履歴JSON更新（落とさない）
        try:
            words_store.add_effect1(cls, e1)
            words_store.add_effect2(e2)
        except Exception:
            pass  # 履歴保存失敗はアプリを落とさない

        # 10. UI更新（連続仕分け: 同じ位置へスライドする次の未分類画像を自動選択）
        self.selected_image = None
        self._advance_after_removal(old_index)
        self.refresh_effect1_history()
        self.refresh_effect2_history()

    # ──────────────────────────────────────────
    #  未分類一覧
    # ──────────────────────────────────────────

    def _unsorted_images(self):
        if not paths.UNSORTED_DIR.exists():
            return []
        out = [
            p
            for p in sorted(paths.UNSORTED_DIR.iterdir())
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        ]
        return out

    def refresh_unsorted(self):
        """未分類一覧を読み直してグリッドとカウンタを更新する。"""
        self._unsorted_list = self._unsorted_images()
        self._unsorted_grid.refresh(self._unsorted_list)
        self.remaining.set(f"残り {len(self._unsorted_list)} 枚")

    # ──────────────────────────────────────────
    #  連続仕分け（スキップ / 保留 / 削除）
    # ──────────────────────────────────────────

    def _index_of_selected(self) -> int:
        """選択中画像の現在の一覧内インデックス。無ければ 0。"""
        if self.selected_image is None:
            return 0
        try:
            return self._unsorted_list.index(self.selected_image)
        except ValueError:
            return 0

    def _select_at_index(self, idx: int):
        """更新後の一覧で idx 位置（範囲外はクランプ）を選ぶ。空なら選択解除。"""
        if not self._unsorted_list:
            self.selected_image = None
            self._preview.show(None)
            return
        idx = max(0, min(idx, len(self._unsorted_list) - 1))
        self._select_image(self._unsorted_list[idx])

    def _advance_after_removal(self, old_index: int):
        """確定/保留/削除で1枚消えた後、その位置へスライドしてくる次画像を自動選択。"""
        self.refresh_unsorted()
        self._select_at_index(old_index)
        self._update_title()

    def _move_out_of_unsorted(self, src: Path, dest_dir: Path) -> Path:
        """copy→検証→元削除 で src を dest_dir へ退避。最終パスを返す（失敗時は例外）。"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            stem, suffix, n = src.stem, src.suffix, 1
            while dest.exists():
                dest = dest_dir / f"{stem}_dup{n}{suffix}"
                n += 1
        shutil.copy2(src, dest)
        # 検証（存在＋サイズ一致）。NGなら作りかけを消し、元は触らない。
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise OSError("コピー検証に失敗しました。")
        src.unlink()  # 検証OK後にのみ元を削除
        return dest

    def on_skip(self):
        """ファイルを一切変更せず、次の未分類画像へ進む（非破壊）。"""
        if not self._unsorted_list:
            messagebox.showinfo("スキップ", "未分類画像がありません。")
            return
        if self.selected_image is None:
            self._select_at_index(0)
            return
        idx = self._index_of_selected()
        if idx + 1 < len(self._unsorted_list):
            self._select_at_index(idx + 1)
        else:
            messagebox.showinfo("スキップ", "これが最後の未分類画像です。")

    def on_hold(self):
        """選択中画像を _hold へ退避して次へ進む（後で処理する用・復元可能）。"""
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return
        src = self.selected_image
        old_index = self._index_of_selected()
        try:
            self._move_out_of_unsorted(src, paths.HOLD_DIR)
        except Exception as e:
            messagebox.showwarning(
                "保留に失敗",
                f"画像を保留フォルダへ移せませんでした。\n{e}\n\n"
                "画像は _unsorted に残っています。",
            )
            return
        self.selected_image = None
        self._advance_after_removal(old_index)

    def on_delete(self):
        """選択中画像を _trash へ退避（完全削除はしない・確認あり・復元可能）。"""
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return
        src = self.selected_image
        if not messagebox.askyesno(
            "削除の確認",
            f"「{src.name}」をゴミ箱フォルダへ移動します。\n\n"
            "完全削除ではなく material/effect/_trash/ に退避するので、\n"
            "後から手動で復元できます。よろしいですか？",
        ):
            return
        old_index = self._index_of_selected()
        try:
            self._move_out_of_unsorted(src, paths.TRASH_DIR)
        except Exception as e:
            messagebox.showwarning(
                "削除に失敗",
                f"画像をゴミ箱フォルダへ移せませんでした。\n{e}\n\n"
                "画像は _unsorted に残っています。",
            )
            return
        self.selected_image = None
        self._advance_after_removal(old_index)


def main():
    app = EffectSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
