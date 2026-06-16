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
from pathlib import Path
from tkinter import filedialog, messagebox

# ── プロジェクトルートを sys.path に追加（本体 main.py と同様）──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402

from tools.effect_sorter import naming, paths, translate, words_store  # noqa: E402
from tools.effect_sorter.naming import ValidationError  # noqa: E402
from tools.effect_sorter.widgets import (  # noqa: E402
    IMAGE_EXTS,
    PreviewPanel,
    UnsortedGrid,
)

# ── D&D（任意・無くても動く）──
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa: E402

    _DND_AVAILABLE = True
except Exception:
    _DND_AVAILABLE = False


# ── Theme（本体に合わせる）──
ctk.set_appearance_mode("light")
_THEME_PATH = paths.CONFIG_DIR / "pink_theme.json"
if _THEME_PATH.exists():
    ctk.set_default_color_theme(str(_THEME_PATH))
else:
    ctk.set_default_color_theme("blue")


class EffectSorterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("エフェクト素材仕分けツール")
        self.geometry("1200x780")
        self.resizable(True, True)

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
        self.selected_image = None  # _unsorted 内の選択中画像 Path

        self._class_buttons = []
        self._pos_buttons = {}

        self._build_layout()
        self._try_enable_dnd()
        self.refresh_unsorted()
        self.refresh_class_buttons()
        self._update_title()

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
        top = ctk.CTkFrame(self)
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
            fg_color="#e06aa0", hover_color="#c75690",
        ).grid(row=1, column=1, padx=(0, 8), pady=8)

        # ── 左カラム: class + 位置 ──
        left = ctk.CTkFrame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=6)
        left.rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text="class", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self._class_scroll = ctk.CTkScrollableFrame(left, width=150, label_text="")
        self._class_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        pos_frame = ctk.CTkFrame(left, fg_color="transparent")
        pos_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        ctk.CTkLabel(pos_frame, text="位置").pack(anchor="w")
        for pos in ("back", "front"):
            b = ctk.CTkButton(
                pos_frame, text=pos, command=lambda p=pos: self._select_position(p)
            )
            b.pack(fill="x", pady=2)
            self._pos_buttons[pos] = b

        # ── effect① カラム ──
        e1col = ctk.CTkFrame(self)
        e1col.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
        e1col.rowconfigure(3, weight=1)
        ctk.CTkLabel(e1col, text="effect①", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        e1entry = ctk.CTkEntry(e1col, textvariable=self.effect1)
        e1entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(
            e1col, text="日本語→英語に変換", height=26,
            command=lambda: self._translate_field(self.effect1),
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._e1_hist = ctk.CTkScrollableFrame(e1col, label_text="履歴（クラス別）")
        self._e1_hist.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        e1col.columnconfigure(0, weight=1)

        # ── effect② カラム ──
        e2col = ctk.CTkFrame(self)
        e2col.grid(row=1, column=2, sticky="nsew", padx=6, pady=6)
        e2col.rowconfigure(3, weight=1)
        ctk.CTkLabel(e2col, text="effect②", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        e2entry = ctk.CTkEntry(e2col, textvariable=self.effect2)
        e2entry.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(
            e2col, text="日本語→英語に変換", height=26,
            command=lambda: self._translate_field(self.effect2),
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._e2_hist = ctk.CTkScrollableFrame(e2col, label_text="履歴（共通）")
        self._e2_hist.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        e2col.columnconfigure(0, weight=1)

        # ── 右カラム: プレビュー + 未分類 ──
        right = ctk.CTkFrame(self)
        right.grid(row=1, column=3, sticky="nsew", padx=(6, 10), pady=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._preview = PreviewPanel(right)
        self._preview.grid(row=0, column=0, sticky="ew", padx=6, pady=6)

        unsorted_wrap = ctk.CTkFrame(right, fg_color="transparent")
        unsorted_wrap.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        unsorted_wrap.rowconfigure(0, weight=1)
        unsorted_wrap.columnconfigure(0, weight=1)
        self._unsorted_grid = UnsortedGrid(unsorted_wrap, on_select=self._select_image)
        self._unsorted_grid.grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(
            unsorted_wrap, text="＋ 画像を追加", command=self.on_add_images
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self._dnd_label = ctk.CTkLabel(
            unsorted_wrap, text="", text_color="#a05050", font=ctk.CTkFont(size=11)
        )
        self._dnd_label.grid(row=2, column=0, sticky="ew")

        # タイトル欄をライブ更新するため各 Var を監視
        for var in (self.cls, self.position, self.effect1, self.effect2):
            var.trace_add("write", lambda *_: self._update_title())

    # ──────────────────────────────────────────
    #  D&D
    # ──────────────────────────────────────────

    def _try_enable_dnd(self):
        """tkinterdnd2 があれば未分類グリッドにドロップを有効化する。"""
        if not _DND_AVAILABLE:
            self._dnd_label.configure(
                text="D&Dは無効です。『画像を追加』ボタンを使ってください。"
            )
            return
        try:
            TkinterDnD._require(self)
            target = self._unsorted_grid
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._on_drop)
            self._dnd_label.configure(
                text="エクスプローラから未分類エリアへ画像をドロップできます。"
            )
        except Exception:
            self._dnd_label.configure(
                text="D&Dは無効です。『画像を追加』ボタンを使ってください。"
            )

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
        for child in self._class_scroll.winfo_children():
            child.destroy()
        self._class_buttons.clear()

        pngs = (
            sorted(paths.CLASS_BUTTON_DIR.glob("*.png"))
            if paths.CLASS_BUTTON_DIR.exists()
            else []
        )
        if not pngs:
            ctk.CTkLabel(
                self._class_scroll,
                text="クラスボタン用PNGがありません。\nmaterial/class_button/ に\nWS.png 等を置いてください。",
            ).pack(padx=4, pady=4)
            return

        self._class_thumb_refs = []
        for p in pngs:
            name = p.stem  # WS.png → WS
            try:
                img = Image.open(p).convert("RGBA")
                img.thumbnail((48, 48), Image.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self._class_thumb_refs.append(ctk_img)
            except Exception:
                ctk_img = None
            b = ctk.CTkButton(
                self._class_scroll,
                text=name,
                image=ctk_img,
                compound="left",
                command=lambda n=name: self._select_class(n),
            )
            b.pack(fill="x", pady=2)
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
        result, changed = translate.translate(text)
        if changed:
            var.set(result)
        else:
            messagebox.showinfo(
                "辞書に未登録",
                f"「{text}」は辞書にありません。\n"
                "英語キーを直接入力してください。\n"
                f"（辞書を増やすには {paths.DICT_JSON.name} を編集）",
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

        # 10. UI更新
        self.selected_image = None
        self._preview.show(None)
        self.refresh_unsorted_and_autoselect()
        self.refresh_effect1_history()
        self.refresh_effect2_history()
        self._update_title()

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
        self._unsorted_grid.refresh(self._unsorted_images())

    def refresh_unsorted_and_autoselect(self):
        imgs = self._unsorted_images()
        self._unsorted_grid.refresh(imgs)
        if imgs:
            self._select_image(imgs[0])  # 次の未分類画像を自動選択（Phase2）


def main():
    app = EffectSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
