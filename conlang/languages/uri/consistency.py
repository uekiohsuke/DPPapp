"""ウリ語の辞書の検査(言語別機能)

辞書は旧表記で、時代の違う語も混ざっている(文法 0章)。誤りと決めつけられないので、どれも「注意」にする。
規則ファイルの checks にある検査だけを行う(規則ファイルがなければ、音節の検査だけ)。
- syllable_segmentation: 現代の転写にしたとき、音節(CV、CVn、CVng)に分けられるか。分け方が1通りか。
  旧表記の大文字の位置(音節の頭)が、音節の分け方と合っているか。
  近現代の形(history の半母音の挿入、指示詞の変化)なら、現代の形を添える
- known_prefix: ハイフンで区切った接頭辞が、意味範疇の接頭辞(su- など)か。古い接頭辞(xa-)ではないか
- compound_iyi_to_iya: iyi の並びが残っていないか(iya になる)
- avoid_cuwu: 造語で避ける並び(Cuwu)がないか
- particle_known: 訳語の区分が「情詞」の語が、規則ファイルの情詞の一覧にあるか(一覧の情詞が辞書にあるか)
略称(タグ「略称」)は、音節の検査をしない。アポストロフィ(情詞の後置)とハイフンは、語の区切りとして扱う。
"""
from __future__ import annotations

import re

from conlang.core.rules import Rules
from conlang.core.validate import NOTICE, Issue
from conlang.core.zpdic import Dictionary, form

from .lang import UriLang

ABBREVIATION_TAG = "略称"
PARTICLE_TITLE = "情詞"
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


def _syllable_issues(lang: UriLang, wid, f: str, old: str, modern: str) -> list[Issue]:
    vowels = set(lang.vowels)
    alls = lang.syllabify_all(modern)
    if not alls:
        if modern in lang.old_forms:
            new, meaning = lang.old_forms[modern]
            hint = f"近現代の形。現代の形は {new}" + (f"({meaning})" if meaning else "")
        elif any(a in vowels and b in vowels for a, b in zip(modern, modern[1:]) if a != b):
            hint = "母音が続く。近現代の形(半母音の挿入より前)かもしれない"
        else:
            hint = "ウリ語の音素・音節(CV、CVn、CVng)にない並びがある"
        return [Issue(wid, "音節", f"{f}: {modern} を音節に分けられない({hint})", NOTICE)]
    out = []
    if modern in lang.old_forms:  # 音節には分けられるが、近現代の形(指示詞の sugiyu など)
        new, meaning = lang.old_forms[modern]
        out.append(Issue(wid, "近現代の形", f"{f}: {modern} は近現代の形。現代の形は {new}"
                                          + (f"({meaning})" if meaning else ""), NOTICE))
    if len(alls) > 1:
        shown = " / ".join(".".join(s.text for s in a) for a in alls[:3])
        out.append(Issue(wid, "音節", f"{f}: {modern} の音節への分け方が{len(alls)}通りある({shown})", NOTICE))
    marked = lang.old_syllables(old)
    if any(ch.isupper() for ch in old[1:]) and \
            _bounds_of(lang, alls[0], modern) != _without_exception(lang, _bounds(marked), modern):
        out.append(Issue(wid, "旧表記", f"{f}: 大文字の区切り({'.'.join(marked)})が、"
                                       f"音節の分け方({'.'.join(s.text for s in alls[0])})と合わない", NOTICE))
    return out


def check_dictionary(d: Dictionary, rules: Rules | None) -> list[Issue]:
    lang = UriLang.from_rules(rules)
    patterns = lang.avoid_patterns() if lang.enabled("avoid_cuwu") else []
    out: list[Issue] = []
    particles_in_dict: set[str] = set()
    for w in d.words:
        wid, f = w["entry"].get("id"), form(w)
        if not f:
            continue
        modern_all = lang.to_modern(f)
        # 接頭辞
        if lang.enabled("known_prefix"):
            if "-" in f:
                head = lang.to_modern(f.split("-", 1)[0])
                if head and head not in lang.prefixes and lang.syllabify(head) and len(head) <= 4:
                    out.append(Issue(wid, "接頭辞", f"{f}: ハイフンの前の {head}- は、意味範疇の接頭辞"
                                                  f"({'、'.join(p + '-' for p in lang.prefixes)})にない", NOTICE))
            for old, new in lang.old_prefixes.items():
                if modern_all.startswith(old) and lang.syllabify(modern_all[len(old):] or "x"):
                    out.append(Issue(wid, "接頭辞", f"{f}: 古い接頭辞 {old}-(今は {new}-)で始まっているかもしれない", NOTICE))
        # 並び
        if lang.enabled("compound_iyi_to_iya"):
            for bad, good in lang.vowel_fixes:
                if bad in modern_all:
                    out.append(Issue(wid, "複合", f"{f}: {bad} の並びがある({good} になる)", NOTICE))
        for label, pat in patterns:
            if pat.search(modern_all):
                out.append(Issue(wid, "複合", f"{f}: 造語で避ける並び {label} がある", NOTICE))
        # 情詞
        if any(t.get("title") == PARTICLE_TITLE for t in w.get("translations", [])):
            particles_in_dict.add(modern_all)
            if lang.enabled("particle_known") and lang.particles and modern_all not in lang.particles:
                out.append(Issue(wid, "情詞", f"{f}: 訳語に「情詞」があるが、規則ファイルの情詞の一覧にない", NOTICE))
        # 音節
        if lang.enabled("syllable_segmentation") and ABBREVIATION_TAG not in w.get("tags", []):
            for old, modern in words_of(lang, f):
                out += _syllable_issues(lang, wid, f, old, modern)
    if lang.enabled("particle_known"):
        missing = [p for p in lang.particles if p not in particles_in_dict]
        if missing and particles_in_dict:
            out.append(Issue(None, "情詞", f"規則ファイルの情詞のうち、辞書に「情詞」として載っていないもの: "
                                           f"{'、'.join(missing)}", NOTICE))
    return out
