"""LLM の接続(OpenAI 互換の API。Ollama、LM Studio、llama.cpp、Gemini の互換 API など。仕様書 4.6)

接続先とモデルは、言語データではなくこの PC の設定なので、リポジトリやプロジェクトの外に置く:
  Windows: %APPDATA%\\conlang\\llm.json、そのほか: ~/.config/conlang/llm.json
  (環境変数 CONLANG_CONFIG_DIR でフォルダを変えられる)
環境変数 CONLANG_LLM_URL / CONLANG_LLM_MODEL / CONLANG_LLM_KEY があれば、ファイルより優先する
(試作の PUTE_LLM_URL / PUTE_LLM_MODEL / PUTE_LLM_KEY も読む)。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULT_URL = "http://localhost:11434/v1"


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    url: str = DEFAULT_URL
    model: str = ""
    key: str = ""
    temperature: float = 0.2
    timeout: int = 600
    # 考える過程を出すモデル(qwen3 など)の量。"none" で止める(Ollama の OpenAI 互換 API)。空なら送らない
    reasoning_effort: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.url and self.model)


def config_dir() -> Path:
    if os.environ.get("CONLANG_CONFIG_DIR"):
        return Path(os.environ["CONLANG_CONFIG_DIR"])
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "conlang"
    return Path.home() / ".config" / "conlang"


def config_path() -> Path:
    return config_dir() / "llm.json"


def load_config() -> LLMConfig:
    cfg = LLMConfig()
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        names = {f.name for f in fields(LLMConfig)}
        cfg = LLMConfig(**{k: v for k, v in data.items() if k in names})
    except (OSError, ValueError, TypeError):
        pass
    for name in ("url", "model", "key"):
        for prefix in ("CONLANG_LLM_", "PUTE_LLM_"):
            v = os.environ.get(prefix + name.upper())
            if v:
                setattr(cfg, name, v)
                break
    return cfg


def save_config(cfg: LLMConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _request(cfg: LLMConfig, path: str, body: dict | None = None, timeout: int | None = None) -> dict:
    url = cfg.url.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if cfg.key:
        headers["Authorization"] = "Bearer " + cfg.key
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout or cfg.timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"{url} が {e.code} を返した: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"{url} に接続できない: {e}") from e


def list_models(cfg: LLMConfig | None = None) -> list[str]:
    cfg = cfg or load_config()
    data = _request(cfg, "/models", timeout=20)
    return sorted(m.get("id", "") for m in data.get("data", []))


def chat(prompt: str, cfg: LLMConfig | None = None, json_mode: bool = False) -> str:
    """1回だけ問い合わせて、答えの本文を返す"""
    cfg = cfg or load_config()
    if not cfg.ready:
        raise LLMError("LLM のモデルが決まっていない。conlang llm config --url URL --model モデル名 で設定する")
    body = {"model": cfg.model, "temperature": cfg.temperature, "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if cfg.reasoning_effort:
        body["reasoning_effort"] = cfg.reasoning_effort
    data = _request(cfg, "/chat/completions", body)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"答えの形が想定と違う: {str(data)[:300]}") from e
