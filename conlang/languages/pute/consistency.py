"""ピュテ語の辞書の整合性チェック(仕様書 4.3)

- 見出し語・短縮形が音素に分けられるか、分け方が1通りか
- 語の中に現れない並び(aa など)を含まないか
- 語源欄の構成をつないだ綴りが、見出し語と一致するか(誤記の検出)。
  複合語の部品の境目では同じ母音をまとめ、ハイフンで区切る接辞(格接頭辞、su-・ksa-、活用語尾)の境目ではまとめない
- 語源欄の部品が、辞書の語(見出し語・短縮形)と語幹の中の接辞の連なりとして読めるか
"""
from __future__ import annotations

import re

from conlang.core.rules import Rules
from conlang.core.validate import ERROR, NOTICE, Issue
from conlang.core.zpdic import Dictionary, form

from . import phonology as P
from . import rules as PR

ETYMOLOGY_TITLE = "語源"
# 構成の行: 小文字の綴りをハイフンでつないだもの(文章の説明は対象にしない)
STRUCTURE = re.compile(r"^[a-z]+(-[a-z]+)+$")
# ハイフンで区切る接辞(独立した音節。母音をまとめない)。規則ファイルの compounding.affix_boundary.applies_to が優先
DEFAULT_BOUNDARY_AFFIXES = ("case_prefix", "verbalizer", "inflection")
# 語幹の中に入る接辞(ハイフンなし)。語源欄の部品の中に現れてよい
STEM_AFFIXES = ("verbalizer", "nominalizer", "plural", "modifier_kind")


def _default_rules() -> Rules:
    """規則ファイルがないときは、造語支援の初期値(試作の値)を使う"""
    from . import zougo
    d = zougo._DEFAULTS
    return Rules({"phonology": {"vowels": list(d["VOWELS"]), "consonants": {"all": list(d["CONSONANTS"])}},
                  "phonotactics": {"forbidden_substrings": list(d["FORBIDDEN"]),
                                   "forbidden_substrings_provisional": list(d["FORBIDDEN_PROVISIONAL"])}})


def affix_forms(r: Rules, category: str) -> set[str]:
    spec = r.get("affixes", category, default={}) or {}
    return {str(f) for f in (spec.get("forms") or {})} if isinstance(spec, dict) else set()


def inflection_endings(r: Rules) -> set[str]:
    out = set()
    if not r.get("inflection"):
        return out
    for wc in PR.WORD_CLASSES:
        try:
            out |= {f.ending for f in PR.inflection_table(r, wc) if f.ending}
        except Exception:
            continue
    return out


class Checker:
    def __init__(self, d: Dictionary, rules: Rules | None):
        self.d = d
        self.r = rules if rules is not None and PR.vowels(rules) else _default_rules()
        self.vowels = PR.vowels(self.r)
        self.phonemes = PR.phonemes(self.r)
        pt = self.r.get("phonotactics", default={}) or {}
        self.forbidden = [str(x) for x in pt.get("forbidden_substrings", []) or []]
        self.forbidden_prov = [str(x) for x in pt.get("forbidden_substrings_provisional", []) or []]
        boundary = self.r.get("compounding", "affix_boundary", "applies_to", default=None) or DEFAULT_BOUNDARY_AFFIXES
        self.prefixes = set()   # 語頭の、ハイフンで区切る接辞
        self.suffixes = set()   # 語末の、ハイフンで区切る接辞
        self.anywhere = set()   # どこに出てもハイフンで区切る接辞(動詞化など)
        for cat in boundary:
            if cat == "inflection":
                self.suffixes |= inflection_endings(self.r)
            elif cat == "case_prefix":
                self.prefixes |= affix_forms(self.r, cat)
            else:
                self.anywhere |= affix_forms(self.r, cat)
        lex = set()
        for w in d.words:
            if form(w):
                lex.add(form(w))
            lex |= {v.get("form", "") for v in w.get("variations", []) if v.get("form")}
        for cat in STEM_AFFIXES:
            lex |= affix_forms(self.r, cat)
        self.lexicon = lex

    # --- 1語ずつ ---

    def check_form(self, wid, f: str, what: str) -> list[Issue]:
        out = []
        n = P.parse_count(f, self.phonemes)
        if n == 0:
            out.append(Issue(wid, "音素", f"{what} {f} が音素に分けられない", ERROR))
        elif n > 1:
            out.append(Issue(wid, "音素", f"{what} {f} の音素への分け方が{n}通りある", ERROR))
        for bad in self.forbidden:
            if bad in f:
                out.append(Issue(wid, "音韻規則", f"{what} {f} に、語の中に現れない並び「{bad}」がある", ERROR))
        for bad in self.forbidden_prov:
            if bad in f:
                out.append(Issue(wid, "音韻規則", f"{what} {f} に「{bad}」がある【仮】", NOTICE))
        return out

    def merge_flags(self, segs: list[str]) -> list[bool]:
        flags = []
        last = len(segs) - 1
        for i in range(last):
            a, b = segs[i], segs[i + 1]
            affix = ((i == 0 and a in self.prefixes) or (i + 1 == last and b in self.suffixes)
                     or a in self.anywhere or b in self.anywhere)
            flags.append(not affix)
        return flags

    def is_affix(self, segs: list[str], i: int) -> bool:
        s = segs[i]
        return (i == 0 and s in self.prefixes) or (i == len(segs) - 1 and s in self.suffixes) or s in self.anywhere

    def check_etymology(self, w: dict) -> list[Issue]:
        wid, head = w["entry"].get("id"), form(w)
        out = []
        for c in w.get("contents", []):
            if c.get("title") != ETYMOLOGY_TITLE:
                continue
            line = c.get("text", "").split("\n", 1)[0].strip()
            if not STRUCTURE.match(line):
                continue  # 文章の説明
            segs = line.split("-")
            joined = P.join(segs, self.merge_flags(segs), self.vowels, self.phonemes)
            if joined != head:
                out.append(Issue(wid, "語源と見出し語",
                                 f"{head}: 語源欄の構成 {line} をつなぐと {joined} になり、見出し語と合わない", ERROR))
            for i, s in enumerate(segs):
                if self.is_affix(segs, i) or P.readable_as(s, self.lexicon):
                    continue
                why = "音素に分けられない" if P.parse_count(s, self.phonemes) == 0 else "辞書の語や接辞の連なりとして読めない"
                out.append(Issue(wid, "語源の部品", f"{head}: 語源欄の部品 {s} が{why}", ERROR))
        return out

    def run(self) -> list[Issue]:
        out = []
        for w in self.d.words:
            wid, f = w["entry"].get("id"), form(w)
            if f:
                out += self.check_form(wid, f, "見出し語")
            for v in w.get("variations", []):
                if v.get("form"):
                    out += self.check_form(wid, v["form"], f"{f} の変化形「{v.get('title', '')}」")
            if f:
                out += self.check_etymology(w)
        return out


def check_dictionary(d: Dictionary, rules: Rules | None) -> list[Issue]:
    return Checker(d, rules).run()
