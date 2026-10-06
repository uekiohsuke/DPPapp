"""ミャミュ語の、文法 md と規則ファイルの表の比べ方と、規則ファイルの中の点検

prototype/check_rules_docs.py の MYAMYU_CHECKS(表の比べ方)と myamyu_self(規則ファイルの中で気になる点)。
照合の進め方は conlang.core.grammar_check。
"""
from __future__ import annotations

import re

from conlang.core import grammar_check as GC
from conlang.core.grammar_check import diff_maps, diff_sets, table_rows
from conlang.core.rules import Rules


def _g(r: Rules, *keys):
    v = r.get(*keys, default=None)
    if v is None:
        raise KeyError(".".join(keys))
    return v


# ---------- 表の比べ方 ----------

def my_overview(block, r: Rules):
    md = {row[0]: row[1] for row in table_rows(block) if len(row) >= 2}
    yml = {k: ("、".join(v) if isinstance(v, list) else str(v)) for k, v in _g(r, "overview", "items").items()}
    return diff_maps("基本情報", md, yml)


def my_phonemes(block, r: Rules):
    ph = _g(r, "phonology")
    md = {row[0]: [x.strip() for x in row[1].split(",")] for row in table_rows(block) if len(row) >= 2}
    out = []
    for label, key in [("母音", "vowels"), ("子音", "consonants")]:
        out += diff_sets(label, set(md.get(label, [])), set(ph[key]))
    return out


def my_ipa(block, r: Rules):
    md = {}
    for row in table_rows(block):
        m = re.search(r"/([^/]+)/", row[1]) if len(row) >= 2 else None
        md[row[0]] = m.group(1) if m else row[1]
    return diff_maps("発音", md, _g(r, "phonology", "ipa"))


def my_forbidden(block, r: Rules):
    line = next((l for l in block if "存在しない並び" in l), None)
    if line is None:
        return ["「存在しない並び:」の行が見つからない"]
    items = line.split(":", 1)[1].split()
    out = ["存在しない並びに重複がある"] if len(items) != len(set(items)) else []
    return out + diff_sets("存在しない並び", set(items), set(_g(r, "phonotactics", "forbidden_clusters")))


def my_structure(block, r: Rules):
    names = {"動詞": "verb", "名詞": "noun", "形容詞": "adjective"}
    md = {names.get(row[0], row[0]): row[1].split("-") for row in table_rows(block) if len(row) >= 2}
    yml = _g(r, "morphology", "structure")
    return [f"{k} の構成: 文法 md は {md.get(k)}、規則ファイルは {yml.get(k)}"
            for k in sorted(set(md) | set(yml)) if md.get(k) != yml.get(k)]


def slot_table(keys: tuple[str, ...], label: str, order_keys: tuple[str, ...] | None = None):
    """名称 | 形 | 意味 の表。規則ファイルは 形: {name, meaning}。order_keys があれば並びも比べる"""
    def cmp(block, r: Rules):
        yml = _g(r, *keys)
        rows = [row for row in table_rows(block) if len(row) >= 3]
        md = {form: {"name": name, "meaning": meaning} for name, form, meaning in (row[:3] for row in rows)}
        out = []
        for k in sorted(set(md) | set(yml)):
            if k in md and k in yml:
                out += diff_maps(f"{label} {k}", md[k], {kk: str(vv) for kk, vv in (yml[k] or {}).items()})
            else:
                out.append(f"{label} {k}: {'文法 md' if k in md else '規則ファイル'}にだけある")
        if order_keys:
            md_order = [row[1] for row in rows]
            want = list(_g(r, *order_keys))
            if md_order != want:
                out.append(f"{label}の並び: 文法 md は {md_order}、規則ファイルは {want}")
        return out
    return cmp


def my_tense_suffix(block, r: Rules):
    md = {row[0]: row[1].lstrip("-") for row in table_rows(block) if len(row) >= 2}
    return diff_maps("時制接辞", md, _g(r, "verb", "tense_suffix"))


def my_subject(block, r: Rules):
    names = {"一人称": "first", "二人称": "second", "三人称": "third", "非人間": "nonhuman"}
    dash = "—"
    md = {names.get(row[0], row[0]): {"singular": row[1], "plural": row[2], "indefinite": row[3]}
          for row in table_rows(block) if len(row) >= 4}
    yml = {k: {kk: (vv or dash) for kk, vv in v.items()} for k, v in _g(r, "verb", "subject_marker").items()}
    out = []
    for k in sorted(set(md) | set(yml)):
        out += diff_maps(f"主語マーカー {k}", md.get(k, {}), yml.get(k, {}))
    return out


def my_numbers(block, r: Rules):
    md = {row[0]: {"word": row[1], "short": row[2]} for row in table_rows(block) if len(row) >= 3}
    yml = {str(d): {"word": v["word"], "short": v["short"]} for d, v in _g(r, "numbers", "digits").items()}
    out = []
    for k in sorted(set(md) | set(yml), key=lambda x: int(x) if x.isdigit() else 99):
        out += diff_maps(f"数 {k}", md.get(k, {}), yml.get(k, {}))
    return out


def my_quantity(block, r: Rules):
    ex = _g(r, "usage", "quantity", "example")
    line = next((l for l in block if "例" in l), "")
    m = re.search(r"例:\s*(.+?)[(（](.+?)[)）]", line)
    if not m:
        return ["数量指定の例の行が読めない"]
    return diff_maps("数量指定の例", {"form": m.group(1).strip(), "gloss": m.group(2)}, {"form": ex["form"], "gloss": ex["gloss"]})


TABLE_CHECKS: GC.TableChecks = {
    "overview": my_overview,
    "phonology.phonemes": my_phonemes,
    "phonology.ipa": my_ipa,
    "phonotactics.forbidden": my_forbidden,
    "morphology.structure": my_structure,
    "verb.tense.basic": slot_table(("verb", "tense_basic"), "時制"),
    "verb.tense.suffix": my_tense_suffix,
    "verb.voice": slot_table(("verb", "voice"), "態"),
    "verb.aspect": slot_table(("verb", "aspect"), "相"),
    "verb.mood": slot_table(("verb", "mood"), "法"),
    "verb.subject_marker": my_subject,
    "case.markers": slot_table(("case", "markers"), "格", ("case", "priority_order")),
    "numbers": my_numbers,
    "usage.quantity": my_quantity,
}


# ---------- 規則ファイルの中の点検(文法 md とは関係なく、規則ファイルだけを見る) ----------

def check_rules(r: Rules) -> list[str]:
    """規則ファイルの中で気になる点(試作の myamyu_self)。項目が足りないときは、そのことを返す"""
    try:
        return _self_check(r)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        return [f"規則ファイルを点検できなかった(項目が足りないか、形が想定と違う): {type(e).__name__}: {e}"]


def _segment(word, vowels, consonants):
    units = sorted(set(vowels) | set(consonants), key=len, reverse=True)
    out, i = [], 0
    while i < len(word):
        u = next((x for x in units if word.startswith(x, i)), None)
        if u is None:
            return None
        out.append(u)
        i += len(u)
    return out


def _self_check(r: Rules) -> list[str]:
    notes = []
    rules = r.data
    ph = rules["phonology"]
    V, C = set(ph["vowels"]), set(ph["consonants"])
    forbidden = set(rules["phonotactics"]["forbidden_clusters"])
    verb = rules["verb"]

    # 1. 禁止された並びは、どれも子音2つでできているか
    for f in sorted(forbidden):
        seg = _segment(f, V, C)
        if seg is None or len(seg) != 2 or not all(x in C for x in seg):
            notes.append(f"禁止された並び「{f}」が、子音2つに分けられない: {seg}")

    # 2. 接辞・数の語が、音素に分けられ、禁止された並びを含まないか
    forms: dict[str, list[str]] = {}
    for slot in ["tense_basic", "voice", "aspect", "mood"]:
        for form in verb[slot]:
            forms.setdefault(form, []).append(slot)
    for form in rules["case"]["markers"]:
        forms.setdefault(form, []).append("case")
    for person, d in verb["subject_marker"].items():
        for _, form in d.items():
            if form:
                forms.setdefault(form, []).append(f"subject_marker.{person}")
    for suf in verb["tense_suffix"].values():
        forms.setdefault("-" + suf, []).append("tense_suffix")
    for d, v in rules["numbers"]["digits"].items():
        forms.setdefault(v["word"], []).append(f"number.{d}")
    for form in forms:
        seg = _segment(form.lstrip("-"), V, C)
        if seg is None:
            notes.append(f"「{form}」が音素に分けられない")
            continue
        for a, b in zip(seg, seg[1:]):
            if a in C and b in C and a + b in forbidden:
                notes.append(f"「{form}」が禁止された並び「{a + b}」を含む")

    # 3. 概要の格の一覧と、格の表が合うか
    stated = set(rules["overview"]["items"].get("格", []))
    listed = {v["name"] for v in rules["case"]["markers"].values()}
    if stated != listed:
        notes.append(f"格: 基本情報には {sorted(stated)}、格の表には {sorted(listed)}(差: {sorted(stated ^ listed)})")

    # 4. 派生時制の例が、主となる時制 + 時制接辞 になっているか
    d = verb["tense_derived"]["example"]
    base = {v["name"].replace("時制", ""): k for k, v in verb["tense_basic"].items()}
    expected = base[d["main"]] + verb["tense_suffix"][d["suffix"]]
    if expected != d["form"]:
        notes.append(f"派生時制の例 {d['name']}: 例は {d['form']}、{d['main']}時制の形 + 時制接辞 なら {expected}")

    # 5. 数の略形が、語頭の子音か(他の数が従っているパターン)
    for n, v in rules["numbers"]["digits"].items():
        seg = _segment(v["word"], V, C)
        if seg and seg[0] != v["short"]:
            notes.append(f"数 {n}: 略形 {v['short']}、語 {v['word']} の語頭は {seg[0]}(他の数は語頭の子音)")

    # 6. 数量指定の例の数が、数の表と合うか
    ex = rules["usage"]["quantity"]["example"]
    word = ex["form"].split()[-1][len("uf"):]
    digit = next((n for n, v in rules["numbers"]["digits"].items() if v["word"] == word), None)
    if digit != ex["number"]:
        notes.append(f"数量指定の例 {ex['form']}: 訳は {ex['number']}、{word} は {digit}")

    # 7. 同じ形が複数の枠で使われていないか(規則ファイルで認めたものは除く)
    accepted = set((rules["morphology"].get("homographs") or {}).get("forms", []))
    for form, slots in sorted(forms.items()):
        kinds = {s.split(".")[0] for s in slots}
        if len(kinds) > 1 and not form.startswith("-") and form not in accepted:
            notes.append(f"同形「{form}」が複数の枠にある: {slots}(メモ。枠の位置で区別する)")
    return notes
