"""M3: 規則を YAML に書き、読み込んでアプリが使える"""
import hashlib
import re

import pytest
from conftest import DATA, FIXTURES, REAL_PUTE

from conlang.cli import main
from conlang.core.project import Project
from conlang.core.rules import Rules, RulesError
from conlang.languages.pute import rules as PR
from conlang.languages.pute import zougo

REAL_RULES = DATA / "pute-rules.yaml"
REAL_GRAMMAR = DATA / "pute2-grammar.md"
needs_real_rules = pytest.mark.skipif(not REAL_RULES.exists(), reason="data/pute-rules.yaml がない")


@pytest.fixture
def mini_rules():
    return FIXTURES / "mini_rules.yaml"


@pytest.fixture(autouse=True)
def reset_zougo_rules():
    """zougo の規則はモジュール全体で共有なので、テストごとに初期値へ戻す"""
    zougo.apply_rules(None)
    yield
    zougo.apply_rules(None)


# ---------- 読み込み(共通) ----------

def test_load_and_get(mini_rules):
    r = Rules.load(mini_rules)
    assert r.language == "架空語"
    assert r.get("phonology", "vowels")[-1] == "wo"
    assert r.get("nothing", "here", default=1) == 1


def test_statuses(mini_rules):
    r = Rules.load(mini_rules)
    paths = [s.path for s in r.statuses()]
    assert paths[:3] == ["phonology", "phonotactics", "word_generation"]
    assert "compounding.vowel_merge" in paths and "checks[1]" in paths
    assert r.statuses()[0].ref == "1.1"
    unsettled = {(s.path, s.status) for s in r.unsettled()}
    assert unsettled == {("phonotactics", "メモ"), ("word_generation", "メモ"), ("compounding.vowel_merge", "仮"),
                         ("compounding.open_question", "未確認"), ("checks[1]", "仮")}
    assert next(s for s in r.unsettled() if s.path == "checks[1]").id == "terminology"


def test_invalid_rules(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("a: [1, 2", encoding="utf-8")
    with pytest.raises(RulesError):
        Rules.load(f)
    f.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(RulesError):
        Rules.load(f)
    f.write_text("", encoding="utf-8")
    assert Rules.load(f).data == {}


# ---------- プロジェクト ----------

def test_project_rules(tmp_path, mini_rules):
    p = Project.create(tmp_path / "x", "架空語", "pute")
    assert p.load_rules() is None
    assert not (p.root / "rules").exists()
    before = hashlib.sha256(mini_rules.read_bytes()).hexdigest()
    assert p.import_rules(mini_rules) is None  # 前の規則はないのでバックアップなし
    assert p.rules_path.read_bytes() == mini_rules.read_bytes()
    assert hashlib.sha256(mini_rules.read_bytes()).hexdigest() == before
    bak = p.import_rules(mini_rules)
    assert bak is not None and bak.read_bytes() == mini_rules.read_bytes()
    assert p.load_rules().language == "架空語"


def test_import_bad_rules_keeps_old(tmp_path, mini_rules):
    p = Project.create(tmp_path / "x", "架空語")
    p.import_rules(mini_rules)
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [", encoding="utf-8")
    with pytest.raises(RulesError):
        p.import_rules(bad)
    assert p.rules_path.read_bytes() == mini_rules.read_bytes()


# ---------- ピュテ語の規則の解釈 ----------

def test_phonemes(mini_rules):
    r = Rules.load(mini_rules)
    assert len(PR.vowels(r)) == 6 and len(PR.consonants(r)) == 15
    assert PR.phonemes(r)[0] == "sch"


def test_inflection_table(mini_rules):
    r = Rules.load(mini_rules)
    noun = PR.inflection_table(r, "noun", "kabo")
    assert len(noun) == 2 * 3
    forms = {(f.state, f.tense): f.form for f in noun}
    assert forms[("一般", "常態")] == "kabo"
    assert forms[("高", "過去")] == "kabo-bes"  # 状態形 → 時制の順、ハイフンは語幹とのあいだだけ
    assert len(PR.inflection_table(r, "verb")) == 3 * 4
    adj = {(f.state, f.tense): f.form for f in PR.inflection_table(r, "adjective")}
    assert adj[("一般", "常態")] == "X-wosh" and adj[("高", "現在")] == "X-bas"
    adv = {(f.state, f.tense): f.form for f in PR.inflection_table(r, "adverb")}
    assert adv[("一般", "常態")] == "X-woj" and adv[("低", "否定")] == "X-qov"
    with pytest.raises(RulesError):
        PR.inflection_table(r, "pronoun")


def test_format_table(mini_rules):
    text = PR.format_table(Rules.load(mini_rules), "noun")
    assert "名詞の活用(6通り)" in text
    assert "| 高 | X-b | X-bas | X-bes |" in text


def test_check_rules_clean(mini_rules):
    assert PR.check_rules(Rules.load(mini_rules)) == []


def test_check_rules_finds_problems(mini_rules):
    r = Rules.load(mini_rules)
    r.data["phonology"]["consonants"]["T"].append("th")  # ztl にあった th の重複
    r.data["inflection"]["tense"]["noun"]["未来"] = "ix"  # x は音素にない
    r.data["inflection"]["state"].pop("verb")
    problems = PR.check_rules(r)
    assert "子音が重複している: th" in problems
    assert "inflection.tense.noun.未来 の「ix」が音素に分けられない" in problems
    assert any("verb の state / tense の表がない" in p for p in problems)


# ---------- 造語支援が規則を使う ----------

def test_apply_rules_changes_and_resets(mini_rules):
    r = Rules.load(mini_rules)
    r.data["phonology"]["vowels"].append("y")
    zougo.apply_rules(r.data)
    assert "y" in zougo.VOWELS and "y" in zougo.PHONEMES
    zougo.apply_rules(None)
    assert "y" not in zougo.VOWELS


def test_check_uses_phonotactics(mini_pute, mini_rules):
    zougo.apply_rules(Rules.load(mini_rules).data)
    parts = zougo.load(mini_pute)
    res = zougo.check(["dresi", "jetavo"], parts)
    assert not any("現れない並び" in w for w in res["warnings"])
    # 部品の境目で同じ母音が並ぶときは、まとめるので aa にならない
    res = zougo.check(["jeta", "abo"], parts)
    assert res["word"] == "jetabo" and res["notes"] == ["母音 a が連続するのでまとめた【仮】"]
    # 部品の中にあるときは、音韻規則の警告になる
    res = zougo.check(["kaab", "tchu"], parts)
    assert "語の中に現れない並び「aa」を含む(音韻規則)" in res["warnings"]
    res = zougo.check(["kuub"], parts)
    assert "同じ母音が並ぶ「uu」を含む【仮】" in res["warnings"]


def test_vowel_merge_includes_wo():
    assert zougo.join_parts(["thai", "idra"])[0] == "thaidra"
    word, notes = zougo.join_parts(["kawo", "wosa"])
    assert word == "kawosa" and notes


def test_generate_words(mini_pute, mini_rules):
    zougo.apply_rules(Rules.load(mini_rules).data)
    parts = zougo.load(mini_pute)
    a = zougo.generate_words(parts, 20, seed=3)
    assert a == zougo.generate_words(parts, 20, seed=3)  # 同じ種なら同じ候補
    assert len(a) == 20 and len(set(a)) == 20
    known = {p["form"] for p in parts}
    for w in a:
        n, seq = zougo.phoneme_parses(w)
        assert n == 1 and 2 <= len(seq) <= 5
        assert w not in known
        assert any(u in zougo.VOWELS for u in seq)
        assert zougo.consonant_run(seq) <= 2
        assert not any(bad in w for bad in zougo.FORBIDDEN + zougo.FORBIDDEN_PROVISIONAL)


# ---------- CLI ----------

def test_cli_rules(tmp_path, mini_pute, mini_rules, capsys):
    proj = tmp_path / "x"
    main(["new", str(proj), "--name", "架空語", "--language", "pute"])
    main(["import", str(proj), str(mini_pute)])
    assert main(["rules", "import", str(proj), str(mini_rules)]) == 0
    assert main(["rules", "show", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "[仮] compounding.vowel_merge" in out
    assert "ピュテ語の規則としての点検: 問題なし" in out
    assert main(["pute", "--project", str(proj), "inflect", "noun", "kabo"]) == 0
    assert "| 高 | kabo-b | kabo-bas | kabo-bes |" in capsys.readouterr().out
    assert main(["pute", "--project", str(proj), "gen", "5", "--seed", "1"]) == 0
    assert "新しい基本詞の候補(5個" in capsys.readouterr().out
    assert main(["rules", "show", str(mini_rules), "--all"]) == 0
    assert "[決定] phonology" in capsys.readouterr().out


def test_cli_inflect_needs_rules(mini_pute, capsys):
    main(["pute", "--dict", str(mini_pute), "inflect"])
    assert "規則ファイルから作る" in capsys.readouterr().out


# ---------- 実データ(data/ にあるとき) ----------

@needs_real_rules
def test_real_rules_load_clean():
    r = Rules.load(REAL_RULES)
    assert PR.check_rules(r) == []
    assert len(PR.vowels(r)) == 6 and len(PR.consonants(r)) == 15
    assert len(PR.inflection_table(r, "noun")) == 24
    assert len(PR.inflection_table(r, "verb")) == 30


@needs_real_rules
def test_real_rules_match_zougo_defaults():
    """試作の初期値と規則ファイルが同じ(規則を読めないときも、同じように動く)"""
    zougo.apply_rules(None)
    before = (sorted(zougo.PHONEMES), zougo.FORBIDDEN, zougo.FORBIDDEN_PROVISIONAL, zougo.LENGTH_WEIGHTS, zougo.GEN_FILTERS)
    zougo.apply_rules(Rules.load(REAL_RULES).data)
    after = (sorted(zougo.PHONEMES), zougo.FORBIDDEN, zougo.FORBIDDEN_PROVISIONAL, zougo.LENGTH_WEIGHTS, zougo.GEN_FILTERS)
    assert before == after


def _grammar_table(text, heading):
    """文法 md の節 heading の、最後の展開表(| 状態形 | 常態 | …)を {(状態形, 時制): 形} にする"""
    sec = text.split(heading, 1)[1].split("\n### ", 1)[0]
    rows = [l for l in sec.splitlines() if l.startswith("| ")]
    start = max(i for i, l in enumerate(rows) if l.startswith("| 状態形 |"))
    header = [c.strip() for c in rows[start].strip("|").split("|")]
    out = {}
    for l in rows[start + 1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        state = re.sub(r"(状態)?形$", "", cells[0])
        for t, f in zip(header[1:], cells[1:]):
            out[(state, t)] = f
    return out


@needs_real_rules
@pytest.mark.skipif(not REAL_GRAMMAR.exists(), reason="data/pute2-grammar.md がない")
def test_real_inflection_matches_grammar_md():
    """規則ファイルから作った活用表が、文法 md(8.1、8.2)の展開表と一致する"""
    r = Rules.load(REAL_RULES)
    text = REAL_GRAMMAR.read_text(encoding="utf-8")
    for heading, cls in (("### 8.1", "noun"), ("### 8.2", "verb")):
        expected = _grammar_table(text, heading)
        got = {(f.state, f.tense): f.form for f in PR.inflection_table(r, cls)}
        assert got == expected, cls


@needs_real_rules
@pytest.mark.skipif(not REAL_PUTE.exists(), reason="data/secondpute.json がない")
def test_real_generated_words_avoid_dictionary():
    zougo.apply_rules(Rules.load(REAL_RULES).data)
    parts = zougo.load(REAL_PUTE)
    words = zougo.generate_words(parts, 30, seed=0)
    assert len(words) == 30
    known = {p["form"] for p in parts}
    assert not set(words) & known
