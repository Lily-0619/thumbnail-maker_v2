"""
comfy_client.py
ローカル ComfyUI とやり取りするクライアント（X/Y/Z プロット対応・フル機能版）。

  - 接続確認・（設定があれば）自動起動
  - 利用可能な checkpoint / LoRA / VAE / アップスケーラー / sampler / scheduler の一覧取得
  - 定番機能を盛り込んだ txt2img / img2img ワークフローの組み立て
      * LoRA スタック（複数 LoRA の重ねがけ・個別強度）
      * Hires fix / アップスケール（latent 方式 ＋ アップスケーラーモデル方式）
      * clip skip / VAE 上書き / img2img（元画像 + denoise）
  - 生成リクエスト → 完了ポーリング → 画像取得

本体 core/ai_image.py の ComfyUI 実装を踏襲しつつ拡張している。
本体には依存せず単体で動く（tools は self-contained 方針）。
"""

from __future__ import annotations

import io
import json
import os
import random
import subprocess
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import requests
from PIL import Image

# LoRA を使わない比較列を表すラベル。常に選べる基準列として使う。
NO_LORA = "（LoRAなし）"
# VAE を checkpoint 付属のものにする（上書きしない）ことを表すラベル。
VAE_FROM_CKPT = "（モデル付属）"

# Hires のアップスケール方式
HIRES_NONE = "none"
HIRES_LATENT = "latent"   # LatentUpscaleBy → 2nd KSampler（A1111 の Hires fix 相当）
HIRES_MODEL = "model"     # アップスケーラーモデルで拡大 → 再エンコード → 2nd KSampler

_START_LOCK = threading.Lock()
_PROCESS = None


class ComfyError(Exception):
    """ユーザー向けメッセージ付きの ComfyUI エラー。"""


# ──────────────────────────────────────────
#  生成パラメータ
# ──────────────────────────────────────────


@dataclass
class LoraSpec:
    """1 つの LoRA とその強度。"""

    name: str
    strength_model: float = 1.0
    strength_clip: float = 1.0


@dataclass
class GenParams:
    """1 枚を生成するための全パラメータ。X/Y/Z 軸はこれを複製して書き換える。"""

    prompt: str = ""
    negative: str = ""
    ckpt_name: str = ""
    vae_name: str | None = None            # None / VAE_FROM_CKPT ならモデル付属

    loras: list[LoraSpec] = field(default_factory=list)

    width: int = 768
    height: int = 432
    steps: int = 28
    cfg_scale: float = 7.0
    sampler_name: str = "euler"
    scheduler: str = "normal"
    seed: int | None = None
    clip_skip: int = 1                     # A1111 流（1=なし, 2 以上で skip）
    denoise: float = 1.0                   # txt2img は 1.0、img2img で下げる

    # img2img（任意）
    init_image_name: str | None = None     # ComfyUI にアップロード済みのファイル名

    # Hires fix / アップスケール（任意）
    hires_mode: str = HIRES_NONE
    hires_scale: float = 1.5
    hires_steps: int = 12
    hires_denoise: float = 0.5
    hires_upscaler: str = ""               # HIRES_MODEL のときのアップスケーラーモデル名
    hires_sampler: str = ""                # 空ならベースと同じ

    def copy(self) -> "GenParams":
        return replace(self, loras=[replace(l) for l in self.loras])


# ──────────────────────────────────────────
#  接続・自動起動
# ──────────────────────────────────────────


def comfy_url(cfg: dict) -> str:
    return cfg.get("url", "http://127.0.0.1:8188").rstrip("/")


def is_running(url: str, timeout: int = 3) -> bool:
    try:
        return requests.get(f"{url}/system_stats", timeout=timeout).status_code == 200
    except requests.exceptions.RequestException:
        return False


def _config_path(value, base_dir: Path | None = None) -> Path:
    expanded = os.path.expandvars(str(value or "").strip())
    if not expanded:
        return Path()
    path = Path(expanded).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path


def ensure_ready(config: dict, start_if_needed: bool = True) -> str:
    """ComfyUI に接続できるか確認し、設定で許可されていれば自動起動する。"""
    cfg = config.get("comfyui", {})
    url = comfy_url(cfg)
    if is_running(url):
        return f"ComfyUI 接続OK（{url}）"

    with _START_LOCK:
        if is_running(url):
            return f"ComfyUI 接続OK（{url}）"
        if not start_if_needed or not cfg.get("auto_start", False):
            raise ComfyError(
                f"ComfyUI に接続できません（{url}）。\n"
                "ComfyUI を起動してから『接続 / 一覧更新』を押してください。"
            )

        missing = [k for k in ("python_path", "main_path", "working_dir") if not str(cfg.get(k, "")).strip()]
        if missing:
            raise ComfyError(
                "ComfyUI の自動起動設定が足りません。\n"
                f"ai_config.json の comfyui.{', comfyui.'.join(missing)} を設定してください。"
            )

        working_dir = _config_path(cfg.get("working_dir"))
        python_path = _config_path(cfg.get("python_path"), working_dir)
        main_path = _config_path(cfg.get("main_path"), working_dir)
        problems = [
            f"{label} が見つかりません: {p}"
            for label, p in (
                ("working_dir", working_dir),
                ("python_path", python_path),
                ("main_path", main_path),
            )
            if not p.exists()
        ]
        if problems:
            raise ComfyError("ComfyUI を自動起動できません。\n" + "\n".join(problems))

        extra_args = cfg.get("extra_args", [])
        if isinstance(extra_args, str):
            extra_args = [a for a in extra_args.split(" ") if a]
        if not isinstance(extra_args, list):
            extra_args = []

        command = [str(python_path), str(main_path), *[str(a) for a in extra_args]]
        global _PROCESS
        try:
            _PROCESS = subprocess.Popen(
                command,
                cwd=str(working_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as e:
            raise ComfyError(f"ComfyUI の起動に失敗しました。\n{e}")

        startup_timeout = int(cfg.get("startup_timeout_seconds", 90))
        deadline = time.time() + max(startup_timeout, 1)
        while time.time() < deadline:
            if is_running(url):
                return f"ComfyUI を自動起動しました（{url}）"
            if _PROCESS.poll() is not None:
                raise ComfyError("ComfyUI のプロセスが起動直後に終了しました。ComfyUI 側のログを確認してください。")
            time.sleep(1.0)
        raise ComfyError(
            f"ComfyUI を起動しましたが {startup_timeout} 秒以内に接続できませんでした（{url}）。\n"
            "初回起動が遅い場合は ai_config.json の comfyui.startup_timeout_seconds を増やしてください。"
        )


# ──────────────────────────────────────────
#  一覧取得（checkpoint / LoRA / VAE / アップスケーラー / sampler / scheduler）
# ──────────────────────────────────────────


def _object_info(url: str, class_type: str, timeout: int) -> dict:
    try:
        resp = requests.get(f"{url}/object_info/{class_type}", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get(class_type, {})
    except Exception:
        return {}


def _list_input_choices(url: str, class_type: str, field_name: str, timeout: int) -> list[str]:
    """/object_info から、あるノードの入力候補（一覧）を取り出す。"""
    info = _object_info(url, class_type, timeout)
    try:
        choices = info["input"]["required"][field_name][0]
    except (KeyError, TypeError, IndexError):
        try:
            choices = info["input"]["optional"][field_name][0]
        except (KeyError, TypeError, IndexError):
            return []
    return [str(c) for c in choices] if isinstance(choices, list) else []


def list_checkpoints(url: str, timeout: int = 15) -> list[str]:
    return _list_input_choices(url, "CheckpointLoaderSimple", "ckpt_name", timeout)


def list_loras(url: str, timeout: int = 15) -> list[str]:
    return _list_input_choices(url, "LoraLoader", "lora_name", timeout)


def list_vaes(url: str, timeout: int = 15) -> list[str]:
    return _list_input_choices(url, "VAELoader", "vae_name", timeout)


def list_upscalers(url: str, timeout: int = 15) -> list[str]:
    return _list_input_choices(url, "UpscaleModelLoader", "model_name", timeout)


def list_samplers(url: str, timeout: int = 15) -> list[str]:
    names = _list_input_choices(url, "KSampler", "sampler_name", timeout)
    return names or [
        "euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde",
        "dpmpp_sde", "dpmpp_3m_sde", "ddim", "uni_pc",
    ]


def list_schedulers(url: str, timeout: int = 15) -> list[str]:
    names = _list_input_choices(url, "KSampler", "scheduler", timeout)
    return names or ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform"]


def upload_image(url: str, image_path: Path, timeout: int = 60) -> str:
    """img2img 用の元画像を ComfyUI の input にアップロードし、LoadImage 用の名前を返す。"""
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        image_path.suffix.lower(), "image/png"
    )
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f.read(), mime)}
    resp = requests.post(f"{url}/upload/image", files=files, data={"overwrite": "true"}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    name = data.get("name", image_path.name)
    subfolder = data.get("subfolder", "")
    return f"{subfolder}/{name}" if subfolder else name


# ──────────────────────────────────────────
#  ワークフロー組み立て（フル機能 txt2img / img2img + Hires）
# ──────────────────────────────────────────


def _round8(value: int) -> int:
    """SD が扱いやすいよう8の倍数に丸める（最低64）。"""
    return max(64, int(round(value / 8)) * 8)


class _Graph:
    """ノード ID を自動採番しながら ComfyUI の API 形式グラフを組み立てる小道具。"""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self._n = 0

    def add(self, class_type: str, inputs: dict) -> str:
        self._n += 1
        node_id = str(self._n)
        self.nodes[node_id] = {"class_type": class_type, "inputs": inputs}
        return node_id


def build_workflow(p: GenParams) -> tuple[dict, int]:
    """GenParams からフル機能の ComfyUI ワークフローを組み立てる。

    Returns:
        (workflow, seed) — 実際に使用した seed も返す（ラベル・保存名用）。
    """
    seed = p.seed if p.seed is not None else random.randint(0, 2**63 - 1)
    width = _round8(p.width)
    height = _round8(p.height)

    g = _Graph()

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": p.ckpt_name})
    model_ref = [ckpt, 0]
    clip_ref = [ckpt, 1]

    # VAE：上書き指定があれば VAELoader、なければ checkpoint 付属
    if p.vae_name and p.vae_name != VAE_FROM_CKPT:
        vae_node = g.add("VAELoader", {"vae_name": p.vae_name})
        vae_ref = [vae_node, 0]
    else:
        vae_ref = [ckpt, 2]

    # LoRA スタック（順に重ねがけ）
    for lora in p.loras:
        if not lora.name or lora.name == NO_LORA:
            continue
        lora_node = g.add(
            "LoraLoader",
            {
                "lora_name": lora.name,
                "strength_model": float(lora.strength_model),
                "strength_clip": float(lora.strength_clip),
                "model": model_ref,
                "clip": clip_ref,
            },
        )
        model_ref = [lora_node, 0]
        clip_ref = [lora_node, 1]

    # clip skip（A1111 流：1=なし。2 以上で CLIPSetLastLayer を挿入）
    if p.clip_skip and int(p.clip_skip) > 1:
        skip_node = g.add(
            "CLIPSetLastLayer",
            {"stop_at_clip_layer": -int(p.clip_skip), "clip": clip_ref},
        )
        clip_ref = [skip_node, 0]

    pos = g.add("CLIPTextEncode", {"text": p.prompt, "clip": clip_ref})
    neg = g.add("CLIPTextEncode", {"text": p.negative, "clip": clip_ref})

    # 初期 latent：img2img なら元画像をエンコード、txt2img なら空 latent
    if p.init_image_name:
        load = g.add("LoadImage", {"image": p.init_image_name})
        latent_ref = [g.add("VAEEncode", {"pixels": [load, 0], "vae": vae_ref}), 0]
    else:
        latent_ref = [
            g.add("EmptyLatentImage", {"width": width, "height": height, "batch_size": 1}),
            0,
        ]

    sampler = g.add(
        "KSampler",
        {
            "seed": seed,
            "steps": int(p.steps),
            "cfg": float(p.cfg_scale),
            "sampler_name": p.sampler_name,
            "scheduler": p.scheduler,
            "denoise": float(p.denoise),
            "model": model_ref,
            "positive": [pos, 0],
            "negative": [neg, 0],
            "latent_image": latent_ref,
        },
    )
    samples_ref = [sampler, 0]

    # Hires fix / アップスケール（2nd pass）
    if p.hires_mode == HIRES_LATENT and p.hires_scale and p.hires_scale > 1.0:
        up = g.add(
            "LatentUpscaleBy",
            {"upscale_method": "nearest-exact", "scale_by": float(p.hires_scale), "samples": samples_ref},
        )
        samples_ref = _second_sampler(g, p, model_ref, pos, neg, [up, 0], seed)
    elif p.hires_mode == HIRES_MODEL and p.hires_upscaler and p.hires_scale and p.hires_scale > 1.0:
        decoded = g.add("VAEDecode", {"samples": samples_ref, "vae": vae_ref})
        loader = g.add("UpscaleModelLoader", {"model_name": p.hires_upscaler})
        upscaled = g.add(
            "ImageUpscaleWithModel", {"upscale_model": [loader, 0], "image": [decoded, 0]}
        )
        # アップスケーラーモデルは固定倍率なので、目標倍率にリサイズし直す
        scaled = g.add(
            "ImageScale",
            {
                "upscale_method": "lanczos",
                "width": _round8(int(width * p.hires_scale)),
                "height": _round8(int(height * p.hires_scale)),
                "crop": "disabled",
                "image": [upscaled, 0],
            },
        )
        encoded = g.add("VAEEncode", {"pixels": [scaled, 0], "vae": vae_ref})
        samples_ref = _second_sampler(g, p, model_ref, pos, neg, [encoded, 0], seed)

    decode = g.add("VAEDecode", {"samples": samples_ref, "vae": vae_ref})
    g.add("SaveImage", {"filename_prefix": "model_tester", "images": [decode, 0]})

    return g.nodes, seed


def _second_sampler(g: "_Graph", p: GenParams, model_ref, pos, neg, latent_ref, seed) -> list:
    """Hires 用の 2 回目 KSampler を追加し、出力 latent 参照を返す。"""
    node = g.add(
        "KSampler",
        {
            "seed": seed,
            "steps": int(p.hires_steps),
            "cfg": float(p.cfg_scale),
            "sampler_name": p.hires_sampler or p.sampler_name,
            "scheduler": p.scheduler,
            "denoise": float(p.hires_denoise),
            "model": model_ref,
            "positive": [pos, 0],
            "negative": [neg, 0],
            "latent_image": latent_ref,
        },
    )
    return [node, 0]


# ──────────────────────────────────────────
#  生成（キュー投入 → ポーリング → 画像取得）
# ──────────────────────────────────────────


def generate(url: str, workflow: dict, timeout: int = 300) -> Image.Image:
    """ワークフローを ComfyUI に投げ、生成された画像を1枚返す。"""
    client_id = f"model_tester-{random.randint(0, 1_000_000)}"
    try:
        resp = requests.post(
            f"{url}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=timeout
        )
    except requests.exceptions.RequestException as e:
        raise ComfyError(f"ComfyUI への生成リクエストに失敗しました: {e}")
    if resp.status_code != 200:
        raise ComfyError(f"ComfyUI エラー (HTTP {resp.status_code}):\n{resp.text[:500]}")
    prompt_id = resp.json().get("prompt_id")
    if not prompt_id:
        raise ComfyError("ComfyUI が生成IDを返しませんでした。")

    image_info = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            h = requests.get(f"{url}/history/{prompt_id}", timeout=30)
        except requests.exceptions.RequestException:
            time.sleep(1.0)
            continue
        if h.status_code == 200:
            data = h.json().get(prompt_id)
            if data:
                # SaveImage の出力（最後のノード）を優先して拾う
                for node_out in data.get("outputs", {}).values():
                    images = node_out.get("images")
                    if images:
                        image_info = images[-1]
                        break
                if image_info is not None:
                    break
                status = data.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(f"生成中にエラーが発生しました:\n{json.dumps(status)[:500]}")
        time.sleep(1.0)

    if image_info is None:
        raise ComfyError("生成がタイムアウトしました。steps や解像度を下げるか、timeout_seconds を増やしてください。")

    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    img_resp = requests.get(f"{url}/view", params=params, timeout=timeout)
    img_resp.raise_for_status()
    return Image.open(io.BytesIO(img_resp.content))
