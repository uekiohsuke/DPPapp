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
  文法 md を省くと、規則ファイルの grammar_doc に書かれたファイル(規則ファイルと同じ場所)を使う。
  言語ごとの表の比べ方は、規則ファイルの language で選ぶ(ピュテ語 → PUTE_CHECKS、ウリ語 → URI_CHECKS)。
"""
import os
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


PUTE_CHECKS = {
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


# ---- ウリ語 ----

def diff_maps(label, md, yml):
    """キー → 値 の辞書どうしを比べる"""
    out = []
    for k in sorted(set(md) | set(yml)):
        a, b = md.get(k), yml.get(k)
        if a is None:
            out.append(f"{label} {k}: 規則ファイルにだけある({b})")
        elif b is None:
            out.append(f"{label} {k}: 文法 md にだけある({a})")
        elif a != b:
            out.append(f"{label} {k}: 文法 md は {a!r}、規則ファイルは {b!r}")
    return out


def uri_general(block, rules):
    """一般的な音素の表。母音の行と子音の行(続きの行は種別が空)から、転写 → 発音 を集める"""
    vowels, consonants, current = {}, {}, None
    for cells in table_rows(block):
        if cells[0]:
            current = cells[0]
        target = vowels if current == "母音" else consonants
        for key, ipa in re.findall(r"([a-z]+) /([^/]+)/", cells[1]):
            target[key] = ipa
    g = rules["phonology"]["general"]
    return diff_maps("母音", vowels, g["vowels"]) + diff_maps("子音", consonants, g["consonants"])


def uri_special(block, rules):
    md = {}
    for key, cell in table_rows(block):
        ipa = re.search(r"/([^/]+)/", cell).group(1)
        md[key] = (ipa, "使われない" not in cell, "音素表にはない" not in cell)   # (発音, 使われるか, 音素か)
    yml = {k: (v["ipa"], v.get("used", True), v.get("phoneme", True)) for k, v in rules["phonology"]["special"].items()}
    return diff_maps("特殊な音", md, yml)


def uri_counts(block, rules):
    """文章中の個数(母音は5つ、一般的なものが19個…)を、規則ファイルの個数と、実際の表の数の両方と比べる"""
    text = "".join(block)
    ph = rules["phonology"]
    actual = {
        "vowel": len(ph["general"]["vowels"]),
        "consonant_general": len(ph["general"]["consonants"]),
        "consonant_special": sum(1 for v in ph["special"].values() if v.get("used", True) and v.get("phoneme", True)),
    }
    md = {}
    for key, pat in [("vowel", r"母音は(\d+)つ"), ("consonant_general", r"一般的なものが(\d+)個"),
                     ("consonant_special", r"特殊なものが[^、。]*?(\d+)個")]:
        m = re.search(pat, text)
        if m:
            md[key] = int(m.group(1))
    out = diff_maps("個数(文法 md と規則ファイルの counts)", md, ph["counts"])
    out += diff_maps("個数(規則ファイルの counts と実際の一覧)", ph["counts"], actual)
    return out


def uri_prefixes(block, rules):
    md = set()
    for form, pos_cell, meaning in table_rows(block):
        m = re.match(r"^(.+?)[(（](.+)[)）]$", pos_cell)
        pos, noun = (m.group(1), m.group(2)) if m else (pos_cell, "")
        md.add((form, pos, noun, meaning))
    yml = {(f["form"], f["pos"], f["noun_name"], f["meaning"]) for f in rules["prefixes"]["forms"]}
    out = []
    for t in sorted(md - yml):
        out.append(f"文法 md にだけある接頭辞の行 {t}")
    for t in sorted(yml - md):
        out.append(f"規則ファイルにだけある接頭辞の行 {t}")
    return out


def uri_particles(block, rules):
    p = rules["particles"]
    md, total = {}, 0
    for cat, cell in table_rows(block):
        md[cat] = {}
        for item in cell.split(" / "):
            m = re.match(r"^(\S+)\s+(.+)$", item.strip())
            md[cat][m.group(1)] = m.group(2)
            total += 1
    out = []
    for cat in sorted(set(md) | set(p["categories"])):
        out += diff_maps(f"情詞 [{cat}]", md.get(cat, {}), p["categories"].get(cat, {}))
    if total != p["count"]:
        out.append(f"情詞の数: 文法 md の表には {total} 個、規則ファイルの count は {p['count']}")
    return out


def uri_personal(block, rules):
    names = {"一人称": "first", "二人称": "second", "三人称": "third"}
    md = {}
    for label, sg, pl in table_rows(block):
        md[names.get(label, label)] = {"singular": sg, "plural": pl}
    yml = rules["pronouns"]["personal"]
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_maps(f"人称代名詞 {k}", md.get(k, {}), yml.get(k, {}))
    return out


def make_meaning_table(getter, label):
    """語 | 意味 の表。意味は、規則ファイルの値で始まっていればよい(補足の括弧書きが md にあるため)"""
    def cmp(block, rules):
        yml = getter(rules)
        md = {k: v for k, v in table_rows(block)}
        out = []
        for k in sorted(set(md) | set(yml)):
            a, b = md.get(k), yml.get(k)
            if a is None:
                out.append(f"{label} {k}: 規則ファイルにだけある({b})")
            elif b is None:
                out.append(f"{label} {k}: 文法 md にだけある({a})")
            elif not a.startswith(b):
                out.append(f"{label} {k}: 文法 md は「{a}」、規則ファイルは「{b}」")
        return out
    return cmp


def uri_eras(block, rules):
    names = [re.sub(r"[(（].*?[)）]", "", x).replace("ウリ語", "").strip() for x in block[0].split("→")]
    yml = rules["history"]["eras"]
    return [] if names == yml else [f"時代の並び: 文法 md は {names}、規則ファイルは {yml}"]


def uri_semivowel(block, rules):
    md = {old: {"to": new, "meaning": meaning} for old, new, meaning in table_rows(block)}
    yml = rules["history"]["semivowel_insertion"]
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_maps(f"半母音の挿入 {k}", md.get(k, {}), yml.get(k, {}))
    return out


URI_CHECKS = {
    "phonology.general": uri_general,
    "phonology.special": uri_special,
    "phonology.notes": uri_counts,
    "prefixes": uri_prefixes,
    "particles.list": uri_particles,
    "pronouns.personal": uri_personal,
    "pronouns.demonstrative": make_meaning_table(lambda r: r["pronouns"]["demonstrative"], "指示詞"),
    "pronouns.other": make_meaning_table(lambda r: r["pronouns"]["other"], "その他の代名詞"),
    "history.eras": uri_eras,
    "history.semivowel": uri_semivowel,
}

# 規則ファイルの language の先頭がこれに一致する言語の表を使う
REGISTRIES = {"ピュテ": PUTE_CHECKS, "ウリ": URI_CHECKS}


def pick_registry(rules):
    lang = str(rules.get("language", ""))
    for prefix, reg in REGISTRIES.items():
        if lang.startswith(prefix):
            return reg
    raise SystemExit(f"language「{lang}」に対応する表の比べ方がない(REGISTRIES に足す)")


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

    registry = pick_registry(rules)
    for a, fn in registry.items():
        if a in anchors:
            for p in fn(anchors[a], rules):
                problems.append(f"[{a}] {p}")

    llm = sorted(a for a in anchors if a not in registry)
    return problems, llm, anchors, refs


def main():
    rules_path = sys.argv[1] if len(sys.argv) > 1 else "pute-rules.yaml"
    if len(sys.argv) > 2:
        md_path = sys.argv[2]
    else:
        doc = yaml.safe_load(open(rules_path, encoding="utf-8"))["grammar_doc"]
        md_path = os.path.join(os.path.dirname(os.path.abspath(rules_path)), doc)
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