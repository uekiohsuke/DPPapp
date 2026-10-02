"""ピュテ語の規則ファイル(pute-rules.yaml の形)の解釈と点検"""
from __future__ import annotations

from dataclasses import dataclass

from conlang.core.rules import Rules, RulesError

WORD_CLASSES = ("noun", "verb", "adjective", "adverb")
CLASS_NAMES = {"noun": "名詞", "verb": "動詞", "adjective": "形容詞", "adverb": "副詞"}


def vowels(r: Rules) -> list[str]:
    return list(r.get("phonology", "vowels", default=[]) or [])


def consonants(r: Rules) -> list[str]:
    groups = r.get("phonology", "consonants", default={}) or {}
    if isinstance(groups, dict):
        return [c for g in groups.values() for c in (g or [])]
    return list(groups)


def phonemes(r: Rules) -> list[str]:
    """長いものから照合する順"""
    return sorted(vowels(r) + consonants(r), key=len, reverse=True)


def _parse_count(s: str, phs: list[str]) -> int:
    """s を音素に分ける方法の数(phonology.parse_count と同じ数え方)"""
    count = [0] * (len(s) + 1)
    count[0] = 1
    for i in range(len(s)):
        if count[i]:
            for p in phs:
                if s.startswith(p, i):
                    count[i + len(p)] += count[i]
    return count[len(s)]


# ---------- 活用 ----------

@dataclass(frozen=True)
class InflectedForm:
    state: str
    tense: str
    ending: str   # 語幹の後ろに付く部分(なければ "")
    form: str     # ハイフンを入れた形(X-ket)。語尾がなければ語幹のまま


def _class_tables(r: Rules, word_class: str) -> tuple[dict, dict, dict]:
    if word_class not in WORD_CLASSES:
        raise RulesError(f"品詞は {' / '.join(WORD_CLASSES)} のどれか: {word_class}")
    overrides = {}
    base = word_class
    cls = r.get("inflection", "classes", word_class)
    if isinstance(cls, dict):
        base = cls.get("same_as", word_class)
        overrides = cls.get("overrides", {}) or {}
    states = r.get("inflection", "state", base)
    tenses = r.get("inflection", "tense", base)
    if not isinstance(states, dict) or not isinstance(tenses, dict):
        raise RulesError(f"inflection に {base} の state / tense の表がない")
    return states, tenses, overrides


def inflection_table(r: Rules, word_class: str, stem: str = "X") -> list[InflectedForm]:
    """語尾の一覧を組み合わせて、活用の表を作る(状態形 × 時制などの順)。
    語尾は inflection.order の順(状態形 → 時制)につなぎ、語幹とのあいだだけハイフンで区切る(文法 8.1)"""
    states, tenses, overrides = _class_tables(r, word_class)
    order = r.get("inflection", "order", default=["state", "tense"]) or ["state", "tense"]
    out = []
    for s_name, s_end in states.items():
        for t_name, t_end in tenses.items():
            key = f"{s_name}.{t_name}"
            if key in overrides:
                ending = str(overrides[key] or "")
            else:
                parts = {"state": str(s_end or ""), "tense": str(t_end or "")}
                ending = "".join(parts[o] for o in order if o in parts)
            out.append(InflectedForm(s_name, t_name, ending, f"{stem}-{ending}" if ending else stem))
    return out


def format_table(r: Rules, word_class: str, stem: str = "X") -> str:
    states, tenses, _ = _class_tables(r, word_class)
    forms = {(f.state, f.tense): f.form for f in inflection_table(r, word_class, stem)}
    lines = [f"{CLASS_NAMES[word_class]}の活用({len(forms)}通り)",
             "| 状態形 | " + " | ".join(tenses) + " |",
             "|---" * (len(tenses) + 1) + "|"]
    for s in states:
        lines.append(f"| {s} | " + " | ".join(forms[(s, t)] for t in tenses) + " |")
    return "\n".join(lines)


# ---------- 点検 ----------

def check_rules(r: Rules) -> list[str]:
    """規則ファイルそのものの点検。見つかった問題を文で返す(空なら問題なし)"""
    out = []
    vs, cs = vowels(r), consonants(r)
    if not vs:
        out.append("phonology.vowels がない")
    if not cs:
        out.append("phonology.consonants がない")
    for name, items in (("母音", vs), ("子音", cs)):
        dup = sorted({x for x in items if items.count(x) > 1})
        if dup:
            out.append(f"{name}が重複している: {', '.join(dup)}")
    both = sorted(set(vs) & set(cs))
    if both:
        out.append(f"母音と子音の両方にある: {', '.join(both)}")
    phs = phonemes(r)
    if not phs:
        return out

    def must_parse(where, s):
        if s and _parse_count(s, phs) == 0:
            out.append(f"{where} の「{s}」が音素に分けられない")

    for name in ("forbidden_substrings", "forbidden_substrings_provisional"):
        for s in r.get("phonotactics", name, default=[]) or []:
            must_parse(f"phonotactics.{name}", str(s))
    affixes = r.get("affixes", default={}) or {}
    for cat, spec in affixes.items():
        forms = (spec or {}).get("forms", {}) if isinstance(spec, dict) else {}
        for f in forms:
            must_parse(f"affixes.{cat}", str(f))
    for kind in ("tense", "state"):
        for cls, table in (r.get("inflection", kind, default={}) or {}).items():
            for name, end in (table or {}).items():
                must_parse(f"inflection.{kind}.{cls}.{name}", str(end or ""))
    for wc in WORD_CLASSES:
        try:
            inflection_table(r, wc)
        except RulesError as e:
            out.append(str(e))
    return out
