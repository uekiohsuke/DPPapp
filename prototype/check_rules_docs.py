#!/usr/bin/env python3
"""文法 md と規則ファイル(YAML)の食い違いを調べる(コードで調べられる部分)

対応づけは、節の番号ではなく、md の中の目印(<!-- rule: ID -->)と、YAML の ref キーで行う。
章立てや節の番号が変わっても、この検査は壊れない。

調べること:
  1. YAML の ref が指す目印が、md にあるか
  2. md の目印に対応する規則が、YAML にあるか
  3. 表になっているもの(音素、接辞、活用の語尾)が、YAML と一致するか
  4. 表で調べられない目印(文章の記述)の一覧。これは LLM に調べさせる対象

使い方:  python3 check_rules_docs.py [規則ファイル] [文法 md]
"""
import re
import sys

import yaml

ANCHOR = re.compile(r"^<!--\s*rule:\s*([\w.\-]+)\s*-->\s*$")


def read_anchors(md_text):
    """目印ごとに、直後の連続する行(空行か見出しで終わる)を切り出す"""
    lines = md_text.split("\n")
    out = {}
    for i, line in enumerate(lines):
        m = ANCHOR.match(line)
        if not m:
            continue
        j = i + 1
        block = []
        while j < len(lines) and lines[j].strip() and not lines[j].startswith("#") and not ANCHOR.match(lines[j]):
            block.append(lines[j])
            j += 1
        out[m.group(1)] = block
    return out


def collect_refs(node, path=""):
    """YAML の中の ref キーを集める。戻り値: [(YAML のキーの道筋, 目印の ID)]"""
    refs = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "ref":
                if isinstance(v, str):
                    refs.append((path, v))
                elif isinstance(v, dict):
                    refs += [(f"{path}.{sub}" if path else sub, a) for sub, a in v.items()]
            else:
                refs += collect_refs(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        pass
    return refs


def table_rows(block):
    rows = []
    for line in block:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else rows  # 先頭は見出し行


def get(node, dotted):
    for key in dotted.split("."):
        node = node[key]
    return node


# ---- 表ごとの比べ方。戻り値: 食い違いの文章のリスト ----

def cmp_vowels(block, rules):
    header = [c.strip() for c in block[0].strip().strip("|").split("|")][1:]
    return diff_sets("母音", set(header), set(rules["phonology"]["vowels"]))


def cmp_consonants(block, rules):
    md = {}
    for series, cell in table_rows(block):
        md[series.rstrip("音")] = set(re.findall(r"([a-z]+) \[", cell))
    yml = {k: set(v) for k, v in rules["phonology"]["consonants"].items()}
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_sets(f"子音 {k} 音", md.get(k, set()), yml.get(k, set()))
    return out


def cmp_forms(block, forms, strip_key="-", name_cell=0, key_cell=1, name_first=True):
    md = {}
    for cells in table_rows(block):
        name, key = (cells[name_cell], cells[key_cell]) if name_first else (cells[key_cell], cells[name_cell])
        md[key.strip(strip_key)] = name
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


def cmp_case(block, rules):
    return cmp_forms(block, rules["affixes"]["case_prefix"]["forms"], name_cell=0, key_cell=1)


def cmp_verbalizer(block, rules):
    return cmp_forms(block, rules["affixes"]["verbalizer"]["forms"], name_cell=1, key_cell=0)


def cmp_plural(block, rules):
    return cmp_forms(block, rules["affixes"]["plural"]["forms"], name_cell=0, key_cell=1)


def cmp_modifier(block, rules):
    return cmp_forms(block, rules["affixes"]["modifier_kind"]["forms"], name_cell=0, key_cell=1)


def make_infl(kind, base):
    def cmp(block, rules):
        yml = rules["inflection"][kind][base]
        md = {}
        for name, ending in table_rows(block):
            n = name.replace("状態形", "").replace("形", "") if kind == "state" else name
            md[n] = "" if ending == "語幹のまま" else ending.lstrip("-")
        out = []
        for k in sorted(set(md) | set(yml)):
            if md.get(k) != yml.get(k):
                out.append(f"{base} の{'状態形' if kind == 'state' else '時制'} {k}: 文法 md は {md.get(k)!r}、規則ファイルは {yml.get(k)!r}")
        return out
    return cmp


def diff_sets(label, md, yml):
    out = []
    if md - yml:
        out.append(f"{label}: 文法 md にだけある {sorted(md - yml)}")
    if yml - md:
        out.append(f"{label}: 規則ファイルにだけある {sorted(yml - md)}")
    return out


TABLE_CHECKS = {
    "phonology.vowels": cmp_vowels,
    "phonology.consonants": cmp_consonants,
    "affixes.case_prefix": cmp_case,
    "affixes.verbalizer": cmp_verbalizer,
    "affixes.plural": cmp_plural,
    "affixes.modifier_kind": cmp_modifier,
    "inflection.noun.tense": make_infl("tense", "noun"),
    "inflection.noun.state": make_infl("state", "noun"),
    "inflection.verb.tense": make_infl("tense", "verb"),
    "inflection.verb.state": make_infl("state", "verb"),
}


def run(rules_path, md_path):
    rules = yaml.safe_load(open(rules_path, encoding="utf-8"))
    anchors = read_anchors(open(md_path, encoding="utf-8").read())
    refs = collect_refs(rules)
    problems, notes = [], []

    ref_ids = {a for _, a in refs}
    for path, a in refs:
        if a not in anchors:
            problems.append(f"規則ファイルの {path} の ref「{a}」が、文法 md に見つからない")
    for a in anchors:
        if a not in ref_ids:
            problems.append(f"文法 md の目印「{a}」に対応する規則が、規則ファイルにない")

    for a, fn in TABLE_CHECKS.items():
        if a in anchors:
            for p in fn(anchors[a], rules):
                problems.append(f"[{a}] {p}")

    llm = sorted(a for a in anchors if a not in TABLE_CHECKS)
    return problems, llm, anchors, refs


def main():
    rules_path = sys.argv[1] if len(sys.argv) > 1 else "pute-rules.yaml"
    md_path = sys.argv[2] if len(sys.argv) > 2 else "pute2-grammar.md"
    problems, llm, anchors, refs = run(rules_path, md_path)
    print(f"目印 {len(anchors)} 個、ref {len(refs)} 個を照合した。")
    if problems:
        print(f"食い違い {len(problems)} 件:")
        for p in problems:
            print("  - " + p)
    else:
        print("食い違いは見つからなかった。")
    if llm:
        print("\n文章の記述なので、LLM に調べさせる目印(md の該当箇所と、対応する規則を渡す):")
        for a in llm:
            where = ", ".join(p for p, x in refs if x == a)
            print(f"  - {a}  ← 規則: {where}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())