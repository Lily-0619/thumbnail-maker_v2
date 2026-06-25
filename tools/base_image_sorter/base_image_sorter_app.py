"""
base_image_sorter_app.py
拠点サムネイル画像 仕分けツール（LoRA学習用）エントリーポイント。

起動:
    python tools/base_image_sorter/base_image_sorter_app.py

使い方の流れ:
  1. 仕分けたい画像を「入力画像」エリアへドラッグ&ドロップ（または「＋ 画像を追加」）
  2. 1枚ずつプレビューを見ながら、拠点名（曜日別の縦リスト）と時間帯（朝/昼/夕/夜）を選ぶ
  3. ✔ 確定で {拠点名}_{時間帯}_{3桁連番}.png にリネームし、
     material/back/<拠点名>/ へ自動で移動（copy/変換→検証→元削除）
  4. 同じ位置にスライドしてくる次の画像が自動選択され、続けて仕分けできる

仕分け先は material/back に固定（拠点ごとにサブフォルダ）。
effect_sorter と同じ CustomTkinter + pink_theme + HachiMaruPop で書く。
"""

import ctypes
import platform
import shutil
import sys
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter.font as tkfont

# ── プロジェクトルートを sys.path に追加（effect_sorter と同様）──
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

from tools.base_image_sorter import bases, naming, paths  # noqa: E402
from tools.base_image_sorter.naming import ValidationError  # noqa: E402
from tools.base_image_sorter.widgets import (  # noqa: E402
    IMAGE_EXTS,
    ImageGrid,
    PreviewPanel,
)

# ── Theme（effect_sorter に合わせる）──
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

UI_FONT_FILE_NAME = "HachiMaruPop-Regular.ttf"
UI_FONT_FAMILY = "Hachi Maru Pop"
UI_FONT_CANDIDATES = (
    paths.PROJECT_ROOT / "font" / "JP" / UI_FONT_FILE_NAME,
    Path("D:/bdm-thumbnail_app_v02/font/JP") / UI_FONT_FILE_NAME,
)


def _register_ui_font() -> str:
    """UI表示用フォントを登録し、CustomTkinterの既定フォント名を返す。"""
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
    """標準Tk系の文字にも同じフォントを適用する。"""
    for font_name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(font_name).configure(family=family)
        except Exception:
            pass


PINK = {
    "window": "#fdeaf3",
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
    # 拠点ボタン（淡いパープル／くすみ系）。文字は読みやすいよう濃色。
    "base": "#c6b6e2",
    "base_hover": "#b09cd4",
    "base_text": "#3f2a44",
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
        """tkinterdnd2が無い環境向け。「＋ 画像を追加」で取り込む。"""


class BaseImageSorterApp(DnDCTk):
    def __init__(self):
        super().__init__()
        self.title("拠点画像 仕分けツール")
        self._ui_font_family = _register_ui_font()
        _apply_tk_default_font(self._ui_font_family)
        self.geometry("1280x820")
        self.resizable(True, True)
        self.configure(fg_color=PINK["window"])

        # 起動時に仕分け先フォルダを保証（なければ作る・あっても壊さない）
        paths.ensure_dirs()

        # 状態
        self.base = ctk.StringVar(value="")
        self.time_of_day = ctk.StringVar(value="")
        self.filename_preview = ctk.StringVar(value="")
        self.remaining = ctk.StringVar(value="残り 0 枚")
        self.selected_image = None  # 選択中画像 Path（投入された元の場所）
        self._image_list = []  # 仕分け対象（D&D/追加された画像）のメモリ上リスト

        self._base_buttons = []  # (拠点名, button)
        self._time_buttons = {}  # 時間帯キー -> button

        self._build_layout()
        self._enable_dnd()
        self.refresh_base_buttons()
        self.refresh()
        self._select_at_index(0)
        self._update_filename_preview()
        self._bind_shortcuts()

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=0)  # 拠点リスト（固定幅）
        self.columnconfigure(1, weight=1)  # 時間帯＋プレビュー
        self.columnconfigure(2, weight=1)  # 入力画像一覧
        self.rowconfigure(1, weight=1)

        # ── 上部: タイトル + 保存先(固定) + ファイル名プレビュー + 確定 ──
        top = ctk.CTkFrame(self, fg_color=PINK["panel"])
        top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 6))
        top.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top, text="拠点画像 仕分け", font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 2))

        ctk.CTkLabel(top, text="保存先：", anchor="w").grid(
            row=1, column=0, sticky="w", padx=(8, 0), pady=4
        )
        ctk.CTkLabel(
            top, text=f"{paths.OUTPUT_DIR}\\<拠点名>\\", anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=4)

        ctk.CTkLabel(top, text="出力ファイル名：", anchor="w").grid(
            row=2, column=0, sticky="w", padx=(8, 0), pady=(4, 8)
        )
        ctk.CTkLabel(
            top, textvariable=self.filename_preview, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=(4, 8))
        ctk.CTkButton(
            top, text="✔ 確定 (Enter)", width=130, command=self.on_confirm,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).grid(row=2, column=2, sticky="e", padx=(0, 8), pady=(4, 8))

        # ── 左カラム: 拠点（曜日見出し付き縦リスト） ──
        left = ctk.CTkFrame(self, fg_color=PINK["panel"])
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=6)
        left.rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="拠点", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        self._base_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", width=260
        )
        self._base_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        # ── 中央カラム: 時間帯 + プレビュー + アクション ──
        center = ctk.CTkFrame(self, fg_color=PINK["panel"])
        center.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(2, weight=1)

        ctk.CTkLabel(center, text="時間帯", anchor="w").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 0)
        )
        time_frame = ctk.CTkFrame(center, fg_color="transparent")
        time_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        for idx, (key, label) in enumerate(bases.TIMES_OF_DAY):
            time_frame.columnconfigure(idx, weight=1)
            b = ctk.CTkButton(
                time_frame, text=label, command=lambda k=key: self._select_time(k),
                fg_color=PINK["button"], hover_color=PINK["button_hover"],
            )
            b.grid(row=0, column=idx, sticky="ew", padx=3, pady=2)
            self._time_buttons[key] = b

        self._preview = PreviewPanel(center)
        self._preview.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)

        # アクションバー（残り枚数 + スキップ/保留/削除）
        actions = ctk.CTkFrame(center, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
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

        # ── 右カラム: 入力画像一覧（D&Dドロップ先） ──
        right = ctk.CTkFrame(self, fg_color=PINK["panel"])
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 10), pady=6)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self._image_grid = ImageGrid(right, on_select=self._select_image)
        self._image_grid.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        bottom = ctk.CTkFrame(right, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        ctk.CTkButton(
            bottom, text="＋ 画像を追加", command=self.on_add_images,
            fg_color=PINK["button"], hover_color=PINK["button_hover"],
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bottom, text="クリア", width=64, command=self.on_clear_list,
            fg_color=PINK["skip"], hover_color=PINK["skip_hover"],
        ).pack(side="left", padx=2)
        self._dnd_label = ctk.CTkLabel(
            bottom, text="", text_color="#a05050", font=ctk.CTkFont(size=11)
        )
        self._dnd_label.pack(side="left", padx=8)

        # 拠点・時間帯が変わったらファイル名プレビューを更新
        for var in (self.base, self.time_of_day):
            var.trace_add("write", lambda *_: self._update_filename_preview())

    # ──────────────────────────────────────────
    #  キーボードショートカット
    # ──────────────────────────────────────────

    def _bind_shortcuts(self):
        """Enter=確定 / 1〜4=時間帯 / →=スキップ。"""
        self.bind("<Return>", lambda _e: self.on_confirm())
        self.bind("<Right>", lambda _e: self.on_skip())
        for idx, (key, _label) in enumerate(bases.TIMES_OF_DAY, start=1):
            self.bind(str(idx), lambda _e, k=key: self._select_time(k))

    # ──────────────────────────────────────────
    #  D&D / 追加（仕分け対象のメモリ上リストへ）
    # ──────────────────────────────────────────

    def _enable_dnd(self):
        if DND_FILES is None:
            self._dnd_label.configure(
                text="D&Dは無効です。「＋ 画像を追加」で取り込んでください。"
            )
            return
        # ドロップ先を広めに登録する。CTkScrollableFrame は内部に canvas を持ち、
        # 一覧が空のときは可視部分が canvas なので、grid本体だけだと最初の投入を
        # 取りこぼす。ウィンドウ全体／一覧の内部frame／内部canvas／外枠frame を登録する。
        targets = [self, self._image_grid]
        for attr in ("_parent_canvas", "_parent_frame"):
            widget = getattr(self._image_grid, attr, None)
            if widget is not None:
                targets.append(widget)
        for target in targets:
            try:
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
        self._dnd_label.configure(text="画像/フォルダをここへドラッグ&ドロップで追加")

    def _on_drop(self, event):
        self._add_paths(self._parse_dnd_paths(event.data))

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

    def on_add_images(self):
        files = filedialog.askopenfilenames(
            title="追加する画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp"), ("すべて", "*.*")],
        )
        if files:
            self._add_paths(files)

    def _add_paths(self, raw_paths):
        """画像ファイル（とフォルダ内の画像）を仕分け対象リストへ追加する。"""
        added = 0
        for f in raw_paths:
            p = Path(f)
            if p.is_dir():
                for q in sorted(p.iterdir()):
                    if (
                        q.is_file()
                        and q.suffix.lower() in IMAGE_EXTS
                        and q not in self._image_list
                    ):
                        self._image_list.append(q)
                        added += 1
            elif (
                p.is_file()
                and p.suffix.lower() in IMAGE_EXTS
                and p not in self._image_list
            ):
                self._image_list.append(p)
                added += 1
        if added:
            had_selection = self.selected_image is not None
            self.refresh()
            if not had_selection:
                self._select_at_index(0)

    def on_clear_list(self):
        """仕分け対象リストを空にする（ファイルは移動・削除しない）。"""
        if not self._image_list:
            return
        if not messagebox.askyesno(
            "クリア確認",
            "入力画像の一覧を空にします。\n（ファイル自体は移動も削除もしません）\nよろしいですか？",
        ):
            return
        self._image_list = []
        self.selected_image = None
        self.refresh()
        self._preview.show(None)
        self._update_filename_preview()

    # ──────────────────────────────────────────
    #  拠点・時間帯ボタン
    # ──────────────────────────────────────────

    def refresh_base_buttons(self):
        for child in self._base_frame.winfo_children():
            child.destroy()
        self._base_buttons = []
        for day, names in bases.BASES_BY_DAY.items():
            ctk.CTkLabel(
                self._base_frame, text=f"― {day} ―",
                font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
            ).pack(fill="x", padx=4, pady=(8, 2))
            for name in names:
                b = ctk.CTkButton(
                    self._base_frame, text=bases.display_name(name), anchor="w",
                    height=44, font=ctk.CTkFont(size=12),
                    fg_color=PINK["base"], hover_color=PINK["base_hover"],
                    text_color=PINK["base_text"],
                    command=lambda n=name: self._select_base(n),
                )
                # 2行表示（英語名＋（日本語名））の行頭を左にそろえる。
                # CTkButton内部ラベルの既定 justify は中央寄せでガタつくため。
                if getattr(b, "_text_label", None) is not None:
                    b._text_label.configure(justify="left")
                b.pack(fill="x", padx=4, pady=2)
                self._base_buttons.append((name, b))
        self._highlight_base(self.base.get())

    def _select_base(self, name):
        self.base.set(name)
        self._highlight_base(name)

    def _highlight_base(self, name):
        for n, b in self._base_buttons:
            b.configure(border_width=3 if n == name else 0)

    def _select_time(self, key):
        self.time_of_day.set(key)
        for k, b in self._time_buttons.items():
            b.configure(border_width=3 if k == key else 0)

    def _select_image(self, path):
        self.selected_image = Path(path)
        self._image_grid.set_selected(self.selected_image)
        self._preview.show(self.selected_image)

    # ──────────────────────────────────────────
    #  ファイル名プレビュー
    # ──────────────────────────────────────────

    def _update_filename_preview(self):
        base = self.base.get()
        t = self.time_of_day.get()
        seq = None
        if base and t:
            try:
                target = paths.output_target_dir(base)
                seq = naming.next_sequence(target, base, t)
            except Exception:
                seq = None
        self.filename_preview.set(naming.title_preview(base, t, seq))

    # ──────────────────────────────────────────
    #  入力一覧（メモリ上リスト）
    # ──────────────────────────────────────────

    def refresh(self):
        """一覧を更新する。実体が消えた画像（移動済み等）は自動で取り除く。"""
        self._image_list = [p for p in self._image_list if p.exists()]
        self._image_grid.refresh(self._image_list)
        self.remaining.set(f"残り {len(self._image_list)} 枚")

    # ──────────────────────────────────────────
    #  確定フロー（保存 → 検証 → 元削除）
    # ──────────────────────────────────────────

    def on_confirm(self):
        # 0. 画像が選択されているか
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return

        base = self.base.get()
        t = self.time_of_day.get()
        old_index = self._index_of_selected()  # 連続仕分け: 確定後この位置へ次画像が来る

        # 1. バリデーション
        try:
            naming.validate(base, t)
        except ValidationError as e:
            messagebox.showwarning("入力エラー", f"{e}\n\n画像は移動していません。")
            return

        src = self.selected_image

        try:
            # 2. 保存先フォルダ（material/back/<拠点名>/）を用意
            target_dir = paths.output_target_dir(base)
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showwarning(
                "フォルダ作成失敗",
                f"保存先フォルダを作成できませんでした。\n{e}\n\n画像は移動していません。",
            )
            return

        try:
            # 3. 連番を再計算し、衝突する限り +1（多重起動・取りこぼしの保険）
            seq = naming.next_sequence(target_dir, base, t)
            for _ in range(1000):
                final_name = naming.build_filename(base, t, seq)
                final_path = target_dir / final_name
                if not final_path.exists():
                    break
                seq += 1
            else:
                raise OSError("連番の空きが見つかりませんでした。")

            # 4. 保存（png はバイト無劣化コピー、それ以外は PNG 変換）
            self._save_to_output(src, final_path)

        except Exception as e:
            # 作りかけがあれば消す。元画像はそのまま残す。
            try:
                if "final_path" in locals() and final_path.exists():
                    final_path.unlink(missing_ok=True)
            except Exception:
                pass
            messagebox.showwarning(
                "保存失敗",
                f"画像の保存に失敗しました。\n{e}\n\n元画像はそのまま残っています。",
            )
            return

        # 5. 元画像を削除（＝移動完了）
        try:
            src.unlink(missing_ok=True)
        except Exception as e:
            messagebox.showwarning(
                "元画像の削除に失敗",
                f"保存は成功しましたが、元画像を削除できませんでした。\n{e}\n"
                f"保存先：{final_path}\n手動で元の {src.name} を整理してください。",
            )

        # 6. UI更新（連続仕分け: 同じ位置へスライドする次の画像を自動選択）
        self.selected_image = None
        self._advance_after_removal(old_index)

    @staticmethod
    def _save_to_output(src: Path, final_path: Path):
        """src を final_path(.png) として保存し、検証する（失敗時は例外）。"""
        if src.suffix.lower() == ".png":
            # PNG はバイト無劣化でコピー（サイズ一致で検証）。
            shutil.copy2(src, final_path)
            if not final_path.exists() or final_path.stat().st_size != src.stat().st_size:
                raise OSError("コピー検証に失敗しました。")
        else:
            # jpg / jpeg / webp は Pillow で PNG に変換（透過保持）。
            with Image.open(src) as im:
                im.save(final_path, "PNG")
            if not final_path.exists() or final_path.stat().st_size == 0:
                raise OSError("保存後の検証に失敗しました。")

    # ──────────────────────────────────────────
    #  連続仕分け（インデックス管理）
    # ──────────────────────────────────────────

    def _index_of_selected(self) -> int:
        """選択中画像の現在の一覧内インデックス。無ければ 0。"""
        if self.selected_image is None:
            return 0
        try:
            return self._image_list.index(self.selected_image)
        except ValueError:
            return 0

    def _select_at_index(self, idx: int):
        """更新後の一覧で idx 位置（範囲外はクランプ）を選ぶ。空なら選択解除。"""
        if not self._image_list:
            self.selected_image = None
            self._preview.show(None)
            return
        idx = max(0, min(idx, len(self._image_list) - 1))
        self._select_image(self._image_list[idx])

    def _advance_after_removal(self, old_index: int):
        """確定/保留/削除で1枚消えた後、その位置へスライドしてくる次画像を自動選択。"""
        self.refresh()
        self._select_at_index(old_index)
        self._update_filename_preview()

    def _move_out(self, src: Path, dest_dir: Path) -> Path:
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

    # ──────────────────────────────────────────
    #  スキップ / 保留 / 削除
    # ──────────────────────────────────────────

    def on_skip(self):
        """ファイルを一切変更せず、次の画像へ進む（非破壊）。"""
        if not self._image_list:
            messagebox.showinfo("スキップ", "入力画像がありません。")
            return
        if self.selected_image is None:
            self._select_at_index(0)
            return
        idx = self._index_of_selected()
        if idx + 1 < len(self._image_list):
            self._select_at_index(idx + 1)
        else:
            messagebox.showinfo("スキップ", "これが最後の入力画像です。")

    def on_hold(self):
        """選択中画像を material/back/_hold へ退避して次へ進む（復元可能）。"""
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return
        src = self.selected_image
        old_index = self._index_of_selected()
        try:
            self._move_out(src, paths.HOLD_DIR)
        except Exception as e:
            messagebox.showwarning(
                "保留に失敗",
                f"画像を保留フォルダへ移せませんでした。\n{e}\n\n元画像はそのまま残っています。",
            )
            return
        self.selected_image = None
        self._advance_after_removal(old_index)

    def on_delete(self):
        """選択中画像を material/back/_trash へ退避（完全削除はしない・確認あり）。"""
        if self.selected_image is None or not self.selected_image.exists():
            messagebox.showwarning("未選択", "画像が選択されていません。")
            return
        src = self.selected_image
        if not messagebox.askyesno(
            "削除の確認",
            f"「{src.name}」をゴミ箱フォルダへ移動します。\n\n"
            f"完全削除ではなく {paths.TRASH_DIR} に退避するので、\n"
            "後から手動で復元できます。よろしいですか？",
        ):
            return
        old_index = self._index_of_selected()
        try:
            self._move_out(src, paths.TRASH_DIR)
        except Exception as e:
            messagebox.showwarning(
                "削除に失敗",
                f"画像をゴミ箱フォルダへ移せませんでした。\n{e}\n\n元画像はそのまま残っています。",
            )
            return
        self.selected_image = None
        self._advance_after_removal(old_index)


def main():
    app = BaseImageSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
