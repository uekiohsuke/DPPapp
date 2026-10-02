"""文法 md と規則ファイルの食い違いの検査(仕様書 4.7)

- 表になっているもの(音素、接辞の一覧、語尾の表、活用の展開表)は、コードで比べる(check_tables)。
  表の正は規則ファイル。食い違いは「文法 md を直す候補」として出す
- 文章で書かれた記述と規則ファイルの矛盾は、LLM に候補を挙げさせる(build_llm_prompt / parse_llm_answer)。
  LLM の答えは候補にすぎず、「問題なし」を保証しない

文法 md の節番号(1.1、5 など)は、二期ピュテ語の文法 md(pute2-grammar.md)の章立てに合わせている。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from conlang.core.rules import Rules

from . import rules as PR

HEADING = re.compile(r"^(#{1,6})\s+(\S+)")


# ---------- 文法 md の読み取り ----------

def section(text: str, number: str) -> str | None:
    """節番号(例: "1.1"、"5")の本文。次の同じか上の階層の見出しまで"""
    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        if start is None:
            if m.group(2).rstrip(".") == number:
                start, level = i + 1, len(m.group(1))
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    return None if start is None else "\n".join(lines[start:])


def heading_line(text: str, number: str) -> str | None:
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and m.group(2).rstrip(".") == number:
            return line
    return None


def tables(body: str) -> list[list[list[str]]]:
    """本文の Markdown の表を、行ごとのセルの一覧にする(区切りの行は除く)"""
    out, cur = [], []
    for line in body.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                cur.append(cells)
        elif cur:
            out.append(cur)
            cur = []
    return out


def _form(cell: str) -> str:
    """「-at」「su-」「語幹のまま」「s [s]」などから綴りだけを取り出す"""
    cell = cell.strip()
    if cell in ("語幹のまま", "", "-"):
        return ""
    cell = re.split(r"[\s\[(]", cell, 1)[0]
    return cell.strip("-")


def _state_name(cell: str) -> str:
    """「高状態形」「一般形」→「高」「一般」(規則ファイルの名前に合わせる)"""
    return re.sub(r"(状態)?形$", "", cell.strip())


# ---------- 表の照合 ----------

@dataclass
class _Ctx:
    text: str
    rules: Rules
    out: list

    def body(self, number: str, what: str) -> str | None:
        b = section(self.text, number)
        if b is None:
            self.out.append(f"文法 {number}({what}): 文法 md にこの節が見つからない")
        return b

    def compare(self, where: str, md: dict, rules: dict, label: str = "") -> None:
        for k in sorted(set(md) | set(rules), key=lambda x: (list(md) + list(rules)).index(x)):
            a, b = md.get(k), rules.get(k)
            if a == b:
                continue
            if a is None:
                self.out.append(f"{where}: {k} が規則ファイルにあるが、文法 md にない(規則ファイルは {b!r})")
            elif b is None:
                self.out.append(f"{where}: {k} が文法 md にあるが、規則ファイルにない(文法 md は {a!r})")
            else:
                self.out.append(f"{where}: {k}{label} が、文法 md は {a!r}、規則ファイルは {b!r}")


def _vowels(c: _Ctx) -> None:
    vs = PR.vowels(c.rules)
    if not vs:
        return
    body = c.body("1.1", "母音")
    if body is None:
        return
    ts = tables(body)
    md = ts[0][0][1:] if ts else []
    c.compare("文法 1.1(母音)", {v: "あり" for v in md}, {v: "あり" for v in vs})


def _consonants(c: _Ctx) -> None:
    groups = c.rules.get("phonology", "consonants", default={}) or {}
    if not isinstance(groups, dict) or not groups:
        return
    body = c.body("1.2", "子音")
    if body is None:
        return
    md = {}
    for t in tables(body):
        for row in t[1:]:
            if len(row) >= 2:
                key = re.sub(r"音$", "", row[0])
                md[key] = [_form(x) for x in re.split(r"[、,]", row[1]) if _form(x)]
    c.compare("文法 1.2(子音)", md, {str(k): list(v or []) for k, v in groups.items()}, " 系列の子音")


def _affix_table(c: _Ctx, number: str, what: str, category: str, form_col: int, meaning_col: int) -> None:
    """接辞の表。規則ファイルは {綴り: 意味}"""
    spec = c.rules.get("affixes", category, default=None)
    if not isinstance(spec, dict) or not spec.get("forms"):
        return
    body = c.body(number, what)
    if body is None:
        return
    md = {}
    for t in tables(body)[:1]:
        for row in t[1:]:
            if len(row) > max(form_col, meaning_col):
                md[_form(row[form_col])] = re.split(r"[。(]", row[meaning_col], 1)[0].strip()
    rules = {str(k): str(v) for k, v in spec["forms"].items()}
    c.compare(f"文法 {number}({what})", md, rules, " の意味")


def _nominalizer(c: _Ctx) -> None:
    spec = c.rules.get("affixes", "nominalizer", default=None)
    if not isinstance(spec, dict) or not spec.get("forms"):
        return
    line = heading_line(c.text, "2.3")
    if line is None:
        c.out.append("文法 2.3(名詞化の接尾辞): 文法 md にこの節が見つからない")
        return
    md = {m: "あり" for m in re.findall(r"-([a-z]+)", line)}
    c.compare("文法 2.3(名詞化の接尾辞、見出し)", md, {str(k): "あり" for k in spec["forms"]})


def _inflection(c: _Ctx, number: str, cls: str, name: str) -> None:
    tense = c.rules.get("inflection", "tense", cls, default=None)
    state = c.rules.get("inflection", "state", cls, default=None)
    if not isinstance(tense, dict) or not isinstance(state, dict):
        return
    body = c.body(number, f"{name}の活用")
    if body is None:
        return
    ts = tables(body)
    simple = [t for t in ts if t and len(t[0]) == 2]
    expansion = [t for t in ts if t and t[0][0] == "状態形"]
    if len(simple) >= 1:
        c.compare(f"文法 {number}({name}の時制などの語尾)",
                  {r[0]: _form(r[1]) for r in simple[0][1:]}, {k: str(v or "") for k, v in tense.items()})
    if len(simple) >= 2:
        c.compare(f"文法 {number}({name}の状態形の語尾)",
                  {_state_name(r[0]): _form(r[1]) for r in simple[1][1:]}, {k: str(v or "") for k, v in state.items()})
    if expansion:
        t = expansion[-1]
        header = t[0][1:]
        md = {}
        for row in t[1:]:
            for tn, cell in zip(header, row[1:]):
                md[f"{_state_name(row[0])}.{tn}"] = cell
        got = {f"{f.state}.{f.tense}": f.form for f in PR.inflection_table(c.rules, cls)}
        c.compare(f"文法 {number}({name}の展開表)", md, got, " の形")


def _adjective_adverb(c: _Ctx) -> None:
    classes = c.rules.get("inflection", "classes", default={}) or {}
    rules = {}
    for wc, label in (("adjective", "形容詞"), ("adverb", "副詞")):
        ov = (classes.get(wc) or {}).get("overrides", {}) if isinstance(classes.get(wc), dict) else {}
        if "一般.常態" in (ov or {}):
            rules[label] = str(ov["一般.常態"])
    if not rules:
        return
    body = c.body("8.3", "形容詞と副詞の活用")
    if body is None:
        return
    md = dict(re.findall(r"(形容詞|副詞)が\s*-([a-z]+)", body))
    c.compare("文法 8.3(一般形の常態)", md, rules, " の語尾")


def check_tables(grammar_text: str, rules: Rules) -> list[str]:
    """表の食い違いを文で返す(空なら一致)"""
    c = _Ctx(grammar_text, rules, [])
    _vowels(c)
    _consonants(c)
    _affix_table(c, "2.2", "動詞化・被動詞化の接頭辞", "verbalizer", 0, 1)
    _nominalizer(c)
    _affix_table(c, "3", "修飾種別", "modifier_kind", 1, 0)
    _affix_table(c, "4", "複数形", "plural", 1, 0)
    _affix_table(c, "5", "格", "case_prefix", 1, 0)
    _inflection(c, "8.1", "noun", "名詞")
    _inflection(c, "8.2", "verb", "動詞")
    _adjective_adverb(c)
    return c.out


# ---------- LLM による検査(文章の記述) ----------

LLM_INSTRUCTIONS = """\
あなたは人工言語の文法文書を点検する。下の「文法文書」(人が読むための説明)と「規則ファイル」(コードが処理するデータ、YAML)を読み、
文章で書かれた記述が規則ファイルの内容と矛盾している箇所を探す。

守ること:
- 表(音素、語尾の表、接辞の一覧)の食い違いは、別にコードで調べるので挙げなくてよい。文章の記述(「〜は〜に付く」「〜のときは〜する」など)を見る
- 矛盾の「候補」を挙げる。確信がないものは confidence を低くする。直すかどうかは本人が決める
- 文法文書の【仮】【メモ】と、規則ファイルの status(仮・メモ・未確認)の食い違いも挙げてよい
- 見つからなければ candidates を空にする

次の JSON だけを出力する(説明文やコードフェンスは付けない)。
{
  "candidates": [
    {
      "section": "文法文書の節番号(例: 2.5)",
      "grammar_quote": "文法文書の該当箇所(短く引用)",
      "rule": "規則ファイルの該当箇所(例: compounding.vowel_merge)",
      "problem": "何が食い違っているか(1〜2文)",
      "suggestion": "どちらをどう直すとよいかの案(1文)",
      "confidence": "高 / 中 / 低"
    }
  ]
}
"""


def build_llm_prompt(grammar_text: str, rules_text: str) -> str:
    return "\n".join([LLM_INSTRUCTIONS, "【規則ファイル】", rules_text.strip(), "", "【文法文書】", grammar_text.strip()])


@dataclass
class Candidate:
    section: str
    grammar_quote: str
    rule: str
    problem: str
    suggestion: str
    confidence: str


def parse_llm_answer(text: str) -> list[Candidate]:
    """LLM の答えから候補を取り出す。JSON が読めなければ ValueError"""
    s = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("JSON が見つからない")
    data = json.loads(s[i:j + 1])
    out = []
    for c in data.get("candidates", []) or []:
        if isinstance(c, dict):
            out.append(Candidate(*(str(c.get(k, "") or "") for k in
                                   ("section", "grammar_quote", "rule", "problem", "suggestion", "confidence"))))
    return out


def format_candidates(cands: list[Candidate]) -> str:
    if not cands:
        return "LLM は食い違いの候補を挙げなかった(見落としがありうるので、問題がないことの保証ではない)"
    lines = [f"LLM が挙げた食い違いの候補({len(cands)}件。直すかどうかは本人が決める):"]
    for i, c in enumerate(cands, 1):
        lines.append(f"  {i}. [確信度 {c.confidence or '?'}] 文法 {c.section} ⇔ 規則 {c.rule}")
        if c.grammar_quote:
            lines.append(f"     文法: 「{c.grammar_quote}」")
        lines.append(f"     食い違い: {c.problem}")
        if c.suggestion:
            lines.append(f"     案: {c.suggestion}")
    return "\n".join(lines)
