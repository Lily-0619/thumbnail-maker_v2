"""
ai_image.py
AI画像生成モジュール。

背景(拠点名から連想されるリアルダークファンタジー調)と
後方エフェクト(キャラに合わせた透過エフェクト)をAIで生成する。

対応プロバイダー:
  - openai   : OpenAI gpt-image-1(推奨。透過PNGを直接生成できる)
  - stability: Stability AI(Stable Diffusion公式API)
  - sdwebui  : ローカルのStable Diffusion WebUI(AUTOMATIC1111)

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
import re
import sys
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


def _generate_sdwebui(prompt: str, negative: str, config: dict) -> Image.Image:
    cfg = config.get("sdwebui", {})
    url = cfg.get("url", "http://127.0.0.1:7860").rstrip("/")
    timeout = config.get("timeout_seconds", 180)

    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": cfg.get("width", 1344),
        "height": cfg.get("height", 768),
        "steps": cfg.get("steps", 28),
        "cfg_scale": cfg.get("cfg_scale", 7),
    }
    if cfg.get("sampler_name"):
        payload["sampler_name"] = cfg["sampler_name"]

    try:
        resp = requests.post(f"{url}/sdapi/v1/txt2img", json=payload, timeout=timeout)
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
    provider = config.get("provider", "openai")
    prompt, negative = build_background_prompt(node_name)

    if provider == "openai":
        img = _generate_openai(prompt, config)
    elif provider == "stability":
        img = _generate_stability(prompt, negative, config)
    elif provider == "sdwebui":
        img = _generate_sdwebui(prompt, negative, config)
    else:
        raise AIImageError(f"不明なprovider設定です: {provider} (openai / stability / sdwebui のいずれか)")

    out_dir = PROJECT_ROOT / config.get("background_output_dir", "assets/backgrounds/ai")
    return _save_image(img.convert("RGB"), out_dir, f"bg_{_safe_slug(node_name)}")


def generate_effect(effect_type: str) -> Path:
    """エフェクト種類から後方エフェクト(透過PNG)を生成して保存する。

    material/サンプル(またはmaterial/sample)に同名フォルダ・ファイルがあれば
    参考画像として使用する(openaiのみ)。

    Returns:
        保存したPNGファイルのパス
    """
    effect_type = effect_type.strip()
    if not effect_type:
        raise AIImageError("エフェクト種類が空です。")

    config = load_ai_config()
    provider = config.get("provider", "openai")
    prompt, negative = build_effect_prompt(effect_type)

    if provider == "openai":
        reference = find_reference_image(effect_type, config)
        img = _generate_openai(prompt, config, transparent=True, reference_path=reference)
        if "A" not in img.getbands() or img.convert("RGBA").getextrema()[3] == (255, 255):
            # 万一透過になっていない場合は黒→透過変換でフォールバック
            img = _black_to_alpha(img)
    elif provider == "stability":
        img = _black_to_alpha(_generate_stability(prompt + " on a pure black background", negative, config))
    elif provider == "sdwebui":
        img = _black_to_alpha(_generate_sdwebui(prompt + ", pure black background", negative, config))
    else:
        raise AIImageError(f"不明なprovider設定です: {provider} (openai / stability / sdwebui のいずれか)")

    out_dir = PROJECT_ROOT / config.get("effect_output_dir", "assets/effects/ai")
    return _save_image(img.convert("RGBA"), out_dir, f"effect_{_safe_slug(effect_type)}")


def check_setup() -> str:
    """セットアップ状態を確認して結果メッセージを返す(課金は発生しない)。"""
    lines = []
    config = load_ai_config()
    provider = config.get("provider", "openai")
    lines.append(f"・provider 設定           : {provider}")
    lines.append("・config/ai_config.json   : OK")
    load_ai_prompts()
    lines.append("・config/ai_prompts.json  : OK")

    if provider in ("openai", "stability"):
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
