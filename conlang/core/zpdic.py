"""zpdic 形式(OTM-JSON 互換。words / zpdic / snoj の3キー)の辞書の読み書き

読んだ JSON は dict のまま持ち、未知のキーやフィールドも含めてすべて保つ。
書き出すときは、元のファイルの書式(字下げの流儀、改行コード、末尾の改行、BOM)に合わせる。
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

TOP_KEYS = ("words", "zpdic", "snoj")

DEFAULT_WORD = {
    "entry": {"id": -1, "form": ""},
    "translations": [],
    "tags": [],
    "contents": [],
    "variations": [],
    "relations": [],
}


class ZpdicError(ValueError):
    """zpdic 形式として読めない"""


# ---------- 書式 ----------

@dataclass(frozen=True)
class JsonStyle:
    """JSON の書式。kind は python(json.dumps の indent)/ jackson(zpdic の書き出し)/ compact"""
    kind: str = "python"
    indent: int = 2
    newline: str = "\n"
    trailing_newline: bool = False
    bom: bool = False


def detect_style(text: str, bom: bool = False) -> JsonStyle:
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing = text.endswith("\n")
    lf = text.replace("\r\n", "\n")
    if "\n" not in lf.strip():
        return JsonStyle("compact", 0, newline, trailing, bom)
    m = re.search(r"\n( +)\S", lf)
    indent = len(m.group(1)) if m else 2
    kind = "jackson" if re.search(r'^ *"(?:[^"\\]|\\.)*" : ', lf, re.M) else "python"
    return JsonStyle(kind, indent, newline, trailing, bom)


def _jackson(v, depth: int, indent: int) -> str:
    """Jackson の DefaultPrettyPrinter と同じ形。配列は1行に並べ、オブジェクトだけ字下げを深くする"""
    if isinstance(v, dict):
        if not v:
            return "{ }"
        pad = " " * (indent * (depth + 1))
        items = [f"{pad}{json.dumps(k, ensure_ascii=False)} : {_jackson(x, depth + 1, indent)}" for k, x in v.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * (indent * depth) + "}"
    if isinstance(v, list):
        if not v:
            return "[ ]"
        return "[ " + ", ".join(_jackson(x, depth, indent) for x in v) + " ]"
    return json.dumps(v, ensure_ascii=False)


def dumps(data, style: JsonStyle = JsonStyle()) -> str:
    if style.kind == "jackson":
        text = _jackson(data, 0, style.indent)
    elif style.kind == "compact":
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(data, ensure_ascii=False, indent=style.indent)
    if style.trailing_newline:
        text += "\n"
    if style.newline != "\n":
        text = text.replace("\n", style.newline)
    return text


def encode(data, style: JsonStyle = JsonStyle()) -> bytes:
    return (b"\xef\xbb\xbf" if style.bom else b"") + dumps(data, style).encode("utf-8")


# ---------- 辞書 ----------

@dataclass
class Dictionary:
    data: dict
    style: JsonStyle = field(default_factory=JsonStyle)

    @classmethod
    def new(cls) -> "Dictionary":
        return cls({"words": [], "zpdic": {"defaultWord": copy.deepcopy(DEFAULT_WORD)}, "snoj": None})

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Dictionary":
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw.decode("utf-8-sig")
            data = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ZpdicError(f"JSON として読めない: {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("words"), list):
            raise ZpdicError("zpdic 形式ではない(words の一覧がない)")
        for i, w in enumerate(data["words"]):
            if not isinstance(w, dict) or not isinstance(w.get("entry"), dict):
                raise ZpdicError(f"{i + 1}番目の項目に entry がない")
        return cls(data, detect_style(text, bom))

    @classmethod
    def load(cls, path: str | os.PathLike) -> "Dictionary":
        return cls.from_bytes(Path(path).read_bytes())

    def to_bytes(self) -> bytes:
        return encode(self.data, self.style)

    def save(self, path: str | os.PathLike) -> None:
        """一時ファイルに書いてから置き換える(書きかけで壊れないように)"""
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(self.to_bytes())
        os.replace(tmp, path)

    # --- 項目 ---

    @property
    def words(self) -> list[dict]:
        return self.data["words"]

    def __len__(self) -> int:
        return len(self.words)

    def get(self, word_id: int) -> dict | None:
        return next((w for w in self.words if w["entry"].get("id") == word_id), None)

    def next_id(self) -> int:
        return max((w["entry"].get("id", 0) for w in self.words), default=0) + 1

    def add(self, form: str) -> dict:
        """defaultWord をひな形に、新しい項目を作って末尾に足す"""
        template = (self.data.get("zpdic") or {}).get("defaultWord") or DEFAULT_WORD
        w = copy.deepcopy(template)
        w.setdefault("entry", {})
        w["entry"]["id"] = self.next_id()
        w["entry"]["form"] = form
        self.words.append(w)
        return w

    def replace(self, word_id: int, new: dict) -> bool:
        """同じ位置の項目を new に差し替える"""
        for i, w in enumerate(self.words):
            if w["entry"].get("id") == word_id:
                self.words[i] = new
                return True
        return False

    def remove(self, word_id: int) -> bool:
        w = self.get(word_id)
        if w is None:
            return False
        self.words.remove(w)
        return True


# ---------- 項目のアクセサ ----------

def form(w: dict) -> str:
    return w["entry"].get("form", "")


def meanings(w: dict) -> list[str]:
    return [m for t in w.get("translations", []) for m in t.get("forms", [])]


def content(w: dict, title: str) -> str | None:
    return next((c.get("text", "") for c in w.get("contents", []) if c.get("title") == title), None)
