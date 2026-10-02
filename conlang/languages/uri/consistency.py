"""ウリ語の辞書の検査(言語別機能)

辞書は旧表記で、時代の違う語も混ざっている(文法 0章)。誤りと決めつけられないので、どれも「注意」にする。
- 見出し語を現代の転写にしたとき、音節(CV、CVn、CVng)に分けられるか。
  母音が続くときは、近現代の形(文法 8.3 の半母音の挿入より前)かもしれないと添える
- 音節への分け方が1通りか
- 旧表記の大文字の位置(音節の頭)が、音節への分け方と合っているか
略称(タグ「略称」)は、音節の検査をしない。アポストロフィ(情詞の後置)とハイフンは、語の区切りとして扱う。
"""
from __future__ import annotations

import re

from conlang.core.rules import Rules
from conlang.core.validate import NOTICE, Issue
from conlang.core.zpdic import Dictionary, form

from .lang import UriLang

ABBREVIATION_TAG = "略称"
SPLIT = re.compile(r"[\s'\-]+")


def words_of(lang: UriLang, old: str) -> list[tuple[str, str]]:
    """見出し語を語に分ける: [(旧表記, 現代の転写)]"""
    return [(o, lang.to_modern(o)) for o in SPLIT.split(old) if o]


def _bounds(parts: list[str]) -> set[int]:
    out, pos = set(), 0
    for p in parts[:-1]:
        pos += len(p)
        out.add(pos)
    return out


def _without_exception(lang: UriLang, bounds: set[int], modern: str) -> set[int]:
    """母音で始まる例外の語(uli = 本来は wuli)の中の境目を除く。旧表記では UliPa とも ULi とも書くので、比べない"""
    for w in lang.vowel_initial:
        if modern.startswith(w):
            bounds = {b for b in bounds if b >= len(w)}
    return bounds


def _bounds_of(lang: UriLang, sylls, modern: str) -> set[int]:
    return _without_exception(lang, _bounds([s.text for s in sylls]), modern)


def check_dictionary(d: Dictionary, rules: Rules | None) -> list[Issue]:
    lang = UriLang.from_rules(rules)
    vowels = set(lang.vowels)
    out = []
    for w in d.words:
        wid, f = w["entry"].get("id"), form(w)
        if not f or ABBREVIATION_TAG in w.get("tags", []):
            continue
        for old, modern in words_of(lang, f):
            alls = lang.syllabify_all(modern)
            if not alls:
                if any(a in vowels and b in vowels for a, b in zip(modern, modern[1:]) if a != b):
                    hint = "母音が続く。近現代の形(半母音の挿入より前)かもしれない"
                else:
                    hint = "ウリ語の音素・音節(CV、CVn、CVng)にない並びがある"
                out.append(Issue(wid, "音節", f"{f}: {modern} を音節に分けられない({hint})", NOTICE))
                continue
            if len(alls) > 1:
                shown = " / ".join(".".join(s.text for s in a) for a in alls[:3])
                out.append(Issue(wid, "音節", f"{f}: {modern} の音節への分け方が{len(alls)}通りある({shown})", NOTICE))
            marked = lang.old_syllables(old)
            if any(ch.isupper() for ch in old[1:]) and \
                    _bounds_of(lang, alls[0], modern) != _without_exception(lang, _bounds(marked), modern):
                out.append(Issue(wid, "旧表記", f"{f}: 大文字の区切り({'.'.join(marked)})が、"
                                               f"音節の分け方({'.'.join(s.text for s in alls[0])})と合わない", NOTICE))
    return out
