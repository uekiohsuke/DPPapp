"""ミャミュ語の言語別機能(基本の部分)"""
import pytest
from conftest import DATA, FIXTURES

from conlang.cli import main
from conlang.core import grammar_check as GC
from conlang.core import registry
from conlang.core.rules import Rules, RulesError
from conlang.core.validate import ERROR, NOTICE, check_all
from conlang.core.zpdic import Dictionary
from conlang.languages.myamyu import consistency
from conlang.languages.myamyu import grammar_check as MG
from conlang.languages.myamyu.lang import MyamyuLang

RULES = FIXTURES / "mini_myamyu_rules.yaml"
GRAMMAR = FIXTURES / "mini-myamyu-grammar.md"
REAL_RULES = DATA / "myamyu-rules.yaml"
REAL_GRAMMAR = DATA / "myamyu-grammar.md"
registry.load_builtin()
MYAMYU = registry.get("myamyu")


@pytest.fixture
def lang():
    return MyamyuLang.from_rules(Rules.load(RULES))


# ---------- 規則の読み込みと音 ----------

def test_needs_rules():
    with pytest.raises(RulesError):
        MyamyuLang.from_rules(None)


def test_segment(lang):
    assert lang.segment("nyapo") == ["ny", "a", "p", "o"]   # ny は1つの子音
    assert lang.segment("tox") is None
    assert lang.clusters(lang.segment("aptka")) == ["pt", "tk"]
    assert lang.same_runs(lang.segment("assa")) == ["s"]


def test_apply_phonotactics(lang):
    assert lang.apply_phonotactics("assa") == ("asa", ["同じ子音 s が続くので1つにした"])
    word, notes = lang.apply_phonotactics("apta")
    assert word == "ata" and "最初の子音 p を落とした" in notes[0]
    assert lang.apply_phonotactics("anyka")[0] == "aka"   # ny も1つの子音として落ちる
    assert lang.apply_phonotactics("apppta")[0] == "ata"  # 何度でも当てる
    assert lang.apply_phonotactics("kapa") == ("kapa", [])


# ---------- 動詞 ----------

def test_affix_lookup(lang):
    assert lang.find("時制", "未来").form == "ma"
    assert lang.find("時制", "未来時制").form == "ma"
    assert lang.find("態", "ak").name == "受動態"
    assert lang.find("主語マーカー", "三人称単数").form == "ok"
    assert lang.find("主語マーカー", "三人称不定").form == "okso"
    assert lang.find("格", "処格").form == "ak"
    assert lang.find("法", "希求法") is None
    assert ("mas", "未来時制+未来の時制接辞") in lang.tense_forms()


def test_verb_form(lang):
    chosen = {"時制": lang.find("時制", "未来"), "態": lang.find("態", "受動態"), "相": lang.find("相", "起動相"),
              "主語マーカー": lang.find("主語マーカー", "三人称単数")}
    hyphen, word, notes = lang.verb_form("sum", chosen)
    assert hyphen == "ma-sum-ak-ok-ok" and word == "masumakokok" and notes == []
    # 置かない枠は飛ばす(どの枠を省けるかは文法 md にないので、指定したものだけを置く)
    hyphen, word, _ = lang.verb_form("kap", {"時制": lang.find("時制", "過去"), "主語マーカー": lang.find("主語マーカー", "iks")})
    assert (hyphen, word) == ("pi-kap-iks", "pikapiks")
    assert lang.verb_form("sap", {})[:2] == ("sap", "sap")


def test_verb_form_applies_phonotactics_at_boundaries(lang):
    """枠の境目で存在しない並びになると、最初の子音が落ちる(派生時制 pip + 語幹 tak → p + t)"""
    hyphen, word, notes = lang.verb_form("tak", {"時制": "pip"})
    assert hyphen == "pip-tak" and word == "pitak"
    assert notes == ["存在しない並び pt になるので、最初の子音 p を落とした"]
    hyphen, word, notes = lang.verb_form("sas", {"時制": "mas"})  # s + s → s
    assert (hyphen, word) == ("mas-sas", "masas") and "同じ子音 s" in notes[0]


def test_parse_homographs_by_position(lang):
    """同形の ok(起動相/三人称単数)は、付く位置で決まる"""
    ps = lang.parse_verb("ma-sum-ak-ok-ok")
    assert len(ps) == 1
    p = ps[0]
    assert p["時制"] == ("ma", "未来時制") and p["語幹"] == "sum"
    assert (p["態"].name, p["相"].name, p["主語マーカー"].name) == ("受動態", "起動相", "三人称単数")
    # ハイフンがないと、辞書がないので語幹は決まらない。意図した読み方は候補に入る
    ps = lang.parse_verb("masumakokok")
    assert any(p["語幹"] == "sum" and p["時制"] == ("ma", "未来時制") and p["相"].name == "起動相"
               and p["主語マーカー"].name == "三人称単数" for p in ps)
    assert any(p["語幹"] == "um" and p["時制"][0] == "mas" for p in ps)   # 派生時制 mas + 語幹 um とも読める
    assert any(p["語幹"] == "masum" and p["時制"] is None for p in ps)    # 時制を置かない読み方もある


def test_parse_derived_tense(lang):
    ps = lang.parse_verb("mas-kup-ot")
    assert ps[0]["時制"] == ("mas", "未来時制+未来の時制接辞")
    assert lang.parse_verb("ma-kup-xx") == []


def test_numbers(lang):
    assert lang.number_word(1) == "kia"
    with pytest.raises(RulesError):
        lang.number_word(12)


# ---------- 文法 md と規則ファイル ----------

def test_grammar_tables_match():
    rep = GC.run(GRAMMAR.read_text(encoding="utf-8"), Rules.load(RULES), MG.TABLE_CHECKS)
    assert rep.problems == []
    assert rep.prose_anchors == ["word_order"]


@pytest.mark.parametrize("old, new, expected", [
    ("| 格 | 主格、処格 |", "| 格 | 主格 |", "[overview] 基本情報 格:"),
    ("| 子音 | p, t, k, s, m, ny, f |", "| 子音 | p, t, k, s, m, f |", "[phonology.phonemes] 子音: 規則ファイルにだけある ['ny']"),
    ("| ny | /ɲ/ |", "| ny | /n/ |", "[phonology.ipa] 発音 ny:"),
    ("- 存在しない並び: pt tk nyk", "- 存在しない並び: pt tk", "[phonotactics.forbidden] 存在しない並び: 規則ファイルにだけある ['nyk']"),
    ("| 動詞 | 時制-語幹-態-相-法-主語マーカー |", "| 動詞 | 時制-語幹-態-法-主語マーカー |", "[morphology.structure] verb の構成:"),
    ("| 未来時制 | ma | 架空の未来 |", "| 未来時制 | mo | 架空の未来 |", "[verb.tense.basic] 時制 ma: 規則ファイルにだけある"),
    ("| 未来 | -s |", "| 未来 | -z |", "[verb.tense.suffix] 時制接辞 未来:"),
    ("| 受動態 | ak | 架空の受動 |", "| 受動態 | ak | 違う意味 |", "[verb.voice] 態 ak meaning:"),
    ("| 三人称 | ok | oks | okso |", "| 三人称 | ok | oks | — |", "[verb.subject_marker] 主語マーカー third indefinite:"),
    ("| 主格 | ta | 架空の主体 |\n| 処格 | ak | 架空の場所 |", "| 処格 | ak | 架空の場所 |\n| 主格 | ta | 架空の主体 |",
     "[case.markers] 格の並び:"),
    ("| 1 | kia | k |", "| 1 | kio | k |", "[numbers] 数 1 word:"),
    ("- 例: momo ufkia(一つの架空のもの)", "- 例: momo ufkia(二つの架空のもの)", "[usage.quantity] 数量指定の例 gloss:"),
])
def test_grammar_table_differences(old, new, expected):
    text = GRAMMAR.read_text(encoding="utf-8")
    assert old in text
    problems = GC.run(text.replace(old, new), Rules.load(RULES), MG.TABLE_CHECKS).problems
    assert any(p.startswith(expected) for p in problems), problems


# ---------- 規則ファイルの中の点検 ----------

def test_check_rules_clean():
    assert MG.check_rules(Rules.load(RULES)) == []


def test_check_rules_finds_problems():
    r = Rules.load(RULES)
    d = r.data
    d["phonotactics"]["forbidden_clusters"].append("pa")              # 子音2つでない
    d["verb"]["mood"]["apt"] = {"name": "架空法", "meaning": "x"}      # 禁止された並びを含む
    d["overview"]["items"]["格"] = ["主格", "処格", "与格"]            # 概要と格の表が合わない
    d["verb"]["tense_derived"]["example"]["form"] = "mos"              # 派生時制の例が合わない
    d["numbers"]["digits"][1]["short"] = "s"                           # 略形が語頭の子音でない
    d["usage"]["quantity"]["example"]["number"] = 0                   # 例の数が合わない
    d["case"]["markers"]["is"] = {"name": "属格", "meaning": "x"}      # 相の is と同形(認めていない)
    notes = MG.check_rules(r)
    joined = "\n".join(notes)
    for frag in ("禁止された並び「pa」が、子音2つに分けられない", "「apt」が禁止された並び「pt」を含む",
                 "格: 基本情報には", "派生時制の例 大未来: 例は mos、未来時制の形 + 時制接辞 なら mas",
                 "数 1: 略形 s、語 kia の語頭は k", "数量指定の例 momo ufkia: 訳は 0、kia は 1", "同形「is」が複数の枠にある"):
        assert frag in joined, (frag, notes)


def test_check_rules_missing_items():
    notes = MG.check_rules(Rules({"phonology": {"vowels": ["a"], "consonants": ["k"]}}))
    assert notes and notes[0].startswith("規則ファイルを点検できなかった")


# ---------- 辞書の検査 ----------

def _dict(*forms):
    d = Dictionary.new()
    for f in forms:
        w = d.add(f)
        w["translations"] = [{"title": "", "forms": ["x"]}]
    return d


def test_dictionary_check():
    d = _dict("nyapo", "apta", "kassa", "tox", "ma-sum")
    issues = check_all(d, Rules.load(RULES), MYAMYU)
    by = {(i.word_id, i.kind, i.level) for i in issues}
    assert (2, "音の連なり", ERROR) in by and (3, "音の連なり", NOTICE) in by and (4, "音素", ERROR) in by
    assert not any(i.word_id in (1, 5) for i in issues)
    assert any("規則どおりなら ata" in i.message for i in issues)
    assert consistency.check_dictionary(d, None) == []  # 規則ファイルがなければ言語別の検査はしない


# ---------- CLI ----------

def test_cli(tmp_path, capsys):
    proj = tmp_path / "my"
    main(["new", str(proj), "--name", "ミャミュ語", "--language", "myamyu"])
    main(["rules", "import", str(proj), str(RULES)])
    main(["grammar", "import", str(proj), str(GRAMMAR)])
    base = ["myamyu", "--project", str(proj)]
    capsys.readouterr()
    assert main(base + ["segment", "nyapo", "apta"]) == 0
    out = capsys.readouterr().out
    assert "nyapo: ny.a.p.o" in out and "apta: a.p.t.a  ! 存在しない並び: pt" in out
    assert main(base + ["sound", "kap-ta", "assa"]) == 0
    out = capsys.readouterr().out
    assert "kap-ta-assa → kataasa" in out and "最初の子音 p を落とした" in out  # 母音をまとめる規則はない
    assert main(base + ["verb", "sum", "--tense", "未来", "--voice", "受動態", "--aspect", "ok", "--subject", "三人称単数"]) == 0
    assert "ma-sum-ak-ok-ok → masumakokok" in capsys.readouterr().out
    assert main(base + ["verb", "sum", "--tense", "mas"]) == 0
    assert "mas-sum → masum" in capsys.readouterr().out
    assert main(base + ["verb", "sum", "--mood", "希求法"]) == 2
    assert "使えるもの: am(命令法)" in capsys.readouterr().out
    assert main(base + ["parse", "ma-sum-ak-ok-ok"]) == 0
    assert "相 ok(起動相) / 主語マーカー ok(三人称単数)" in capsys.readouterr().out
    assert main(base + ["affixes"]) == 0
    assert "■ 格: ta(主格)、ak(処格)" in capsys.readouterr().out
    assert main(base + ["number", "1", "5"]) == 0
    out = capsys.readouterr().out
    assert "1: kia(略形 k)" in out and "5: 数 5 の語は規則ファイルにない" in out
    assert main(["grammar", "check", str(proj)]) == 0
    assert "食い違いはない" in capsys.readouterr().out
    assert main(["rules", "show", str(proj)]) == 0
    assert "ミャミュ語の規則としての点検: 問題なし" in capsys.readouterr().out
    assert main(["myamyu", "segment", "a"]) == 2  # 規則ファイルがない


# ---------- 実データ ----------

needs_real = pytest.mark.skipif(not (REAL_RULES.exists() and REAL_GRAMMAR.exists()), reason="実データがない")


@needs_real
def test_real_myamyu():
    r = Rules.load(REAL_RULES)
    rep = GC.run(REAL_GRAMMAR.read_text(encoding="utf-8"), r, MG.TABLE_CHECKS)
    assert rep.problems == [] and rep.anchors >= 21
    assert MG.check_rules(r) == []
    lang = MyamyuLang.from_rules(r)
    assert len(lang.vowels) == 4 and len(lang.consonants) == 12
    # 同形の ol(起動相/三人称単数)を、枠の位置で読み分ける
    p = lang.parse_verb("ze-gaz-af-ol-esh-ol")[0]
    assert (p["相"].name, p["主語マーカー"].name) == ("起動相", "三人称単数")
    assert lang.apply_phonotactics("gafbazssa")[0] == "gabazsa"
