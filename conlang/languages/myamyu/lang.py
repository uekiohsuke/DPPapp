"""ミャミュ語の規則(規則ファイル myamyu-rules.yaml から読む)

- 音素: 母音4、子音12。sh・mj は2文字で1つの子音
- 音の連なり: 同じ子音が続くときは1つになる。禁止された並び(fb など)になるときは、並びの最初の子音が落ちる
- 動詞の枠: 時制-語幹-態-相-法-主語マーカー。同形の接辞(af、ol、ul)は、付く位置(枠)で区別する
- 名詞: 格マーカー-語幹-後置詞
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conlang.core.rules import Rules, RulesError

# 動詞の枠(規則ファイルの morphology.structure.verb の名前 → verb の項目)
VERB_SLOTS = {"時制": "tense_basic", "態": "voice", "相": "aspect", "法": "mood", "主語マーカー": "subject_marker"}
NUMBERS = {"singular": "単数", "plural": "複数", "indefinite": "不定"}
PERSONS = {"first": "一人称", "second": "二人称", "third": "三人称", "nonhuman": "非人間"}


@dataclass(frozen=True)
class Affix:
    form: str
    slot: str     # 時制 / 態 / 相 / 法 / 主語マーカー / 格
    name: str     # 現在時制、受動態、三人称単数 など
    meaning: str = ""


@dataclass
class MyamyuLang:
    vowels: list[str] = field(default_factory=list)
    consonants: list[str] = field(default_factory=list)
    forbidden: set[str] = field(default_factory=set)
    merge_same: bool = True
    drop_first: bool = True
    verb_structure: list[str] = field(default_factory=list)
    slots: dict[str, list[Affix]] = field(default_factory=dict)   # 枠 → 接辞
    tense_suffix: dict[str, str] = field(default_factory=dict)    # 現在 → l
    cases: list[Affix] = field(default_factory=list)
    digits: dict[int, tuple[str, str]] = field(default_factory=dict)  # 数 → (語, 略形)
    checks: set[str] | None = None
    rules: Rules | None = None

    @classmethod
    def from_rules(cls, r: Rules | None) -> "MyamyuLang":
        if r is None:
            raise RulesError("ミャミュ語の機能は規則ファイル(myamyu-rules.yaml)から動く。--project か --rules で指定する")
        lang = cls(rules=r)
        ph = r.get("phonology", default={}) or {}
        lang.vowels = [str(v) for v in ph.get("vowels", []) or []]
        lang.consonants = [str(c) for c in ph.get("consonants", []) or []]
        pt = r.get("phonotactics", default={}) or {}
        lang.forbidden = {str(x) for x in pt.get("forbidden_clusters", []) or []}
        lang.merge_same = pt.get("same_consonant_run", "merge") == "merge"
        lang.drop_first = (pt.get("on_forbidden_cluster") or {}).get("action", "drop_first_consonant") == "drop_first_consonant"
        lang.verb_structure = [str(s) for s in r.get("morphology", "structure", "verb", default=[]) or []]
        verb = r.get("verb", default={}) or {}
        for slot, key in VERB_SLOTS.items():
            if key == "subject_marker":
                items = []
                for person, d in (verb.get(key) or {}).items():
                    for num, form in (d or {}).items():
                        if form:
                            items.append(Affix(str(form), slot, f"{PERSONS.get(person, person)}{NUMBERS.get(num, num)}"))
            else:
                items = [Affix(str(f), slot, str((v or {}).get("name", "")), str((v or {}).get("meaning", "")))
                         for f, v in (verb.get(key) or {}).items()]
            lang.slots[slot] = items
        lang.tense_suffix = {str(k): str(v) for k, v in (verb.get("tense_suffix") or {}).items()}
        lang.cases = [Affix(str(f), "格", str((v or {}).get("name", "")), str((v or {}).get("meaning", "")))
                      for f, v in (r.get("case", "markers", default={}) or {}).items()]
        for n, v in (r.get("numbers", "digits", default={}) or {}).items():
            lang.digits[int(n)] = (str(v.get("word", "")), str(v.get("short", "")))
        checks = r.get("checks", default=None)
        if isinstance(checks, list):
            lang.checks = {str(c.get("id")) for c in checks if isinstance(c, dict) and c.get("id")}
        return lang

    def enabled(self, check_id: str) -> bool:
        return self.checks is None or check_id in self.checks

    # ---------- 音素 ----------

    @property
    def units(self) -> list[str]:
        return sorted(set(self.vowels) | set(self.consonants), key=len, reverse=True)

    def segment(self, word: str) -> list[str] | None:
        """音素に分ける(2文字の子音 sh・mj を先に取る)。分けられなければ None"""
        units = self.units
        out, i = [], 0
        while i < len(word):
            u = next((x for x in units if word.startswith(x, i)), None)
            if u is None:
                return None
            out.append(u)
            i += len(u)
        return out

    def is_consonant(self, u: str) -> bool:
        return u in self.consonants

    def clusters(self, seq: list[str]) -> list[str]:
        """禁止された並び(子音2つ)を、見つかった順に"""
        return [a + b for a, b in zip(seq, seq[1:]) if self.is_consonant(a) and self.is_consonant(b) and a + b in self.forbidden]

    def same_runs(self, seq: list[str]) -> list[str]:
        return [a for a, b in zip(seq, seq[1:]) if self.is_consonant(a) and a == b]

    def apply_phonotactics(self, word: str) -> tuple[str, list[str]]:
        """音の連なりの規則を当てる: 同じ子音の連続を1つに、禁止された並びは最初の子音を落とす。
        戻り値は (直した綴り, 何をしたかの注記)。音素に分けられなければ、そのまま返す"""
        seq = self.segment(word)
        if seq is None:
            return word, ["音素に分けられないので、そのままにした"]
        notes = []
        changed = True
        while changed:
            changed = False
            for i in range(len(seq) - 1):
                a, b = seq[i], seq[i + 1]
                if not (self.is_consonant(a) and self.is_consonant(b)):
                    continue
                if a == b and self.merge_same:
                    notes.append(f"同じ子音 {a} が続くので1つにした")
                elif a + b in self.forbidden and self.drop_first:
                    notes.append(f"存在しない並び {a}{b} になるので、最初の子音 {a} を落とした")
                else:
                    continue
                del seq[i]
                changed = True
                break
        return "".join(seq), notes

    # ---------- 動詞 ----------

    def find(self, slot: str, key: str) -> Affix | None:
        """枠の中の接辞を、形か名前で探す(例: 時制の「未来時制」「未来」「ze」)"""
        for a in self.slots.get(slot, []) + (self.cases if slot == "格" else []):
            short = a.name
            for tail in ("時制", "態", "相", "法", "格"):
                if short.endswith(tail) and len(short) > len(tail):
                    short = short[: -len(tail)]
                    break
            if key in (a.form, a.name, short):
                return a
        return None

    def tense_forms(self) -> list[tuple[str, str]]:
        """時制の形: 基本時制と、派生時制(主となる時制 + 時制接辞)。[(形, 名前)]"""
        out = [(a.form, a.name) for a in self.slots.get("時制", [])]
        base = {a.name.replace("時制", ""): a.form for a in self.slots.get("時制", [])}
        for main, form in base.items():
            for name, suf in self.tense_suffix.items():
                out.append((form + suf, f"{main}時制+{name}の時制接辞"))
        return out

    def verb_form(self, stem: str, chosen: dict[str, Affix | str]) -> tuple[str, str, list[str]]:
        """枠の並びに接辞を置いて動詞の形を作る。戻り値は (ハイフンで区切った形, 綴り, 音の連なりの注記)
        chosen: 枠 → 接辞(時制は派生時制の形の文字列でもよい)。空の枠は置かない"""
        parts = []
        for slot in self.verb_structure or ["時制", "語幹", "態", "相", "法", "主語マーカー"]:
            if slot == "語幹":
                parts.append(stem)
                continue
            a = chosen.get(slot)
            if a:
                parts.append(a.form if isinstance(a, Affix) else str(a))
        hyphen = "-".join(parts)
        word, notes = self.apply_phonotactics("".join(parts))
        return hyphen, word, notes

    def parse_verb(self, word: str, limit: int = 30) -> list[dict]:
        """動詞の形を、時制-語幹-態-相-法-主語マーカー の枠に分ける候補(語幹は辞書がないので、残りの部分)。
        どの枠も置かないことがありうるとして探す。同形の接辞は、付く位置で決まる。
        音の連なりの規則で子音が落ちた形は、組み立て直して同じ綴りになるものだけを返す"""
        if "-" in word:
            return self._parse_hyphenated(word)
        structure = self.verb_structure or ["時制", "語幹", "態", "相", "法", "主語マーカー"]
        after = structure[structure.index("語幹") + 1:]
        tenses = [("", "")] + self.tense_forms()
        out = []

        def suffixes(i, acc):
            """語幹の後ろの枠を、後ろから順に選ぶ"""
            if i < 0:
                yield list(reversed(acc))
                return
            slot = after[i]
            yield from suffixes(i - 1, acc + [None])
            for a in self.slots.get(slot, []):
                yield from suffixes(i - 1, acc + [a])

        for t_form, t_name in tenses:
            if not word.startswith(t_form):
                continue
            for chosen in suffixes(len(after) - 1, []):
                tail = "".join(a.form for a in chosen if a)
                if tail and not word.endswith(tail):
                    continue
                stem = word[len(t_form):len(word) - len(tail)]
                if not stem or self.segment(stem) is None:
                    continue
                picks = {"時制": t_form} if t_form else {}
                picks.update({s: a for s, a in zip(after, chosen) if a})
                _, rebuilt, _ = self.verb_form(stem, picks)
                if rebuilt != word:
                    continue
                out.append({"時制": (t_form, t_name) if t_form else None, "語幹": stem,
                            **{s: a for s, a in zip(after, chosen)}})
                if len(out) >= limit:
                    return out
        # 置いた枠の多いものから(枠を少なく見ると、語幹に接辞が残るため)
        out.sort(key=lambda p: (-sum(1 for k, v in p.items() if k != "語幹" and v), len(p["語幹"])))
        return out

    def _parse_hyphenated(self, word: str) -> list[dict]:
        """ハイフンで区切った形(時制-語幹-態-相-法-主語マーカー)を、枠の位置で読む"""
        parts = word.split("-")
        structure = self.verb_structure or ["時制", "語幹", "態", "相", "法", "主語マーカー"]
        tense_forms = dict(self.tense_forms())
        result: dict = {}
        i = 0
        if parts and parts[0] in tense_forms and len(parts) > 1:
            result["時制"] = (parts[0], tense_forms[parts[0]])
            i = 1
        if i >= len(parts):
            return []
        result["語幹"] = parts[i]
        rest = parts[i + 1:]
        slots = structure[structure.index("語幹") + 1:]
        j = 0
        for p in rest:
            while j < len(slots) and not any(a.form == p for a in self.slots.get(slots[j], [])):
                j += 1
            if j >= len(slots):
                return []
            result[slots[j]] = next(a for a in self.slots[slots[j]] if a.form == p)
            j += 1
        return [result]

    # ---------- 数 ----------

    def number_word(self, n: int) -> str:
        if n not in self.digits:
            raise RulesError(f"数 {n} の語は規則ファイルにない(0〜9 の語だけがある。位取りの作り方は文法 md にない)")
        return self.digits[n][0]
