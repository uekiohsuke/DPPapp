"""ミャミュ語の辞書の検査(規則ファイルの checks にあるものだけ)

- phoneme_segmentation: 見出し語が音素(sh・mj は1つの子音)に分けられるか
- forbidden_cluster: 存在しない並び(fb など)を含まないか(誤り)
- same_consonant_merge: 同じ子音が続いていないか(1つになるはず)
辞書の語は活用などを当てた形ではないはずなので、音の連なりの規則に合わない綴りは「誤り」にする。
"""
from __future__ import annotations

import re

from conlang.core.rules import Rules, RulesError
from conlang.core.validate import ERROR, NOTICE, Issue
from conlang.core.zpdic import Dictionary, form

from .lang import MyamyuLang

SPLIT = re.compile(r"[\s\-]+")


def check_dictionary(d: Dictionary, rules: Rules | None) -> list[Issue]:
    try:
        lang = MyamyuLang.from_rules(rules)
    except RulesError:
        return []  # 規則ファイルがなければ、言語別の検査はしない
    out = []
    for w in d.words:
        wid, f = w["entry"].get("id"), form(w)
        for part in (p for p in SPLIT.split(f.lower()) if p):
            seq = lang.segment(part)
            if seq is None:
                if lang.enabled("phoneme_segmentation"):
                    out.append(Issue(wid, "音素", f"{f}: {part} がミャミュ語の音素に分けられない", ERROR))
                continue
            if lang.enabled("forbidden_cluster"):
                for c in lang.clusters(seq):
                    fixed, _ = lang.apply_phonotactics(part)
                    out.append(Issue(wid, "音の連なり", f"{f}: 存在しない並び {c} がある(規則どおりなら {fixed})", ERROR))
            if lang.enabled("same_consonant_merge"):
                for c in lang.same_runs(seq):
                    out.append(Issue(wid, "音の連なり", f"{f}: 同じ子音 {c} が続いている(1つになる)", NOTICE))
    return out
