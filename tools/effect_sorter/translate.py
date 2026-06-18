"""
translate.py
Ollama（オラマ）を使って日本語→英語キーへ変換する。

  - ローカルの Ollama API（標準: http://127.0.0.1:11434）を使う。
  - 返す文字はファイル名に使いやすい half-width ASCII の snake_case に正規化する。
  - 失敗時は TranslationError を投げ、呼び出し側でユーザーに案内する。
  - 旧辞書ファイルは既存ユーザーの資産として残すが、通常翻訳にはAIを使う。
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import requests

from . import paths

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_START_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_START_TIMEOUT_SECONDS", "30"))
OLLAMA_AUTO_START = os.environ.get("OLLAMA_AUTO_START", "1").strip().lower() not in {"0", "false", "no"}
OLLAMA_START_COMMAND = os.environ.get("OLLAMA_START_COMMAND", "ollama serve")
OLLAMA_EXE = os.environ.get("OLLAMA_EXE", "").strip()
# モデル未取得なら自動 pull するか（初回のみDLが走る。0/false/no でOFF）
OLLAMA_AUTO_PULL = os.environ.get("OLLAMA_AUTO_PULL", "1").strip().lower() not in {"0", "false", "no"}
# pull はモデルのDLを伴うため長め
OLLAMA_PULL_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_PULL_TIMEOUT_SECONDS", "1800"))
_OLLAMA_PROCESS = None
# 起動・pull の多重実行を防ぐ（連打・複数スレッド対策）
_OLLAMA_LOCK = threading.Lock()


class TranslationError(Exception):
    """Ollama翻訳に失敗したときのユーザー向けエラー。"""


class OllamaStartupError(Exception):
    """Ollama起動確認に失敗したときのユーザー向けエラー。"""


# 無ければ生成する初期辞書（§8-1）
_INITIAL_DICT = {
    "蓮": "lotus",
    "蝶": "butterfly",
    "雷": "thunder",
    "氷": "ice",
    "花": "flower",
    "光": "light",
    "闇": "dark",
    "霧": "mist",
    "煙": "smoke",
}


def ensure_file():
    """辞書JSONが無い場合のみ初期辞書で生成する。既存は上書きしない。"""
    if not paths.DICT_JSON.exists():
        _atomic_write(paths.DICT_JSON, _INITIAL_DICT)


def load() -> dict:
    """辞書を読む。無ければ初期辞書を返す。"""
    if not paths.DICT_JSON.exists():
        return dict(_INITIAL_DICT)
    try:
        with open(paths.DICT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return dict(_INITIAL_DICT)


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def is_ollama_ready(timeout: int = 2) -> bool:
    """Ollama APIが応答するか確認する。"""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
    except requests.RequestException:
        return False
    return resp.status_code == 200


def ensure_ollama_ready(start_if_needed: bool = True) -> str:
    """
    Ollamaが起動済みか確認し、必要なら `ollama serve` を起動する。

    Windows / Mac ともに Ollama の標準CLI名 `ollama` を使う。
    場所が違う場合は OLLAMA_START_COMMAND で変更できる。
    """
    if is_ollama_ready():
        return f"Ollama ready: {OLLAMA_URL}"

    if not start_if_needed or not OLLAMA_AUTO_START:
        raise OllamaStartupError(
            "Ollamaが起動していません。\n"
            "Ollamaを起動してから、もう一度試してください。"
        )

    # 多重起動を避けるためロックで直列化。待っている間に他スレッドが
    # 起動を完了させたら、その結果を使う。
    with _OLLAMA_LOCK:
        if is_ollama_ready():
            return f"Ollama ready: {OLLAMA_URL}"

        _start_ollama_process()
        deadline = time.time() + OLLAMA_START_TIMEOUT_SECONDS
        while time.time() < deadline:
            if is_ollama_ready():
                return f"Ollama started: {OLLAMA_URL}"
            time.sleep(1)

    raise OllamaStartupError(
        "Ollamaを自動起動しましたが、時間内に接続できませんでした。\n"
        f"接続先: {OLLAMA_URL}\n"
        "初回はOllama本体の起動やモデル準備に時間がかかることがあります。"
    )


# ──────────────────────────────────────────
#  モデルの準備（存在確認・自動pull・ウォームアップ）
# ──────────────────────────────────────────


def list_models(timeout: int = 5) -> list[str]:
    """Ollamaに登録済みのモデル名一覧を返す（取得失敗時は空）。"""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            return [m.get("name", "") for m in resp.json().get("models", [])]
    except requests.RequestException:
        pass
    return []


def _model_matches(name: str, target: str) -> bool:
    """`llama3.1` と `llama3.1:latest` のような表記揺れを吸収して一致判定する。"""
    if not name:
        return False
    return name == target or name.split(":")[0] == target.split(":")[0]


def is_model_ready(timeout: int = 5) -> bool:
    """使用モデルがOllamaに取り込まれているか確認する。"""
    return any(_model_matches(name, OLLAMA_MODEL) for name in list_models(timeout))


def _pull_model() -> None:
    """使用モデルを `ollama pull` 相当でダウンロードする（初回のみ・時間がかかる）。"""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/pull",
            json={"name": OLLAMA_MODEL, "stream": False},
            timeout=OLLAMA_PULL_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise OllamaStartupError(f"モデルの取得に接続できませんでした: {e}")
    if resp.status_code != 200:
        raise OllamaStartupError(
            f"モデル {OLLAMA_MODEL} の取得に失敗しました (HTTP {resp.status_code})。\n"
            f"{resp.text[:200]}"
        )


def ensure_model_ready(pull_if_needed: bool = True, progress=None) -> str:
    """使用モデルが無ければ取得する。`progress(msg)` で途中経過を通知できる。"""
    if is_model_ready():
        return f"モデル準備済み: {OLLAMA_MODEL}"

    if not pull_if_needed or not OLLAMA_AUTO_PULL:
        raise OllamaStartupError(
            f"モデル {OLLAMA_MODEL} が見つかりません。\n"
            f"コマンドプロンプトで『ollama pull {OLLAMA_MODEL}』を実行してください。"
        )

    with _OLLAMA_LOCK:
        if is_model_ready():
            return f"モデル準備済み: {OLLAMA_MODEL}"
        if progress:
            progress(f"モデル {OLLAMA_MODEL} を取得中（初回のみ・数分かかります）…")
        _pull_model()

    if is_model_ready():
        return f"モデル取得完了: {OLLAMA_MODEL}"
    raise OllamaStartupError(f"モデル {OLLAMA_MODEL} を取得できませんでした。")


def warmup() -> None:
    """モデルをメモリに先読みさせ、初回翻訳のタイムアウトを防ぐ（失敗は無視）。"""
    if not is_model_ready():
        return
    try:
        requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        pass


def prepare_ollama(progress=None) -> str:
    """起動確認→モデル確認/取得→ウォームアップまでを一括で行う（起動時用）。

    `progress(msg)` を渡すと各段階のメッセージを受け取れる。
    """
    def report(msg):
        if progress:
            progress(msg)

    report("Ollama 起動確認中…")
    ensure_ollama_ready(start_if_needed=True)
    report("モデル確認中…")
    ensure_model_ready(pull_if_needed=True, progress=report)
    report("モデル読み込み中…")
    warmup()
    return f"Ollama 準備完了: {OLLAMA_MODEL}"


def _resolve_ollama_args() -> list[str]:
    args = shlex.split(OLLAMA_START_COMMAND)
    if not args:
        raise OllamaStartupError("OLLAMA_START_COMMAND が空です。")

    command = args[0]
    is_plain_ollama = command.lower() in {"ollama", "ollama.exe"} and "/" not in command and "\\" not in command
    if is_plain_ollama:
        resolved = _find_ollama_executable()
        if resolved:
            args[0] = resolved
    return args


def _find_ollama_executable() -> str | None:
    """PATHに無い場合も、Windowsの標準インストール先からOllamaを探す。"""
    candidates = []
    if OLLAMA_EXE:
        candidates.append(OLLAMA_EXE)

    found = shutil.which("ollama")
    if found:
        candidates.append(found)

    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        candidates.extend(
            [
                str(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe"),
                str(Path(local_appdata) / "Ollama" / "ollama.exe"),
                str(Path(program_files) / "Ollama" / "ollama.exe"),
                str(Path(program_files_x86) / "Ollama" / "ollama.exe"),
            ]
        )
    else:
        candidates.extend(("/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"))

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _start_ollama_process() -> None:
    """Ollamaサーバーをバックグラウンド起動する。"""
    global _OLLAMA_PROCESS
    if _OLLAMA_PROCESS and _OLLAMA_PROCESS.poll() is None:
        return

    args = _resolve_ollama_args()

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        devnull = subprocess.DEVNULL
        _OLLAMA_PROCESS = subprocess.Popen(
            args,
            stdin=devnull,
            stdout=devnull,
            stderr=devnull,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        raise OllamaStartupError(
            "Ollamaコマンドが見つかりません。\n"
            "Windows / Mac に Ollama をインストールしてからアプリを起動してください。\n"
            f"実行しようとしたコマンド: {OLLAMA_START_COMMAND}\n"
            "PATHに無い場合は OLLAMA_EXE に ollama.exe の場所を指定できます。"
        )
    except OSError as e:
        raise OllamaStartupError(
            "Ollamaの自動起動に失敗しました。\n"
            f"実行しようとしたコマンド: {OLLAMA_START_COMMAND}\n詳細: {e}"
        )


def translate_via_dict(text: str):
    """同梱辞書（config/effect_sorter_dict.json）で日本語→英語キーへ変換する。

    Ollamaが使えないときのフォールバック。完全一致を優先し、無ければ
    既知の語を含む部分一致で連結する。
    戻り値: (変換後文字列, 変換できたか bool)
    """
    text = (text or "").strip()
    if not text:
        return "", False
    table = load()

    # 1) 完全一致
    if text in table:
        key = normalize_key(table[text])
        if key:
            return key, True

    # 2) 部分一致（既知の語が含まれていれば連結する）
    found = [en for jp, en in table.items() if jp and jp in text]
    if found:
        key = normalize_key("_".join(found))
        if key:
            return key, True

    return "", False


def translate(text: str, allow_dict_fallback: bool = True):
    """
    入力文字列を英語キーへ変換して返す。

    まず Ollama を試し、使えない/失敗した場合は同梱辞書にフォールバックする
    （allow_dict_fallback=False で辞書を使わない）。

    戻り値: (変換後文字列, 変換できたか bool)
      - 空文字は (元の文字列, False)。
      - Ollama / 辞書のどちらも失敗したときだけ TranslationError を投げる。
    """
    if not text:
        return text, False

    ollama_problem = None
    try:
        ensure_ollama_ready(start_if_needed=True)
        if is_model_ready():
            normalized = normalize_key(_ask_ollama(text))
            if normalized:
                return normalized, True
            ollama_problem = "Ollamaがファイル名に使える英語を返しませんでした。"
        else:
            ollama_problem = f"モデル {OLLAMA_MODEL} がまだ準備できていません。"
    except (OllamaStartupError, TranslationError) as e:
        ollama_problem = str(e)

    # フォールバック: 同梱辞書
    if allow_dict_fallback:
        result, ok = translate_via_dict(text)
        if ok:
            return result, True

    raise TranslationError(
        "Ollamaでも辞書でも変換できませんでした。\n"
        "・別の日本語で試す\n"
        "・英語キーを直接入力する\n"
        "・辞書(config/effect_sorter_dict.json)に語を追加する\n"
        f"（Ollama側の状況: {ollama_problem}）"
    )


def _ask_ollama(text: str) -> str:
    prompt = (
        "Translate the following Japanese game visual-effect keyword into a short English file-name key.\n"
        "Rules:\n"
        "- Return only the key, no explanation.\n"
        "- Use lowercase English words.\n"
        "- Use underscores between words.\n"
        "- Do not use Japanese, spaces, punctuation, or quotes.\n"
        "- Keep it short, usually 1 to 3 words.\n\n"
        f"Japanese keyword: {text}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.exceptions.ConnectionError as e:
        raise TranslationError(
            "Ollamaに接続できません。\n"
            "Ollamaを起動してから、もう一度『日本語→英語に変換』を押してください。\n"
            f"接続先: {OLLAMA_URL}\n詳細: {e}"
        )
    except requests.exceptions.Timeout:
        raise TranslationError(
            "Ollamaの翻訳がタイムアウトしました。\n"
            "Ollamaが起動しているか、モデルのダウンロードが終わっているか確認してください。"
        )

    if resp.status_code != 200:
        raise TranslationError(
            f"Ollama APIエラーです。HTTP {resp.status_code}\n"
            f"接続先: {OLLAMA_URL}\n"
            f"モデル: {OLLAMA_MODEL}\n"
            f"詳細: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise TranslationError(f"Ollamaの返答をJSONとして読めませんでした。\n詳細: {e}")
    return str(data.get("response", "")).strip()


def normalize_key(value: str) -> str:
    """Ollamaの返答を命名ルールに合う英語キーへ正規化する。"""
    value = value.strip().strip("\"'`")
    value = value.lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    return value
