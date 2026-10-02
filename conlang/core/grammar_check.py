"""文法文書と規則ファイルの食い違いの検査。言語に依存しない部分(仕様書 4.7)

prototype/check_rules_docs.py の run を、言語ごとの「表の比べ方」を受け取る形にしたもの。
- 目印(<!-- rule: ID -->)と ref の対応(rule_docs.check_links)
- 表になっているもの: 言語が渡す TABLE_CHECKS(目印の ID → 比べ方)で比べる。表の正は規則ファイル
- 文章で書かれた目印: 文書の該当箇所と ref が指す規則を組にして LLM に渡し、矛盾の候補を挙げさせる。
  LLM の答えは候補にすぎず、「問題なし」を保証しない
言語ごとの表の比べ方は、registry の grammar_table_checks に置く(ピュテ語は pute/grammar_check.py)。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from . import llm, llm_log
from . import rule_docs as RD
from .rules import Rules

TableChecks = dict[str, Callable[[list[str], Rules], list[str]]]
PURPOSE = "grammar-check"


# ---------- 表の読み取り(比べ方を書くときに使う) ----------

def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(block: list[str]) -> list[list[str]]:
    """表の行(見出し行と区切りの行を除く)"""
    rows = [cells(l) for l in block if l.strip().startswith("|")]
    rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r if c)]
    return rows[1:]


def diff_maps(label: str, md: dict, yml: dict) -> list[str]:
    """キー → 値 の辞書どうしを比べる"""
    out = []
    for k in sorted(set(md) | set(yml), key=str):
        a, b = md.get(k), yml.get(k)
        if a is None:
            out.append(f"{label} {k}: 規則ファイルにだけある({b})")
        elif b is None:
            out.append(f"{label} {k}: 文法 md にだけある({a})")
        elif a != b:
            out.append(f"{label} {k}: 文法 md は {a!r}、規則ファイルは {b!r}")
    return out


def diff_sets(label: str, md: set, yml: set) -> list[str]:
    out = []
    if md - yml:
        out.append(f"{label}: 文法 md にだけある {sorted(md - yml)}")
    if yml - md:
        out.append(f"{label}: 規則ファイルにだけある {sorted(yml - md)}")
    return out


# ---------- 照合 ----------

@dataclass
class Report:
    problems: list[str]        # 食い違い(目印と ref の対応、表の中身)
    prose_anchors: list[str]   # 文章の記述なので、LLM に調べさせる目印
    anchors: int
    refs: int


def run(grammar_text: str, rules: Rules, table_checks: TableChecks) -> Report:
    anchors = RD.read_anchors(grammar_text)
    refs = RD.collect_refs(rules.data)
    problems = RD.check_links(anchors, refs)
    for a, fn in table_checks.items():
        if a in anchors:
            try:
                problems += [f"[{a}] {p}" for p in fn(anchors[a], rules)]
            except (KeyError, TypeError, AttributeError, ValueError) as e:
                problems.append(f"[{a}] 表を比べられなかった(表か規則ファイルの形が想定と違う): {type(e).__name__}: {e}")
    prose = sorted(a for a in anchors if a not in table_checks)  # 文書の中の順に左右されないように
    return Report(problems, prose, len(anchors), len(refs))


def llm_pairs(grammar_text: str, rules: Rules, table_checks: TableChecks) -> list[RD.Pair]:
    rep = run(grammar_text, rules, table_checks)
    return RD.pairs(RD.read_anchors(grammar_text), RD.collect_refs(rules.data), rules, set(rep.prose_anchors))


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


# ---------- CLI と画面から使う手順 ----------

USAGE = """\
grammar-check [--grammar FILE] [--prompt-only | --llm | --response FILE] [--force]
  文法文書の目印と規則ファイルの ref の対応、表(音素、接辞、語尾など)の食い違いをコードで調べる。
  --prompt-only   文章の記述を LLM に調べさせるためのプロンプトを出す(好きなチャットに貼る)
  --llm           LLM の API を呼ぶ(接続先は conlang llm config で設定する)
  --response FILE 別のチャットの答えを読み込む
  --force         文法文書と規則ファイルが前回から変わっていなくても、LLM に調べさせる
"""


def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def run_cli(argv: list[str], ctx, table_checks: TableChecks) -> int:
    """結果を print する。ctx は registry.Context(rules と project を使う)"""
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    r = ctx.rules
    if r is None:
        print("規則ファイルがない。--project か --rules で指定する")
        return 2
    gpath = _opt(argv, "--grammar")
    path = Path(gpath) if gpath else (ctx.project.grammar_path(r) if ctx.project else None)
    if path is None or not path.exists():
        print("文法文書が見つからない。--grammar FILE で指定するか、conlang grammar import で取り込む")
        return 2
    grammar = path.read_text(encoding="utf-8-sig")
    rules_text = r.path.read_text(encoding="utf-8-sig") if r.path else repr(r.data)

    rep = run(grammar, r, table_checks)
    diffs = rep.problems
    print(f"{path} と {r.path or '規則'} の照合(目印 {rep.anchors}個、ref {rep.refs}個。表の正は規則ファイル):")
    if diffs:
        for d in diffs:
            print(f"  ! {d}")
    else:
        print("  食い違いはない")
    if rep.prose_anchors:
        print("  文章の記述なので LLM に調べさせる目印: " + "、".join(rep.prose_anchors))
    print()

    pairs = llm_pairs(grammar, r, table_checks)
    prompt = build_llm_prompt(pairs)
    if "--prompt-only" in argv:
        print(prompt)
        return 1 if diffs else 0
    resp = _opt(argv, "--response")
    if "--llm" not in argv and resp is None:
        print("文章の記述の検査は、--prompt-only / --llm / --response で LLM に調べさせる")
        return 1 if diffs else 0

    log_dir = ctx.project.llm_log_dir if ctx.project else None
    inputs = {"grammar": grammar, "rules": rules_text}
    if resp is None and log_dir and "--force" not in argv and not llm_log.inputs_changed(log_dir, PURPOSE, inputs):
        print("文法文書と規則ファイルは、前回 LLM に調べさせたときから変わっていない。もう一度調べるときは --force")
        return 1 if diffs else 0
    model = "(貼り付けた答え)"
    if resp:
        answer = Path(resp).read_text(encoding="utf-8-sig")
    else:
        cfg = llm.load_config()
        model = f"{cfg.model} @ {cfg.url}"
        print(f"LLM に問い合わせている: {model}(目印 {len(pairs)}個)")
        try:
            answer = llm.chat(prompt, cfg, json_mode=True)
        except llm.LLMError as e:
            print(f"エラー: {e}")
            return 1
    if log_dir:
        saved = llm_log.save_call(log_dir, PURPOSE, prompt, answer, model=model,
                                  grammar=str(path), rules=str(r.path or ""))
        print(f"(履歴: {saved})")
    try:
        cands = parse_llm_answer(answer)
    except ValueError as e:
        print(f"LLM の答えを読めなかった: {e}\n--- 答え ---\n{answer}")
        return 1
    if log_dir:
        llm_log.remember_inputs(log_dir, PURPOSE, inputs)
    print(format_candidates(cands))
    return 1 if diffs or cands else 0


def run_llm(ctx, table_checks: TableChecks, force: bool) -> int:
    """画面の「文章の記述を LLM で調べる」から使う"""
    return run_cli(["--llm"] + (["--force"] if force else []), ctx, table_checks)
