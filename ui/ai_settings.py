"""
ai_settings.py
AI画像生成の設定(config/ai_config.json)をGUIから編集するダイアログ。

JSONを直接開かなくても、よく触る項目(プロバイダー・ComfyUIのモデル・
生成サイズ・hires・エフェクト透過化方式・タイムアウト)を変更できる。

  - 保存は load_ai_config() で読んだ dict の該当キーだけを書き換えて
    save_ai_config() でアトミックに書き戻す。_comment 系キーや
    このダイアログが扱わないキー(sdwebui / stability / openai の詳細等)は
    そのまま保持される。
  - ComfyUI が起動していればモデル(checkpoint)一覧をドロップダウンに出す。
    取得はスレッドで行い、UI更新は after() 経由(本体アプリと同じ作法)。
"""

import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from core import ai_image

PROVIDERS = ["comfyui", "sdwebui", "stability", "openai"]
HIRES_MODES = ["latent", "model"]
EFFECT_METHODS = ["black_to_alpha", "rembg"]
CKPT_AUTO_LABEL = "（自動選択）"

LABEL_WIDTH = 170
PAD = {"padx": 10, "pady": 3}


class AISettingsDialog(ctk.CTkToplevel):
    """config/ai_config.json を編集する設定ダイアログ。"""

    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.title("⚙️ AI設定 (config/ai_config.json)")
        self.geometry("600x780")
        self.resizable(True, True)
        self.grab_set()
        self._on_saved = on_saved

        try:
            self._config = ai_image.load_ai_config()
        except Exception as e:
            messagebox.showerror("AI設定", f"設定ファイルを読み込めませんでした:\n{e}", parent=self)
            self.destroy()
            return

        cfg = self._config
        comfy = cfg.get("comfyui", {})
        hires = comfy.get("hires", {})
        effect = cfg.get("effect_transparency", {})

        # ── 現在値を編集用変数へ ──
        self.provider = ctk.StringVar(value=str(cfg.get("provider", "comfyui")))
        self.timeout_seconds = ctk.StringVar(value=str(cfg.get("timeout_seconds", 600)))

        self.comfy_url = ctk.StringVar(value=str(comfy.get("url", "http://127.0.0.1:8188")))
        self.comfy_auto_start = ctk.BooleanVar(value=bool(comfy.get("auto_start", False)))
        ckpt = str(comfy.get("ckpt_name", "") or "").strip()
        self.comfy_ckpt = ctk.StringVar(value=ckpt if ckpt else CKPT_AUTO_LABEL)
        self.comfy_width = ctk.StringVar(value=str(comfy.get("width", 1344)))
        self.comfy_height = ctk.StringVar(value=str(comfy.get("height", 768)))
        self.comfy_steps = ctk.StringVar(value=str(comfy.get("steps", 28)))
        self.comfy_cfg_scale = ctk.StringVar(value=str(comfy.get("cfg_scale", 7)))
        self.comfy_sampler = ctk.StringVar(value=str(comfy.get("sampler_name", "euler")))
        self.comfy_scheduler = ctk.StringVar(value=str(comfy.get("scheduler", "normal")))

        self.hires_enabled = ctk.BooleanVar(value=bool(hires.get("enabled", False)))
        mode = str(hires.get("mode", "latent"))
        self.hires_mode = ctk.StringVar(value=mode if mode in HIRES_MODES else "latent")
        self.hires_target_width = ctk.StringVar(value=str(hires.get("target_width", 1920)))
        self.hires_steps = ctk.StringVar(value=str(hires.get("steps", 16)))
        self.hires_denoise = ctk.StringVar(value=str(hires.get("denoise", 0.4)))
        self.hires_upscaler = ctk.StringVar(value=str(hires.get("upscaler", "")))

        method = str(effect.get("method", "black_to_alpha")).strip().lower()
        self.effect_method = ctk.StringVar(value=method if method in EFFECT_METHODS else "black_to_alpha")
        self.effect_rembg_model = ctk.StringVar(value=str(effect.get("rembg_model", "birefnet-general")))

        self.status = ctk.StringVar(value="")
        self._warnings = []

        self._build()
        # ComfyUIが起動していればモデル一覧を自動取得(裏で・失敗しても無害)
        self.after(200, self._fetch_checkpoints_async)

    # ──────────────────────────────────────────
    #  Layout
    # ──────────────────────────────────────────

    def _build(self):
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # ── 基本 ──
        self._section(body, "🌐 基本")
        self._row_menu(body, "プロバイダー", self.provider, PROVIDERS)
        self._row_entry(body, "タイムアウト(秒)", self.timeout_seconds)
        self._note(body, "sdwebui / stability / openai の詳細設定は config/ai_config.json を直接編集してください。")

        # ── ComfyUI ──
        self._section(body, "🖥️ ComfyUI（標準プロバイダー）")
        self._row_entry(body, "URL", self.comfy_url)
        self._row_switch(body, "自動起動 (auto_start)", self.comfy_auto_start)

        ckpt_row = ctk.CTkFrame(body, fg_color="transparent")
        ckpt_row.pack(fill="x", **PAD)
        ctk.CTkLabel(ckpt_row, text="モデル (ckpt_name)", width=LABEL_WIDTH, anchor="w").pack(side="left")
        self._ckpt_menu = ctk.CTkOptionMenu(
            ckpt_row, variable=self.comfy_ckpt, values=self._initial_ckpt_values()
        )
        self._ckpt_menu.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._ckpt_btn = ctk.CTkButton(ckpt_row, text="🔄 一覧取得", width=90, command=self._fetch_checkpoints_async)
        self._ckpt_btn.pack(side="left")
        self._note(body, "「（自動選択）」= ComfyUI にあるモデルを自動採用。一覧取得は ComfyUI 起動中のみ有効。")

        self._row_entry(body, "生成幅 (width)", self.comfy_width)
        self._row_entry(body, "生成高さ (height)", self.comfy_height)
        self._row_entry(body, "Steps", self.comfy_steps)
        self._row_entry(body, "CFG Scale", self.comfy_cfg_scale)
        self._row_entry(body, "Sampler", self.comfy_sampler)
        self._row_entry(body, "Scheduler", self.comfy_scheduler)

        # ── hires ──
        self._section(body, "🔍 背景の高解像度化 (hires)")
        self._row_switch(body, "有効 (enabled)", self.hires_enabled)
        self._row_menu(body, "方式 (mode)", self.hires_mode, HIRES_MODES)
        self._row_entry(body, "目標幅 (target_width)", self.hires_target_width)
        self._row_entry(body, "2パス目 Steps", self.hires_steps)
        self._row_entry(body, "Denoise", self.hires_denoise)
        self._row_entry(body, "Upscaler (mode=model時)", self.hires_upscaler)
        self._note(body, "VRAM不足で落ちる場合は目標幅を 1536 や 1280 に下げてください。")

        # ── エフェクト透過化 ──
        self._section(body, "🌟 エフェクトの透過化")
        self._row_menu(body, "方式 (method)", self.effect_method, EFFECT_METHODS)
        self._row_entry(body, "rembgモデル", self.effect_rembg_model)
        self._note(
            body,
            "black_to_alpha=黒背景→透過（発光系向き・標準） / rembg=AI切り抜き"
            "（暗い色のエフェクトも残せる。pip install rembg が必要。未導入時は自動で標準方式に戻る）。",
        )

        # ── 下部: ステータス + ボタン ──
        ctk.CTkLabel(self, textvariable=self.status, text_color="#a05050", wraplength=560, justify="left").pack(
            anchor="w", padx=12, pady=(4, 0)
        )
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btns, text="💾 保存", height=38, font=ctk.CTkFont(size=14, weight="bold"), command=self._save).pack(
            side="left", fill="x", expand=True, padx=(0, 4)
        )
        ctk.CTkButton(btns, text="キャンセル", height=38, fg_color="#9a8aa0", hover_color="#7d6e84", command=self.destroy).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )

    def _section(self, parent, text: str):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(12, 2))

    def _note(self, parent, text: str):
        ctk.CTkLabel(parent, text=text, text_color="gray", wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(0, 2))

    def _row_entry(self, parent, label: str, var: ctk.StringVar):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", **PAD)
        ctk.CTkLabel(row, text=label, width=LABEL_WIDTH, anchor="w").pack(side="left")
        ctk.CTkEntry(row, textvariable=var).pack(side="left", fill="x", expand=True)

    def _row_menu(self, parent, label: str, var: ctk.StringVar, values: list[str]):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", **PAD)
        ctk.CTkLabel(row, text=label, width=LABEL_WIDTH, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row, variable=var, values=values).pack(side="left", fill="x", expand=True)

    def _row_switch(self, parent, label: str, var: ctk.BooleanVar):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", **PAD)
        ctk.CTkLabel(row, text=label, width=LABEL_WIDTH, anchor="w").pack(side="left")
        ctk.CTkSwitch(row, text="", variable=var).pack(side="left")

    # ──────────────────────────────────────────
    #  Checkpoint一覧
    # ──────────────────────────────────────────

    def _initial_ckpt_values(self) -> list[str]:
        values = [CKPT_AUTO_LABEL]
        current = self.comfy_ckpt.get()
        if current and current != CKPT_AUTO_LABEL:
            values.append(current)
        return values

    def _fetch_checkpoints_async(self):
        self.status.set("ComfyUI からモデル一覧を取得中...")
        threading.Thread(target=self._fetch_checkpoints_worker, daemon=True).start()

    def _fetch_checkpoints_worker(self):
        # ダイアログで編集中のURLを反映して問い合わせる
        config = dict(self._config)
        comfy = dict(config.get("comfyui", {}))
        comfy["url"] = self.comfy_url.get().strip() or comfy.get("url", "http://127.0.0.1:8188")
        config["comfyui"] = comfy
        names = ai_image.list_comfyui_checkpoints(config)
        try:
            self.after(0, self._apply_checkpoints, names)
        except tk.TclError:
            pass  # ダイアログが既に閉じられている

    def _apply_checkpoints(self, names: list[str]):
        if not self.winfo_exists():
            return
        if not names:
            self.status.set("モデル一覧を取得できませんでした（ComfyUI 未起動でも保存はできます）。")
            return
        values = [CKPT_AUTO_LABEL] + names
        current = self.comfy_ckpt.get()
        if current and current not in values:
            values.append(current)
        self._ckpt_menu.configure(values=values)
        self.status.set(f"モデル一覧を取得しました（{len(names)}件）。")

    # ──────────────────────────────────────────
    #  Save
    # ──────────────────────────────────────────

    def _int_of(self, var: ctk.StringVar, label: str, current) -> int:
        try:
            return int(float(var.get().strip()))
        except (ValueError, AttributeError):
            self._warnings.append(f"{label} が数値でないため元の値({current})のままにしました。")
            return int(current)

    def _float_of(self, var: ctk.StringVar, label: str, current) -> float:
        try:
            return float(var.get().strip())
        except (ValueError, AttributeError):
            self._warnings.append(f"{label} が数値でないため元の値({current})のままにしました。")
            return float(current)

    def _save(self):
        self._warnings = []
        try:
            # 保存直前にディスクから読み直し、GUI外の編集を消さないようにする
            config = ai_image.load_ai_config()
        except Exception:
            config = self._config

        config["provider"] = self.provider.get()
        config["timeout_seconds"] = self._int_of(self.timeout_seconds, "タイムアウト(秒)", config.get("timeout_seconds", 600))

        comfy = config.setdefault("comfyui", {})
        comfy["url"] = self.comfy_url.get().strip() or "http://127.0.0.1:8188"
        comfy["auto_start"] = bool(self.comfy_auto_start.get())
        ckpt = self.comfy_ckpt.get().strip()
        comfy["ckpt_name"] = "" if ckpt == CKPT_AUTO_LABEL else ckpt
        comfy["width"] = self._int_of(self.comfy_width, "生成幅", comfy.get("width", 1344))
        comfy["height"] = self._int_of(self.comfy_height, "生成高さ", comfy.get("height", 768))
        comfy["steps"] = self._int_of(self.comfy_steps, "Steps", comfy.get("steps", 28))
        comfy["cfg_scale"] = self._float_of(self.comfy_cfg_scale, "CFG Scale", comfy.get("cfg_scale", 7))
        comfy["sampler_name"] = self.comfy_sampler.get().strip() or "euler"
        comfy["scheduler"] = self.comfy_scheduler.get().strip() or "normal"

        hires = comfy.setdefault("hires", {})
        hires["enabled"] = bool(self.hires_enabled.get())
        hires["mode"] = self.hires_mode.get()
        hires["target_width"] = self._int_of(self.hires_target_width, "目標幅", hires.get("target_width", 1920))
        hires["steps"] = self._int_of(self.hires_steps, "2パス目 Steps", hires.get("steps", 16))
        hires["denoise"] = self._float_of(self.hires_denoise, "Denoise", hires.get("denoise", 0.4))
        hires["upscaler"] = self.hires_upscaler.get().strip()

        effect = config.setdefault("effect_transparency", {})
        effect["method"] = self.effect_method.get()
        effect["rembg_model"] = self.effect_rembg_model.get().strip() or "birefnet-general"

        try:
            ai_image.save_ai_config(config)
        except OSError as e:
            messagebox.showerror("AI設定", f"保存に失敗しました:\n{e}", parent=self)
            return

        self._config = config
        message = "保存しました。次回のAI生成から反映されます。"
        if self._warnings:
            message += "\n\n" + "\n".join(self._warnings)
            messagebox.showwarning("AI設定", message, parent=self)
        else:
            messagebox.showinfo("AI設定", message, parent=self)
        if self._on_saved:
            self._on_saved()
        self.destroy()
