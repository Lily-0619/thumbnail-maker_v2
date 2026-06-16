"""
comfy_client.py
ローカル ComfyUI とやり取りするクライアント。

  - 接続確認・（設定があれば）自動起動
  - 利用可能な checkpoint / LoRA の一覧取得（/object_info）
  - LoRA に対応した txt2img ワークフローの組み立て
  - 生成リクエスト → 完了ポーリング → 画像取得

本体 core/ai_image.py の ComfyUI 実装を踏襲しつつ、LoRA 適用（LoraLoader ノード）を
追加している。本体には依存せず単体で動く（tools は self-contained 方針）。
"""

import io
import json
import os
import random
import subprocess
import threading
import time
from pathlib import Path

import requests
from PIL import Image

# LoRA を使わない比較列を表すラベル。常に選べる基準列として使う。
NO_LORA = "（LoRAなし）"

_START_LOCK = threading.Lock()
_PROCESS = None


class ComfyError(Exception):
    """ユーザー向けメッセージ付きの ComfyUI エラー。"""


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
#  一覧取得（checkpoint / LoRA）
# ──────────────────────────────────────────


def _list_object(url: str, class_type: str, field: str, timeout: int) -> list[str]:
    """/object_info から、あるノードの入力候補（ファイル名一覧）を取り出す。"""
    try:
        resp = requests.get(f"{url}/object_info/{class_type}", timeout=timeout)
        resp.raise_for_status()
        info = resp.json()
        choices = info[class_type]["input"]["required"][field][0]
    except Exception:
        return []
    return [str(c) for c in choices] if isinstance(choices, list) else []


def list_checkpoints(url: str, timeout: int = 15) -> list[str]:
    return _list_object(url, "CheckpointLoaderSimple", "ckpt_name", timeout)


def list_loras(url: str, timeout: int = 15) -> list[str]:
    return _list_object(url, "LoraLoader", "lora_name", timeout)


# ──────────────────────────────────────────
#  ワークフロー組み立て（LoRA 対応 txt2img）
# ──────────────────────────────────────────


def _round8(value: int) -> int:
    """SD が扱いやすいよう8の倍数に丸める（最低64）。"""
    return max(64, int(round(value / 8)) * 8)


def build_workflow(
    prompt: str,
    negative: str,
    ckpt_name: str,
    *,
    lora_name: str | None = None,
    lora_strength: float = 1.0,
    width: int = 768,
    height: int = 432,
    steps: int = 28,
    cfg_scale: float = 7.0,
    sampler_name: str = "euler",
    scheduler: str = "normal",
    seed: int | None = None,
) -> tuple[dict, int]:
    """ComfyUI の API 形式ワークフローを組み立てる。

    lora_name を指定すると CheckpointLoaderSimple と CLIP/KSampler の間に
    LoraLoader を挿入して LoRA を適用する。指定しなければ素の checkpoint のみ。

    Returns:
        (workflow, seed) — 実際に使用した seed も返す（ラベル・保存名用）。
    """
    if seed is None:
        seed = random.randint(0, 2**63 - 1)
    width = _round8(width)
    height = _round8(height)

    workflow = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg_scale,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "model_tester", "images": ["8", 0]}},
    }

    if lora_name:
        # LoraLoader を checkpoint(4) と CLIP/KSampler の間に挿入。
        workflow["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
        }
        workflow["6"]["inputs"]["clip"] = ["10", 1]
        workflow["7"]["inputs"]["clip"] = ["10", 1]
        workflow["3"]["inputs"]["model"] = ["10", 0]

    return workflow, seed


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
                for node_out in data.get("outputs", {}).values():
                    images = node_out.get("images")
                    if images:
                        image_info = images[0]
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
