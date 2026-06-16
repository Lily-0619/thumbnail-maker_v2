"""
model_tester_app.py
モデル(checkpoint) × LoRA 比較ツール エントリーポイント。

起動:
    python tools/model_tester/model_tester_app.py

同じプロンプト・同じシードを「選んだ複数モデル × 選んだ複数LoRA」で一括生成し、
行=モデル / 列=LoRA のグリッドに並べて見比べる（XYプロット/コンタクトシート風）。
本体 ui/app.py と同じく CustomTkinter で書く。本体は一切変更しない。
"""

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
from tkinter import messagebox  # noqa: E402

from tools.model_tester import comfy_client, config_loader  # noqa: E402
from tools.model_tester.comfy_client import NO_LORA, ComfyError  # noqa: E402

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
    "cell_wait": "#efe2ea",
}

CELL_SIZE = (220, 124)  # 比較セルのサムネ（16:9想定）


# ──────────────────────────────────────────
#  画像ユーティリティ
# ──────────────────────────────────────────


def make_thumbnail(image: Image.Image, size):
    """アスペクト比を保ったままセル用サムネを作って返す（中央寄せの透明キャンバス）。"""
    img = image.convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    canvas.paste(img, offset)
    return canvas


def short_label(name: str, limit: int = 22) -> str:
    """ファイル名から拡張子を外し、長すぎれば省略して表示用にする。"""
    if name == NO_LORA:
        return name
    stem = Path(name).name
    for ext in (".safetensors", ".ckpt", ".pt"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return stem if len(stem) <= limit else stem[: limit - 1] + "…"


def slug(name: str) -> str:
    """保存ファイル名用に英数記号へ単純化する。"""
    if name == NO_LORA:
        return "noLora"
    stem = Path(name).stem
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in stem) or "x"


class ZoomWindow(ctk.CTkToplevel):
    """画像を大きく表示する別ウィンドウ。"""

    def __init__(self, parent, path: Path, caption: str = ""):
        super().__init__(parent)
        self.title(f"拡大 - {caption or Path(path).name}")
        self.geometry("1000x720")
        self._img_ref = None
        try:
            with Image.open(path) as opened:
                img = opened.convert("RGBA")
        except Exception:
            ctk.CTkLabel(self, text="画像を開けませんでした。").pack(pady=20)
            return
        max_side = 940
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
        self.title("モデル / LoRA 比較ツール")
        self.geometry("1320x880")
        self.configure(fg_color=PINK["window"])

        self.config_data = config_loader.load_config()
        self.cfg = self.config_data.get("comfyui", {})
        self.url = comfy_client.comfy_url(self.cfg)
        self.timeout = int(self.config_data.get("timeout_seconds", 300))

        # ── 入力状態 ──
        self.steps = ctk.StringVar(value=str(self.cfg.get("steps", 28)))
        self.cfg_scale = ctk.StringVar(value=str(self.cfg.get("cfg_scale", 7)))
        self.width = ctk.StringVar(value=str(self.cfg.get("width", 768)))
        self.height = ctk.StringVar(value=str(self.cfg.get("height", 432)))
        self.seed_text = ctk.StringVar(value="")
        self.same_seed = ctk.BooleanVar(value=True)
        self.lora_strength = ctk.StringVar(value="1.0")
        self.status = ctk.StringVar(value="未接続。『接続 / 一覧更新』を押してください。")
        self.progress = ctk.StringVar(value="")

        # checkpoint / LoRA の選択状態
        self._ckpt_order: list[str] = []
        self._lora_order: list[str] = [NO_LORA]
        self._ckpt_vars: dict[str, ctk.BooleanVar] = {}
        self._lora_vars: dict[str, ctk.BooleanVar] = {NO_LORA: ctk.BooleanVar(value=True)}

        # 結果グリッド
        self._cells: dict[tuple[str, str], ctk.CTkLabel] = {}
        self._cell_paths: dict[tuple[str, str], Path] = {}
        self._thumb_refs: list = []
        self._last_run_dir: Path | None = None
        self._busy = False

        self._build_layout()
        # 起動と同時に接続・一覧取得を試みる
        self._connect_and_list()

    # ──────────────────────────────────────────
    #  レイアウト
    # ──────────────────────────────────────────

    def _build_layout(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # ── 上部バー ──
        top = ctk.CTkFrame(self, fg_color=PINK["panel"])
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        top.columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="モデル / LoRA 比較", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        ctk.CTkLabel(top, textvariable=self.status, anchor="w", text_color="#7a3b5a").grid(
            row=0, column=1, sticky="ew", padx=10
        )

        # ── 左：操作パネル（スクロール可能）──
        controls = ctk.CTkScrollableFrame(self, fg_color=PINK["panel"], width=360, label_text="設定")
        controls.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=6)
        controls.columnconfigure(0, weight=1)
        self._build_controls(controls)

        # ── 右：結果グリッド ──
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
        ctk.CTkLabel(
            self._results,
            text="ここに比較結果が並びます。\n左で設定して『▶ 一括生成』を押してください。",
            justify="left",
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

    def _build_controls(self, parent):
        r = 0

        ctk.CTkLabel(parent, text="プロンプト", anchor="w").grid(row=r, column=0, sticky="ew", padx=8, pady=(8, 0)); r += 1
        self._prompt_box = ctk.CTkTextbox(parent, height=80, wrap="word")
        self._prompt_box.insert("1.0", "1girl, fantasy knight, dramatic lighting, masterpiece, best quality")
        self._prompt_box.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1

        ctk.CTkLabel(parent, text="ネガティブプロンプト", anchor="w").grid(row=r, column=0, sticky="ew", padx=8, pady=(4, 0)); r += 1
        self._neg_box = ctk.CTkTextbox(parent, height=56, wrap="word")
        self._neg_box.insert("1.0", "lowres, bad anatomy, worst quality, blurry")
        self._neg_box.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1

        # 数値パラメータ（2列）
        params = ctk.CTkFrame(parent, fg_color="transparent")
        params.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1
        params.columnconfigure((1, 3), weight=1)
        for i, (label, var) in enumerate(
            (("steps", self.steps), ("cfg", self.cfg_scale), ("幅", self.width), ("高さ", self.height))
        ):
            row, col = divmod(i, 2)
            ctk.CTkLabel(params, text=label, width=40, anchor="e").grid(row=row, column=col * 2, sticky="e", padx=(0, 4), pady=2)
            ctk.CTkEntry(params, textvariable=var, width=80).grid(row=row, column=col * 2 + 1, sticky="ew", pady=2)

        # シード
        seed_row = ctk.CTkFrame(parent, fg_color="transparent")
        seed_row.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1
        seed_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(seed_row, text="seed", width=40, anchor="e").grid(row=0, column=0, padx=(0, 4))
        ctk.CTkEntry(seed_row, textvariable=self.seed_text, placeholder_text="空=ランダム").grid(row=0, column=1, sticky="ew")
        ctk.CTkCheckBox(parent, text="全セルで同じシードを使う（比較用・推奨）", variable=self.same_seed).grid(
            row=r, column=0, sticky="w", padx=8, pady=(0, 4)
        ); r += 1

        # LoRA 強度
        ls = ctk.CTkFrame(parent, fg_color="transparent")
        ls.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1
        ls.columnconfigure(1, weight=1)
        ctk.CTkLabel(ls, text="LoRA強度", anchor="e").grid(row=0, column=0, padx=(0, 4))
        ctk.CTkEntry(ls, textvariable=self.lora_strength, width=80).grid(row=0, column=1, sticky="w")

        # モデル一覧
        ctk.CTkLabel(parent, text="モデル (checkpoint)", anchor="w").grid(row=r, column=0, sticky="ew", padx=8, pady=(6, 0)); r += 1
        self._ckpt_frame = ctk.CTkScrollableFrame(parent, height=150, label_text="チェックして比較対象に")
        self._ckpt_frame.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1

        # LoRA一覧
        ctk.CTkLabel(parent, text="LoRA", anchor="w").grid(row=r, column=0, sticky="ew", padx=8, pady=(6, 0)); r += 1
        self._lora_frame = ctk.CTkScrollableFrame(parent, height=150, label_text="（LoRAなし）を含む")
        self._lora_frame.grid(row=r, column=0, sticky="ew", padx=8, pady=4); r += 1

        # ボタン
        self._refresh_btn = ctk.CTkButton(parent, text="接続 / 一覧更新", command=self._connect_and_list,
                                           fg_color=PINK["accent"], hover_color=PINK["button_hover"])
        self._refresh_btn.grid(row=r, column=0, sticky="ew", padx=8, pady=(8, 2)); r += 1
        self._gen_btn = ctk.CTkButton(parent, text="▶ 一括生成", command=self.on_generate,
                                      fg_color=PINK["button"], hover_color=PINK["button_hover"],
                                      font=ctk.CTkFont(size=14, weight="bold"), height=40)
        self._gen_btn.grid(row=r, column=0, sticky="ew", padx=8, pady=2); r += 1
        ctk.CTkButton(parent, text="結果をクリア", command=self._clear_results,
                      fg_color="#9a8aa0", hover_color="#7a6a85").grid(row=r, column=0, sticky="ew", padx=8, pady=(2, 8)); r += 1

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
            ckpts = comfy_client.list_checkpoints(self.url, timeout=20)
            loras = comfy_client.list_loras(self.url, timeout=20)
        except ComfyError as e:
            self.after(0, self._on_connect_failed, str(e))
            return
        except Exception as e:  # 予期しない失敗でも落とさない
            self.after(0, self._on_connect_failed, f"想定外のエラー: {e}")
            return
        self.after(0, self._populate_lists, ckpts, loras, msg)

    def _on_connect_failed(self, message: str):
        self._set_busy(False)
        self.status.set("接続に失敗しました。")
        messagebox.showwarning("ComfyUI 接続", message)

    def _populate_lists(self, ckpts, loras, msg):
        self._set_busy(False)
        # checkpoint
        for child in self._ckpt_frame.winfo_children():
            child.destroy()
        self._ckpt_order = list(ckpts)
        new_ckpt_vars = {}
        if not ckpts:
            ctk.CTkLabel(self._ckpt_frame, text="モデルが見つかりません。\nComfyUI の models/checkpoints に\n.safetensors を置いてください。",
                         justify="left").pack(anchor="w", padx=4, pady=4)
        for name in ckpts:
            var = self._ckpt_vars.get(name, ctk.BooleanVar(value=False))
            new_ckpt_vars[name] = var
            ctk.CTkCheckBox(self._ckpt_frame, text=short_label(name, 34), variable=var).pack(anchor="w", padx=4, pady=1)
        # 1つだけなら自動でチェック（すぐ試せるように）
        if len(ckpts) == 1:
            new_ckpt_vars[ckpts[0]].set(True)
        self._ckpt_vars = new_ckpt_vars

        # LoRA（先頭に「なし」を必ず置く）
        for child in self._lora_frame.winfo_children():
            child.destroy()
        self._lora_order = [NO_LORA] + list(loras)
        none_var = self._lora_vars.get(NO_LORA, ctk.BooleanVar(value=True))
        new_lora_vars = {NO_LORA: none_var}
        ctk.CTkCheckBox(self._lora_frame, text=NO_LORA, variable=none_var).pack(anchor="w", padx=4, pady=1)
        if not loras:
            ctk.CTkLabel(self._lora_frame, text="（LoRA未検出。models/loras に置くと\nここに出ます。今はモデル比較のみ可）",
                         justify="left", text_color="#7a3b5a").pack(anchor="w", padx=4, pady=2)
        for name in loras:
            var = self._lora_vars.get(name, ctk.BooleanVar(value=False))
            new_lora_vars[name] = var
            ctk.CTkCheckBox(self._lora_frame, text=short_label(name, 34), variable=var).pack(anchor="w", padx=4, pady=1)
        self._lora_vars = new_lora_vars

        self.status.set(f"{msg}　モデル {len(ckpts)}個 / LoRA {len(loras)}個")

    # ──────────────────────────────────────────
    #  入力読み取り
    # ──────────────────────────────────────────

    def _read_params(self) -> dict:
        """数値パラメータを検証して返す。不正なら ValueError(message)。"""
        def as_int(var, label, lo, hi):
            try:
                v = int(float(var.get()))
            except ValueError:
                raise ValueError(f"{label} は数値で入力してください。現在：{var.get()}")
            if not (lo <= v <= hi):
                raise ValueError(f"{label} は {lo}〜{hi} の範囲にしてください。現在：{v}")
            return v

        steps = as_int(self.steps, "steps", 1, 150)
        width = as_int(self.width, "幅", 64, 2048)
        height = as_int(self.height, "高さ", 64, 2048)
        try:
            cfg_scale = float(self.cfg_scale.get())
        except ValueError:
            raise ValueError(f"cfg は数値で入力してください。現在：{self.cfg_scale.get()}")
        try:
            strength = float(self.lora_strength.get())
        except ValueError:
            raise ValueError(f"LoRA強度 は数値で入力してください。現在：{self.lora_strength.get()}")

        seed = None
        seed_raw = self.seed_text.get().strip()
        if seed_raw:
            try:
                seed = int(seed_raw)
            except ValueError:
                raise ValueError(f"seed は整数で入力してください（空ならランダム）。現在：{seed_raw}")

        return {
            "steps": steps, "cfg_scale": cfg_scale, "width": width, "height": height,
            "strength": strength, "seed": seed,
            "sampler_name": self.cfg.get("sampler_name", "euler"),
            "scheduler": self.cfg.get("scheduler", "normal"),
        }

    def _selected(self, order, vars_) -> list[str]:
        return [name for name in order if vars_.get(name) and vars_[name].get()]

    # ──────────────────────────────────────────
    #  一括生成
    # ──────────────────────────────────────────

    def on_generate(self):
        if self._busy:
            return
        prompt = self._prompt_box.get("1.0", "end").strip()
        negative = self._neg_box.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("入力エラー", "プロンプトを入力してください。")
            return
        ckpts = self._selected(self._ckpt_order, self._ckpt_vars)
        loras = self._selected(self._lora_order, self._lora_vars)
        if not ckpts:
            messagebox.showwarning("入力エラー", "比較するモデル(checkpoint)を1つ以上チェックしてください。")
            return
        if not loras:
            messagebox.showwarning("入力エラー", "LoRAの列を1つ以上チェックしてください（『（LoRAなし）』だけでも可）。")
            return
        try:
            params = self._read_params()
        except ValueError as e:
            messagebox.showwarning("入力エラー", str(e))
            return

        # 同じシードで比較する場合、ここで1つ決めて全セルに使う
        if params["seed"] is None and self.same_seed.get():
            params["seed"] = random.randint(0, 2**63 - 1)

        combos = [(c, l) for c in ckpts for l in loras]
        self._build_result_grid(ckpts, loras)
        self._last_run_dir = PROJECT_ROOT / "outputs" / "model_tester" / datetime.now().strftime("%Y%m%d_%H%M%S")

        self._set_busy(True)
        self.progress.set(f"生成中 0 / {len(combos)} ...")
        threading.Thread(
            target=self._generate_worker,
            args=(combos, prompt, negative, params),
            daemon=True,
        ).start()

    def _generate_worker(self, combos, prompt, negative, params):
        # 最初に接続確認（ここで失敗したらバッチ全体を中止）
        try:
            comfy_client.ensure_ready(self.config_data, start_if_needed=True)
        except ComfyError as e:
            self.after(0, self._abort_batch, str(e))
            return

        total = len(combos)
        done = 0
        for ckpt, lora in combos:
            self.after(0, self._mark_cell_running, ckpt, lora)
            lora_name = None if lora == NO_LORA else lora
            try:
                workflow, used_seed = comfy_client.build_workflow(
                    prompt, negative, ckpt,
                    lora_name=lora_name, lora_strength=params["strength"],
                    width=params["width"], height=params["height"],
                    steps=params["steps"], cfg_scale=params["cfg_scale"],
                    sampler_name=params["sampler_name"], scheduler=params["scheduler"],
                    seed=params["seed"],
                )
                image = comfy_client.generate(self.url, workflow, timeout=self.timeout)
                path = self._save_result(image, ckpt, lora, used_seed)
                self.after(0, self._place_result, ckpt, lora, image, path, used_seed)
            except Exception as e:
                self.after(0, self._place_error, ckpt, lora, str(e))
            done += 1
            self.after(0, self.progress.set, f"生成中 {done} / {total} ...")

        self.after(0, self._finish_batch, total)

    def _save_result(self, image: Image.Image, ckpt, lora, seed) -> Path:
        run_dir = self._last_run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        name = f"{slug(ckpt)}__{slug(lora)}__s{params_strength(self.lora_strength.get())}__seed{seed}.png"
        out = run_dir / name
        n = 1
        while out.exists():
            out = run_dir / f"{slug(ckpt)}__{slug(lora)}__s{params_strength(self.lora_strength.get())}__seed{seed}_{n}.png"
            n += 1
        image.convert("RGB").save(out, "PNG")
        return out

    # ── 結果グリッド描画 ──

    def _build_result_grid(self, ckpts, loras):
        for child in self._results.winfo_children():
            child.destroy()
        self._cells.clear()
        self._cell_paths.clear()
        self._thumb_refs.clear()

        ctk.CTkLabel(self._results, text="model ＼ LoRA", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, padx=4, pady=4, sticky="nsew"
        )
        for c, lora in enumerate(loras, start=1):
            ctk.CTkLabel(self._results, text=short_label(lora, 24), font=ctk.CTkFont(size=12, weight="bold"),
                         wraplength=CELL_SIZE[0]).grid(row=0, column=c, padx=4, pady=4, sticky="nsew")
        for rr, ckpt in enumerate(ckpts, start=1):
            ctk.CTkLabel(self._results, text=short_label(ckpt, 24), font=ctk.CTkFont(size=12, weight="bold"),
                         wraplength=130, justify="left").grid(row=rr, column=0, padx=4, pady=4, sticky="nsew")
            for c, lora in enumerate(loras, start=1):
                cell = ctk.CTkLabel(self._results, text="生成待ち", width=CELL_SIZE[0], height=CELL_SIZE[1],
                                    fg_color=PINK["cell_wait"], corner_radius=6)
                cell.grid(row=rr, column=c, padx=4, pady=4)
                self._cells[(ckpt, lora)] = cell

    def _mark_cell_running(self, ckpt, lora):
        cell = self._cells.get((ckpt, lora))
        if cell is not None:
            cell.configure(text="生成中 ...")

    def _place_result(self, ckpt, lora, image, path, seed):
        cell = self._cells.get((ckpt, lora))
        if cell is None:
            return
        thumb = make_thumbnail(image, CELL_SIZE)
        ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=CELL_SIZE)
        self._thumb_refs.append(ctk_img)
        cell.configure(image=ctk_img, text="", fg_color=PINK["cell"])
        self._cell_paths[(ckpt, lora)] = path
        caption = f"{short_label(ckpt)} / {short_label(lora)} / seed {seed}"
        cell.bind("<Button-1>", lambda e, p=path, cap=caption: ZoomWindow(self, p, cap))

    def _place_error(self, ckpt, lora, message):
        cell = self._cells.get((ckpt, lora))
        if cell is not None:
            cell.configure(text=f"失敗\n{message[:60]}", fg_color="#f3d6d6")

    def _abort_batch(self, message):
        self._set_busy(False)
        self.progress.set("中止しました。")
        messagebox.showwarning("ComfyUI 接続", message)

    def _finish_batch(self, total):
        self._set_busy(False)
        ok = len(self._cell_paths)
        self.progress.set(f"完了：{ok} / {total} 枚　保存先: outputs/model_tester/{self._last_run_dir.name}")

    def _clear_results(self):
        if self._busy:
            return
        for child in self._results.winfo_children():
            child.destroy()
        self._cells.clear()
        self._cell_paths.clear()
        self._thumb_refs.clear()
        self.progress.set("")
        ctk.CTkLabel(self._results, text="結果をクリアしました。", justify="left").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

    def on_open_output(self):
        target = self._last_run_dir if (self._last_run_dir and self._last_run_dir.exists()) \
            else PROJECT_ROOT / "outputs" / "model_tester"
        target.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(target))  # Windows
        except AttributeError:
            messagebox.showinfo("保存先", f"保存先フォルダ：\n{target}")

    # ──────────────────────────────────────────
    #  共通
    # ──────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._gen_btn.configure(state=state)
        self._refresh_btn.configure(state=state)


def params_strength(value: str) -> str:
    """保存名用に強度を安全な文字列にする（小数点を p に）。"""
    try:
        return f"{float(value):.2f}".replace(".", "p")
    except ValueError:
        return "1p00"


def main():
    app = ModelTesterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
