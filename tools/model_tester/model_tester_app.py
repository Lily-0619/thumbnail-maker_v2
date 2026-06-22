"""
model_tester_app.py
A1111 風 X/Y/Z プロット比較ツール（ComfyUI バックエンド）。

起動:
    python tools/model_tester/model_tester_app.py

X 軸=列 / Y 軸=行 / Z 軸=グリッドを複数枚、という A1111 の「X/Y/Z plot」と同じ考え方で、
Checkpoint / LoRA / Steps / CFG / Sampler / Seed / Prompt S/R などを自由に組み合わせて
一括生成し、ラベル付きの比較グリッド画像にまとめる。

定番機能を一通り搭載:
  - LoRA スタック（複数 LoRA の重ねがけ・個別強度）
  - Hires fix / アップスケール（latent ＋ アップスケーラーモデル）
  - clip skip / VAE 上書き / img2img
本体 ui/app.py と同じく CustomTkinter で書く。本体は一切変更しない。
"""

from __future__ import annotations

import os
import random
import sys
import threading
from datetime import datetime
from pathlib import Path

# ── プロジェクトルートを sys.path に追加（本体 main.py と同様）──
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

from tools.model_tester import comfy_client, config_loader, xyz_plot  # noqa: E402
from tools.model_tester.comfy_client import (  # noqa: E402
    HIRES_LATENT,
    HIRES_MODEL,
    HIRES_NONE,
    NO_LORA,
    VAE_FROM_CKPT,
    ComfyError,
    GenParams,
    LoraSpec,
)
from tools.model_tester.xyz_plot import (  # noqa: E402
    AXIS_LABELS,
    AXIS_NONE,
    AXIS_PROMPT_SR,
    LIST_AXES,
    Axis,
    AxisError,
)

# ── Theme（本体に合わせる。pink_theme は config/ と assets/config/ の両方を探す）──
ctk.set_appearance_mode("light")
for _theme in (
    PROJECT_ROOT / "config" / "pink_theme.json",
    PROJECT_ROOT / "assets" / "config" / "pink_theme.json",
):
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
    "accent": "#3f94d1",
    "cell": "#ffffff",
    "muted": "#9a8aa0",
}

LORA_SLOTS = 4               # ベース LoRA スタックの段数
GRID_CELL = (320, 180)       # 保存グリッドの 1 セル（16:9 想定）
PREVIEW_MAX_W = 760          # 結果プレビュー画像の最大幅


def short_label(name: str, limit: int = 30) -> str:
    if name in (NO_LORA, VAE_FROM_CKPT):
        return name
    stem = Path(name).name
    for ext in (".safetensors", ".ckpt", ".pt", ".pth"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return stem if len(stem) <= limit else stem[: limit - 1] + "…"


def slug(name: str) -> str:
    if name in (NO_LORA, VAE_FROM_CKPT):
        return "none"
    stem = Path(str(name)).stem
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in stem) or "x"


class ZoomWindow(ctk.CTkToplevel):
    """グリッド画像を大きく表示する別ウィンドウ。"""

    def __init__(self, parent, path: Path, caption: str = ""):
        super().__init__(parent)
        self.title(f"拡大 - {caption or Path(path).name}")
        self.geometry("1200x820")
        self._img_ref = None
        try:
            with Image.open(path) as opened:
                img = opened.convert("RGB")
        except Exception:
            ctk.CTkLabel(self, text="画像を開けませんでした。").pack(pady=20)
            return
        max_side = 1120
        w, h = img.size
        scale = min(max_side / w, max_side / h, 1.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        self._img_ref = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        if caption:
            ctk.CTkLabel(self, text=caption, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(8, 0))
        ctk.CTkLabel(self, image=self._img_ref, text="").pack(expand=True, fill="both", padx=10, pady=10)


# ──────────────────────────────────────────
#  アプリ本体
# ──────────────────────────────────────────


class ModelTesterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("X/Y/Z プロット比較ツール（ComfyUI）")
        self.geometry("1360x900")
        self.configure(fg_color=PINK["window"])

        self.config_data = config_loader.load_config()
        self.cfg = self.config_data.get("comfyui", {})
        self.url = comfy_client.comfy_url(self.cfg)
        self.timeout = int(self.config_data.get("timeout_seconds", 300))

        # サーバーから取得する一覧
        self.checkpoints: list[str] = []
        self.loras: list[str] = []
        self.vaes: list[str] = []
        self.upscalers: list[str] = []
        self.samplers: list[str] = ["euler"]
        self.schedulers: list[str] = ["normal"]

        # ── ベース設定の状態変数 ──
        self.v_steps = ctk.StringVar(value=str(self.cfg.get("steps", 28)))
        self.v_cfg = ctk.StringVar(value=str(self.cfg.get("cfg_scale", 7)))
        self.v_width = ctk.StringVar(value=str(self.cfg.get("width", 768)))
        self.v_height = ctk.StringVar(value=str(self.cfg.get("height", 432)))
        self.v_seed = ctk.StringVar(value="")
        self.v_clip = ctk.StringVar(value="1")
        self.v_ckpt = ctk.StringVar(value="")
        self.v_vae = ctk.StringVar(value=VAE_FROM_CKPT)
        self.v_sampler = ctk.StringVar(value=self.cfg.get("sampler_name", "euler"))
        self.v_scheduler = ctk.StringVar(value=self.cfg.get("scheduler", "normal"))

        # img2img
        self.v_img2img = ctk.StringVar(value="")
        self.v_img_denoise = ctk.StringVar(value="0.6")

        # Hires
        self.v_hires_mode = ctk.StringVar(value="OFF")
        self.v_hires_scale = ctk.StringVar(value="1.5")
        self.v_hires_steps = ctk.StringVar(value="12")
        self.v_hires_denoise = ctk.StringVar(value="0.5")
        self.v_hires_upscaler = ctk.StringVar(value="")

        # LoRA スタック（段ごとに name var, weight var）
        self.lora_name_vars = [ctk.StringVar(value=NO_LORA) for _ in range(LORA_SLOTS)]
        self.lora_weight_vars = [ctk.StringVar(value="1.0") for _ in range(LORA_SLOTS)]

        # 軸（X/Y/Z）の状態
        self.axis_type_vars = {a: ctk.StringVar(value="（なし）") for a in ("X", "Y", "Z")}
        self._axis_value_frames: dict[str, ctk.CTkFrame] = {}
        self._axis_value_widgets: dict[str, dict] = {"X": {}, "Y": {}, "Z": {}}

        self.status = ctk.StringVar(value="未接続。『接続 / 一覧更新』を押してください。")
        self.progress = ctk.StringVar(value="")

        self._busy = False
        self._last_run_dir: Path | None = None
        self._grid_paths: list[Path] = []
        self._img_refs: list = []  # CTkImage の参照保持

        self._build_layout()
        self._connect_and_list()

    # ──────────────────────────────────────────
    #  レイアウト
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color=PINK["panel"])
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        top.columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="X / Y / Z プロット比較", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        ctk.CTkLabel(top, textvariable=self.status, anchor="w", text_color="#7a3b5a").grid(
            row=0, column=1, sticky="ew", padx=10
        )

        controls = ctk.CTkScrollableFrame(self, fg_color=PINK["panel"], width=420, label_text="設定")
        controls.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=6)
        controls.columnconfigure(0, weight=1)
        self._build_controls(controls)

        right = ctk.CTkFrame(self, fg_color=PINK["panel"])
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        rhead = ctk.CTkFrame(right, fg_color="transparent")
        rhead.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        rhead.columnconfigure(0, weight=1)
        ctk.CTkLabel(rhead, textvariable=self.progress, anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(rhead, text="保存先を開く", width=110, command=self.on_open_output,
                      fg_color=PINK["accent"], hover_color=PINK["button_hover"]).grid(row=0, column=1, padx=4)

        self._results = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._results.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        self._results.columnconfigure(0, weight=1)
        self._show_placeholder()

    def _build_controls(self, parent):
        r = 0

        def section(text):
            nonlocal r
            ctk.CTkLabel(parent, text=text, anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold"), text_color="#7a3b5a").grid(
                row=r, column=0, sticky="ew", padx=8, pady=(10, 2)); r += 1

        # ── プロンプト ──
        section("プロンプト")
        self._prompt_box = ctk.CTkTextbox(parent, height=78, wrap="word")
        self._prompt_box.insert("1.0", "1girl, fantasy knight, dramatic lighting, masterpiece, best quality")
        self._prompt_box.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1
        ctk.CTkLabel(parent, text="ネガティブ", anchor="w").grid(row=r, column=0, sticky="ew", padx=8); r += 1
        self._neg_box = ctk.CTkTextbox(parent, height=52, wrap="word")
        self._neg_box.insert("1.0", "lowres, bad anatomy, worst quality, blurry")
        self._neg_box.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1

        # ── ベース設定 ──
        section("ベース設定（軸にしない項目の既定値）")
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        grid.columnconfigure((1, 3), weight=1)
        for i, (label, var) in enumerate(
            (("steps", self.v_steps), ("cfg", self.v_cfg), ("幅", self.v_width),
             ("高さ", self.v_height), ("seed", self.v_seed), ("clip skip", self.v_clip))
        ):
            row, col = divmod(i, 2)
            ctk.CTkLabel(grid, text=label, width=56, anchor="e").grid(row=row, column=col * 2, sticky="e", padx=(0, 4), pady=2)
            ent = ctk.CTkEntry(grid, textvariable=var, width=90)
            if var is self.v_seed:
                ent.configure(placeholder_text="空=ランダム")
            ent.grid(row=row, column=col * 2 + 1, sticky="ew", pady=2)

        self._ckpt_menu = self._labeled_menu(parent, r, "モデル", self.v_ckpt, ["(接続待ち)"]); r += 1
        self._sampler_menu = self._labeled_menu(parent, r, "Sampler", self.v_sampler, self.samplers); r += 1
        self._scheduler_menu = self._labeled_menu(parent, r, "Scheduler", self.v_scheduler, self.schedulers); r += 1
        self._vae_menu = self._labeled_menu(parent, r, "VAE", self.v_vae, [VAE_FROM_CKPT]); r += 1

        # ── LoRA スタック ──
        section("LoRA スタック（重ねがけ可）")
        self._lora_menus = []
        for i in range(LORA_SLOTS):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.grid(row=r, column=0, sticky="ew", padx=8, pady=1); r += 1
            row.columnconfigure(0, weight=1)
            menu = ctk.CTkOptionMenu(row, variable=self.lora_name_vars[i], values=[NO_LORA])
            menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ctk.CTkEntry(row, textvariable=self.lora_weight_vars[i], width=60).grid(row=0, column=1)
            self._lora_menus.append(menu)

        # ── Hires / アップスケール ──
        section("Hires fix / アップスケール")
        hrow = ctk.CTkFrame(parent, fg_color="transparent")
        hrow.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        hrow.columnconfigure(1, weight=1)
        ctk.CTkLabel(hrow, text="方式", width=56, anchor="e").grid(row=0, column=0, padx=(0, 4))
        ctk.CTkOptionMenu(hrow, variable=self.v_hires_mode,
                          values=["OFF", "latent（再サンプル）", "アップスケーラーモデル"]).grid(row=0, column=1, sticky="ew")
        hgrid = ctk.CTkFrame(parent, fg_color="transparent")
        hgrid.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        hgrid.columnconfigure((1, 3), weight=1)
        for i, (label, var) in enumerate(
            (("倍率", self.v_hires_scale), ("steps", self.v_hires_steps), ("denoise", self.v_hires_denoise))
        ):
            row, col = divmod(i, 2)
            ctk.CTkLabel(hgrid, text=label, width=56, anchor="e").grid(row=row, column=col * 2, sticky="e", padx=(0, 4), pady=2)
            ctk.CTkEntry(hgrid, textvariable=var, width=90).grid(row=row, column=col * 2 + 1, sticky="ew", pady=2)
        self._upscaler_menu = self._labeled_menu(parent, r, "Upscaler", self.v_hires_upscaler, ["(接続後に取得)"]); r += 1

        # ── img2img ──
        section("img2img（任意）")
        irow = ctk.CTkFrame(parent, fg_color="transparent")
        irow.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        irow.columnconfigure(0, weight=1)
        ctk.CTkEntry(irow, textvariable=self.v_img2img, placeholder_text="元画像パス（空=txt2img）").grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(irow, text="選択", width=56, command=self._pick_init_image,
                      fg_color=PINK["accent"], hover_color=PINK["button_hover"]).grid(row=0, column=1)
        ctk.CTkButton(irow, text="×", width=28, command=lambda: self.v_img2img.set(""),
                      fg_color=PINK["muted"], hover_color="#7a6a85").grid(row=0, column=2, padx=(4, 0))
        idr = ctk.CTkFrame(parent, fg_color="transparent")
        idr.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        ctk.CTkLabel(idr, text="denoise", width=56, anchor="e").grid(row=0, column=0, padx=(0, 4))
        ctk.CTkEntry(idr, textvariable=self.v_img_denoise, width=90).grid(row=0, column=1, sticky="w")

        # ── X / Y / Z 軸 ──
        section("X / Y / Z 軸")
        for axis in ("X", "Y", "Z"):
            block = ctk.CTkFrame(parent, fg_color=PINK["cell"], corner_radius=8)
            block.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1
            block.columnconfigure(1, weight=1)
            ctk.CTkLabel(block, text=f"{axis} 軸", width=44,
                         font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, padx=6, pady=6)
            ctk.CTkOptionMenu(
                block, variable=self.axis_type_vars[axis], values=list(AXIS_LABELS.keys()),
                command=lambda _v, a=axis: self._rebuild_axis_value(a),
            ).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
            value_frame = ctk.CTkFrame(block, fg_color="transparent")
            value_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
            value_frame.columnconfigure(0, weight=1)
            self._axis_value_frames[axis] = value_frame
            self._rebuild_axis_value(axis)

        # ── ボタン ──
        self._refresh_btn = ctk.CTkButton(parent, text="接続 / 一覧更新", command=self._connect_and_list,
                                           fg_color=PINK["accent"], hover_color=PINK["button_hover"])
        self._refresh_btn.grid(row=r, column=0, sticky="ew", padx=8, pady=(10, 2)); r += 1
        self._gen_btn = ctk.CTkButton(parent, text="▶ プロット生成", command=self.on_generate,
                                      fg_color=PINK["button"], hover_color=PINK["button_hover"],
                                      font=ctk.CTkFont(size=14, weight="bold"), height=40)
        self._gen_btn.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1

    def _labeled_menu(self, parent, row, label, var, values):
        """ラベル＋OptionMenu を指定行に1行作って、その OptionMenu を返す。"""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(row_frame, text=label, width=56, anchor="e").grid(row=0, column=0, padx=(0, 4))
        menu = ctk.CTkOptionMenu(row_frame, variable=var, values=values or ["(なし)"])
        menu.grid(row=0, column=1, sticky="ew")
        return menu

    # ── 軸の値入力エリアを種類に応じて作り直す ──

    def _rebuild_axis_value(self, axis: str):
        frame = self._axis_value_frames[axis]
        for child in frame.winfo_children():
            child.destroy()
        self._axis_value_widgets[axis] = {}
        kind = AXIS_LABELS.get(self.axis_type_vars[axis].get(), AXIS_NONE)
        if kind == AXIS_NONE:
            ctk.CTkLabel(frame, text="（この軸は使わない）", text_color=PINK["muted"]).grid(row=0, column=0, sticky="w")
            return
        if kind in LIST_AXES:
            values = self._axis_source_values(kind)
            box = ctk.CTkScrollableFrame(frame, height=110, fg_color=PINK["panel"], label_text="チェックで比較対象に")
            box.grid(row=0, column=0, sticky="ew")
            check_vars: dict[str, ctk.BooleanVar] = {}
            if not values:
                ctk.CTkLabel(box, text="（接続して一覧を取得してください）", text_color=PINK["muted"]).pack(anchor="w")
            for name in values:
                v = ctk.BooleanVar(value=False)
                check_vars[name] = v
                ctk.CTkCheckBox(box, text=short_label(name, 34), variable=v).pack(anchor="w", padx=4, pady=1)
            self._axis_value_widgets[axis] = {"checks": check_vars}
        else:
            hint = {
                AXIS_PROMPT_SR: "検索語, 置換1, 置換2 …",
            }.get(kind, "カンマ区切り（例: 20, 28, 35）")
            ent = ctk.CTkEntry(frame, placeholder_text=hint)
            ent.grid(row=0, column=0, sticky="ew")
            self._axis_value_widgets[axis] = {"entry": ent}

    def _axis_source_values(self, kind: str) -> list[str]:
        from tools.model_tester.xyz_plot import (
            AXIS_CKPT, AXIS_LORA, AXIS_SAMPLER, AXIS_SCHEDULER,
        )
        if kind == AXIS_CKPT:
            return self.checkpoints
        if kind == AXIS_LORA:
            return [NO_LORA] + self.loras
        if kind == AXIS_SAMPLER:
            return self.samplers
        if kind == AXIS_SCHEDULER:
            return self.schedulers
        return []

    def _read_axis(self, axis: str) -> Axis:
        kind = AXIS_LABELS.get(self.axis_type_vars[axis].get(), AXIS_NONE)
        if kind == AXIS_NONE:
            return Axis(AXIS_NONE, [])
        widgets = self._axis_value_widgets.get(axis, {})
        if "checks" in widgets:
            values = [name for name, v in widgets["checks"].items() if v.get()]
            if not values:
                raise AxisError(f"{axis} 軸の比較対象を1つ以上チェックしてください。")
            return Axis(kind, values)
        ent = widgets.get("entry")
        raw = ent.get() if ent is not None else ""
        from tools.model_tester.xyz_plot import parse_values
        return Axis(kind, parse_values(kind, raw))

    # ──────────────────────────────────────────
    #  接続 & 一覧取得
    # ──────────────────────────────────────────

    def _connect_and_list(self):
        if self._busy:
            return
        self._set_busy(True)
        self.status.set("ComfyUI に接続中 / 一覧取得中...")
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        try:
            msg = comfy_client.ensure_ready(self.config_data, start_if_needed=True)
            data = {
                "ckpts": comfy_client.list_checkpoints(self.url, timeout=20),
                "loras": comfy_client.list_loras(self.url, timeout=20),
                "vaes": comfy_client.list_vaes(self.url, timeout=20),
                "upscalers": comfy_client.list_upscalers(self.url, timeout=20),
                "samplers": comfy_client.list_samplers(self.url, timeout=20),
                "schedulers": comfy_client.list_schedulers(self.url, timeout=20),
            }
        except ComfyError as e:
            self.after(0, self._on_connect_failed, str(e))
            return
        except Exception as e:
            self.after(0, self._on_connect_failed, f"想定外のエラー: {e}")
            return
        self.after(0, self._populate_lists, data, msg)

    def _on_connect_failed(self, message: str):
        self._set_busy(False)
        self.status.set("接続に失敗しました。")
        messagebox.showwarning("ComfyUI 接続", message)

    def _populate_lists(self, data, msg):
        self._set_busy(False)
        self.checkpoints = data["ckpts"]
        self.loras = data["loras"]
        self.vaes = data["vaes"]
        self.upscalers = data["upscalers"]
        self.samplers = data["samplers"] or self.samplers
        self.schedulers = data["schedulers"] or self.schedulers

        self._ckpt_menu.configure(values=self.checkpoints or ["(モデルなし)"])
        if self.checkpoints and self.v_ckpt.get() not in self.checkpoints:
            self.v_ckpt.set(self.checkpoints[0])

        self._sampler_menu.configure(values=self.samplers)
        if self.v_sampler.get() not in self.samplers:
            self.v_sampler.set(self.samplers[0])
        self._scheduler_menu.configure(values=self.schedulers)
        if self.v_scheduler.get() not in self.schedulers:
            self.v_scheduler.set(self.schedulers[0])

        self._vae_menu.configure(values=[VAE_FROM_CKPT] + self.vaes)
        for menu in self._lora_menus:
            menu.configure(values=[NO_LORA] + self.loras)
        self._upscaler_menu.configure(values=self.upscalers or ["(なし)"])
        if self.upscalers and not self.v_hires_upscaler.get():
            self.v_hires_upscaler.set(self.upscalers[0])

        # 既に開いている軸の値エリア（リスト型）を再構築
        for axis in ("X", "Y", "Z"):
            kind = AXIS_LABELS.get(self.axis_type_vars[axis].get(), AXIS_NONE)
            if kind in LIST_AXES:
                self._rebuild_axis_value(axis)

        self.status.set(
            f"{msg}　モデル{len(self.checkpoints)} / LoRA{len(self.loras)} / "
            f"VAE{len(self.vaes)} / Upscaler{len(self.upscalers)}"
        )

    # ──────────────────────────────────────────
    #  ベース GenParams 構築
    # ──────────────────────────────────────────

    def _build_base_params(self) -> GenParams:
        def as_int(var, label, lo, hi):
            try:
                v = int(float(var.get()))
            except ValueError:
                raise AxisError(f"{label} は数値で入力してください。現在: {var.get()}")
            if not (lo <= v <= hi):
                raise AxisError(f"{label} は {lo}〜{hi} にしてください。現在: {v}")
            return v

        def as_float(var, label):
            try:
                return float(var.get())
            except ValueError:
                raise AxisError(f"{label} は数値で入力してください。現在: {var.get()}")

        prompt = self._prompt_box.get("1.0", "end").strip()
        negative = self._neg_box.get("1.0", "end").strip()
        if not prompt:
            raise AxisError("プロンプトを入力してください。")

        ckpt = self.v_ckpt.get().strip()
        if not ckpt or ckpt.startswith("("):
            raise AxisError("モデル(checkpoint)を選んでください（接続後に一覧から選択）。")

        seed = None
        seed_raw = self.v_seed.get().strip()
        if seed_raw:
            try:
                seed = int(seed_raw)
            except ValueError:
                raise AxisError(f"seed は整数で入力してください（空=ランダム）。現在: {seed_raw}")

        loras: list[LoraSpec] = []
        for name_var, w_var in zip(self.lora_name_vars, self.lora_weight_vars):
            name = name_var.get()
            if name and name != NO_LORA:
                loras.append(LoraSpec(name, as_float(w_var, "LoRA強度"), as_float(w_var, "LoRA強度")))

        vae = self.v_vae.get()
        vae_name = None if vae == VAE_FROM_CKPT else vae

        # Hires
        hires_mode = {"OFF": HIRES_NONE, "latent（再サンプル）": HIRES_LATENT,
                      "アップスケーラーモデル": HIRES_MODEL}.get(self.v_hires_mode.get(), HIRES_NONE)
        upscaler = self.v_hires_upscaler.get()
        if hires_mode == HIRES_MODEL and (not upscaler or upscaler.startswith("(")):
            raise AxisError("アップスケーラーモデル方式を使うには Upscaler を選んでください（接続後に取得）。")

        # img2img
        init_name = None
        denoise = 1.0
        init_path = self.v_img2img.get().strip()
        if init_path:
            p = Path(init_path)
            if not p.exists():
                raise AxisError(f"img2img の元画像が見つかりません: {init_path}")
            try:
                init_name = comfy_client.upload_image(self.url, p, timeout=60)
            except Exception as e:
                raise AxisError(f"元画像のアップロードに失敗しました: {e}")
            denoise = as_float(self.v_img_denoise, "img2img denoise")

        return GenParams(
            prompt=prompt,
            negative=negative,
            ckpt_name=ckpt,
            vae_name=vae_name,
            loras=loras,
            width=as_int(self.v_width, "幅", 64, 4096),
            height=as_int(self.v_height, "高さ", 64, 4096),
            steps=as_int(self.v_steps, "steps", 1, 200),
            cfg_scale=as_float(self.v_cfg, "cfg"),
            sampler_name=self.v_sampler.get(),
            scheduler=self.v_scheduler.get(),
            seed=seed,
            clip_skip=as_int(self.v_clip, "clip skip", 1, 12),
            denoise=denoise,
            init_image_name=init_name,
            hires_mode=hires_mode,
            hires_scale=as_float(self.v_hires_scale, "Hires 倍率"),
            hires_steps=as_int(self.v_hires_steps, "Hires steps", 1, 200),
            hires_denoise=as_float(self.v_hires_denoise, "Hires denoise"),
            hires_upscaler=upscaler if hires_mode == HIRES_MODEL else "",
        )

    # ──────────────────────────────────────────
    #  生成
    # ──────────────────────────────────────────

    def on_generate(self):
        if self._busy:
            return
        try:
            base = self._build_base_params()
            x = self._read_axis("X")
            y = self._read_axis("Y")
            z = self._read_axis("Z")
        except AxisError as e:
            messagebox.showwarning("入力エラー", str(e))
            return

        # 全セルでシードを揃える（Seed 軸を使わず、seed 未指定なら 1 つ固定）
        from tools.model_tester.xyz_plot import AXIS_SEED
        seed_is_axis = AXIS_SEED in (x.kind, y.kind, z.kind)
        if base.seed is None and not seed_is_axis:
            base.seed = random.randint(0, 2**63 - 1)

        jobs = xyz_plot.build_jobs(base, x, y, z)
        if not jobs:
            messagebox.showwarning("入力エラー", "生成する組み合わせがありません。")
            return
        if len(jobs) > 64 and not messagebox.askyesno(
            "確認", f"{len(jobs)} 枚を生成します。時間がかかりますが続けますか？"
        ):
            return

        # 軸ヘッダー（保存グリッド・表示用）
        self._x_headers = self._axis_headers(x)
        self._y_headers = self._axis_headers(y)
        self._z_headers = self._axis_headers(z)

        self._last_run_dir = PROJECT_ROOT / "outputs" / "model_tester" / datetime.now().strftime("%Y%m%d_%H%M%S")
        self._grid_paths = []
        self._img_refs = []
        self._cell_images: dict[tuple[int, int, int], Image.Image] = {}
        self._prepare_results_view(x, y, z)

        self._set_busy(True)
        self.progress.set(f"生成中 0 / {len(jobs)} ...")
        threading.Thread(target=self._generate_worker, args=(jobs,), daemon=True).start()

    def _axis_headers(self, axis: Axis) -> list[str]:
        from tools.model_tester.xyz_plot import value_label
        if not axis.active:
            return [""]
        if axis.kind == AXIS_PROMPT_SR:
            return [value_label(axis.kind, v) for v in axis.values[1:]]
        return [value_label(axis.kind, v) for v in axis.values]

    def _generate_worker(self, jobs):
        try:
            comfy_client.ensure_ready(self.config_data, start_if_needed=True)
        except ComfyError as e:
            self.after(0, self._abort_batch, str(e))
            return

        total = len(jobs)
        done = 0
        for job in jobs:
            self.after(0, self._mark_running, job)
            try:
                workflow, used_seed = comfy_client.build_workflow(job.params)
                image = comfy_client.generate(self.url, workflow, timeout=self.timeout)
                path = self._save_cell(image, job, used_seed)
                self._cell_images[(job.z_index, job.y_index, job.x_index)] = image
                self.after(0, self._place_cell, job, image, path)
            except Exception as e:
                self.after(0, self._place_error, job, str(e))
            done += 1
            self.after(0, self.progress.set, f"生成中 {done} / {total} ...")

        self.after(0, self._finish_batch, total)

    def _save_cell(self, image: Image.Image, job, seed) -> Path:
        run_dir = self._last_run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        name = f"z{job.z_index}_y{job.y_index}_x{job.x_index}_seed{seed}.png"
        out = run_dir / name
        image.convert("RGB").save(out, "PNG")
        return out

    # ── 結果表示（Z ごとにライブのセル枠 → 完了でグリッド画像を保存）──

    def _show_placeholder(self):
        for child in self._results.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._results,
            text="左で X / Y / Z 軸を設定して『▶ プロット生成』を押してください。\n"
                 "X=列、Y=行、Z=グリッドを複数枚に分けます。",
            justify="left",
        ).grid(row=0, column=0, padx=12, pady=12, sticky="w")

    def _prepare_results_view(self, x: Axis, y: Axis, z: Axis):
        for child in self._results.winfo_children():
            child.destroy()
        self._cell_widgets: dict[tuple[int, int, int], ctk.CTkLabel] = {}
        cols = len(self._x_headers)
        rows = len(self._y_headers)
        cell_w, cell_h = 150, 84

        gr = 0
        for zi, zhead in enumerate(self._z_headers):
            if z.active:
                ctk.CTkLabel(self._results, text=f"Z: {zhead}",
                             font=ctk.CTkFont(size=13, weight="bold"), text_color="#7a3b5a").grid(
                    row=gr, column=0, sticky="w", padx=6, pady=(8, 2)); gr += 1
            block = ctk.CTkFrame(self._results, fg_color=PINK["panel"])
            block.grid(row=gr, column=0, sticky="w", padx=6, pady=4); gr += 1

            ctk.CTkLabel(block, text="Y＼X", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=3, pady=3)
            for ci, xhead in enumerate(self._x_headers, start=1):
                ctk.CTkLabel(block, text=xhead or "—", font=ctk.CTkFont(size=11, weight="bold"),
                             wraplength=cell_w).grid(row=0, column=ci, padx=3, pady=3)
            for ri, yhead in enumerate(self._y_headers, start=1):
                ctk.CTkLabel(block, text=yhead or "—", font=ctk.CTkFont(size=11, weight="bold"),
                             wraplength=110, justify="left").grid(row=ri, column=0, padx=3, pady=3)
                for ci in range(1, cols + 1):
                    cell = ctk.CTkLabel(block, text="待機", width=cell_w, height=cell_h,
                                        fg_color=PINK["cell"], corner_radius=4)
                    cell.grid(row=ri, column=ci, padx=3, pady=3)
                    self._cell_widgets[(zi, ri - 1, ci - 1)] = cell

    def _mark_running(self, job):
        cell = self._cell_widgets.get((job.z_index, job.y_index, job.x_index))
        if cell is not None:
            cell.configure(text="生成中…")

    def _place_cell(self, job, image, path):
        cell = self._cell_widgets.get((job.z_index, job.y_index, job.x_index))
        if cell is None:
            return
        thumb = image.convert("RGB")
        thumb.thumbnail((150, 84), Image.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=thumb.size)
        self._img_refs.append(ctk_img)
        cell.configure(image=ctk_img, text="")

    def _place_error(self, job, message):
        cell = self._cell_widgets.get((job.z_index, job.y_index, job.x_index))
        if cell is not None:
            cell.configure(text=f"失敗\n{message[:50]}", fg_color="#f3d6d6")

    def _abort_batch(self, message):
        self._set_busy(False)
        self.progress.set("中止しました。")
        messagebox.showwarning("ComfyUI 接続", message)

    def _finish_batch(self, total):
        self._set_busy(False)
        # Z ごとにラベル付きグリッド画像を合成・保存し、結果欄に表示
        for zi, zhead in enumerate(self._z_headers):
            cells = {
                (job_y, job_x): img
                for (z, job_y, job_x), img in self._cell_images.items() if z == zi
            }
            if not cells:
                continue
            title = f"Z: {zhead}" if zhead else ""
            grid = xyz_plot.compose_grid(
                cells, x_headers=self._x_headers, y_headers=self._y_headers,
                title=title, cell_size=GRID_CELL,
            )
            grid_path = self._last_run_dir / f"grid_z{zi}.png"
            grid.convert("RGB").save(grid_path, "PNG")
            self._grid_paths.append(grid_path)
            self._append_grid_preview(grid, grid_path, title)

        ok = len(self._cell_images)
        self.progress.set(
            f"完了：{ok} / {total} 枚　グリッド {len(self._grid_paths)} 枚保存："
            f"outputs/model_tester/{self._last_run_dir.name}"
        )

    def _append_grid_preview(self, grid_image: Image.Image, path: Path, caption: str):
        # ライブのセル枠を消して、合成済みグリッド画像（クリックで拡大）を並べる
        if not getattr(self, "_grid_view_started", False):
            for child in self._results.winfo_children():
                child.destroy()
            self._grid_view_started = True
            self._grid_view_row = 0

        img = grid_image.convert("RGB")
        scale = min(PREVIEW_MAX_W / img.width, 1.0)
        size = (int(img.width * scale), int(img.height * scale))
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self._img_refs.append(ctk_img)

        if caption:
            ctk.CTkLabel(self._results, text=caption, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#7a3b5a").grid(row=self._grid_view_row, column=0, sticky="w", padx=6, pady=(8, 0))
            self._grid_view_row += 1
        lbl = ctk.CTkLabel(self._results, image=ctk_img, text="")
        lbl.grid(row=self._grid_view_row, column=0, sticky="w", padx=6, pady=4)
        lbl.bind("<Button-1>", lambda e, p=path, cap=caption: ZoomWindow(self, p, cap))
        self._grid_view_row += 1

    # ──────────────────────────────────────────
    #  その他
    # ──────────────────────────────────────────

    def _pick_init_image(self):
        path = filedialog.askopenfilename(
            title="img2img 元画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.webp"), ("すべて", "*.*")],
        )
        if path:
            self.v_img2img.set(path)

    def on_open_output(self):
        target = self._last_run_dir if (self._last_run_dir and self._last_run_dir.exists()) \
            else PROJECT_ROOT / "outputs" / "model_tester"
        target.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(target))  # Windows
        except AttributeError:
            messagebox.showinfo("保存先", f"保存先フォルダ：\n{target}")

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._gen_btn.configure(state=state)
        self._refresh_btn.configure(state=state)
        if not busy:
            self._grid_view_started = False


def main():
    app = ModelTesterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
