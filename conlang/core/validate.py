"""辞書の警告と整合性チェックのうち、言語に依存しないもの

- 空の項目・重複(M2)
- 似た綴りの語、語源欄などの旧用語(M4)
言語別の検査(音素、語源欄の綴りなど)は、言語別機能が registry の check_dictionary で足す。

段階:
- 誤り: 直す必要があるもの(誤記、旧用語、同じ綴り、id の重複)
- 注意: 確かめたほうがよいもの(空の項目、似た綴り)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .rules import Rules
from .zpdic import Dictionary, form, meanings

ERROR = "誤り"
NOTICE = "注意"


@dataclass(frozen=True)
class Issue:
    word_id: int | None
    kind: str
    message: str
    level: str = NOTICE


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
    """空の項目と重複"""
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
                out.append(Issue(_id(w), "同じ綴り", f"{f}: 同じ見出し語が{len(ws)}つある(id {ids})", ERROR))
    for wid, ws in by_id.items():
        if len(ws) > 1:
            out.append(Issue(wid, "id の重複", f"id {wid} が{len(ws)}つの項目で使われている", ERROR))
    return out


# ---------- 整合性(M4) ----------

def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def check_similar(d: Dictionary, max_distance: int = 1, min_length: int = 4) -> list[Issue]:
    """綴りが非常に似た見出し語(違いが max_distance 文字以内)。誤記とは限らないので「注意」"""
    heads = [(w, form(w)) for w in d.words if len(form(w)) >= min_length]
    out = []
    for i, (w1, f1) in enumerate(heads):
        for w2, f2 in heads[i + 1:]:
            if f1 != f2 and abs(len(f1) - len(f2)) <= max_distance and edit_distance(f1, f2) <= max_distance:
                out.append(Issue(_id(w1), "似た綴り", f"{f1} と {f2}(id {_id(w2)})の綴りが{edit_distance(f1, f2)}文字だけ違う"))
    return out


def terminology_map(rules: Rules | None) -> dict[str, str]:
    """規則ファイルの checks にある {id: terminology, map: {旧: 新}}"""
    if rules is None:
        return {}
    for c in rules.get("checks", default=[]) or []:
        if isinstance(c, dict) and c.get("id") == "terminology":
            return {str(k): str(v) for k, v in (c.get("map") or {}).items()}
    return {}


def check_terminology(d: Dictionary, rules: Rules | None) -> list[Issue]:
    """内容欄(語源・語義など)に、旧い用語が残っていないか"""
    terms = terminology_map(rules)
    out = []
    for w in d.words:
        for c in w.get("contents", []):
            for old, new in terms.items():
                if old in c.get("text", ""):
                    out.append(Issue(_id(w), "旧用語",
                                     f"{form(w)}: 内容「{c.get('title', '')}」に旧い用語「{old}」がある(今は「{new}」)", ERROR))
    return out


def check_all(d: Dictionary, rules: Rules | None = None, language=None) -> list[Issue]:
    """共通の検査と、言語別の検査(language は registry.LanguageModule)をまとめて行う"""
    min_length = getattr(language, "similar_min_length", 4) if language is not None else 4
    out = check_dictionary(d) + check_similar(d, min_length=min_length) + check_terminology(d, rules)
    if language is not None and language.check_dictionary is not None:
        out += language.check_dictionary(d, rules)
    return out
