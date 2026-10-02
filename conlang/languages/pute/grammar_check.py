"""ピュテ語の、文法 md と規則ファイルの表の比べ方(prototype/check_rules_docs.py の PUTE_CHECKS)

照合の進め方(目印と ref、LLM に渡す組など)は言語に依存しないので conlang.core.grammar_check にある。
ここには、目印の ID ごとの表の比べ方だけを置く。
"""
from __future__ import annotations

import re

from conlang.core import grammar_check as GC
from conlang.core.grammar_check import (  # noqa: F401  (これまでの呼び出し口)
    Candidate, Report, build_llm_prompt, extract_json, format_candidates, parse_llm_answer, table_rows,
)
from conlang.core.rules import Rules


def _ending(cell: str) -> str:
    cell = cell.strip()
    return "" if cell in ("語幹のまま", "", "-") else cell.lstrip("-")


def cmp_vowels(block, r: Rules):
    header = next((l for l in block if l.strip().startswith("|")), None)
    md = set(GC.cells(header)[1:]) if header else set()
    return GC.diff_sets("母音", md, set(r.get("phonology", "vowels", default=[]) or []))


def cmp_consonants(block, r: Rules):
    md = {}
    for row in table_rows(block):
        if len(row) >= 2:
            md[re.sub(r"音$", "", row[0])] = set(re.findall(r"([a-z]+)\s*\[", row[1]))
    yml = {str(k): set(v or []) for k, v in (r.get("phonology", "consonants", default={}) or {}).items()}
    out = []
    for k in sorted(set(md) | set(yml)):
        out += GC.diff_sets(f"子音 {k} 音", md.get(k, set()), yml.get(k, set()))
    return out


def _cmp_forms(block, forms: dict, form_cell: int, name_cell: int):
    """接辞の表。規則ファイルは {綴り: 名前}。文法 md の名前は、規則の名前で始まっていればよい(「被動詞化。〜」など)"""
    md = {}
    for row in table_rows(block):
        if len(row) > max(form_cell, name_cell):
            md[row[form_cell].strip("-")] = row[name_cell]
    forms = {str(k): str(v) for k, v in (forms or {}).items()}
    out = []
    for k in sorted(set(md) | set(forms)):
        a, b = md.get(k), forms.get(k)
        if a is None:
            out.append(f"{k}: 規則ファイルにだけある({b})")
        elif b is None:
            out.append(f"{k}: 文法 md にだけある({a})")
        elif not a.startswith(b):
            out.append(f"{k}: 文法 md は「{a}」、規則ファイルは「{b}」")
    return out


def _affix(category: str, form_cell: int, name_cell: int):
    def cmp(block, r: Rules):
        return _cmp_forms(block, r.get("affixes", category, "forms", default={}), form_cell, name_cell)
    return cmp


def _inflection(kind: str, cls: str):
    def cmp(block, r: Rules):
        yml = {k: str(v or "") for k, v in (r.get("inflection", kind, cls, default={}) or {}).items()}
        md = {}
        for row in table_rows(block):
            if len(row) >= 2:
                name = re.sub(r"(状態)?形$", "", row[0]) if kind == "state" else row[0]
                md[name] = _ending(row[1])
        label = "状態形" if kind == "state" else "時制"
        return [f"{cls} の{label} {k}: 文法 md は {md.get(k)!r}、規則ファイルは {yml.get(k)!r}"
                for k in sorted(set(md) | set(yml), key=lambda x: (list(md) + list(yml)).index(x)) if md.get(k) != yml.get(k)]
    return cmp


# 目印の ID → 比べ方。ここにない目印は、文章の記述として LLM に調べさせる
TABLE_CHECKS: GC.TableChecks = {
    "phonology.vowels": cmp_vowels,
    "phonology.consonants": cmp_consonants,
    "affixes.case_prefix": _affix("case_prefix", 1, 0),
    "affixes.verbalizer": _affix("verbalizer", 0, 1),
    "affixes.plural": _affix("plural", 1, 0),
    "affixes.modifier_kind": _affix("modifier_kind", 1, 0),
    "inflection.noun.tense": _inflection("tense", "noun"),
    "inflection.noun.state": _inflection("state", "noun"),
    "inflection.verb.tense": _inflection("tense", "verb"),
    "inflection.verb.state": _inflection("state", "verb"),
}


# --- これまでの呼び出し口(ピュテ語の表の比べ方を使う) ---

def run(grammar_text: str, rules: Rules) -> GC.Report:
    return GC.run(grammar_text, rules, TABLE_CHECKS)


def check_tables(grammar_text: str, rules: Rules) -> list[str]:
    return run(grammar_text, rules).problems


def llm_pairs(grammar_text: str, rules: Rules):
    return GC.llm_pairs(grammar_text, rules, TABLE_CHECKS)
