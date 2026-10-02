"""ウリ語の、文法 md と規則ファイルの表の比べ方(prototype/check_rules_docs.py の URI_CHECKS)

照合の進め方は conlang.core.grammar_check。ここには、目印の ID ごとの表の比べ方だけを置く。
"""
from __future__ import annotations

import re

from conlang.core import grammar_check as GC
from conlang.core.grammar_check import diff_maps, table_rows
from conlang.core.rules import Rules


def _g(r: Rules, *keys, default=None):
    v = r.get(*keys, default=default)
    if v is None:
        raise KeyError(".".join(keys))
    return v


def uri_general(block, r: Rules):
    """一般的な音素の表。母音の行と子音の行(続きの行は種別が空)から、転写 → 発音 を集める"""
    vowels, consonants, current = {}, {}, None
    for row in table_rows(block):
        if row[0]:
            current = row[0]
        target = vowels if current == "母音" else consonants
        for key, ipa in re.findall(r"([a-z]+) /([^/]+)/", row[1] if len(row) > 1 else ""):
            target[key] = ipa
    g = _g(r, "phonology", "general")
    return diff_maps("母音", vowels, g["vowels"]) + diff_maps("子音", consonants, g["consonants"])


def uri_special(block, r: Rules):
    md = {}
    for row in table_rows(block):
        key, cell = row[0], row[1]
        m = re.search(r"/([^/]+)/", cell)
        md[key] = (m.group(1) if m else cell, "使われない" not in cell, "音素表にはない" not in cell)  # (発音, 使われるか, 音素か)
    yml = {k: (v["ipa"], v.get("used", True), v.get("phoneme", True)) for k, v in _g(r, "phonology", "special").items()}
    return diff_maps("特殊な音", md, yml)


def uri_counts(block, r: Rules):
    """文章中の個数(母音は5つ、一般的なものが19個…)を、規則ファイルの個数と、実際の一覧の数の両方と比べる"""
    text = "".join(block)
    ph = _g(r, "phonology")
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


def uri_prefixes(block, r: Rules):
    md = set()
    for row in table_rows(block):
        form, pos_cell, meaning = row[0], row[1], row[2]
        m = re.match(r"^(.+?)[(（](.+)[)）]$", pos_cell)
        pos, noun = (m.group(1), m.group(2)) if m else (pos_cell, "")
        md.add((form, pos, noun, meaning))
    yml = {(f["form"], f["pos"], f["noun_name"], f["meaning"]) for f in _g(r, "prefixes", "forms")}
    return ([f"文法 md にだけある接頭辞の行 {t}" for t in sorted(md - yml)]
            + [f"規則ファイルにだけある接頭辞の行 {t}" for t in sorted(yml - md)])


def uri_particles(block, r: Rules):
    p = _g(r, "particles")
    md, total = {}, 0
    for row in table_rows(block):
        cat, cell = row[0], row[1]
        md[cat] = {}
        for item in cell.split(" / "):
            m = re.match(r"^(\S+)\s+(.+)$", item.strip())
            if m:
                md[cat][m.group(1)] = m.group(2)
                total += 1
    out = []
    for cat in sorted(set(md) | set(p["categories"])):
        out += diff_maps(f"情詞 [{cat}]", md.get(cat, {}), p["categories"].get(cat, {}))
    if total != p["count"]:
        out.append(f"情詞の数: 文法 md の表には {total} 個、規則ファイルの count は {p['count']}")
    return out


def uri_personal(block, r: Rules):
    names = {"一人称": "first", "二人称": "second", "三人称": "third"}
    md = {}
    for row in table_rows(block):
        label, sg, pl = row[0], row[1], row[2]
        md[names.get(label, label)] = {"singular": sg, "plural": pl}
    yml = _g(r, "pronouns", "personal")
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_maps(f"人称代名詞 {k}", md.get(k, {}), yml.get(k, {}))
    return out


def meaning_table(keys: tuple[str, ...], label: str):
    """語 | 意味 の表。意味は、規則ファイルの値で始まっていればよい(補足の括弧書きが md にあるため)"""
    def cmp(block, r: Rules):
        yml = {str(k): str(v) for k, v in _g(r, *keys).items()}
        md = {row[0]: row[1] for row in table_rows(block) if len(row) >= 2}
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


def uri_eras(block, r: Rules):
    names = [re.sub(r"[(（].*?[)）]", "", x).replace("ウリ語", "").strip() for x in block[0].split("→")]
    yml = list(_g(r, "history", "eras"))
    return [] if names == yml else [f"時代の並び: 文法 md は {names}、規則ファイルは {yml}"]


def uri_semivowel(block, r: Rules):
    md = {row[0]: {"to": row[1], "meaning": row[2]} for row in table_rows(block) if len(row) >= 3}
    yml = _g(r, "history", "semivowel_insertion")
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_maps(f"半母音の挿入 {k}", md.get(k, {}), yml.get(k, {}))
    return out


TABLE_CHECKS: GC.TableChecks = {
    "phonology.general": uri_general,
    "phonology.special": uri_special,
    "phonology.notes": uri_counts,
    "prefixes": uri_prefixes,
    "particles.list": uri_particles,
    "pronouns.personal": uri_personal,
    "pronouns.demonstrative": meaning_table(("pronouns", "demonstrative"), "指示詞"),
    "pronouns.other": meaning_table(("pronouns", "other"), "その他の代名詞"),
    "history.eras": uri_eras,
    "history.semivowel": uri_semivowel,
}
