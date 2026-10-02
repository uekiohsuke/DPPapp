"""ウリ語の言語別機能(基本の部分)"""
import pytest
from conftest import DATA, FIXTURES

from conlang.cli import main
from conlang.core import registry
from conlang.core.rules import Rules
from conlang.core.validate import ERROR, check_all
from conlang.core.zpdic import Dictionary
from conlang.languages.uri import consistency
from conlang.languages.uri.lang import UriLang

MINI = FIXTURES / "mini_uri.json"
REAL_URI = DATA / "uri.json"
REAL_URI_RULES = DATA / "uri-rules.yaml"
registry.load_builtin()
URI = registry.get("uri")


@pytest.fixture
def lang():
    return UriLang()


def texts(sylls):
    return [s.text for s in sylls]


def test_to_modern(lang):
    assert lang.to_modern("SuKaHuDu") == "sukahudu"
    assert lang.to_modern("KU") == "kuu"              # 子音の後ろの大文字の母音は長音
    assert lang.to_modern("FoTONe") == "fotoone"
    assert lang.to_modern("TenNO") == "tennoo"
    assert lang.to_modern("UliShoRo") == "ulishoro"   # 語頭の大文字の母音は長音ではない
    assert lang.to_modern("ReKiYaYuHan VoRaLangKi") == "rekiyayuhan voralangki"


def test_old_syllables(lang):
    assert lang.old_syllables("SuKaHuDu") == ["su", "ka", "hu", "du"]
    assert lang.old_syllables("FoTONe") == ["fo", "too", "ne"]
    assert lang.old_syllables("KanTi") == ["kan", "ti"]
    assert lang.old_syllables("UliPa") == ["uli", "pa"]


def test_syllabify(lang):
    assert texts(lang.syllabify("sukahudu")) == ["su", "ka", "hu", "du"]
    assert texts(lang.syllabify("kanti")) == ["kan", "ti"]          # CVn
    assert texts(lang.syllabify("rewing")) == ["re", "wing"]        # CVng
    assert texts(lang.syllabify("tokoopan")) == ["to", "koo", "pan"]  # 長音
    assert lang.syllabify("tokoopan")[1].long
    assert texts(lang.syllabify("shoro")) == ["sho", "ro"]
    assert texts(lang.syllabify("ulipa")) == ["u", "li", "pa"]       # uli だけは母音で始まってよい
    assert lang.syllabify("apa") is None
    assert lang.syllabify("noe") is None                             # 母音が続く(近現代の形)
    assert lang.syllabify("kran") is None                            # 子音が続く


def test_split_prefix(lang):
    assert lang.split_prefix("sukoruma") == ("su", "koruma")
    assert lang.split_prefix("voralangki") == ("vora", "langki")
    assert lang.split_prefix("koruma") == ("", "koruma")


MINI_RULES = FIXTURES / "mini_uri_rules.yaml"
MINI_GRAMMAR = FIXTURES / "mini-uri-grammar.md"


def test_lang_from_rules():
    lang = UriLang.from_rules(Rules.load(MINI_RULES))
    assert lang.vowels == ["a", "e", "i", "o", "u"]
    assert "x" in lang.consonants and "ch" not in lang.consonants  # x は音素ではないが綴りに使う。ch は使われない
    assert lang.codas == ["n", "ng"] and lang.vowel_initial == ["uli"]
    assert lang.prefixes == {"su": "動詞(状態名詞)", "lo": "接続詞(句接続名詞)/文章接続詞(文章接続名詞)"}
    assert lang.particles == {"ni": "架空の過去", "tu": "架空の未来", "lu": "架空の否定"}
    assert lang.old_forms == {"noe": ("noye", "架空の古い接続"), "sugiri": ("suri", "指示詞")}
    assert lang.old_prefixes == {"xa": "xu"} and lang.vowel_fixes == [("iyi", "iya")]
    assert lang.enabled("avoid_cuwu") and not UriLang.from_rules(None).enabled("avoid_cuwu")
    r = Rules({"phonology": {"general": {"vowels": {"a": "a", "i": "i"}, "consonants": {"k": "k", "t": "t"}},
                             "syllable": {"units": ["CV", "CVn"], "initial_w_omission": []}}})
    small = UriLang.from_rules(r)
    assert small.consonants == ["k", "t"] and small.codas == ["n"]
    assert small.syllabify("katin") is not None and small.syllabify("kotin") is None and small.syllabify("ulipa") is None


def test_consistency_without_rules():
    """規則ファイルがなければ、音節の検査だけ"""
    d = Dictionary.load(MINI)
    issues = consistency.check_dictionary(d, None)
    by_id = {i.word_id: i.message for i in issues}
    assert set(by_id) == {5, 8}
    assert "近現代の形(半母音の挿入より前)かもしれない" in by_id[5]  # Noe: 母音が続く
    assert "大文字の区切り(koru.ma)" in by_id[8]                      # KoruMa: 大文字の書き漏らし
    assert all(i.level != ERROR for i in issues)  # 旧表記・時代の混在があるので、どれも「注意」
    # 略称(XQ)は音節の検査をしない


def test_consistency_with_rules():
    d = Dictionary.load(MINI)
    add = lambda form, title="名詞": d.words.append(  # noqa: E731
        {"entry": {"id": 100 + len(d.words), "form": form}, "translations": [{"title": title, "forms": ["x"]}],
         "tags": [], "contents": [], "variations": [], "relations": []})
    add("Ni", "情詞")          # 一覧にある情詞
    add("Ko", "情詞")          # 一覧にない情詞
    add("KiYiRa")              # iyi
    add("TuWuMa")              # Cuwu
    add("XaKoRuMa")            # 古い接頭辞 xa-
    add("Mo-KoRuMa")           # 知らない接頭辞 mo-
    add("SuGiRi")              # 近現代の指示詞
    issues = consistency.check_dictionary(d, Rules.load(MINI_RULES))
    msgs = [i.message for i in issues]
    assert "Noe: noe を音節に分けられない(近現代の形。現代の形は noye(架空の古い接続))" in msgs
    assert "Ko: 訳語に「情詞」があるが、規則ファイルの情詞の一覧にない" in msgs
    assert not any(m.startswith("Ni:") for m in msgs)
    assert "規則ファイルの情詞のうち、辞書に「情詞」として載っていないもの: tu、lu" in msgs
    assert "KiYiRa: iyi の並びがある(iya になる)" in msgs
    assert "TuWuMa: 造語で避ける並び Cuwu がある" in msgs
    assert "XaKoRuMa: 古い接頭辞 xa-(今は xu-)で始まっているかもしれない" in msgs
    assert any(m.startswith("Mo-KoRuMa: ハイフンの前の mo- は、意味範疇の接頭辞") for m in msgs)
    assert "SuGiRi: sugiri は近現代の形。現代の形は suri(指示詞)" in msgs


def test_check_all_uses_uri_settings():
    d = Dictionary.load(MINI)
    issues = check_all(d, None, URI)
    assert not any(i.kind == "似た綴り" for i in issues)  # 7文字未満の1文字違いは数えない(KoRuMa と KoruMa)
    assert {i.word_id for i in issues if i.kind in ("音節", "旧表記")} == {5, 8}


def test_transcription_hook():
    to_modern = URI.transcriptions["現代の転写"](None)
    assert to_modern("ToKOPan") == "tokoopan"


def test_cli(capsys):
    base = ["uri", "--dict", str(MINI)]
    assert main(base + ["modern", "FoTONe", "KU"]) == 0
    assert "FoTONe\tfotoone" in capsys.readouterr().out
    assert main(base + ["syllables", "ReWing", "noe"]) == 0
    out = capsys.readouterr().out
    assert "ReWing(rewing): re.wing" in out and "noe: (音節に分けられない)" in out
    assert main(base + ["analyze", "SuKoRuMa"]) == 0
    out = capsys.readouterr().out
    assert "接頭辞: su-(動詞(状態名詞)) + koruma" in out and "koruma は辞書にある: KoRuMa" in out
    assert main(base + ["find", "石"]) == 0
    assert "koruma  (KoRuMa)  架空の石" in capsys.readouterr().out
    assert main(["uri", "--help"]) == 0


def test_cli_check_project(tmp_path, capsys):
    proj = tmp_path / "uri"
    main(["new", str(proj), "--name", "ウリ語", "--language", "uri"])
    main(["import", str(proj), str(MINI)])
    capsys.readouterr()
    assert main(["check", str(proj)]) == 0  # 注意だけ
    assert "言語別の検査 ウリ語" in capsys.readouterr().out


# ---------- 文法 md と規則ファイル ----------

def test_grammar_tables_match():
    from conlang.languages.uri.grammar_check import TABLE_CHECKS
    from conlang.core import grammar_check as GC
    text = MINI_GRAMMAR.read_text(encoding="utf-8")
    rep = GC.run(text, Rules.load(MINI_RULES), TABLE_CHECKS)
    assert rep.problems == []
    assert (rep.anchors, rep.refs) == (9, 9)
    assert rep.prose_anchors == ["compounding", "phonology.syllable"]


@pytest.mark.parametrize("old, new, expected", [
    ("e /e/、i /i/", "e /e/、i /ɪ/", "[phonology.general] 母音 i: 文法 md は 'ɪ'、規則ファイルは 'i'"),
    ("| x | /ks/(音素表にはないが、このように発音する) |", "| x | /ks/ |", "[phonology.special] 特殊な音 x:"),
    ("一般的なものが19個", "一般的なものが20個", "[phonology.notes] 個数(文法 md と規則ファイルの counts) consonant_general:"),
    ("| su- | 動詞(状態名詞) |", "| su- | 動詞(動作名詞) |", "[prefixes] 文法 md にだけある接頭辞の行"),
    ("tu 架空の未来", "tu 架空の未来 / ka 架空の命令", "[particles.list] 情詞 [時相] ka: 文法 md にだけある"),
    ("| 二人称 | pipo | piposha |", "| 二人称 | pipo | pipo |", "[pronouns.personal] 人称代名詞 second plural:"),
    ("| noe | noye |", "| noe | nowe |", "[history.semivowel] 半母音の挿入 noe to:"),
])
def test_grammar_table_differences(old, new, expected):
    from conlang.languages.uri.grammar_check import TABLE_CHECKS
    from conlang.core import grammar_check as GC
    text = MINI_GRAMMAR.read_text(encoding="utf-8")
    assert old in text
    problems = GC.run(text.replace(old, new), Rules.load(MINI_RULES), TABLE_CHECKS).problems
    assert any(p.startswith(expected) for p in problems), problems


def test_grammar_check_survives_missing_rules():
    """規則ファイルに表の項目がないときも、止まらずに「比べられなかった」と出す"""
    from conlang.languages.uri.grammar_check import TABLE_CHECKS
    from conlang.core import grammar_check as GC
    r = Rules.load(MINI_RULES)
    del r.data["particles"]
    problems = GC.run(MINI_GRAMMAR.read_text(encoding="utf-8"), r, TABLE_CHECKS).problems
    assert any(p.startswith("[particles.list] 表を比べられなかった") for p in problems)


def test_cli_grammar_check(tmp_path, capsys):
    proj = tmp_path / "uri"
    main(["new", str(proj), "--name", "ウリ語", "--language", "uri"])
    main(["import", str(proj), str(MINI)])
    main(["rules", "import", str(proj), str(MINI_RULES)])
    main(["grammar", "import", str(proj), str(MINI_GRAMMAR)])
    capsys.readouterr()
    assert main(["grammar", "check", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "目印 9個、ref 9個" in out and "食い違いはない" in out
    assert main(["uri", "--project", str(proj), "grammar-check", "--prompt-only"]) == 0
    assert "【目印: compounding】" in capsys.readouterr().out
    assert main(["uri", "--project", str(proj), "particles"]) == 0
    out = capsys.readouterr().out
    assert "ni  架空の過去    辞書: (辞書にない)" in out
    assert URI.check_grammar(MINI_GRAMMAR.read_text(encoding="utf-8"), Rules.load(MINI_RULES)) == []
    assert URI.llm_grammar_check is not None


@pytest.mark.skipif(not (REAL_URI_RULES.exists() and (DATA / "uri-grammar.md").exists()), reason="実データがない")
def test_real_uri_grammar_matches_rules():
    from conlang.languages.uri.grammar_check import TABLE_CHECKS
    from conlang.core import grammar_check as GC
    rep = GC.run((DATA / "uri-grammar.md").read_text(encoding="utf-8"), Rules.load(REAL_URI_RULES), TABLE_CHECKS)
    assert rep.problems == [] and rep.anchors >= 20


@pytest.mark.skipif(not REAL_URI.exists(), reason="data/uri.json がない")
def test_real_uri_dictionary():
    """実際の辞書: ほとんどの語が音節に分けられ、分けられないのは近現代の形などに限られる"""
    rules = Rules.load(REAL_URI_RULES) if REAL_URI_RULES.exists() else None
    d = Dictionary.load(REAL_URI)
    issues = consistency.check_dictionary(d, rules)
    assert len(issues) <= 15
    assert not any(i.kind == "旧表記" for i in issues)
    modern_hiatus = {"Joi", "Hian", "Foe", "Deon", "Sian", "Noi", "Moin", "Geon", "Noing"}  # 文法 8.3 の近現代の形
    flagged = {i.message.split(":")[0] for i in issues}
    assert modern_hiatus <= flagged
