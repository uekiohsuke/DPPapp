"""LLM 呼び出しの履歴と、入力が変わったかどうかの記録(プロジェクトの llm_log/)

- save_call: プロンプトと答えを1回ごとに JSON で残す(仕様書 4.6)
- inputs_changed / remember_inputs: 前回と同じ入力なら、LLM を呼ばずに済ませるため(仕様書 4.7「変わったときだけ実行」)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

STATE_FILE = "state.json"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_call(log_dir: str | Path, purpose: str, prompt: str, answer: str | None, **extra) -> Path:
    now = datetime.now()
    path = Path(log_dir) / f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{purpose}.json"
    _write(path, {"purpose": purpose, "time": now.isoformat(timespec="seconds"), "prompt": prompt,
                  "answer": answer, **extra})
    return path


def list_calls(log_dir: str | Path, purpose: str | None = None) -> list[Path]:
    d = Path(log_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.name != STATE_FILE and (purpose is None or p.stem.endswith(f"-{purpose}")))


def fingerprint(texts: dict[str, str]) -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in texts.items()}


def _state(log_dir: Path) -> dict:
    f = Path(log_dir) / STATE_FILE
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def inputs_changed(log_dir: str | Path, key: str, texts: dict[str, str]) -> bool:
    return _state(Path(log_dir)).get(key) != fingerprint(texts)


def remember_inputs(log_dir: str | Path, key: str, texts: dict[str, str]) -> None:
    state = _state(Path(log_dir))
    state[key] = fingerprint(texts)
    _write(Path(log_dir) / STATE_FILE, state)
