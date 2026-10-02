"""ウリ語の音韻と表記(規則ファイルから読む。なければ文法 md 1章の値)

- 音節は CV、CVn、CVng(文法 1.2)。長音は母音を重ねる(現代の転写)
- 辞書の綴りは旧表記: 音節の頭を大文字にし、長音は母音を大文字で書く(SuKaHuDu、KU、FoTONe)
- 現代の転写は小文字で、長音は母音を重ねる(sukahudu、kuu、fotoone)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conlang.core.rules import Rules

DEFAULT_VOWELS = ["a", "e", "i", "o", "u"]
DEFAULT_CONSONANTS = ["l", "r", "m", "n", "ng", "g", "z", "s", "sh", "t", "k", "f", "v", "p", "w", "y", "d", "b", "th",
                      "h", "j", "q", "x"]
DEFAULT_CODAS = ["n", "ng"]
DEFAULT_PREFIXES = {"su": "動詞(状態名詞)", "xu": "被動詞(被状態名詞)", "vora": "形容詞(属性名詞)",
                    "gara": "副詞(変化属性名詞)", "ra": "直接比喩修飾詞(比喩名詞)", "lo": "接続詞(句接続名詞)"}
# 語頭が母音に見える例外(文法 1.2: uli は本来 wuli)
DEFAULT_VOWEL_INITIAL = ["uli"]


@dataclass(frozen=True)
class Syllable:
    onset: str     # 子音(母音で始まる例外の語では空)
    vowel: str     # 長音なら母音を重ねたもの(aa)
    coda: str = ""  # n か ng

    @property
    def text(self) -> str:
        return self.onset + self.vowel + self.coda

    @property
    def long(self) -> bool:
        return len(self.vowel) == 2


@dataclass
class UriLang:
    vowels: list[str] = field(default_factory=lambda: list(DEFAULT_VOWELS))
    consonants: list[str] = field(default_factory=lambda: list(DEFAULT_CONSONANTS))
    codas: list[str] = field(default_factory=lambda: list(DEFAULT_CODAS))
    prefixes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PREFIXES))
    vowel_initial: list[str] = field(default_factory=lambda: list(DEFAULT_VOWEL_INITIAL))
    rules: Rules | None = None

    # 規則ファイルから読んだ、検査で使う一覧
    particles: dict[str, str] = field(default_factory=dict)          # 情詞 → 意味
    old_forms: dict[str, tuple[str, str]] = field(default_factory=dict)  # 近現代の形 → (現代の形, 意味)
    old_prefixes: dict[str, str] = field(default_factory=dict)        # 古い接頭辞 → 今の接頭辞(xa- → xu-)
    avoid: list[str] = field(default_factory=list)                    # 造語で避ける並び(C は子音)
    vowel_fixes: list[tuple[str, str]] = field(default_factory=list)  # 発音しにくい並びの直し方(iyi → iya)
    checks: set[str] | None = None                                    # 規則ファイルの checks の id(なければ None)

    @classmethod
    def from_rules(cls, r: Rules | None) -> "UriLang":
        """規則ファイル(uri-rules.yaml の形)から読む。項目がなければ、文法 md 1〜2章の初期値のまま"""
        lang = cls(rules=r)
        if r is None:
            return lang
        ph = r.get("phonology", default={}) or {}
        general = ph.get("general") or {}
        if general.get("vowels"):
            lang.vowels = [str(v) for v in general["vowels"]]
        if general.get("consonants"):
            special = ph.get("special") or {}
            # 綴りに使うもの: 一般的な子音と、特殊な音のうち使われるもの(x は音素ではないが綴りには使う)
            lang.consonants = [str(c) for c in general["consonants"]] + \
                              [str(k) for k, v in special.items() if (v or {}).get("used", True)]
        syl = ph.get("syllable") or {}
        if syl.get("units"):
            # CVn、CVng → n、ng
            lang.codas = [str(u)[2:] for u in syl["units"] if str(u).startswith("CV") and str(u) != "CV"]
        if syl.get("initial_w_omission") is not None:
            lang.vowel_initial = [str(w) for w in syl["initial_w_omission"] or []]
        forms = r.get("prefixes", "forms", default=None)
        if isinstance(forms, list) and forms:
            lang.prefixes = {}
            for f in forms:
                key = str(f.get("form", "")).strip("-")
                name = f"{f.get('pos', '')}({f.get('noun_name', '')})" if f.get("noun_name") else str(f.get("pos", ""))
                lang.prefixes[key] = f"{lang.prefixes[key]}/{name}" if key in lang.prefixes else name
        for words in (r.get("particles", "categories", default={}) or {}).values():
            lang.particles.update({str(k): str(v) for k, v in (words or {}).items()})
        for old, v in (r.get("history", "semivowel_insertion", default={}) or {}).items():
            lang.old_forms[str(old)] = (str((v or {}).get("to", "")), str((v or {}).get("meaning", "")))
        for old, new in (r.get("history", "changes", "demonstratives", default={}) or {}).items():
            lang.old_forms[str(old)] = (str(new), "指示詞")
        pp = r.get("history", "changes", "passive_prefix", default=None)
        if isinstance(pp, dict) and pp.get("from"):
            lang.old_prefixes[str(pp["from"]).strip("-")] = str(pp.get("to", "")).strip("-")
        lang.avoid = [str(s) for s in r.get("compounding", "avoid_sequences", default=[]) or []]
        lang.vowel_fixes = [(str(v["from"]), str(v["to"])) for v in r.get("compounding", "vowel_sequence", default=[]) or []
                            if isinstance(v, dict) and v.get("from")]
        checks = r.get("checks", default=None)
        if isinstance(checks, list):
            lang.checks = {str(c.get("id")) for c in checks if isinstance(c, dict) and c.get("id")}
        return lang

    def enabled(self, check_id: str) -> bool:
        """規則ファイルの checks にある検査か(規則ファイルがなければ、音節の検査だけ)"""
        if self.checks is None:
            return check_id == "syllable_segmentation"
        return check_id in self.checks

    def avoid_patterns(self) -> list:
        """避ける並び(Cuwu の C は子音)を正規表現にする"""
        import re
        cons = "|".join(re.escape(c) for c in sorted(self.consonants, key=len, reverse=True))
        return [(s, re.compile(re.escape(s).replace("C", f"(?:{cons})"))) for s in self.avoid]

    # ---------- 旧表記 → 現代の転写 ----------

    def to_modern(self, old: str) -> str:
        """辞書の旧表記を、現代の転写にする。子音の後ろの大文字の母音は長音(母音を重ねる)"""
        out = []
        prev_consonant = False
        for ch in old:
            low = ch.lower()
            if low in "aeiou" and ch.isupper() and prev_consonant:
                out.append(low * 2)
            else:
                out.append(low)
            prev_consonant = ch.isalpha() and low not in "aeiou"
        return "".join(out)

    def old_syllables(self, old: str) -> list[str]:
        """旧表記の大文字で区切った音節(現代の転写にしたもの)。大文字の子音か、語頭・母音の後ろの大文字の母音で始まる"""
        out: list[str] = []
        prev = ""
        for ch in old:
            low = ch.lower()
            starts = ch.isupper() and (low not in "aeiou" or not prev or prev.lower() in "aeiou")
            if starts or not out:
                out.append("")
            if low in "aeiou" and ch.isupper() and prev and prev.lower() not in "aeiou":
                out[-1] += low * 2  # 長音
            else:
                out[-1] += low
            prev = ch
        return out

    # ---------- 音節 ----------

    def _onsets(self) -> list[str]:
        return sorted(self.consonants, key=len, reverse=True)

    def syllabify_all(self, word: str, limit: int = 20) -> list[list[Syllable]]:
        """現代の転写の1語を、音節に分ける方法をすべて挙げる"""
        onsets, codas = self._onsets(), sorted(self.codas, key=len, reverse=True)
        vowels = self.vowels
        out: list[list[Syllable]] = []

        def nuclei(i):
            for v in vowels:
                if word.startswith(v * 2, i):
                    yield v * 2
                if word.startswith(v, i):
                    yield v

        def go(i, acc):
            if len(out) >= limit:
                return
            if i == len(word):
                out.append(list(acc))
                return
            starts = [o for o in onsets if word.startswith(o, i)]
            if i == 0 and any(word.startswith(w) for w in self.vowel_initial):
                starts.append("")  # 母音で始まる例外の語
            for o in starts:
                j = i + len(o)
                for v in nuclei(j):
                    k = j + len(v)
                    for c in [""] + [c for c in codas if word.startswith(c, k)]:
                        acc.append(Syllable(o, v, c))
                        go(k + len(c), acc)
                        acc.pop()

        go(0, [])
        # 長音を少なく、音節の少ない読み方から
        out.sort(key=lambda s: (len(s), sum(x.long for x in s)))
        return out

    def syllabify(self, word: str) -> list[Syllable] | None:
        """音節の分け方のうち、1つ(なければ None)"""
        alls = self.syllabify_all(word, limit=5)
        return alls[0] if alls else None

    def split_prefix(self, word: str) -> tuple[str, str]:
        """意味範疇の接頭辞と、残り。接頭辞がなければ ("", word)。残りが音節に分けられるものだけ"""
        for p in sorted(self.prefixes, key=len, reverse=True):
            if word.startswith(p) and len(word) > len(p) and self.syllabify(word[len(p):]):
                return p, word[len(p):]
        return "", word
