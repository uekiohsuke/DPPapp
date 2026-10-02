"""規則ファイルを、ピュテ語の規則として読んだもの(造語支援と整合性チェックが共有する)

規則ファイルがない、または項目が欠けているときは、試作(prototype/pute_zougo.py)の初期値を使う。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conlang.core.rules import Rules

from . import phonology as P
from . import rules as PR

# 試作の初期値
DEFAULT_VOWELS = ["wo", "a", "e", "i", "o", "u"]
DEFAULT_CONSONANTS = ["sch", "tch", "sh", "sx", "tr", "th", "dr", "s", "k", "t", "d", "j", "q", "v", "b"]
DEFAULT_FORBIDDEN = ["aa", "ee", "ii", "oo", "uu", "wowo"]
DEFAULT_LENGTH_WEIGHTS = {2: 3, 3: 3, 4: 2, 5: 1}
DEFAULT_GEN_FILTERS = {"not_existing_word": True, "not_readable_as_parts": True, "min_edit_distance": 2,
                       "min_vowels": 1, "min_consonants": 1, "max_consonant_run": 2}

# ハイフンで区切る接辞(独立した音節。母音をまとめない)。規則ファイルの compounding.affix_boundary.applies_to が優先
DEFAULT_BOUNDARY_AFFIXES = ("case_prefix", "verbalizer", "inflection")
# 語幹の中に入る接辞(ハイフンなし。複合語の部品と同じく母音をまとめる)
STEM_AFFIXES = ("nominalizer", "plural", "modifier_kind")


def _affix_forms(r: Rules, category: str) -> dict[str, str]:
    spec = r.get("affixes", category, default={}) or {}
    forms = spec.get("forms") if isinstance(spec, dict) else None
    return {str(k): str(v) for k, v in (forms or {}).items()}


def _inflection_endings(r: Rules) -> set[str]:
    out = set()
    if not r.get("inflection"):
        return out
    for wc in PR.WORD_CLASSES:
        try:
            out |= {f.ending for f in PR.inflection_table(r, wc) if f.ending}
        except Exception:
            continue
    return out


@dataclass
class PuteLang:
    vowels: list[str] = field(default_factory=lambda: list(DEFAULT_VOWELS))
    consonants: list[str] = field(default_factory=lambda: list(DEFAULT_CONSONANTS))
    forbidden: list[str] = field(default_factory=lambda: list(DEFAULT_FORBIDDEN))
    forbidden_provisional: list[str] = field(default_factory=list)
    length_weights: dict[int, int] = field(default_factory=lambda: dict(DEFAULT_LENGTH_WEIGHTS))
    gen_filters: dict = field(default_factory=lambda: dict(DEFAULT_GEN_FILTERS))
    # 接辞: 綴り → 名前
    prefixes: dict[str, str] = field(default_factory=dict)     # 語頭の、ハイフンで区切る接辞(格接頭辞)
    suffixes: dict[str, str] = field(default_factory=dict)     # 語末の、ハイフンで区切る接辞(活用語尾)
    anywhere: dict[str, str] = field(default_factory=dict)     # どこでもハイフンで区切る接辞(動詞化 su- など)
    stem_affixes: dict[str, str] = field(default_factory=dict)  # 語幹の中の接辞(-ku、複数形、修飾種別)
    merge_derivational: bool = True  # 母音で始まる派生接尾辞も母音をまとめる(仕様書 10)
    rules: Rules | None = None

    @property
    def phonemes(self) -> list[str]:
        return sorted(self.vowels + self.consonants, key=len, reverse=True)

    @classmethod
    def from_rules(cls, r: Rules | None) -> "PuteLang":
        lang = cls(rules=r)
        if r is None:
            return lang
        if PR.vowels(r):
            lang.vowels = PR.vowels(r)
        if PR.consonants(r):
            lang.consonants = PR.consonants(r)
        pt = r.get("phonotactics", default=None)
        if isinstance(pt, dict):
            lang.forbidden = [str(x) for x in pt.get("forbidden_substrings", lang.forbidden) or []]
            lang.forbidden_provisional = [str(x) for x in pt.get("forbidden_substrings_provisional", []) or []]
        wg = r.get("word_generation", default=None)
        if isinstance(wg, dict):
            if wg.get("length_in_units"):
                lang.length_weights = {int(k): int(v) for k, v in wg["length_in_units"].items()}
            lang.gen_filters = {**lang.gen_filters, **(wg.get("filters") or {})}
        boundary = r.get("compounding", "affix_boundary", "applies_to", default=None) or DEFAULT_BOUNDARY_AFFIXES
        for cat in boundary:
            if cat == "inflection":
                lang.suffixes.update({e: "活用語尾" for e in _inflection_endings(r)})
            elif cat == "case_prefix":
                lang.prefixes.update(_affix_forms(r, cat))
            else:
                lang.anywhere.update(_affix_forms(r, cat))
        for cat in STEM_AFFIXES:
            if cat not in boundary:
                lang.stem_affixes.update(_affix_forms(r, cat))
        dsv = r.get("compounding", "derivational_suffix_vowel", default=None)
        if isinstance(dsv, dict) and "merge" in dsv:
            lang.merge_derivational = bool(dsv["merge"])
        return lang

    # --- 音素 ---

    def parse_count(self, s: str) -> int:
        return P.parse_count(s, self.phonemes)

    def parse(self, s: str) -> list[str] | None:
        return P.parse(s, self.phonemes)

    def is_boundary_affix(self, segs: list[str], i: int) -> bool:
        s = segs[i]
        return (i == 0 and s in self.prefixes) or (i == len(segs) - 1 and s in self.suffixes) or s in self.anywhere

    def merge_flags(self, segs: list[str]) -> list[bool]:
        """境目ごとに、同じ母音をまとめるか(ハイフンで区切る接辞の前後はまとめない)"""
        return [not (self.is_boundary_affix(segs, i) or self.is_boundary_affix(segs, i + 1))
                for i in range(len(segs) - 1)]

    def join(self, segs: list[str], merge: list[bool] | None = None) -> tuple[str, list[str]]:
        """部品をつなぐ。戻り値は (綴り, 母音をまとめた注記)"""
        merge = self.merge_flags(segs) if merge is None else merge
        if not segs:
            return "", []
        s, notes = segs[0], []
        for i, f in enumerate(segs[1:]):
            a, b = self.parse(s), self.parse(f)
            if merge[i] and a and b and a[-1] in self.vowels and a[-1] == b[0]:
                s += f[len(b[0]):]
                notes.append(f"母音 {b[0]} が連続するのでまとめた")
            else:
                s += f
        return s, notes

    def phonotactic_problems(self, word: str) -> list[tuple[str, bool]]:
        """(並び, 【仮】か) の一覧"""
        return [(b, False) for b in self.forbidden if b in word] + \
               [(b, True) for b in self.forbidden_provisional if b in word]
