"""文法 md と規則ファイルの食い違いの検査(仕様書 4.7)

prototype/check_rules_docs.py を取り込んだもの。対応づけは、目印(<!-- rule: ID -->)と ref で行う
(conlang.core.rule_docs)。節の番号は使わないので、章立てが変わっても検査は壊れない。

- 表になっているもの(音素、接辞の一覧、活用の語尾)は、コードで比べる(check_tables)。表の正は規則ファイル
- 文章で書かれた目印は、文書の該当箇所と ref が指す規則を組にして LLM に渡し、矛盾の候補を挙げさせる
  (build_llm_prompt / parse_llm_answer)。LLM の答えは候補にすぎず、「問題なし」を保証しない
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml

from conlang.core import rule_docs as RD
from conlang.core.rules import Rules


# ---------- 表の読み取り ----------

def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(block: list[str]) -> list[list[str]]:
    """表の行(見出し行と区切りの行を除く)"""
    rows = [_cells(l) for l in block if l.strip().startswith("|")]
    rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r if c)]
    return rows[1:]


def _ending(cell: str) -> str:
    cell = cell.strip()
    return "" if cell in ("語幹のまま", "", "-") else cell.lstrip("-")


def _diff_sets(label: str, md: set, yml: set) -> list[str]:
    out = []
    if md - yml:
        out.append(f"{label}: 文法 md にだけある {sorted(md - yml)}")
    if yml - md:
        out.append(f"{label}: 規則ファイルにだけある {sorted(yml - md)}")
    return out


# ---------- 表ごとの比べ方。(目印の範囲, 規則) → 食い違いの文 ----------

def cmp_vowels(block, r: Rules):
    header = next((l for l in block if l.strip().startswith("|")), None)
    md = set(_cells(header)[1:]) if header else set()
    return _diff_sets("母音", md, set(r.get("phonology", "vowels", default=[]) or []))


def cmp_consonants(block, r: Rules):
    md = {}
    for row in table_rows(block):
        if len(row) >= 2:
            md[re.sub(r"音$", "", row[0])] = set(re.findall(r"([a-z]+)\s*\[", row[1]))
    yml = {str(k): set(v or []) for k, v in (r.get("phonology", "consonants", default={}) or {}).items()}
    out = []
    for k in sorted(set(md) | set(yml)):
        out += _diff_sets(f"子音 {k} 音", md.get(k, set()), yml.get(k, set()))
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
TABLE_CHECKS = {
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


@dataclass
class Report:
    problems: list[str]        # 食い違い(目印と ref の対応、表の中身)
    prose_anchors: list[str]   # 文章の記述なので、LLM に調べさせる目印
    anchors: int
    refs: int


def run(grammar_text: str, rules: Rules) -> Report:
    anchors = RD.read_anchors(grammar_text)
    refs = RD.collect_refs(rules.data)
    problems = RD.check_links(anchors, refs)
    for a, fn in TABLE_CHECKS.items():
        if a in anchors:
            problems += [f"[{a}] {p}" for p in fn(anchors[a], rules)]
    prose = sorted(a for a in anchors if a not in TABLE_CHECKS)  # 文書の中の順に左右されないように
    return Report(problems, prose, len(anchors), len(refs))


def check_tables(grammar_text: str, rules: Rules) -> list[str]:
    """registry の check_grammar。食い違いを文で返す(空なら一致)"""
    return run(grammar_text, rules).problems


# ---------- LLM による検査(文章の記述) ----------

LLM_INSTRUCTIONS = """\
あなたは人工言語の文法文書を点検する。下に、文法文書(人が読むための説明)の一部と、
それに対応する規則ファイル(コードが処理するデータ、YAML)の一部を、目印ごとに組にして示す。
各組について、文章の記述が規則ファイルの内容と矛盾していないかを調べる。

守ること:
- 矛盾の「候補」を挙げる。確信がないものは confidence を低くする。直すかどうかは本人が決める
- 文法文書の【決定】【仮】【メモ】と、規則ファイルの status(決定・仮・メモ・未確認)の食い違いも挙げてよい
- 言い回しの違いだけで、内容が同じものは挙げない
- 見つからなければ candidates を空にする

次の JSON だけを出力する(説明文やコードフェンスは付けない)。
{
  "candidates": [
    {
      "anchor": "目印の ID(下の【目印: …】の …)",
      "grammar_quote": "文法文書の該当箇所(短く引用)",
      "rule": "規則ファイルの該当箇所(例: compounding.vowel_merge)",
      "problem": "何が食い違っているか(1〜2文)",
      "suggestion": "どちらをどう直すとよいかの案(1文)",
      "confidence": "高 / 中 / 低"
    }
  ]
}
"""


def llm_pairs(grammar_text: str, rules: Rules) -> list[RD.Pair]:
    rep = run(grammar_text, rules)
    return RD.pairs(RD.read_anchors(grammar_text), RD.collect_refs(rules.data), rules, set(rep.prose_anchors))


def build_llm_prompt(pairs: list[RD.Pair]) -> str:
    out = [LLM_INSTRUCTIONS]
    for p in pairs:
        out.append(f"【目印: {p.anchor}】")
        out.append("文法文書:")
        out += [f"  {l}" for l in p.text]
        out.append("規則ファイル:")
        dumped = yaml.safe_dump(p.rules, allow_unicode=True, sort_keys=False, default_flow_style=False)
        out += [f"  {l}" for l in dumped.rstrip().splitlines()]
        out.append("")
    return "\n".join(out)


@dataclass
class Candidate:
    anchor: str
    grammar_quote: str
    rule: str
    problem: str
    suggestion: str
    confidence: str


FIELDS = ("anchor", "grammar_quote", "rule", "problem", "suggestion", "confidence")


def extract_json(text: str) -> dict:
    """LLM の答えから JSON を取り出す(<think> の部分とコードフェンスは除く)。読めなければ ValueError"""
    s = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("JSON が見つからない")
    try:
        return json.loads(s[i:j + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON として読めない: {e}") from e


def parse_llm_answer(text: str) -> list[Candidate]:
    data = extract_json(text)
    out = []
    for c in data.get("candidates", []) or []:
        if isinstance(c, dict):
            if "anchor" not in c and "section" in c:  # 古い形の答え
                c = {**c, "anchor": c["section"]}
            out.append(Candidate(*(str(c.get(k, "") or "") for k in FIELDS)))
    return out


def format_candidates(cands: list[Candidate]) -> str:
    if not cands:
        return "LLM は食い違いの候補を挙げなかった(見落としがありうるので、問題がないことの保証ではない)"
    lines = [f"LLM が挙げた食い違いの候補({len(cands)}件。直すかどうかは本人が決める):"]
    for i, c in enumerate(cands, 1):
        lines.append(f"  {i}. [確信度 {c.confidence or '?'}] 目印 {c.anchor} ⇔ 規則 {c.rule}")
        if c.grammar_quote:
            lines.append(f"     文法: 「{c.grammar_quote}」")
        lines.append(f"     食い違い: {c.problem}")
        if c.suggestion:
            lines.append(f"     案: {c.suggestion}")
    return "\n".join(lines)
