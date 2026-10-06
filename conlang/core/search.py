"""辞書の検索(見出し語・訳語・内容)。言語に依存しない"""
from __future__ import annotations

from dataclasses import dataclass, field

from .zpdic import Dictionary, form

# 検索する場所
FORM = "見出し語"
TRANSLATION = "訳語"
CONTENT = "内容"  # 語義・語源などの内容欄。content_titles で見出しを絞れる
TAG = "タグ"
ALL_TARGETS = (FORM, TRANSLATION, CONTENT, TAG)

# 一致のしかた
PARTIAL = "部分一致"
PREFIX = "前方一致"
EXACT = "完全一致"
MODES = (PARTIAL, PREFIX, EXACT)


@dataclass
class Query:
    text: str = ""
    targets: tuple[str, ...] = (FORM, TRANSLATION)
    mode: str = PARTIAL
    content_titles: tuple[str, ...] = ()  # 空なら、すべての内容欄
    ignore_case: bool = True


@dataclass
class Hit:
    word: dict
    score: int
    where: list[str] = field(default_factory=list)


def _match(hay: str, needle: str, mode: str, ignore_case: bool) -> bool:
    if ignore_case:
        hay, needle = hay.lower(), needle.lower()
    if mode == EXACT:
        return hay == needle
    if mode == PREFIX:
        return hay.startswith(needle)
    return needle in hay


def _fields(w: dict, q: Query):
    """(場所, 文字列, 完全一致のときの点) を出す"""
    if FORM in q.targets:
        yield FORM, form(w), 100
        for v in w.get("variations", []):
            yield FORM, v.get("form", ""), 80
    if TRANSLATION in q.targets:
        for t in w.get("translations", []):
            for m in t.get("forms", []):
                yield TRANSLATION, m, 90
    if CONTENT in q.targets:
        for c in w.get("contents", []):
            if not q.content_titles or c.get("title") in q.content_titles:
                yield f"{CONTENT}({c.get('title', '')})", c.get("text", ""), 40
    if TAG in q.targets:
        for t in w.get("tags", []):
            yield TAG, t, 50


def search(d: Dictionary, q: Query) -> list[Hit]:
    """一致した項目を、近い順(完全一致を先)に返す。空の検索語なら全項目を辞書の順で返す"""
    text = q.text.strip()
    if not text:
        return [Hit(w, 0) for w in d.words]
    hits = []
    for i, w in enumerate(d.words):
        score, where = 0, []
        for place, hay, exact_score in _fields(w, q):
            if hay and _match(hay, text, q.mode, q.ignore_case):
                s = exact_score if _match(hay, text, EXACT, q.ignore_case) else exact_score // 2
                score = max(score, s)
                if place not in where:
                    where.append(place)
        if score:
            hits.append((score, i, Hit(w, score, where)))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [h for _, _, h in hits]


def titles(d: Dictionary, key: str) -> list[str]:
    """項目の一覧(translations / contents / variations / relations)の title を、よく使われている順に。
    同じ回数なら辞書に出てくる順。空のものは除く"""
    from collections import Counter
    seq = [str(x.get("title", "")) for w in d.words for x in w.get(key, []) if isinstance(x, dict)]
    counts = Counter(seq)
    order = {t: i for i, t in enumerate(dict.fromkeys(seq))}
    return sorted((t for t in counts if t.strip()), key=lambda t: (-counts[t], order[t]))


def translation_titles(d: Dictionary) -> list[str]:
    """辞書の訳語の区分(名詞、存在概念 など)を、よく使われている順に"""
    return titles(d, "translations")


def content_titles(d: Dictionary) -> list[str]:
    """辞書に出てくる内容欄の見出し(出てくる順)"""
    seen = []
    for w in d.words:
        for c in w.get("contents", []):
            t = c.get("title", "")
            if t not in seen:
                seen.append(t)
    return seen
