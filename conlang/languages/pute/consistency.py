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
from .lang import PuteLang

ETYMOLOGY_TITLE = "語源"
# 構成の行: 小文字の綴りをハイフンでつないだもの(文章の説明は対象にしない)
STRUCTURE = re.compile(r"^[a-z]+(-[a-z]+)+$")


def etymology_structure(w: dict) -> list[str] | None:
    """語源欄の1行目が構成(a-b-c)なら、部品の一覧。文章の説明や語源欄がなければ None"""
    for c in w.get("contents", []):
        if c.get("title") == ETYMOLOGY_TITLE:
            line = c.get("text", "").split("\n", 1)[0].strip()
            if STRUCTURE.match(line):
                return line.split("-")
    return None


class Checker:
    def __init__(self, d: Dictionary, rules: Rules | None):
        self.d = d
        self.lang = PuteLang.from_rules(rules)
        lex = set()
        for w in d.words:
            if form(w):
                lex.add(form(w))
            lex |= {v.get("form", "") for v in w.get("variations", []) if v.get("form")}
        lex |= set(self.lang.stem_affixes)
        # 動詞化の su- などは、複合語の部品の中にも現れる(suschwoa = su + schwoa)
        lex |= set(self.lang.anywhere)
        self.lexicon = lex

    def check_form(self, wid, f: str, what: str) -> list[Issue]:
        out = []
        n = self.lang.parse_count(f)
        if n == 0:
            out.append(Issue(wid, "音素", f"{what} {f} が音素に分けられない", ERROR))
        elif n > 1:
            out.append(Issue(wid, "音素", f"{what} {f} の音素への分け方が{n}通りある", ERROR))
        for bad, provisional in self.lang.phonotactic_problems(f):
            if provisional:
                out.append(Issue(wid, "音韻規則", f"{what} {f} に「{bad}」がある【仮】", NOTICE))
            else:
                out.append(Issue(wid, "音韻規則", f"{what} {f} に、語の中に現れない並び「{bad}」がある", ERROR))
        return out

    def check_etymology(self, w: dict) -> list[Issue]:
        wid, head = w["entry"].get("id"), form(w)
        segs = etymology_structure(w)
        if segs is None:
            return []
        out = []
        line = "-".join(segs)
        joined, _ = self.lang.join(segs)
        if joined != head:
            out.append(Issue(wid, "語源と見出し語",
                             f"{head}: 語源欄の構成 {line} をつなぐと {joined} になり、見出し語と合わない", ERROR))
        for i, s in enumerate(segs):
            if self.lang.is_boundary_affix(segs, i) or P.readable_as(s, self.lexicon):
                continue
            why = "音素に分けられない" if self.lang.parse_count(s) == 0 else "辞書の語や接辞の連なりとして読めない"
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
