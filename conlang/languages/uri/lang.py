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

    @classmethod
    def from_rules(cls, r: Rules | None) -> "UriLang":
        lang = cls(rules=r)
        if r is None:
            return lang
        ph = r.get("phonology", default={}) or {}
        if ph.get("vowels"):
            lang.vowels = [str(v) for v in ph["vowels"]]
        cons = ph.get("consonants")
        if isinstance(cons, dict):
            lang.consonants = [str(c) for g in cons.values() for c in (g or [])]
        elif cons:
            lang.consonants = [str(c) for c in cons]
        syl = r.get("syllable", default={}) or {}
        if syl.get("codas"):
            lang.codas = [str(c) for c in syl["codas"]]
        if syl.get("vowel_initial_words") is not None:
            lang.vowel_initial = [str(w) for w in syl["vowel_initial_words"] or []]
        pre = r.get("affixes", "prefix", "forms", default=None)
        if pre:
            lang.prefixes = {str(k): str(v) for k, v in pre.items()}
        return lang

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
