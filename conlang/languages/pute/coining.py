"""ピュテ語の造語支援(仕様書 4.4)。規則ファイル(YAML)に従って動く

prototype/pute_zougo.py の find / check / suggest / gen / decompose を、規則ファイルから動く形にしたもの。
結果はデータとして返し、表示は cli_coining(CLI)や画面がする。

- 検索: 訳語・語義・語源から既存語を探す
- 組み合わせの検査: 同じ綴りの既存語、別の読み方(曖昧さ)、綴りの近い既存語、音素、音韻規則、長さ
- 提案: キーワードごとに部品の候補を出し、組み合わせを順位づけする(大本の概念が先頭)
- 形態素分解: 語を部品に分ける。複合語の境目で母音をまとめた所も読む(thaidra = thai + idra)
- 長さの管理: 長大語を警告し、部品を短縮形に替えた候補を出す
- 基本詞の自動生成: 音韻規則に合い、既存語と衝突しない綴りを作る
- LLM による分解: 概念を要素に分け、辞書と照らす(プロンプトと、答えの照合)
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

from conlang.core.rules import Rules
from conlang.core.validate import edit_distance
from conlang.core.zpdic import Dictionary

from .consistency import etymology_structure
from .lang import PuteLang

HEAD = "見出し語"
SHORT = "短縮形"
AFFIX = "接辞"
LONG_WORD = 20  # これ以上の文字数を長大語として警告する(試作と同じ)


@dataclass
class Part:
    """造語に使える部品(見出し語、短縮形、接辞)"""
    form: str
    kind: str
    head: str = ""            # 見出し語(接辞は空)
    meanings: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)   # 訳語の区分
    text: str = ""            # 内容欄をつないだもの(検索用)
    ety: str = ""             # 語源欄
    word_id: int | None = None
    affix_kind: str = ""      # 接辞の種類(格接頭辞、動詞化 など)

    def describe(self) -> str:
        if self.kind == AFFIX:
            return f"{self.form}({self.affix_kind})"
        return f"{self.form}({'/'.join(self.meanings[:2])})"


@dataclass
class CheckResult:
    forms: list[str]
    word: str
    notes: list[str]
    warnings: list[str]
    phonemes: list[str] | None
    length: int
    percentile: int
    existing: Part | None = None

    @property
    def hyphen(self) -> str:
        return "-".join(self.forms)


@dataclass
class Reading:
    """形態素分解の1つの読み方"""
    segments: list[Part]
    merged: list[bool]        # 境目ごとに、母音をまとめて読んだか
    matches_etymology: bool = False

    @property
    def forms(self) -> list[str]:
        return [p.form for p in self.segments]

    def show(self) -> str:
        out = self.segments[0].form
        for seg, m in zip(self.segments[1:], self.merged):
            out += ("~" if m else " + ") + seg.form
        return out


@dataclass
class Analysis:
    word: str
    readings: list[Reading]
    etymology: list[str] | None   # 辞書の語なら、語源欄の構成
    existing: Part | None
    truncated: bool = False


@dataclass
class SuggestResult:
    candidates: list[tuple[str, list[Part]]]        # キーワードごとの部品の候補
    missing: list[str]                               # 辞書に当たる語がないキーワード
    existing: list[tuple[CheckResult, list[Part]]]   # すでに辞書にある語になる組み合わせ
    ranked: list[tuple[CheckResult, list[Part]]]     # 新しい組み合わせ(警告が少なく、短い順)


@dataclass
class Element:
    """LLM が分けた要素を、辞書と照らしたもの"""
    role: str
    meaning: str
    reason: str
    claimed: str | None   # LLM が既存語として挙げた語
    part: Part | None     # 辞書で見つかった部品
    fixed: str = ""       # LLM の主張を直したときの説明

    @property
    def form(self) -> str | None:
        return self.part.form if self.part else None


class Coiner:
    def __init__(self, d: Dictionary, rules: Rules | None = None):
        self.d = d
        self.lang = PuteLang.from_rules(rules)
        self.parts: list[Part] = []
        for w in d.words:
            head = w["entry"].get("form", "")
            if not head:
                continue
            meanings = [m for t in w.get("translations", []) for m in t.get("forms", [])]
            kinds = sorted({t.get("title") for t in w.get("translations", []) if t.get("title")})
            text = " ".join(c.get("text", "") for c in w.get("contents", []))
            ety = next((c.get("text", "") for c in w.get("contents", []) if c.get("title") == "語源"), "")
            base = dict(head=head, meanings=meanings, kinds=kinds, text=text, ety=ety, word_id=w["entry"].get("id"))
            self.parts.append(Part(form=head, kind=HEAD, **base))
            for v in w.get("variations", []):
                if v.get("form") and v["form"] != head:
                    self.parts.append(Part(form=v["form"], kind=SHORT, **base))
        self.heads = {p.form: p for p in self.parts if p.kind == HEAD}
        self.affixes: list[Part] = []
        for table, label in ((self.lang.anywhere, "ハイフンで区切る接辞"), (self.lang.stem_affixes, "語幹の接辞"),
                             (self.lang.prefixes, "格接頭辞"), (self.lang.suffixes, "活用語尾")):
            for f, name in table.items():
                self.affixes.append(Part(form=f, kind=AFFIX, affix_kind=name or label))
        self._edges: dict[str, tuple[str | None, str | None]] = {}
        self._by_form: dict[str, list[Part]] = {}
        for p in self.parts:
            self._by_form.setdefault(p.form, []).append(p)

    # ---------- 検索 ----------

    def search(self, keyword: str) -> list[Part]:
        """訳語・語義・語源・見出し語に keyword を含む語を、近い順に返す(試作と同じ点数)"""
        scored = []
        for p in self.parts:
            if p.kind != HEAD:
                continue
            s = 0
            if keyword in p.meanings:
                s = 100
            elif any(keyword in m for m in p.meanings):
                s = 60
            elif keyword in p.text:
                s = 30
            elif keyword == p.form:
                s = 100
            elif keyword in p.form and len(keyword) >= 2 and keyword.isascii():
                s = 20
            if s:
                scored.append((s, p))
        scored.sort(key=lambda x: (-x[0], len(x[1].form)))
        return [p for _, p in scored]

    def forms_of(self, p: Part) -> list[Part]:
        """その語の見出し語と短縮形を、短い順に"""
        return sorted((q for q in self.parts if q.head == p.head), key=lambda q: len(q.form))

    def resolve(self, token: str) -> Part | None:
        """token(見出し語・短縮形・訳語・接辞)から部品を探す。完全一致を優先する"""
        if token in self._by_form:
            return self._by_form[token][0]
        by_mean = [p for p in self.parts if token in p.meanings and p.kind == HEAD]
        if by_mean:
            return by_mean[0]
        return next((a for a in self.affixes if a.form == token), None)

    # ---------- 形態素分解 ----------

    def _lexicon(self) -> list[Part]:
        return self.parts + self.affixes

    def _edge_phonemes(self, form: str) -> tuple[str | None, str | None]:
        """綴りの最初と最後の音素(分けられなければ None)"""
        if form not in self._edges:
            ph = self.lang.parse(form)
            self._edges[form] = (ph[0], ph[-1]) if ph else (None, None)
        return self._edges[form]

    def _is_boundary_affix(self, p: Part) -> bool:
        return p.kind == AFFIX and p.form not in self.lang.stem_affixes

    def readings(self, word: str, limit: int = 300, max_segments: int = 10) -> tuple[list[Reading], bool]:
        """word を部品の連なりとして読む方法を、部品の少ない読み方から順に挙げる(最大 limit 個)。
        複合語の部品どうしの境目では、同じ母音をまとめて読む(前の部品の語末の母音と、次の部品の語頭の母音が重なる)。
        ハイフンで区切る接辞の前後ではまとめない。格接頭辞は語頭だけ、活用語尾は語末だけに置く。
        戻り値は (読み方, 打ち切ったか)"""
        lex = self._lexicon()
        vowels = set(self.lang.vowels)
        n = len(word)
        out: list[Reading] = []
        seen: set[tuple] = set()

        def allowed(p: Part, start: int, end: int) -> bool:
            if p.kind != AFFIX:
                return True
            if p.form in self.lang.stem_affixes or p.form in self.lang.anywhere:
                return True
            if p.affix_kind == "活用語尾":
                return end == n and start > 0
            return start == 0 and end < n  # 格接頭辞

        def go(i: int, prev: Part | None, segs: list[Part], merged: list[bool], budget: int) -> bool:
            if len(out) >= limit:
                return False
            if i == n:
                key = tuple((s.form, s.kind, s.head) for s in segs) + tuple(merged)
                if segs and key not in seen:
                    seen.add(key)
                    out.append(Reading(list(segs), list(merged)))
                return True
            if budget == 0:
                return True
            for p in lex:
                f = p.form
                steps = []
                if word.startswith(f, i):
                    steps.append((i + len(f), False))                  # そのまま続く
                if prev is not None and not self._is_boundary_affix(prev) and not self._is_boundary_affix(p):
                    first, _ = self._edge_phonemes(f)
                    _, last = self._edge_phonemes(prev.form)
                    if first and first == last and first in vowels:  # 母音が重なる
                        rest = f[len(first):]
                        if rest and word.startswith(rest, i):
                            steps.append((i + len(rest), True))
                for end, m in steps:
                    start = i - (len(f) - (end - i)) if m else i
                    if not allowed(p, start, end):
                        continue
                    segs.append(p)
                    if prev is not None:
                        merged.append(m)
                    ok = go(end, p, segs, merged, budget - 1)
                    segs.pop()
                    if prev is not None:
                        merged.pop()
                    if not ok:
                        return False
            return True

        truncated = False
        for k in range(1, max_segments + 1):  # 部品の少ない読み方から
            if not go(0, None, [], [], k):
                truncated = True
                break
        # 同じ部品数なら、見出し語を多く使う順
        out.sort(key=lambda r: (len(r.segments), sum(1 for s in r.segments if s.kind != HEAD), r.show()))
        return out, truncated

    def analyze(self, word: str, limit: int = 300) -> Analysis:
        """形態素分解。辞書の語なら、語源欄の構成と一致する読み方に印を付ける"""
        rs, truncated = self.readings(word, limit)
        existing = self.heads.get(word)
        ety = None
        if existing is not None:
            w = self.d.get(existing.word_id)
            ety = etymology_structure(w) if w else None
        if ety:
            # 語源欄の部品の境目が、読み方の境目にすべて含まれていれば一致とする
            # (語源欄の部品を、さらに細かく読んだもの。suschwoa = su + schwoa)
            ety_bounds = self._bounds(ety)
            for r in rs:
                r.matches_etymology = ety_bounds <= self._reading_bounds(r)
        # 単独の見出し語として読むだけの読み方は、分解ではないので除く
        rs = [r for r in rs if not (len(r.segments) == 1 and r.segments[0].form == word)]
        return Analysis(word, rs, ety, existing, truncated)

    def readable_as_parts(self, word: str) -> bool:
        """既存の部品(語幹の接辞を含む)の連なりとして読めるか。基本詞の生成で避ける"""
        lex = self.parts + [a for a in self.affixes if a.form in self.lang.stem_affixes]
        forms = sorted({p.form for p in lex}, key=len, reverse=True)
        ok = [False] * (len(word) + 1)
        ok[0] = True
        for i in range(len(word)):
            if ok[i]:
                for f in forms:
                    if word.startswith(f, i):
                        ok[i + len(f)] = True
        return ok[len(word)]

    # ---------- 組み合わせの検査 ----------

    def join(self, forms: list[str]) -> tuple[str, list[str]]:
        return self.lang.join(forms)

    def check(self, forms: list[str]) -> CheckResult:
        word, notes = self.join(forms)
        warnings: list[str] = []
        n_ph = self.lang.parse_count(word)
        ph = self.lang.parse(word)
        if n_ph == 0:
            warnings.append("ピュテ語の音素に分けられない文字を含む")
        elif n_ph > 1:
            warnings.append(f"音素への分け方が{n_ph}通りある")
        for bad, provisional in self.lang.phonotactic_problems(word):
            warnings.append(f"同じ母音が並ぶ「{bad}」を含む【仮】" if provisional
                            else f"語の中に現れない並び「{bad}」を含む(音韻規則)")
        existing = self.heads.get(word)
        if existing:
            warnings.append(f"すでに辞書にある語と同じ綴り: {word}({'、'.join(existing.meanings)})")
        others = self._other_readings(word, forms)
        if others:
            warnings.append("別の部品の組み合わせとしても読める: " + " / ".join(r.show() for r in others[:3]))
        near = sorted(((edit_distance(word, h), h) for h in self.heads if h != word), key=lambda x: x[0])
        near = [(dd, h) for dd, h in near if dd <= 2 and len(h) >= 4]
        if near:
            warnings.append("綴りが近い既存語: " + "、".join(
                f"{h}({'/'.join(self.heads[h].meanings[:1])})" for _, h in near[:3]))
        lens = sorted(len(h) for h in self.heads) or [0]
        percentile = round(sum(1 for x in lens if x <= len(word)) / len(lens) * 100)
        if len(word) >= LONG_WORD:
            warnings.append(f"{len(word)}文字。辞書の中でも長い方(上位{100 - percentile + 1}%)")
        return CheckResult(list(forms), word, notes, warnings, ph, len(word), percentile, existing)

    def _other_readings(self, word: str, forms: list[str]) -> list[Reading]:
        """意図した部品とは別の読み方。意図した部品をさらに細かく分けただけのものは除く"""
        rs, _ = self.readings(word, limit=100)
        intended_bounds = self._bounds(forms)
        out = []
        for r in rs:
            if r.forms == list(forms) or (len(r.segments) == 1 and r.segments[0].form == word):
                continue
            if intended_bounds <= self._reading_bounds(r):
                continue
            out.append(r)
        return out

    def _bounds(self, forms: list[str]) -> set[int]:
        """つないだ綴りの中で、2番目以降の部品が始まる位置(母音をまとめたときは、重なった母音の位置)"""
        out = set()
        if not forms:
            return out
        merge = self.lang.merge_flags(forms)
        s = forms[0]
        for i, f in enumerate(forms[1:]):
            joined, _ = self.lang.join([s, f], [merge[i]])
            overlap = len(s) + len(f) - len(joined)
            out.add(len(s) - overlap)
            s = joined
        return out

    def _reading_bounds(self, r: Reading) -> set[int]:
        out, pos = set(), 0
        for i, seg in enumerate(r.segments):
            start = pos
            if i > 0:
                if r.merged[i - 1]:
                    start -= len(self._edge_phonemes(seg.form)[0] or "")
                out.add(start)
            pos = start + len(seg.form)
        return out

    # ---------- 提案 ----------

    def suggest(self, keywords: list[str], any_order: bool = False, per_keyword: int = 3) -> SuggestResult:
        cands, missing = [], []
        for kw in keywords:
            hits = self.search(kw)[:per_keyword]
            if not hits:
                missing.append(kw)
            cands.append((kw, hits))
        if missing:
            return SuggestResult(cands, missing, [], [])
        options = []
        for _, hits in cands:
            opts = []
            for p in hits:
                opts += self.forms_of(p)[:2]
            options.append(opts)
        results, seen = [], set()
        for choice in itertools.product(*options):
            orders = itertools.permutations(range(len(choice))) if any_order else [range(len(choice))]
            for order in orders:
                ps = [choice[i] for i in order]
                key = tuple(p.form for p in ps)
                if key in seen or len({p.head for p in ps}) < len(ps):
                    continue  # 同じ語を2回使う案は除く
                seen.add(key)
                results.append((self.check([p.form for p in ps]), ps))
        existing = [(r, ps) for r, ps in results if r.existing is not None]
        ranked = sorted(((r, ps) for r, ps in results if r.existing is None),
                        key=lambda x: (len(x[0].warnings), x[0].length))
        return SuggestResult(cands, [], existing, ranked)

    # ---------- 長さの管理 ----------

    def shorten(self, forms: list[str], top: int = 10) -> list[CheckResult]:
        """部品を、同じ語の短縮形(見出し語)に替えた組み合わせを、短い順に出す。元より長いものは出さない"""
        options = []
        for f in forms:
            p = self.resolve(f)
            options.append([q.form for q in self.forms_of(p)] if p and p.kind != AFFIX else [f])
        original = self.join(forms)[0]
        out, seen = [], set()
        for combo in itertools.product(*options):
            if list(combo) == list(forms) or combo in seen:
                continue
            seen.add(combo)
            r = self.check(list(combo))
            if r.length < len(original):
                out.append(r)
        out.sort(key=lambda r: (r.existing is not None, len(r.warnings), r.length))
        return out[:top]

    def shorten_word(self, word: str, top: int = 5, readings: int = 20) -> tuple[Reading | None, list[CheckResult]]:
        """既存の語(長大語)を短くする候補。形態素分解の読み方を細かいものまで試し、部品を短縮形に替える。
        戻り値は (基にした分解のうち、語源欄と一致する最初のもの、候補)"""
        a = self.analyze(word)
        base = next((r for r in a.readings if r.matches_etymology), a.readings[0] if a.readings else None)
        found: dict[str, CheckResult] = {}
        for r in a.readings[:readings]:
            for alt in self.shorten(r.forms, top=top * 3):
                if alt.word != word and alt.word not in found:
                    found[alt.word] = alt
        out = sorted(found.values(), key=lambda r: (r.existing is not None, len(r.warnings), r.length))
        return base, out[:top]

    def long_words(self, threshold: int = LONG_WORD) -> list[Part]:
        return sorted((p for p in self.heads.values() if len(p.form) >= threshold), key=lambda p: -len(p.form))

    # ---------- 基本詞の自動生成 ----------

    def generate(self, n: int = 10, length: int | None = None, min_vowels: int | None = None,
                 seed: int | None = None, max_tries: int = 50000) -> list[str]:
        """音韻規則に合う新しい基本詞の候補を作る(仕様書 4.4)。
        音素の数を重み(length_in_units)で選び、母音と子音からすべて同じ確率で選ぶ(secpute.ztl と同じ)。
        規則ファイルの filters は最低限の条件なので、引数で緩めることはできず、厳しくするだけ"""
        rnd = random.Random(seed)
        f = self.lang.gen_filters
        floor_v = int(f.get("min_vowels", 0) or 0)
        min_v = floor_v if min_vowels is None else max(min_vowels, floor_v)
        min_c = int(f.get("min_consonants", 0) or 0)
        max_run = f.get("max_consonant_run")
        min_dist = int(f.get("min_edit_distance", 0) or 0)
        vowels, consonants = self.lang.vowels, self.lang.consonants
        units = vowels + consonants
        lens, weights = zip(*sorted(self.lang.length_weights.items()))
        known = {p.form for p in self.parts}
        heads = list(self.heads)
        out: list[str] = []
        tries = 0
        while len(out) < n and tries < max_tries:
            tries += 1
            k = length or rnd.choices(lens, weights)[0]
            seq = [rnd.choice(units) for _ in range(k)]
            w = "".join(seq)
            if w in out or self.lang.phonotactic_problems(w):
                continue
            if sum(1 for u in seq if u in vowels) < min_v or sum(1 for u in seq if u in consonants) < min_c:
                continue
            if max_run is not None and _consonant_run(seq, vowels) > int(max_run):
                continue
            if self.lang.parse_count(w) != 1:   # 音素への分け方が1通りでなければ避ける
                continue
            if f.get("not_existing_word") and w in known:
                continue
            if f.get("not_readable_as_parts") and self.readable_as_parts(w):
                continue
            if min_dist and any(len(h) >= 3 and edit_distance(w, h) < min_dist for h in heads):
                continue
            out.append(w)
        return out


def _consonant_run(seq: list[str], vowels: list[str]) -> int:
    run = best = 0
    for u in seq:
        run = 0 if u in vowels else run + 1
        best = max(best, run)
    return best


# ---------- LLM による分解 ----------

LLM_RULES = """\
ピュテ語は、曖昧さをなくすことを方針にした人工言語で、文化的設定は学術言語に近い。
語は、既存の語をつなげて作る。つなぎ方の規則は次のとおり。
- 大本の概念を先頭に置き、修飾や限定を後ろへ伸ばしていく(例: 生物-内 = 女性、節点-外 = 孤立点、辺-数 = 次数)
- 部品は、辞書の見出し語か、その短縮形をそのまま使う。部品どうしは単純にくっつける
- 前の部品の語末と次の部品の語頭が同じ母音なら、1つにまとめる(thai + idra → thaidra)
- 既存語で表せるものは、必ず既存語を使う。同じ意味の新しい語は作らない
- 既存の複合語(辞書にある見出し語)も、1つの部品として使ってよい
- 既存語で表せない要素だけを「未収録」とし、新しく基本詞を作る候補として挙げる
"""

LLM_SCHEMA = """\
次の JSON だけを出力する(説明文やコードフェンスは付けない)。

{
  "concept": "造語したい概念",
  "elements": [
    {
      "role": "核" または "修飾",
      "meaning": "この要素の意味(日本語)",
      "existing": "辞書の見出し語または短縮形をそのまま書く。既存語で表せないときは null",
      "reason": "なぜこの語を選んだか、または既存語で表せない理由(1文)"
    }
  ],
  "note": "分解の仕方に迷った点や、別の分け方があればここに書く(省略可)"
}

守ること:
- elements は、大本の概念(核)を先頭にして、後ろへ伸ばす順に並べる。核は1つ
- elements の数は最小にする。細かく分けすぎない
- existing には、下の辞書にある語だけを書く。辞書にない語を書いてはいけない
"""


def inventory_lines(c: Coiner, concept: str | None = None, limit: int = 400) -> list[str]:
    """LLM に渡す辞書の一覧。語数が多いときは、概念の文字列に関係する語を優先して limit 語に絞る"""
    heads = [p for p in c.parts if p.kind == HEAD]
    if len(heads) > limit and concept:
        heads = sorted(heads, key=lambda p: -sum(1 for m in p.meanings if m and (m in concept or concept in m)))[:limit]
    lines = []
    for p in heads:
        short = [q.form for q in c.parts if q.head == p.head and q.kind == SHORT]
        row = f"{p.form} | {'/'.join(p.meanings)}"
        if short:
            row += " | 短縮形: " + ",".join(short)
        if p.ety:
            row += " | 構成: " + p.ety.replace("\n", " = ")
        lines.append(row)
    return lines


def build_decompose_prompt(c: Coiner, concept: str, memo: str = "") -> str:
    out = [LLM_RULES, "【辞書(見出し語 | 訳語 | 短縮形 | 構成)】", *inventory_lines(c, concept), "",
           LLM_SCHEMA, f"【造語したい概念】{concept}"]
    if memo:
        out.append(f"【補足】{memo}")
    return "\n".join(out)


def ground(c: Coiner, data: dict) -> list[Element]:
    """LLM の答えを辞書と照らし合わせる。辞書にない語を既存と主張していたら、未収録に直す(仕様書 4.4)"""
    els = []
    for e in data.get("elements", []) or []:
        if not isinstance(e, dict):
            continue
        ex = e.get("existing")
        ex = str(ex).strip() if ex not in (None, "", "null") else None
        p = c.resolve(ex) if ex else None
        if p is not None and p.kind == AFFIX:
            p = None
        el = Element(str(e.get("role", "")), str(e.get("meaning", "")), str(e.get("reason", "")), ex, p)
        if ex and p is None:
            el.fixed = f"LLM が既存語として挙げた {ex} は辞書にないので、未収録として扱う"
        els.append(el)
    return els
