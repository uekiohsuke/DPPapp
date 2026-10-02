"""辞書の基本的な警告(空の項目・重複)。言語に依存しない

言語別の整合性チェック(音素、語源欄の綴りなど)は M4 で言語別機能として足す。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .zpdic import Dictionary, form, meanings


@dataclass(frozen=True)
class Issue:
    word_id: int | None
    kind: str
    message: str


def _id(w: dict):
    return w["entry"].get("id")


def check_word(w: dict) -> list[Issue]:
    """1つの項目だけで分かる警告"""
    wid, out = _id(w), []
    f = form(w)
    if not f.strip():
        out.append(Issue(wid, "空の見出し語", "見出し語が空"))
    elif f != f.strip():
        out.append(Issue(wid, "空白", f"見出し語の前後に空白がある: {f!r}"))
    if not [m for m in meanings(w) if m.strip()]:
        out.append(Issue(wid, "訳語なし", f"{f or '(空)'}: 訳語がない"))
    for t in w.get("translations", []):
        if any(not m.strip() for m in t.get("forms", [])):
            out.append(Issue(wid, "空の訳語", f"{f}: 区分「{t.get('title', '')}」に空の訳語がある"))
    for c in w.get("contents", []):
        if not c.get("text", "").strip():
            out.append(Issue(wid, "空の内容", f"{f}: 内容「{c.get('title', '')}」が空"))
    for v in w.get("variations", []):
        if not v.get("form", "").strip():
            out.append(Issue(wid, "空の変化形", f"{f}: 変化形「{v.get('title', '')}」の綴りが空"))
    return out


def check_dictionary(d: Dictionary) -> list[Issue]:
    out = []
    for w in d.words:
        out.extend(check_word(w))
    by_form, by_id = defaultdict(list), defaultdict(list)
    for w in d.words:
        if form(w).strip():
            by_form[form(w)].append(w)
        by_id[_id(w)].append(w)
    for f, ws in by_form.items():
        if len(ws) > 1:
            ids = "、".join(str(_id(w)) for w in ws)
            for w in ws:
                out.append(Issue(_id(w), "同じ綴り", f"{f}: 同じ見出し語が{len(ws)}つある(id {ids})"))
    for wid, ws in by_id.items():
        if len(ws) > 1:
            out.append(Issue(wid, "id の重複", f"id {wid} が{len(ws)}つの項目で使われている"))
    return out
