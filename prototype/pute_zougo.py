#!/usr/bin/env python3
"""ピュテ語 造語支援ツール(標準ライブラリのみ)

辞書(secondpute_q.json)の語を部品として、新しい概念の造語案を作り、検査する。

使い方:
  python3 pute_zougo.py find 力 数          訳語・語義・語源に キーワード を含む語を探す
  python3 pute_zougo.py check 節点 外        部品をつないだ形を検査する(部品は 見出し語・短縮形・訳語 のどれでもよい)
  python3 pute_zougo.py suggest 辺 数        キーワードごとに部品の候補を出し、組み合わせを検査して順位づけする
  python3 pute_zougo.py parts                部品(見出し語と短縮形)の一覧を出す
  python3 pute_zougo.py decompose 重力加速度  LLM に概念を要素へ分解させ、既存語と照らし合わせる
      --prompt-only        LLM に渡すプロンプトだけを出す(好きなチャットに貼って使う)
      --response FILE      LLM の答え(JSON)をファイルから読む
      --memo "補足"        概念についての補足をプロンプトに足す
    API を呼ぶときは、環境変数 PUTE_LLM_URL(既定 http://localhost:11434/v1)、
    PUTE_LLM_MODEL、PUTE_LLM_KEY を設定する。OpenAI 互換の API なら使える
  python3 pute_zougo.py gen [個数]           新しい基本詞の候補を作る(音韻規則に合い、既存語と衝突しないもの)
      --len N 音素の数  --seed N 乱数の種  --min-vowels N 母音の最低数
  suggest は、最初のキーワードを大本の概念として、与えた順に並べる(--any-order で並べ替える)

規則は pute-rules.yaml(PUTE_RULES で変えられる。PyYAML が要る)から読む。
辞書のパスは環境変数 PUTE_DICT で変えられる(既定: このファイルと同じ場所の secondpute_q.json)。
"""
import itertools
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.environ.get("PUTE_DICT", os.path.join(HERE, "secondpute_q.json"))

RULES_PATH = os.environ.get("PUTE_RULES", os.path.join(HERE, "pute-rules.yaml"))

# 音素などの規則。pute-rules.yaml から読む(読めないときは、ここにある初期値を使う)
VOWELS = ["wo", "a", "e", "i", "o", "u"]
CONSONANTS = ["sch", "tch", "sh", "sx", "tr", "th", "dr", "s", "k", "t", "d", "j", "q", "v", "b"]
PHONEMES = sorted(VOWELS + CONSONANTS, key=len, reverse=True)
FORBIDDEN = ["aa", "ee", "ii", "oo", "wowo"]
FORBIDDEN_PROVISIONAL = ["uu"]
LENGTH_WEIGHTS = {2: 3, 3: 3, 4: 2, 5: 1}
GEN_FILTERS = {"not_existing_word": True, "not_readable_as_parts": True, "min_edit_distance": 2,
               "min_vowels": 1, "max_consonant_run": 2}


def apply_rules(path=None):
    """規則ファイル(YAML)を読み、音素などの規則を差し替える"""
    global VOWELS, CONSONANTS, PHONEMES, FORBIDDEN, FORBIDDEN_PROVISIONAL, LENGTH_WEIGHTS, GEN_FILTERS
    path = path or RULES_PATH
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            r = yaml.safe_load(f)
    except (ImportError, OSError):
        return False
    ph = r.get("phonology", {})
    VOWELS = list(ph.get("vowels", VOWELS))
    CONSONANTS = [c for group in ph.get("consonants", {}).values() for c in group] or CONSONANTS
    PHONEMES = sorted(VOWELS + CONSONANTS, key=len, reverse=True)
    pt = r.get("phonotactics", {})
    FORBIDDEN = list(pt.get("forbidden_substrings", FORBIDDEN))
    FORBIDDEN_PROVISIONAL = list(pt.get("forbidden_substrings_provisional", FORBIDDEN_PROVISIONAL))
    wg = r.get("word_generation", {})
    LENGTH_WEIGHTS = {int(k): v for k, v in wg.get("length_in_units", LENGTH_WEIGHTS).items()}
    GEN_FILTERS = {**GEN_FILTERS, **wg.get("filters", {})}
    return True


apply_rules()


def load():
    with open(DICT, encoding="utf-8") as f:
        d = json.load(f)
    parts = []  # dict: form, kind(見出し/短縮), head, meanings, kinds, ety
    for w in d["words"]:
        head = w["entry"]["form"]
        if not head:
            continue
        meanings = [m for t in w["translations"] for m in t["forms"]]
        kinds = sorted({t["title"] for t in w["translations"] if t["title"]})
        text = " ".join(c["text"] for c in w["contents"])
        ety = next((c["text"] for c in w["contents"] if c["title"] == "語源"), "")
        entry = dict(form=head, head=head, kind="見出し語", meanings=meanings,
                     kinds=kinds, text=text, ety=ety)
        parts.append(entry)
        for v in w["variations"]:
            if v["form"] and v["form"] != head:
                parts.append(dict(entry, form=v["form"], kind="短縮形"))
    return parts


# ---------- 音素・形態素の分割 ----------

def phoneme_parses(s):
    """s を音素に分ける方法の数と、その1つ(最長一致)。分けられなければ (0, None)"""
    n = len(s)
    count = [0] * (n + 1)
    count[0] = 1
    for i in range(n):
        if count[i]:
            for p in PHONEMES:
                if s.startswith(p, i):
                    count[i + len(p)] += count[i]
    greedy, i = [], 0
    while i < n:
        for p in PHONEMES:
            if s.startswith(p, i):
                greedy.append(p)
                i += len(p)
                break
        else:
            return 0, None
    return count[n], greedy


def morpheme_parses(s, lexicon, limit=50):
    """s を lexicon の語の連なりに分ける方法を列挙する(最大 limit 個)"""
    memo = {}

    def go(i):
        if i == len(s):
            return [[]]
        if i in memo:
            return memo[i]
        out = []
        for w in lexicon:
            if s.startswith(w, i):
                for rest in go(i + len(w)):
                    out.append([w] + rest)
                    if len(out) >= limit:
                        break
            if len(out) >= limit:
                break
        memo[i] = out
        return out

    return go(0)


def join_parts(forms):
    """部品をつなぐ。前の語末と次の語頭が同じ母音(wo を含む)なら1つにまとめる【決定】(thai + idra → thaidra)。
    語の中に同じ母音が並ぶことは、音韻規則(secpute.ztl)で除外されているため"""
    s = forms[0]
    notes = []
    for f in forms[1:]:
        _, a = phoneme_parses(s)
        _, b = phoneme_parses(f)
        if a and b and a[-1] in VOWELS and a[-1] == b[0]:
            s += f[len(b[0]):]
            notes.append(f"母音 {b[0]} が連続するのでまとめた")
        else:
            s += f
    return s, notes


# ---------- 検査 ----------

def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def resolve(token, parts):
    """token(見出し語・短縮形・訳語)から部品を探す。完全一致を優先する"""
    exact = [p for p in parts if p["form"] == token]
    if exact:
        return exact[0]
    by_mean = [p for p in parts if token in p["meanings"] and p["kind"] == "見出し語"]
    if by_mean:
        return by_mean[0]
    return None


def check(forms, parts, intended=None):
    lex = sorted({p["form"] for p in parts}, key=len, reverse=True)
    heads = {p["head"]: p for p in parts if p["kind"] == "見出し語"}
    word, notes = join_parts(forms)
    res = dict(word=word, hyphen="-".join(forms), notes=notes, warnings=[], infos=[])
    res["length"] = len(word)
    n_ph, ph = phoneme_parses(word)
    res["phonemes"] = ph
    if n_ph == 0:
        res["warnings"].append("ピュテ語の音素に分けられない文字を含む")
    elif n_ph > 1:
        res["warnings"].append(f"音素への分け方が{n_ph}通りある")
    for bad in FORBIDDEN:
        if bad in word:
            res["warnings"].append(f"語の中に現れない並び「{bad}」を含む(音韻規則)")
    for bad in FORBIDDEN_PROVISIONAL:
        if bad in word:
            res["warnings"].append(f"同じ母音が並ぶ「{bad}」を含む")
    if word in heads:
        h = heads[word]
        res["warnings"].append(f"すでに辞書にある語と同じ綴り: {word}({'、'.join(h['meanings'])})")
    parses = morpheme_parses(word, lex)
    intended = intended or forms
    def bounds(seq):
        out, pos = set(), 0
        for w in seq[:-1]:
            pos += len(w)
            out.add(pos)
        return out

    ib = bounds(list(forms))  # 意図した部品の境目(母音をまとめた場合はずれるので、そのときは比較しない)
    others = []
    for p in parses:
        if "".join(p) != word or p == list(intended) or p == [word]:
            continue
        if not notes and ib <= bounds(p):
            continue  # 意図した部品を、さらに細かく分けただけ
        others.append(p)
    if others:
        shown = [" + ".join(p) for p in others[:3]]
        res["warnings"].append("別の部品の組み合わせとしても読める: " + " / ".join(shown))
    near = sorted(((edit_distance(word, h), h) for h in heads if h != word), key=lambda x: x[0])
    near = [(d, h) for d, h in near if d <= 2 and len(h) >= 4]
    if near:
        res["warnings"].append("綴りが近い既存語: " + "、".join(f"{h}({'/'.join(heads[h]['meanings'][:1])})" for d, h in near[:3]))
    lens = sorted(len(h) for h in heads)
    rank = sum(1 for l in lens if l <= len(word)) / len(lens)
    res["percentile"] = round(rank * 100)
    if len(word) >= 20:
        res["warnings"].append(f"{len(word)}文字。辞書の中でも長い方(上位{100 - res['percentile'] + 1}%)")
    return res


def show(res, parts_info=None):
    print(f"  {res['word']}   ({res['hyphen']}, {res['length']}文字)")
    if parts_info:
        print("    部品: " + " + ".join(parts_info))
    for n in res["notes"]:
        print("    注: " + n)
    for w in res["warnings"]:
        print("    ! " + w)
    if not res["warnings"]:
        print("    問題は見つからなかった")


def describe(p):
    return f"{p['form']}({'/'.join(p['meanings'][:2])})"


# ---------- 検索 ----------

def search(keyword, parts):
    """訳語・語義・語源・見出し語に keyword を含む語を、近い順に返す"""
    scored = []
    for p in parts:
        if p["kind"] != "見出し語":
            continue
        s = 0
        if keyword in p["meanings"]:
            s = 100
        elif any(keyword in m for m in p["meanings"]):
            s = 60
        elif keyword in p["text"]:
            s = 30
        elif keyword == p["form"]:
            s = 100
        elif keyword in p["form"] and len(keyword) >= 2 and keyword.isascii():
            s = 20
        if s:
            scored.append((s, p))
    scored.sort(key=lambda x: (-x[0], len(x[1]["form"])))
    return [p for s, p in scored]


def best_forms(p, parts):
    """その語の見出し語と短縮形を、短い順に返す"""
    return sorted({q["form"] for q in parts if q["head"] == p["head"]}, key=len)


# ---------- コマンド ----------

def cmd_find(args, parts):
    for kw in args:
        print(f"■ {kw}")
        hits = search(kw, parts)
        if not hits:
            print("  該当する語はない。近い意味の語で探すか、新しく基本詞を作る必要がある")
        for p in hits[:12]:
            forms = best_forms(p, parts)
            sh = f"  短縮形: {', '.join(forms[:-1])}" if len(forms) > 1 else ""
            kinds = "・".join(p["kinds"]) or "区分なし"
            print(f"  {p['form']}  {'/'.join(p['meanings'])}  [{kinds}]{sh}")
            if p["ety"]:
                print("      語源: " + p["ety"].replace("\n", " ＝ "))


def cmd_check(args, parts):
    forms, info = [], []
    for t in args:
        p = resolve(t, parts)
        if p is None:
            print(f"部品 {t!r} は辞書にない。見出し語・短縮形・訳語のどれかで指定する")
            return
        forms.append(p["form"])
        info.append(describe(p))
    show(check(forms, parts), info)


def cmd_suggest(args, parts, top=10):
    any_order = "--any-order" in args
    args = [a for a in args if a != "--any-order"]
    cands = []
    for kw in args:
        hits = search(kw, parts)[:3]
        if not hits:
            print(f"「{kw}」に当たる語が辞書にない。基本詞を新しく作るか、別の語で言い換える")
            return
        opts = []
        for p in hits:
            for f in best_forms(p, parts)[:2]:
                opts.append((f, describe(p)))
        cands.append((kw, opts))
        print(f"「{kw}」の候補: " + "、".join(describe(p) for p in hits))
    print()
    results, seen = [], set()
    for choice in itertools.product(*[c[1] for c in cands]):
        orders = itertools.permutations(range(len(choice))) if any_order else [range(len(choice))]
        for order in orders:
            forms = [choice[i][0] for i in order]
            info = [choice[i][1] for i in order]
            key = tuple(forms)
            heads_used = [next(q["head"] for q in parts if q["form"] == f) for f in forms]
            if key in seen or len(set(heads_used)) < len(heads_used):
                continue  # 同じ語を2回使う案は除く
            seen.add(key)
            r = check(forms, parts)
            results.append((len(r["warnings"]), r["length"], r, info))
    existing = [(r, info) for _, _, r, info in results
                if any(w.startswith("すでに辞書にある語") for w in r["warnings"])]
    if existing:
        print("★ この組み合わせは、すでに辞書にある語になっている(新しく作る必要がないかもしれない):")
        for r, info in existing:
            show(r, info)
        print()
    results = [x for x in results if x[2] not in [e[0] for e in existing]]
    results.sort(key=lambda x: (x[0], x[1]))
    print(f"組み合わせ案(警告が少なく、短いものから。全{len(results)}案のうち{min(top, len(results))}案):")
    for _, _, r, info in results[:top]:
        show(r, info)
    print("\n注: 造語は、大本の概念を先頭に置き、後ろへ伸ばしていく。最初のキーワードを大本として扱った。並べ替えて見るときは --any-order")


def cmd_parts(args, parts):
    for p in parts:
        print(f"{p['form']}\t{p['kind']}\t{'/'.join(p['meanings'])}\t{p['head'] if p['kind'] == '短縮形' else ''}")




# ---------- 基本詞の自動生成 ----------

def known_forms(parts):
    """すでに使われている綴り(見出し語、短縮形)と、接辞の綴り"""
    forms = {p["form"] for p in parts}
    return forms


def consonant_run(seq):
    """音素の並びの中で、子音が最大いくつ続くか"""
    run = best = 0
    for u in seq:
        run = 0 if u in VOWELS else run + 1
        best = max(best, run)
    return best


def generate_words(parts, n=10, length=None, min_vowels=None, seed=None, max_tries=50000):
    """音韻規則(pute-rules.yaml)に合う新しい基本詞の候補を作る。
    音素を2〜5個、母音と子音からすべて同じ確率で選ぶ(secpute.ztl と同じ)。
    そのうえで、既存語との衝突を避けるフィルタを通す"""
    import random
    rnd = random.Random(seed)
    if min_vowels is None:
        min_vowels = GEN_FILTERS.get("min_vowels", 0)
    max_run = GEN_FILTERS.get("max_consonant_run")
    units = VOWELS + CONSONANTS
    lens, weights = zip(*sorted(LENGTH_WEIGHTS.items()))
    lex = sorted({p["form"] for p in parts}, key=len, reverse=True)
    heads = [p["form"] for p in parts if p["kind"] == "見出し語"]
    known = known_forms(parts)
    out, tries = [], 0
    while len(out) < n and tries < max_tries:
        tries += 1
        k = length or rnd.choices(lens, weights)[0]
        seq = [rnd.choice(units) for _ in range(k)]
        w = "".join(seq)
        if any(bad in w for bad in FORBIDDEN + FORBIDDEN_PROVISIONAL):
            continue
        if sum(1 for u in seq if u in VOWELS) < min_vowels:
            continue
        if max_run is not None and consonant_run(seq) > max_run:
            continue
        if w in out:
            continue
        if phoneme_parses(w)[0] != 1:   # 音素への分け方が1通りでなければ避ける
            continue
        if GEN_FILTERS.get("not_existing_word") and w in known:
            continue
        if GEN_FILTERS.get("not_readable_as_parts") and morpheme_parses(w, lex, limit=1):
            continue
        d = GEN_FILTERS.get("min_edit_distance", 0)
        if d and any(len(h) >= 3 and edit_distance(w, h) < d for h in heads):
            continue
        out.append(w)
    return out


def cmd_gen(args, parts):
    n, length, seed, min_vowels = 10, None, None, None
    it = iter(args)
    for a in it:
        if a == "--len":
            length = int(next(it))
        elif a == "--seed":
            seed = int(next(it))
        elif a == "--min-vowels":
            min_vowels = int(next(it))
        elif a.isdigit():
            n = int(a)
    words = generate_words(parts, n, length, min_vowels, seed)
    print(f"新しい基本詞の候補({len(words)}個。音素の数 {'指定なし(重み付き)' if not length else length}):")
    for w in words:
        print(f"  {w}   ({len(phoneme_parses(w)[1])}音素)")
    print("\n注: 母音と子音を同じ確率で選び、母音が1個以上・子音の連続が2個以下のものだけを残す【仮】(pute-rules.yaml の filters)")


# ---------- LLM による分解 ----------

RULES = """\
ピュテ語は、曖昧さをなくすことを方針にした人工言語で、文化的設定は学術言語に近い。
語は、既存の語をつなげて作る。つなぎ方の規則は次のとおり。
- 大本の概念を先頭に置き、修飾や限定を後ろへ伸ばしていく(例: 生物-内 = 女性、節点-外 = 孤立点、辺-数 = 次数)
- 部品は、辞書の見出し語か、その短縮形をそのまま使う。部品どうしは単純にくっつける
- 前の部品の語末と次の部品の語頭が同じ単母音なら、1つにまとめる(thai + idra → thaidra)
- 既存語で表せるものは、必ず既存語を使う。同じ意味の新しい語は作らない
- 既存の複合語(辞書にある見出し語)も、1つの部品として使ってよい
- 既存語で表せない要素だけを「未収録」とし、新しく基本詞を作る候補として挙げる
"""

SCHEMA = """\
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


def inventory_lines(parts, concept=None, limit=400):
    """LLM に渡す辞書の一覧。語数が多いときは、概念の文字列に関係する語を優先して limit 語に絞る"""
    heads = [p for p in parts if p["kind"] == "見出し語"]
    if len(heads) > limit and concept:
        def rel(p):
            return sum(1 for m in p["meanings"] if m and (m in concept or concept in m))
        heads = sorted(heads, key=lambda p: -rel(p))[:limit]
    lines = []
    for p in heads:
        short = [q["form"] for q in parts if q["head"] == p["head"] and q["kind"] == "短縮形"]
        row = f"{p['form']} | {'/'.join(p['meanings'])}"
        if short:
            row += " | 短縮形: " + ",".join(short)
        if p["ety"]:
            row += " | 構成: " + p["ety"].replace("\n", " = ")
        lines.append(row)
    return lines


def build_prompt(concept, parts, memo=""):
    out = [RULES, "【辞書(見出し語 | 訳語 | 短縮形 | 構成)】", *inventory_lines(parts, concept), "",
           SCHEMA, f"【造語したい概念】{concept}"]
    if memo:
        out.append(f"【補足】{memo}")
    return "\n".join(out)


def extract_json(text):
    import re
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("JSON が見つからない")
    return json.loads(text[i:j + 1])


def call_llm(prompt):
    """OpenAI 互換のエンドポイント(Ollama、LM Studio、llama.cpp、Gemini の互換 API など)を呼ぶ"""
    import urllib.request
    base = os.environ.get("PUTE_LLM_URL", "http://localhost:11434/v1").rstrip("/")
    model = os.environ.get("PUTE_LLM_MODEL", "")
    key = os.environ.get("PUTE_LLM_KEY", "")
    if not model:
        raise SystemExit("環境変数 PUTE_LLM_MODEL にモデル名を入れる(PUTE_LLM_URL、PUTE_LLM_KEY も必要なら)。"
                         "API を使わないときは --prompt-only で出したプロンプトを貼り、--response で答えを読み込む")
    body = json.dumps({"model": model, "temperature": 0.2,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + key} if key else {})})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def ground(data, parts):
    """LLM の答えを辞書と照らし合わせる。辞書にない語を既存と主張していたら、未収録に直す"""
    els = []
    for e in data.get("elements", []):
        ex = e.get("existing")
        p = resolve(ex, parts) if ex else None
        item = dict(role=e.get("role", ""), meaning=e.get("meaning", ""), reason=e.get("reason", ""),
                    part=p, claimed=ex, form=(ex if p and p["form"] == ex else (p["form"] if p else None)))
        if ex and p is None:
            item["fixed"] = f"LLM が既存語として挙げた {ex} は辞書にないので、未収録として扱う"
        els.append(item)
    return els


def suggest_new_words(missing, parts, per=5):
    """未収録の要素ごとに、新しい基本詞の候補を出す(音韻規則に合い、既存語と衝突しないもの)"""
    for e in missing:
        cands = generate_words(parts, per)
        print(f"  - {e['meaning']}: " + "、".join(cands))


def render(concept, els, parts, note=""):
    n = len(els)
    names = []
    for e in els:
        names.append(f"{e['form']}({e['meaning']})" if e["form"] else f"〈{e['meaning']}〉")
    missing = [e for e in els if not e["form"]]
    print(f"{concept} は、{','.join(names)} という{n}要素に分解できる(大本の概念が先頭)。")
    if missing:
        print("そのうち、" + "、".join(f"「{e['meaning']}」" for e in missing) + " は既存語にない。")
    else:
        print("すべて既存語で表せる。")
    print()
    for i, e in enumerate(els, 1):
        mark = "既存" if e["form"] else "未収録"
        print(f"  {i}. [{e['role']}] {e['meaning']}  → {e['form'] or '(未収録)'}  [{mark}]")
        if e["reason"]:
            print(f"       理由: {e['reason']}")
        if e.get("fixed"):
            print(f"       ! {e['fixed']}")
    if note:
        print(f"\n分解についての補足(LLM): {note}")
    print()
    forms = [e["form"] for e in els if e["form"]]
    if len(forms) < 2:
        print("既存語の要素が1つ以下なので、つないだ形の検査は省く。")
        if missing:
            print("\n新しく作る候補の要素(基本詞にするか、別の言い方で既存語に寄せるかを決める):")
            suggest_new_words(missing, parts)
    elif not missing and forms:
        print("つないだ形の検査:")
        show(check(forms, parts), [describe(e["part"]) for e in els])
    elif forms:
        print("既存語だけでつないだ部分の検査(未収録の要素は、新しい語ができてから足す):")
        show(check(forms, parts), [describe(e["part"]) for e in els if e["part"]])
        print("\n新しく作る候補の要素(基本詞にするか、別の言い方で既存語に寄せるかを決める):")
        suggest_new_words(missing, parts)
    print("\n注: 分解の仕方は LLM の提案で、ヒューリスティックなもの。要素と順序は人が決める。")


def cmd_decompose(args, parts):
    prompt_only = "--prompt-only" in args
    resp = None
    if "--response" in args:
        resp = args[args.index("--response") + 1]
    memo = ""
    if "--memo" in args:
        memo = args[args.index("--memo") + 1]
    skip = {"--prompt-only", "--response", resp, "--memo", memo}
    words = [a for a in args if a not in skip]
    if not words:
        print("概念を指定する。例: python3 pute_zougo.py decompose 重力加速度")
        return
    concept = " ".join(words)
    prompt = build_prompt(concept, parts, memo)
    if prompt_only:
        print(prompt)
        return
    if resp:
        with open(resp, encoding="utf-8") as f:
            text = f.read()
    else:
        text = call_llm(prompt)
    try:
        data = extract_json(text)
    except ValueError as err:
        print(f"LLM の答えを読めなかった: {err}\n--- 答え ---\n{text}")
        return
    render(data.get("concept", concept), ground(data, parts), parts, data.get("note", ""))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    parts = load()
    cmd, args = sys.argv[1], sys.argv[2:]
    table = dict(find=cmd_find, check=cmd_check, suggest=cmd_suggest, parts=cmd_parts, decompose=cmd_decompose, gen=cmd_gen)
    if cmd not in table:
        print(__doc__)
        return
    table[cmd](args, parts)


if __name__ == "__main__":
    main()