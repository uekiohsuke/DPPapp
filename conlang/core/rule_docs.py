"""文法文書(Markdown)と規則ファイル(YAML)の対応づけ。言語に依存しない(仕様書 4.7)

対応づけは、節の番号ではなく目印(アンカー)の ID で行う。章立てや節の番号が変わっても壊れない。
- 文法文書: 規則に対応する表や箇条書きの直前の行に <!-- rule: ID --> と書く。
  範囲は、その直後から、最初の空行か見出し(か次の目印)まで
- 規則ファイル: 規則のブロックに ref キーを置く。値は目印の ID(文字列)か、{ブロック内のキー: ID}
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .rules import Rules

ANCHOR = re.compile(r"^<!--\s*rule:\s*([\w.\-]+)\s*-->\s*$")


@dataclass(frozen=True)
class Ref:
    path: str     # 規則ファイルのキーの道筋(例: inflection.tense.noun)
    anchor: str   # 目印の ID


def read_anchors(md_text: str) -> dict[str, list[str]]:
    """目印ごとに、直後の連続する行を切り出す"""
    lines = md_text.splitlines()
    out: dict[str, list[str]] = {}
    for i, line in enumerate(lines):
        m = ANCHOR.match(line.strip())
        if not m:
            continue
        block = []
        j = i + 1
        while j < len(lines) and lines[j].strip() and not lines[j].startswith("#") and not ANCHOR.match(lines[j].strip()):
            block.append(lines[j])
            j += 1
        out[m.group(1)] = block
    return out


def collect_refs(node, path: str = "") -> list[Ref]:
    """規則ファイルの中の ref キーを、出てくる順に集める"""
    refs: list[Ref] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "ref":
                if isinstance(v, str):
                    refs.append(Ref(path, v))
                elif isinstance(v, dict):
                    refs += [Ref(f"{path}.{sub}" if path else str(sub), str(a)) for sub, a in v.items()]
            else:
                refs += collect_refs(v, f"{path}.{k}" if path else str(k))
    return refs


def check_links(anchors: dict[str, list[str]], refs: list[Ref]) -> list[str]:
    """ref が指す目印が文書にあるか、文書の目印に対応する規則があるか"""
    out = []
    ids = {r.anchor for r in refs}
    for r in refs:
        if r.anchor not in anchors:
            out.append(f"規則ファイルの {r.path} の ref「{r.anchor}」が、文法文書に見つからない")
    for a in sorted(anchors):  # 文書の中の順(章立て)に左右されないように
        if a not in ids:
            out.append(f"文法文書の目印「{a}」に対応する規則が、規則ファイルにない")
    return out


def rule_at(rules: Rules, path: str):
    """キーの道筋(inflection.tense.noun)の値。ドットを含むキーにも対応する"""
    node = rules.data
    parts = path.split(".")
    i = 0
    while i < len(parts):
        if not isinstance(node, dict):
            return None
        for j in range(len(parts), i, -1):  # 長いキー(ドットを含む)を先に試す
            key = ".".join(parts[i:j])
            if key in node:
                node, i = node[key], j
                break
        else:
            return None
    return node


@dataclass
class Pair:
    """LLM に渡す組: 文書の該当箇所と、目印を指す規則"""
    anchor: str
    text: list[str]
    rules: dict  # {規則のキーの道筋: 値}


def pairs(anchors: dict[str, list[str]], refs: list[Ref], rules: Rules, only: set[str] | None = None) -> list[Pair]:
    out = []
    for a, block in anchors.items():
        if only is not None and a not in only:
            continue
        rs = {r.path: rule_at(rules, r.path) for r in refs if r.anchor == a}
        if rs:
            out.append(Pair(a, block, rs))
    return out
