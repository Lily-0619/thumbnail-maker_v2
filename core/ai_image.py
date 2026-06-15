"""
ai_image.py
AI画像生成モジュール。

背景(拠点名から連想されるリアルダークファンタジー調)と
後方エフェクト(キャラに合わせた透過エフェクト)をAIで生成する。

対応プロバイダー:
  - comfyui  : ローカルのComfyUI。標準設定。APIキー不要・無料・全てローカルで動く。
  - sdwebui  : ローカルのStable Diffusion WebUI(AUTOMATIC1111)。
               APIキー不要・無料・全てローカルで動く。
  - stability: Stability AI(クラウドAPI。使う場合のみAPIキーが必要)
  - openai   : OpenAI gpt-image-1(クラウドAPI。現在は未使用)

設定ファイル:
  - config/ai_config.json  : プロバイダー・画像サイズなどの設定
  - config/ai_prompts.json : プロンプト文(自由に編集してOK)
  - .env                   : APIキー(Gitには絶対コミットしない)

コマンドラインからの動作確認:
    python -m core.ai_image check
    python -m core.ai_image bg "Ehwaz Hill"
    python -m core.ai_image effect fire
"""

import base64
import io
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageChops

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AI_CONFIG_PATH = PROJECT_ROOT / "config" / "ai_config.json"
AI_PROMPTS_PATH = PROJECT_ROOT / "config" / "ai_prompts.json"
ENV_PATH = PROJECT_ROOT / ".env"

OPENAI_GENERATIONS_URL = "https://api.openai.com/v1/images/generations"
OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"
_COMFYUI_START_LOCK = threading.Lock()


class AIImageError(Exception):
    """ユーザー向けメッセージ付きのAI生成エラー。"""


# ──────────────────────────────────────────
#  設定・環境変数の読み込み
# ──────────────────────────────────────────


def _load_env_file(path: Path = ENV_PATH) -> None:
    """`.env` ファイルを読み込んで環境変数に反映する(既存の環境変数を優先)。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_ai_config() -> dict:
    if not AI_CONFIG_PATH.exists():
        raise AIImageError(f"設定ファイルが見つかりません: {AI_CONFIG_PATH}")
    with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ai_prompts() -> dict:
    if not AI_PROMPTS_PATH.exists():
        raise AIImageError(f"プロンプト設定が見つかりません: {AI_PROMPTS_PATH}")
    with open(AI_PROMPTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_api_key(provider: str) -> str:
    _load_env_file()
    env_names = {"openai": "OPENAI_API_KEY", "stability": "STABILITY_API_KEY"}
    name = env_names.get(provider)
    if name is None:
        return ""  # sdwebui はAPIキー不要
    key = os.environ.get(name, "").strip()
    if not key:
        raise AIImageError(
            f"APIキーが設定されていません。\n"
            f"プロジェクト直下の .env ファイルに「{name}=あなたのキー」を書いてください。\n"
            f"(.env.example をコピーして .env にリネームすると簡単です)"
        )
    return key


def list_effect_types() -> list[str]:
    """UIのドロップダウン用に、定義済みエフェクト種類の一覧を返す。"""
    try:
        prompts = load_ai_prompts()
        return list(prompts.get("effect", {}).get("types", {}).keys())
    except Exception:
        return ["fire", "ice", "lightning", "dark", "holy", "flower", "butterfly", "blue_purple_magic"]


# ──────────────────────────────────────────
#  プロンプト組み立て
# ──────────────────────────────────────────


def build_background_prompt(node_name: str) -> tuple[str, str]:
    """拠点名から背景生成用の(プロンプト, ネガティブプロンプト)を組み立てる。"""
    prompts = load_ai_prompts()
    bg = prompts.get("background", {})
    hints = bg.get("node_hints", {})
    hint = hints.get(node_name, hints.get("_default", ""))
    prompt = bg.get("template", "{node_name}").format(
        node_name=node_name,
        hint=hint,
        style=bg.get("style", ""),
    )
    return prompt.strip(), bg.get("negative", "")


def build_effect_prompt(effect_type: str) -> tuple[str, str]:
    """エフェクト種類から(プロンプト, ネガティブプロンプト)を組み立てる。"""
    prompts = load_ai_prompts()
    eff = prompts.get("effect", {})
    types = eff.get("types", {})
    type_desc = types.get(effect_type, effect_type)
    prompt = eff.get("template", "{type_desc}").format(
        type_desc=type_desc,
        style=eff.get("style", ""),
    )
    return prompt.strip(), eff.get("negative", "")


def find_reference_image(effect_type: str, config: dict) -> Path | None:
    """material内のサンプルフォルダから、エフェクト種類に合う参考画像を探す。

    探す場所(上から優先):
      material/サンプル/<effect_type>/*.png など
      material/サンプル/<effect_type>*.png のような直置きファイル
    """
    if not config.get("use_sample_reference", True):
        return None
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    for sample_dir in config.get("sample_dirs", []):
        base = PROJECT_ROOT / sample_dir
        if not base.exists():
            continue
        type_dir = base / effect_type
        if type_dir.exists():
            for path in sorted(type_dir.iterdir()):
                if path.is_file() and path.suffix.lower() in exts:
                    return path
        for path in sorted(base.glob(f"{effect_type}*")):
            if path.is_file() and path.suffix.lower() in exts:
                return path
    return None


# ──────────────────────────────────────────
#  プロバイダー実装
# ──────────────────────────────────────────


def _generate_openai(
    prompt: str,
    config: dict,
    transparent: bool = False,
    reference_path: Path | None = None,
) -> Image.Image:
    api_key = get_api_key("openai")
    cfg = config.get("openai", {})
    timeout = config.get("timeout_seconds", 180)
    headers = {"Authorization": f"Bearer {api_key}"}

    common = {
        "model": cfg.get("model", "gpt-image-1"),
        "size": cfg.get("size", "1536x1024"),
        "quality": cfg.get("quality", "medium"),
        "n": 1,
    }
    if transparent:
        common["background"] = "transparent"
        common["output_format"] = "png"

    try:
        if reference_path is not None:
            # サンプル画像を参考にした生成(edits エンドポイント)
            data = {key: str(value) for key, value in common.items()}
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
                reference_path.suffix.lower(), "image/png"
            )
            with open(reference_path, "rb") as f:
                files = {"image": (reference_path.name, f.read(), mime)}
            data["prompt"] = (
                f"{prompt} Use the provided image as a style reference for "
                f"colors, mood and shape of the effect."
            )
            resp = requests.post(OPENAI_EDITS_URL, headers=headers, data=data, files=files, timeout=timeout)
        else:
            payload = dict(common)
            payload["prompt"] = prompt
            resp = requests.post(OPENAI_GENERATIONS_URL, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        raise AIImageError(f"OpenAI APIに接続できません。インターネット接続を確認してください。\n詳細: {e}")
    except requests.exceptions.Timeout:
        raise AIImageError("OpenAI APIがタイムアウトしました。時間をおいて再実行してください。")

    if resp.status_code == 401:
        raise AIImageError("OpenAI APIキーが無効です。.env の OPENAI_API_KEY を確認してください。")
    if resp.status_code == 429:
        raise AIImageError(
            "OpenAI APIの利用制限に達しました。\n"
            "・無料枠/クレジット残高切れの可能性 → https://platform.openai.com/settings/organization/billing で残高を確認\n"
            "・短時間に連続実行した場合は少し待って再実行"
        )
    if resp.status_code != 200:
        raise AIImageError(f"OpenAI APIエラー (HTTP {resp.status_code}):\n{resp.text[:500]}")

    b64 = resp.json()["data"][0]["b64_json"]
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def _generate_stability(prompt: str, negative: str, config: dict) -> Image.Image:
    api_key = get_api_key("stability")
    cfg = config.get("stability", {})
    timeout = config.get("timeout_seconds", 180)

    form = {
        "prompt": (None, prompt),
        "output_format": (None, "png"),
        "aspect_ratio": (None, cfg.get("aspect_ratio", "16:9")),
    }
    if negative:
        form["negative_prompt"] = (None, negative)

    try:
        resp = requests.post(
            cfg.get("endpoint", "https://api.stability.ai/v2beta/stable-image/generate/core"),
            headers={"Authorization": f"Bearer {api_key}", "Accept": "image/*"},
            files=form,
            timeout=timeout,
        )
    except requests.exceptions.ConnectionError as e:
        raise AIImageError(f"Stability APIに接続できません。インターネット接続を確認してください。\n詳細: {e}")
    except requests.exceptions.Timeout:
        raise AIImageError("Stability APIがタイムアウトしました。時間をおいて再実行してください。")

    if resp.status_code == 401:
        raise AIImageError("Stability APIキーが無効です。.env の STABILITY_API_KEY を確認してください。")
    if resp.status_code != 200:
        raise AIImageError(f"Stability APIエラー (HTTP {resp.status_code}):\n{resp.text[:500]}")

    return Image.open(io.BytesIO(resp.content))


def _generate_sdwebui(
    prompt: str,
    negative: str,
    config: dict,
    init_image: Path | None = None,
) -> Image.Image:
    """ローカルのStable Diffusion WebUIで生成する。

    init_image を渡すと img2img になり、サンプル画像の雰囲気に寄せて生成する。
    """
    cfg = config.get("sdwebui", {})
    url = cfg.get("url", "http://127.0.0.1:7860").rstrip("/")
    timeout = config.get("timeout_seconds", 300)

    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": cfg.get("width", 960),
        "height": cfg.get("height", 540),
        "steps": cfg.get("steps", 28),
        "cfg_scale": cfg.get("cfg_scale", 7),
    }
    if cfg.get("sampler_name"):
        payload["sampler_name"] = cfg["sampler_name"]

    endpoint = "txt2img"
    if init_image is not None:
        endpoint = "img2img"
        with open(init_image, "rb") as f:
            payload["init_images"] = [base64.b64encode(f.read()).decode("ascii")]
        # 1.0に近いほど見本から離れる(0.6〜0.8あたりが見本の雰囲気を残しつつ変化する)
        payload["denoising_strength"] = cfg.get("denoising_strength", 0.7)

    try:
        resp = requests.post(f"{url}/sdapi/v1/{endpoint}", json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise AIImageError(
            f"ローカルのStable Diffusion WebUIに接続できません({url})。\n"
            "WebUIを「--api」オプション付きで起動しているか確認してください。\n"
            "例: webui-user.bat の COMMANDLINE_ARGS に --api を追加"
        )
    except requests.exceptions.Timeout:
        raise AIImageError("Stable Diffusion WebUIの生成がタイムアウトしました。stepsを減らすか解像度を下げてください。")

    if resp.status_code != 200:
        raise AIImageError(f"Stable Diffusion WebUIエラー (HTTP {resp.status_code}):\n{resp.text[:500]}")

    b64 = resp.json()["images"][0]
    return Image.open(io.BytesIO(base64.b64decode(b64)))


# ──────────────────────────────────────────
#  ComfyUI(ローカル・標準)
# ──────────────────────────────────────────


def _round8(value: int) -> int:
    """SDが扱いやすいよう8の倍数に丸める(最低64)。"""
    return max(64, int(round(value / 8)) * 8)


def _comfyui_url(cfg: dict) -> str:
    return cfg.get("url", "http://127.0.0.1:8188").rstrip("/")


def _is_comfyui_running(url: str, timeout: int = 3) -> bool:
    try:
        resp = requests.get(f"{url}/system_stats", timeout=timeout)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _config_path(value: str, base_dir: Path | None = None) -> Path:
    expanded = os.path.expandvars(str(value or "").strip())
    if not expanded:
        return Path()
    path = Path(expanded).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path


def ensure_comfyui_ready(config: dict | None = None, start_if_needed: bool = True) -> tuple[bool, str]:
    """ComfyUIの接続確認を行い、必要なら設定に従ってローカル起動する。"""
    config = config or load_ai_config()
    if config.get("provider", "comfyui") != "comfyui":
        return True, "ComfyUI provider is not selected."

    cfg = config.get("comfyui", {})
    url = _comfyui_url(cfg)
    if _is_comfyui_running(url):
        return True, f"ComfyUIは起動済みです({url})。"

    with _COMFYUI_START_LOCK:
        if _is_comfyui_running(url):
            return True, f"ComfyUIは起動済みです({url})。"

        if not start_if_needed:
            return False, f"ComfyUIに接続できません({url})。"

        if not cfg.get("auto_start", False):
            raise AIImageError(
                f"ComfyUIに接続できません({url})。\n"
                "自動起動はOFFです。ComfyUIを手動で起動するか、config/ai_config.json の comfyui.auto_start を true にしてください。"
            )

        missing = [key for key in ("python_path", "main_path", "working_dir") if not str(cfg.get(key, "")).strip()]
        if missing:
            raise AIImageError(
                "ComfyUIの自動起動設定が足りません。\n"
                f"config/ai_config.json の comfyui.{', comfyui.'.join(missing)} を設定してください。"
            )

        working_dir = _config_path(cfg.get("working_dir"))
        python_path = _config_path(cfg.get("python_path"), working_dir)
        main_path = _config_path(cfg.get("main_path"), working_dir)

        problems = []
        if not working_dir.exists():
            problems.append(f"working_dir が見つかりません: {working_dir}")
        if not python_path.exists():
            problems.append(f"python_path が見つかりません: {python_path}")
        if not main_path.exists():
            problems.append(f"main_path が見つかりません: {main_path}")
        if problems:
            raise AIImageError("ComfyUIを自動起動できません。\n" + "\n".join(problems))

        extra_args = cfg.get("extra_args", [])
        if isinstance(extra_args, str):
            extra_args = [arg for arg in extra_args.split(" ") if arg]
        if not isinstance(extra_args, list):
            extra_args = []

        command = [str(python_path), str(main_path), *[str(arg) for arg in extra_args]]
        try:
            process = subprocess.Popen(
                command,
                cwd=str(working_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as e:
            raise AIImageError(f"ComfyUIの起動に失敗しました。\n{e}")

        startup_timeout = int(cfg.get("startup_timeout_seconds", 90))
        deadline = time.time() + max(startup_timeout, 1)
        while time.time() < deadline:
            if _is_comfyui_running(url):
                return True, f"ComfyUIを自動起動しました({url})。"
            if process.poll() is not None:
                raise AIImageError(
                    "ComfyUIのプロセスが起動直後に終了しました。\n"
                    "ComfyUI側のエラー内容を確認してください。"
                )
            time.sleep(1.0)

        raise AIImageError(
            f"ComfyUIを起動しましたが、{startup_timeout}秒以内に接続確認できませんでした({url})。\n"
            "初回起動やモデル読み込みに時間がかかる場合は、config/ai_config.json の comfyui.startup_timeout_seconds を増やしてください。"
        )


def _comfyui_pick_checkpoint(url: str, cfg: dict, timeout: int) -> str:
    """使用するモデル(checkpoint)名を決める。

    config の ckpt_name が指定されていればそれを使う。空ならComfyUIに
    問い合わせて最初に見つかったモデルを自動採用する。
    """
    name = (cfg.get("ckpt_name") or "").strip()
    if name:
        return name
    try:
        resp = requests.get(f"{url}/object_info/CheckpointLoaderSimple", timeout=timeout)
        resp.raise_for_status()
        info = resp.json()
        choices = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception:
        choices = []
    if not choices:
        raise AIImageError(
            "ComfyUIにモデル(checkpoint)が見つかりません。\n"
            "ComfyUIの models/checkpoints フォルダに .safetensors のモデルを置いてください。\n"
            "(例: Civitai から DreamShaper などをダウンロード)"
        )
    return choices[0]


def _comfyui_upload_image(url: str, image_path: Path, timeout: int) -> str:
    """参考画像をComfyUIのinputにアップロードし、LoadImage用のファイル名を返す。"""
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


def _comfyui_build_workflow(
    prompt: str,
    negative: str,
    cfg: dict,
    ckpt_name: str,
    width: int,
    height: int,
    init_image_name: str | None,
) -> dict:
    """ComfyUIのAPI形式ワークフロー(ノードグラフ)を組み立てる。

    init_image_name が指定された場合は img2img(LoadImage→VAEEncode)、
    それ以外は txt2img(EmptyLatentImage)になる。
    """
    seed = random.randint(0, 2**63 - 1)
    workflow = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": cfg.get("steps", 28),
                "cfg": cfg.get("cfg_scale", 7),
                "sampler_name": cfg.get("sampler_name", "euler"),
                "scheduler": cfg.get("scheduler", "normal"),
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "bdm", "images": ["8", 0]}},
    }
    if init_image_name is not None:
        # img2img: 参考画像を読み込んで潜在空間にエンコードし、denoiseで変化量を決める
        workflow["10"] = {"class_type": "LoadImage", "inputs": {"image": init_image_name}}
        workflow["11"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}}
        workflow["3"]["inputs"]["latent_image"] = ["11", 0]
        workflow["3"]["inputs"]["denoise"] = cfg.get("denoising_strength", 0.7)
    else:
        workflow["5"] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        }
    return workflow


def _generate_comfyui(
    prompt: str,
    negative: str,
    config: dict,
    init_image: Path | None = None,
) -> Image.Image:
    """ローカルのComfyUIで画像を生成する。

    init_image を渡すと img2img になり、サンプル画像の雰囲気に寄せて生成する。
    """
    cfg = config.get("comfyui", {})
    url = _comfyui_url(cfg)
    timeout = config.get("timeout_seconds", 300)
    width = _round8(cfg.get("width", 768))
    height = _round8(cfg.get("height", 432))

    # 接続確認(分かりやすいエラーにするため最初に叩く)
    ensure_comfyui_ready(config, start_if_needed=True)

    ckpt_name = _comfyui_pick_checkpoint(url, cfg, timeout)

    init_name = None
    if init_image is not None:
        try:
            init_name = _comfyui_upload_image(url, init_image, timeout)
        except Exception as e:
            raise AIImageError(f"参考画像のアップロードに失敗しました: {e}")

    workflow = _comfyui_build_workflow(prompt, negative, cfg, ckpt_name, width, height, init_name)
    client_id = f"bdm-{random.randint(0, 1_000_000)}"

    try:
        resp = requests.post(f"{url}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise AIImageError(f"ComfyUIへの生成リクエストに失敗しました: {e}")
    if resp.status_code != 200:
        raise AIImageError(f"ComfyUIエラー (HTTP {resp.status_code}):\n{resp.text[:500]}")
    prompt_id = resp.json().get("prompt_id")
    if not prompt_id:
        raise AIImageError(f"ComfyUIが生成IDを返しませんでした:\n{resp.text[:500]}")

    # 生成完了までポーリング(historyに結果が入るまで待つ)
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
                outputs = data.get("outputs", {})
                for node_out in outputs.values():
                    images = node_out.get("images")
                    if images:
                        image_info = images[0]
                        break
                if image_info is not None:
                    break
                status = data.get("status", {})
                if status.get("status_str") == "error":
                    raise AIImageError(f"ComfyUIの生成中にエラーが発生しました:\n{json.dumps(status)[:500]}")
        time.sleep(1.0)

    if image_info is None:
        raise AIImageError("ComfyUIの生成がタイムアウトしました。stepsや解像度を下げるか、timeout_secondsを増やしてください。")

    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    img_resp = requests.get(f"{url}/view", params=params, timeout=timeout)
    img_resp.raise_for_status()
    return Image.open(io.BytesIO(img_resp.content))


# ──────────────────────────────────────────
#  画像加工ユーティリティ
# ──────────────────────────────────────────


def _black_to_alpha(img: Image.Image) -> Image.Image:
    """黒背景のエフェクト画像を透過PNGに変換する。

    透過出力に対応していないプロバイダー(stability / sdwebui)用。
    明るい部分ほど不透明になる(発光エフェクト向けの定番手法)。
    """
    img = img.convert("RGBA")
    r, g, b, _ = img.split()
    alpha = ImageChops.lighter(ImageChops.lighter(r, g), b)
    img.putalpha(alpha)
    return img


def _safe_slug(value: str) -> str:
    value = value.strip().replace(" ", "_").replace("　", "_")
    return re.sub(r"[^0-9A-Za-z_\-ぁ-んァ-ヶ一-龠]+", "", value) or "image"


def _save_image(img: Image.Image, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{name}_{timestamp}.png"
    counter = 1
    while out_path.exists():
        out_path = out_dir / f"{name}_{timestamp}_{counter:02d}.png"
        counter += 1
    img.save(str(out_path), "PNG")
    return out_path


# ──────────────────────────────────────────
#  公開API
# ──────────────────────────────────────────


def generate_background(node_name: str) -> Path:
    """拠点名からリアルダークファンタジー調の背景を生成して保存する。

    Returns:
        保存したPNGファイルのパス
    """
    node_name = node_name.strip()
    if not node_name:
        raise AIImageError("拠点名が空です。先に拠点名を入力してください。")

    config = load_ai_config()
    provider = config.get("provider", "comfyui")
    prompt, negative = build_background_prompt(node_name)

    if provider == "comfyui":
        img = _generate_comfyui(prompt, negative, config)
    elif provider == "sdwebui":
        img = _generate_sdwebui(prompt, negative, config)
    elif provider == "stability":
        img = _generate_stability(prompt, negative, config)
    elif provider == "openai":
        img = _generate_openai(prompt, config)
    else:
        raise AIImageError(f"不明なprovider設定です: {provider} (comfyui / sdwebui / stability / openai のいずれか)")

    out_dir = PROJECT_ROOT / config.get("background_output_dir", "assets/backgrounds/ai")
    return _save_image(img.convert("RGB"), out_dir, f"bg_{_safe_slug(node_name)}")


def generate_effect(effect_type: str) -> Path:
    """エフェクト種類から後方エフェクト(透過PNG)を生成して保存する。

    material/サンプル(またはmaterial/sample)に同名フォルダ・ファイルがあれば
    参考画像として使用する(sdwebuiではimg2img、openaiではedits)。

    Returns:
        保存したPNGファイルのパス
    """
    effect_type = effect_type.strip()
    if not effect_type:
        raise AIImageError("エフェクト種類が空です。")

    config = load_ai_config()
    provider = config.get("provider", "comfyui")
    prompt, negative = build_effect_prompt(effect_type)

    if provider == "comfyui":
        reference = find_reference_image(effect_type, config)
        img = _generate_comfyui(prompt + ", pure black background", negative, config, init_image=reference)
        img = _black_to_alpha(img)
    elif provider == "sdwebui":
        reference = find_reference_image(effect_type, config)
        img = _generate_sdwebui(prompt + ", pure black background", negative, config, init_image=reference)
        img = _black_to_alpha(img)
    elif provider == "stability":
        img = _black_to_alpha(_generate_stability(prompt + " on a pure black background", negative, config))
    elif provider == "openai":
        reference = find_reference_image(effect_type, config)
        img = _generate_openai(prompt, config, transparent=True, reference_path=reference)
        if "A" not in img.getbands() or img.convert("RGBA").getextrema()[3] == (255, 255):
            # 万一透過になっていない場合は黒→透過変換でフォールバック
            img = _black_to_alpha(img)
    else:
        raise AIImageError(f"不明なprovider設定です: {provider} (comfyui / sdwebui / stability / openai のいずれか)")

    out_dir = PROJECT_ROOT / config.get("effect_output_dir", "assets/effects/ai")
    return _save_image(img.convert("RGBA"), out_dir, f"effect_{_safe_slug(effect_type)}")


def check_setup() -> str:
    """セットアップ状態を確認して結果メッセージを返す(課金は発生しない)。"""
    lines = []
    config = load_ai_config()
    provider = config.get("provider", "comfyui")
    lines.append(f"・provider 設定           : {provider}")
    lines.append("・config/ai_config.json   : OK")
    load_ai_prompts()
    lines.append("・config/ai_prompts.json  : OK")

    if provider == "comfyui":
        cfg = config.get("comfyui", {})
        url = _comfyui_url(cfg)
        lines.append(f"・ComfyUI自動起動        : {'ON' if cfg.get('auto_start', False) else 'OFF'}")
        if cfg.get("auto_start", False):
            missing = [key for key in ("python_path", "main_path", "working_dir") if not str(cfg.get(key, "")).strip()]
            status = "OK" if not missing else f"NG({', '.join(missing)} が未設定)"
            lines.append(f"・ComfyUI起動設定        : {status}")
        if _is_comfyui_running(url, timeout=5):
            lines.append(f"・ComfyUI接続({url}) : OK")
        else:
            lines.append(f"・ComfyUI接続({url}) : NG(ComfyUIを起動してください)")
        if _is_comfyui_running(url, timeout=5):
            try:
                ckpt = _comfyui_pick_checkpoint(url, cfg, 15)
                lines.append(f"・モデル(checkpoint)      : OK({ckpt})")
            except AIImageError as e:
                lines.append(f"・モデル(checkpoint)      : NG → {e}")
    elif provider in ("openai", "stability"):
        try:
            get_api_key(provider)
            lines.append("・APIキー(.env)           : OK(設定されています)")
        except AIImageError as e:
            lines.append(f"・APIキー(.env)           : NG → {e}")
    elif provider == "sdwebui":
        url = config.get("sdwebui", {}).get("url", "http://127.0.0.1:7860")
        try:
            requests.get(f"{url.rstrip('/')}/sdapi/v1/sd-models", timeout=5)
            lines.append(f"・WebUI接続({url}) : OK")
        except Exception:
            lines.append(f"・WebUI接続({url}) : NG(WebUIを --api 付きで起動してください)")

    sample_found = False
    for sample_dir in config.get("sample_dirs", []):
        if (PROJECT_ROOT / sample_dir).exists():
            lines.append(f"・サンプルフォルダ        : {sample_dir} を参照します")
            sample_found = True
            break
    if not sample_found:
        lines.append("・サンプルフォルダ        : 見つかりません(なくても動きます)")

    return "\n".join(lines)


# ──────────────────────────────────────────
#  コマンドライン実行
# ──────────────────────────────────────────


def _cli():
    usage = (
        "使い方:\n"
        "  python -m core.ai_image check            ... セットアップ確認(無料)\n"
        '  python -m core.ai_image bg "拠点名"      ... 背景を1枚生成\n'
        "  python -m core.ai_image effect fire       ... エフェクトを1枚生成\n"
        f"  エフェクト種類: {', '.join(list_effect_types())}"
    )
    args = sys.argv[1:]
    if not args:
        print(usage)
        return

    try:
        if args[0] == "check":
            print("[セットアップ確認]")
            print(check_setup())
        elif args[0] == "bg" and len(args) >= 2:
            print(f"[背景生成] 拠点名: {args[1]}")
            path = generate_background(args[1])
            print(f"[完了] 保存先: {path}")
        elif args[0] == "effect" and len(args) >= 2:
            print(f"[エフェクト生成] 種類: {args[1]}")
            path = generate_effect(args[1])
            print(f"[完了] 保存先: {path}")
        else:
            print(usage)
    except AIImageError as e:
        print(f"[エラー]\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
