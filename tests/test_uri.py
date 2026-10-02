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


def test_lang_from_rules():
    r = Rules({"phonology": {"vowels": ["a", "i"], "consonants": {"g": ["k", "t"]}},
               "syllable": {"codas": ["n"], "vowel_initial_words": []},
               "affixes": {"prefix": {"forms": {"ka": "仮"}}}})
    lang = UriLang.from_rules(r)
    assert lang.vowels == ["a", "i"] and lang.consonants == ["k", "t"] and lang.codas == ["n"]
    assert lang.syllabify("katin") is not None and lang.syllabify("kotin") is None
    assert lang.syllabify("ulipa") is None and lang.prefixes == {"ka": "仮"}


def test_consistency():
    d = Dictionary.load(MINI)
    issues = consistency.check_dictionary(d, None)
    by_id = {i.word_id: i.message for i in issues}
    assert set(by_id) == {5, 8}
    assert "近現代の形" in by_id[5]                       # Noe: 母音が続く
    assert "大文字の区切り(koru.ma)" in by_id[8]          # KoruMa: 大文字の書き漏らし
    assert all(i.level != ERROR for i in issues)          # 旧表記・時代の混在があるので、どれも「注意」
    # 略称(XQ)は音節の検査をしない


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
