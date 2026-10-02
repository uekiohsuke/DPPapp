"""M5: 造語支援

- 規則(YAML)に従って動く
- 次数・孤立点など辞書にある語を、分解して再現できる。形態素分解も入る
- 未収録の要素に、新しい基本詞の候補を自動で出せる
"""
import json

import pytest
from conftest import FIXTURES, REAL_PUTE, REAL_RULES

from conlang.cli import main
from conlang.core import llm
from conlang.core.rules import Rules
from conlang.core.zpdic import Dictionary
from conlang.languages.pute.coining import AFFIX, HEAD, SHORT, Coiner, ground
from conlang.languages.pute.consistency import etymology_structure


@pytest.fixture
def rules():
    return Rules.load(FIXTURES / "mini_rules.yaml")


@pytest.fixture
def c(mini_pute, rules):
    return Coiner(Dictionary.load(mini_pute), rules)


def add(d, form, meaning, ety=None, short=None):
    w = d.add(form)
    w["translations"] = [{"title": "", "forms": [meaning]}]
    if ety:
        w["contents"] = [{"title": "語源", "text": ety}]
    if short:
        w["variations"] = [{"title": "短縮形", "form": short}]
    return w


# ---------- 規則に従って動く ----------

def test_rules_drive_phonemes(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    assert "ピュテ語の音素に分けられない文字を含む" in Coiner(d, rules).check(["kabo", "yu"]).warnings
    rules.data["phonology"]["vowels"].append("y")
    assert "ピュテ語の音素に分けられない文字を含む" not in Coiner(d, rules).check(["kabo", "yu"]).warnings


def test_rules_drive_affixes(c):
    """規則ファイルの接辞が、部品として使える(動詞化 sa、活用語尾)"""
    assert c.resolve("sa").kind == AFFIX
    assert c.check(["kabo", "sa", "tchu"]).word == "kabosatchu"
    assert c.join(["dresi", "sa"])[0] == "dresisa"


def test_rules_drive_generation(mini_pute, rules):
    rules.data["word_generation"]["length_in_units"] = {3: 1}
    rules.data["word_generation"]["filters"]["max_consonant_run"] = 1
    words = Coiner(Dictionary.load(mini_pute), rules).generate(20, seed=1)
    c = Coiner(Dictionary.load(mini_pute), rules)
    for w in words:
        seq = c.lang.parse(w)
        assert len(seq) == 3
        assert all(not (a in c.lang.consonants and b in c.lang.consonants) for a, b in zip(seq, seq[1:]))


# ---------- 形態素分解と、辞書の語の再現 ----------

def test_analyze_reproduces_existing_words(c):
    """辞書の複合語を分解すると、語源欄の構成どおりの読み方が見つかる(孤立点、次数)"""
    for word, ety in (("kabotchu", ["kabo", "tchu"]), ("dresijeta", ["dresi", "jeta"])):
        a = c.analyze(word)
        assert a.etymology == ety
        top = a.readings[0]
        assert top.forms == ety and top.matches_etymology
        assert c.join(top.forms)[0] == word  # つなぎ直すと元の語になる


def test_analyze_short_form_and_head(c):
    a = c.analyze("dresijeta")
    seg = a.readings[0].segments[1]
    assert (seg.form, seg.kind, seg.head) == ("jeta", SHORT, "jetavo")


def test_analyze_merged_vowel(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    add(d, "thai", "真")
    add(d, "idra", "偽")
    add(d, "thaidra", "真偽", "thai-idra\n真-偽")
    a = Coiner(d, rules).analyze("thaidra")
    r = a.readings[0]
    assert r.forms == ["thai", "idra"] and r.merged == [True] and r.matches_etymology
    assert r.show() == "thai~idra"


def test_analyze_affixes(c):
    a = c.analyze("kabosatchu")
    assert a.readings[0].forms == ["kabo", "sa", "tchu"]
    assert a.readings[0].merged == [False, False]
    # 活用語尾は語末だけ
    assert [r.forms for r in c.analyze("kaboas").readings] == [["kabo", "as"]]
    assert c.analyze("askabo").readings == []
    # ハイフンで区切る接辞の前後では、母音をまとめて読まない
    assert all(not any(r.merged) for r in c.analyze("dresisa").readings)


def test_analyze_finer_reading_matches_etymology(mini_pute, rules):
    """語源欄の部品を、さらに細かく読んだもの(suschwoa = su + schwoa)も、語源欄と一致とする"""
    d = Dictionary.load(mini_pute)
    add(d, "kabosatchu", "外にした節点", "kabo-satchu\n節点-外にする")
    a = Coiner(d, rules).analyze("kabosatchu")
    assert a.readings[0].forms == ["kabo", "sa", "tchu"] and a.readings[0].matches_etymology


def test_check_reports_other_reading(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    add(d, "kabot", "仮1")
    add(d, "chu", "仮2")  # 音素に分けられないが、部品としては読める
    res = Coiner(d, rules).check(["kabo", "tchu"])
    assert any(w.startswith("別の部品の組み合わせとしても読める: kabot + chu") for w in res.warnings)


def test_check_finer_split_is_not_ambiguity(c):
    """意図した部品を、さらに細かく分けただけの読み方は、曖昧さとして数えない"""
    res = c.check(["kabotchu", "dresi"])
    assert not any("別の部品" in w for w in res.warnings)


# ---------- 長さの管理 ----------

def test_shorten(c):
    alts = c.shorten(["dresi", "jetavo"])
    assert [r.word for r in alts] == ["dresijeta"]
    assert alts[0].existing is not None  # 既存語になる案は、後ろに回す(ここでは1件だけ)


def test_long_words(c):
    assert [p.form for p in c.long_words(9)] == ["dresijeta"]
    base, alts = c.shorten_word("kabotchu")
    assert base.forms == ["kabo", "tchu"] and alts == []


# ---------- 基本詞の自動生成 ----------

def test_generate(c):
    a = c.generate(20, seed=3)
    assert a == c.generate(20, seed=3)  # 同じ種なら同じ候補
    assert a != c.generate(20, seed=4)
    assert len(a) == len(set(a)) == 20
    known = {p.form for p in c.parts}
    for w in a:
        seq = c.lang.parse(w)
        assert c.lang.parse_count(w) == 1 and 2 <= len(seq) <= 5
        assert w not in known and not c.readable_as_parts(w)
        assert any(u in c.lang.vowels for u in seq) and any(u in c.lang.consonants for u in seq)
        assert not c.lang.phonotactic_problems(w)


def test_generate_filters_are_floors(c):
    """規則ファイルの条件は最低限。引数で緩めることはできない"""
    for w in c.generate(30, min_vowels=0, seed=5):
        assert any(u in c.lang.vowels for u in c.lang.parse(w))
    for w in c.generate(10, min_vowels=2, seed=5):
        assert sum(1 for u in c.lang.parse(w) if u in c.lang.vowels) >= 2
    assert all(len(c.lang.parse(w)) == 4 for w in c.generate(10, length=4, seed=5))


def test_generate_avoids_stem_affix_readings(c, rules):
    """語幹の接辞は規則ファイルにない(mini_rules)ので、kabo + sa は読めない扱い。辞書の語の連なりは避ける"""
    assert c.readable_as_parts("kabotchu")
    assert c.readable_as_parts("dresijeta")
    assert not c.readable_as_parts("kabox")


# ---------- LLM による分解: 未収録の要素に基本詞の候補 ----------

ANSWER = {"concept": "外の道", "elements": [
    {"role": "核", "meaning": "道", "existing": "dresi", "reason": "道"},
    {"role": "修飾", "meaning": "外側の特別なもの", "existing": "qqq", "reason": "辞書にない語"},
    {"role": "修飾", "meaning": "接辞", "existing": "sa", "reason": "接辞は語ではない"},
]}


def test_ground(c):
    els = ground(c, ANSWER)
    assert [e.form for e in els] == ["dresi", None, None]
    assert els[1].fixed.startswith("LLM が既存語として挙げた qqq は辞書にない")


def test_decompose_suggests_new_words(capsys, mini_pute, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
    args = ["pute", "--dict", str(mini_pute), "--rules", str(FIXTURES / "mini_rules.yaml"),
            "decompose", "外の道", "--response", str(f), "--seed", "7"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "基本詞の候補" in out
    line = next(l for l in out.splitlines() if l.startswith("  - 外側の特別なもの: "))
    cands = line.split(": ", 1)[1].split("、")
    assert len(cands) == 5
    assert main(args) == 0
    assert line in capsys.readouterr().out  # 同じ種なら同じ候補


def test_decompose_with_llm_and_history(tmp_path, mini_pute, capsys, monkeypatch):
    from test_llm import FakeServer
    monkeypatch.setenv("CONLANG_CONFIG_DIR", str(tmp_path / "cfg"))
    s = FakeServer(reply=json.dumps(ANSWER, ensure_ascii=False))
    try:
        llm.save_config(llm.LLMConfig(url=s.url, model="m"))
        proj = tmp_path / "x"
        main(["new", str(proj), "--name", "架空語", "--language", "pute"])
        main(["import", str(proj), str(mini_pute)])
        capsys.readouterr()
        assert main(["pute", "--project", str(proj), "decompose", "外の道"]) == 0
        out = capsys.readouterr().out
        assert "LLM に問い合わせている: m @ " in out and "履歴:" in out
        assert "【造語したい概念】外の道" in s.requests[-1][2]["messages"][0]["content"]
        assert len(list((proj / "llm_log").glob("*-decompose.json"))) == 1
    finally:
        s.close()


# ---------- CLI ----------

def test_cli_commands(capsys, mini_pute):
    base = ["pute", "--dict", str(mini_pute), "--rules", str(FIXTURES / "mini_rules.yaml")]
    assert main(base + ["analyze", "kabotchu"]) == 0
    out = capsys.readouterr().out
    assert "語源欄の構成: kabo-tchu" in out and "1. kabo + tchu  ← 語源欄と一致" in out
    assert main(base + ["shorten", "dresi", "jetavo"]) == 0
    assert "dresijeta" in capsys.readouterr().out
    assert main(base + ["long", "9"]) == 0
    assert "9文字以上の語(1語)" in capsys.readouterr().out
    assert main(base + ["gen", "3", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "新しい基本詞の候補(3個" in out and "子音が1個以上" in out
    assert main(base + ["parts"]) == 0
    assert "sa\t接辞\t動詞化" in capsys.readouterr().out
    assert main(base + ["check", "節点", "nai"]) == 2
    assert main(["pute", "--help-coining"]) == 0
    assert "analyze" in capsys.readouterr().out


# ---------- 実データ ----------

needs_real = pytest.mark.skipif(not (REAL_PUTE.exists() and REAL_RULES.exists()), reason="実データがない")


@needs_real
def test_real_all_compounds_reproduced():
    """語源欄に構成がある語は、すべて分解して語源欄どおりに再現できる"""
    d = Dictionary.load(REAL_PUTE)
    c = Coiner(d, Rules.load(REAL_RULES))
    words = [w for w in d.words if etymology_structure(w)]
    assert len(words) >= 20
    for w in words:
        a = c.analyze(w["entry"]["form"])
        match = [r for r in a.readings if r.matches_etymology]
        assert match, w["entry"]["form"]
        assert c.join(match[0].forms)[0] == w["entry"]["form"]


@needs_real
def test_real_known_words():
    c = Coiner(Dictionary.load(REAL_PUTE), Rules.load(REAL_RULES))
    # 次数 = 辺-数、孤立点 = 節点-外、真偽 = 真~偽(母音をまとめる)
    for word, top in (("thjadrwoqakujeta", ["thjadrwoqaku", "jeta"]),
                      ("diqakusubothtcheb", ["diqakusuboth", "tcheb"]),
                      ("thaidra", ["thai", "idra"])):
        assert c.analyze(word).readings[0].forms == top
    res = c.suggest(["辺", "数"])
    assert "thjadrwoqakujeta" in [r.word for r, _ in res.existing]


@needs_real
def test_real_generate_and_shorten():
    c = Coiner(Dictionary.load(REAL_PUTE), Rules.load(REAL_RULES))
    words = c.generate(30, seed=0)
    assert len(words) == 30 and not set(words) & {p.form for p in c.parts}
    _, alts = c.shorten_word("eshkikijudrasuschwoa")
    assert "eshdrasuschwoa" in [r.word for r in alts]
