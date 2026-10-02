"""M4: 整合性チェック

- 誤りを含むままの辞書で、誤記6件と用語1件を検出できる。修正済みの辞書では検出が0件(誤検出がない)
- 文法 md と規則ファイルの表の食い違いを、コードで検出できる
- 文章の記述は LLM に候補を挙げさせる(プロンプト、答えの読み取り、履歴、変わったときだけ実行)
"""
import json

import pytest
from conftest import FIXTURES, REAL_GRAMMAR, REAL_PUTE, REAL_PUTE_TYPO, REAL_RULES

from conlang.cli import main
from conlang.core import llm_log, registry
from conlang.core.project import Project
from conlang.core.rules import Rules
from conlang.core.validate import ERROR, NOTICE, check_all, check_similar, check_terminology
from conlang.core.zpdic import Dictionary
from conlang.languages.pute import consistency as C
from conlang.languages.pute import grammar_check as G
from conlang.languages.pute import phonology as P
from conlang.languages.pute import rules as PR

registry.load_builtin()
PUTE = registry.get("pute")
G_TEXT_EMPTY = "# 空の文法\n"


@pytest.fixture
def rules():
    return Rules.load(FIXTURES / "mini_rules.yaml")


@pytest.fixture
def grammar():
    return (FIXTURES / "mini-grammar.md").read_text(encoding="utf-8")


def errors(issues):
    return [i for i in issues if i.level == ERROR]


def etymology(d, wid, text):
    w = d.get(wid)
    w["contents"] = [c for c in w["contents"] if c["title"] != "語源"] + [{"title": "語源", "text": text}]


# ---------- 辞書の整合性(架空の辞書) ----------

def test_clean_dictionary_has_no_errors(mini_pute, rules):
    assert errors(check_all(Dictionary.load(mini_pute), rules, PUTE)) == []


def test_etymology_typo(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    etymology(d, 3, "kabo-tchi\n節点-外")
    found = errors(check_all(d, rules, PUTE))
    assert {i.kind for i in found} == {"語源と見出し語", "語源の部品"}
    assert all(i.word_id == 3 for i in found)
    assert "kabotchi になり、見出し語と合わない" in found[0].message


def test_headword_typo(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    d.get(6)["entry"]["form"] = "dresjeta"  # 語源欄は dresi-jeta のまま
    found = errors(check_all(d, rules, PUTE))
    assert [(i.word_id, i.kind) for i in found] == [(6, "語源と見出し語")]


def test_phoneme_and_phonotactics(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    d.add("kaxo")["translations"] = [{"title": "", "forms": ["仮"]}]
    d.add("kaab")["translations"] = [{"title": "", "forms": ["仮"]}]
    kinds = {(i.word_id, i.kind) for i in errors(check_all(d, rules, PUTE))}
    assert kinds == {(7, "音素"), (8, "音韻規則")}


def test_prose_etymology_is_skipped(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    etymology(d, 3, "大きさのない点から")
    assert errors(check_all(d, rules, PUTE)) == []


def test_terminology(mini_pute, rules):
    d = Dictionary.load(mini_pute)
    etymology(d, 6, "dresi-jeta\n辺-数旧称")
    found = check_terminology(d, rules)
    assert [(i.word_id, i.kind, i.level) for i in found] == [(6, "旧用語", ERROR)]
    assert "「旧称」" in found[0].message and "「新称」" in found[0].message
    assert check_terminology(d, None) == []


def test_similar_is_notice(mini_pute):
    d = Dictionary.load(mini_pute)
    d.add("dresu")
    found = check_similar(d)
    assert [(i.kind, i.level) for i in found] == [("似た綴り", NOTICE)]


def test_join_merges_compound_but_not_affix(mini_pute, rules):
    lang = C.Checker(Dictionary.load(mini_pute), rules).lang
    v, ph = lang.vowels, lang.phonemes
    for segs, joined in ((["kabo", "otchu"], "kabotchu"),   # 複合語の部品はまとめる
                         (["kawo", "wosa"], "kawosa"),       # wo も同じ
                         (["jeta", "av"], "jetaav"),         # 活用語尾はまとめない
                         (["sa", "asi"], "saasi")):          # 動詞化の接頭辞もまとめない
        assert lang.join(segs)[0] == joined
        assert P.join(segs, lang.merge_flags(segs), v, ph) == joined


def test_affix_inside_etymology_part(mini_pute, rules):
    """部品は見出し語そのものとは限らない(sa + tchu のように、接辞と語の連なりとして読めればよい)"""
    d = Dictionary.load(mini_pute)
    w = d.add("kabosatchu")
    w["translations"] = [{"title": "", "forms": ["仮"]}]
    w["contents"] = [{"title": "語源", "text": "kabo-satchu\n節点-外にする"}]
    assert errors(check_all(d, rules, PUTE)) == []


# ---------- 辞書の整合性(実データ: 完了条件) ----------

needs_typo = pytest.mark.skipif(not (REAL_PUTE_TYPO.exists() and REAL_RULES.exists()),
                                reason="data/secondpute_q_with_typos.json か data/pute-rules.yaml がない")


@needs_typo
def test_real_typo_dictionary_detects_six_typos_and_one_term():
    r = Rules.load(REAL_RULES)
    found = errors(check_all(Dictionary.load(REAL_PUTE_TYPO), r, PUTE))
    by_word = {}
    for i in found:
        by_word.setdefault(i.word_id, set()).add(i.kind)
    # 誤記: #42 #51 #53 #54 #60 #75、旧用語: #79(文法 md 12.2)
    assert set(by_word) == {42, 51, 53, 54, 60, 75, 79}
    assert by_word[79] == {"旧用語"}
    for wid in (42, 51, 53, 54, 60, 75):
        assert "語源と見出し語" in by_word[wid]


@pytest.mark.skipif(not (REAL_PUTE.exists() and REAL_RULES.exists()), reason="実データがない")
def test_real_fixed_dictionary_has_no_errors():
    r = Rules.load(REAL_RULES)
    assert errors(check_all(Dictionary.load(REAL_PUTE), r, PUTE)) == []


# ---------- 文法 md と規則ファイルの表 ----------

def test_grammar_tables_match(grammar, rules):
    assert G.check_tables(grammar, rules) == []


@pytest.mark.parametrize("old, new, expected", [
    ("| 転写 | a | e | i | o | u | wo |", "| 転写 | a | e | i | o | wo |", "[phonology.vowels] 母音: 規則ファイルにだけある ['u']"),
    ("| K音 | k [k]、tch [t͡ʃ] |", "| K音 | k [k] |", "[phonology.consonants] 子音 K 音: 規則ファイルにだけある ['tch']"),
    ("| sa- | 動詞化。説明の続き |", "| sa- | 名詞化 |", "[affixes.verbalizer] sa: 文法 md は「名詞化」、規則ファイルは「動詞化」"),
    ("| 過去 | -es |", "| 過去 | -is |", "[inflection.noun.tense] noun の時制 過去: 文法 md は 'is'、規則ファイルは 'es'"),
    ("| 高状態形 | -d |", "| 高状態形 | -dd |", "[inflection.verb.state] verb の状態形 高: 文法 md は 'dd'"),
    # 目印と ref の対応
    ("<!-- rule: affixes.verbalizer -->", "<!-- rule: affixes.verbaliser -->",
     "規則ファイルの affixes.verbalizer の ref「affixes.verbalizer」が、文法文書に見つからない"),
    ("<!-- rule: affixes.verbalizer -->", "<!-- rule: affixes.verbaliser -->",
     "文法文書の目印「affixes.verbaliser」に対応する規則が、規則ファイルにない"),
])
def test_grammar_table_differences(grammar, rules, old, new, expected):
    assert old in grammar
    diffs = G.check_tables(grammar.replace(old, new), rules)
    assert any(d.startswith(expected) for d in diffs), diffs


def test_prose_anchors_go_to_llm(grammar, rules):
    rep = G.run(grammar, rules)
    assert (rep.anchors, rep.refs) == (9, 9)
    assert rep.prose_anchors == ["compounding.rules", "inflection.classes"]
    pairs = G.llm_pairs(grammar, rules)
    assert sorted(p.anchor for p in pairs) == ["compounding.rules", "inflection.classes"]
    assert pairs[0].text == ["- 大本の概念を先頭に置く", "- 同じ母音が並ぶときは1つにまとめる【仮】"]
    assert set(pairs[0].rules) == {"compounding"} and "vowel_merge" in pairs[0].rules["compounding"]
    assert pairs[1].rules["inflection.classes"]["adjective"]["overrides"] == {"一般.常態": "wosh"}


def _renumber(text: str) -> str:
    """見出しの番号をすべて書き換え、章の順番も入れ替える(目印はそのまま)"""
    import re as _re
    text = _re.sub(r"^(#+) (\d+(\.\d+)*)\.?", lambda m: f"{m.group(1)} 9{m.group(2)}.", text, flags=_re.M)
    head, rest = text.split("\n## ", 1)
    chapters = ["## " + c for c in rest.split("\n## ")]
    return head + "\n" + "\n".join(reversed(chapters))


def test_renumbered_grammar_gives_same_result(grammar, rules):
    """仕様書 M4: 文法 md の節番号を書き換えても、検査が壊れない"""
    moved = _renumber(grammar)
    assert "### 1.1" not in moved and "### 91.1." in moved
    assert G.run(moved, rules) == G.run(grammar, rules)
    broken = grammar.replace("| 過去 | -es |", "| 過去 | -is |")
    assert G.check_tables(_renumber(broken), rules) == G.check_tables(broken, rules) != []


@pytest.mark.skipif(not (REAL_GRAMMAR.exists() and REAL_RULES.exists()), reason="実データがない")
def test_real_renumbered_grammar_gives_same_result():
    text = REAL_GRAMMAR.read_text(encoding="utf-8")
    r = Rules.load(REAL_RULES)
    assert G.run(_renumber(text), r) == G.run(text, r)


@pytest.mark.skipif(not (REAL_GRAMMAR.exists() and REAL_RULES.exists()), reason="実データがない")
def test_real_grammar_tables_match():
    text = REAL_GRAMMAR.read_text(encoding="utf-8")
    assert G.check_tables(text, Rules.load(REAL_RULES)) == []


# ---------- LLM による検査 ----------

ANSWER = {"candidates": [{"anchor": "compounding.rules", "grammar_quote": "1つにまとめる【仮】",
                          "rule": "compounding.vowel_merge", "problem": "文書は【仮】、規則は仮", "suggestion": "直す",
                          "confidence": "中"}]}


def test_llm_prompt_and_answer(grammar, rules):
    prompt = G.build_llm_prompt(G.llm_pairs(grammar, rules))
    assert "【目印: compounding.rules】" in prompt and "【目印: inflection.classes】" in prompt
    assert "同じ母音が並ぶときは1つにまとめる【仮】" in prompt and "vowel_merge:" in prompt
    assert "【目印: phonology.vowels】" not in prompt  # 表はコードで調べるので渡さない
    cands = G.parse_llm_answer("<think>考え {途中}</think>\n```json\n" + json.dumps(ANSWER, ensure_ascii=False) + "\n```")
    assert [(c.anchor, c.rule, c.confidence) for c in cands] == [("compounding.rules", "compounding.vowel_merge", "中")]
    assert "候補(1件" in G.format_candidates(cands)
    assert "保証ではない" in G.format_candidates([])
    with pytest.raises(ValueError):
        G.parse_llm_answer("答えなし")
    with pytest.raises(ValueError):
        G.parse_llm_answer("{壊れた JSON")


def test_llm_log(tmp_path):
    p = llm_log.save_call(tmp_path, "grammar-check", "プロンプト", "答え", grammar="g.md")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["prompt"] == "プロンプト" and data["answer"] == "答え" and data["grammar"] == "g.md"
    assert llm_log.list_calls(tmp_path, "grammar-check") == [p]
    inputs = {"grammar": "a", "rules": "b"}
    assert llm_log.inputs_changed(tmp_path, "grammar-check", inputs)
    llm_log.remember_inputs(tmp_path, "grammar-check", inputs)
    assert not llm_log.inputs_changed(tmp_path, "grammar-check", inputs)
    assert llm_log.inputs_changed(tmp_path, "grammar-check", {"grammar": "a2", "rules": "b"})
    assert llm_log.list_calls(tmp_path) == [p]  # 状態のファイルは履歴に数えない


@pytest.fixture
def project(tmp_path, mini_pute):
    proj = tmp_path / "x"
    main(["new", str(proj), "--name", "架空語", "--language", "pute"])
    main(["import", str(proj), str(mini_pute)])
    main(["rules", "import", str(proj), str(FIXTURES / "mini_rules.yaml")])
    main(["grammar", "import", str(proj), str(FIXTURES / "mini-grammar.md")])
    return Project.open(proj)


def test_cli_grammar_check_with_response(project, tmp_path, capsys):
    capsys.readouterr()
    assert project.grammar_path(project.load_rules()).name == "mini-grammar.md"
    assert main(["pute", "--project", str(project.root), "grammar-check"]) == 0
    assert "食い違いはない" in capsys.readouterr().out
    assert main(["pute", "--project", str(project.root), "grammar-check", "--prompt-only"]) == 0
    assert "【目印: compounding.rules】" in capsys.readouterr().out
    ans = tmp_path / "answer.json"
    ans.write_text(json.dumps(ANSWER, ensure_ascii=False), encoding="utf-8")
    assert main(["pute", "--project", str(project.root), "grammar-check", "--response", str(ans)]) == 1
    out = capsys.readouterr().out
    assert "LLM が挙げた食い違いの候補(1件" in out and "履歴:" in out
    assert len(llm_log.list_calls(project.llm_log_dir, "grammar-check")) == 1
    # 文法文書も規則ファイルも変わっていないので、API を呼ばずに終わる
    main(["pute", "--project", str(project.root), "grammar-check", "--llm"])
    assert "前回 LLM に調べさせたときから変わっていない" in capsys.readouterr().out


def test_cli_grammar_check_finds_table_difference(project, capsys):
    g = project.grammar_dir / "mini-grammar.md"
    g.write_text(g.read_text(encoding="utf-8").replace("| 過去 | -es |", "| 過去 | -is |"), encoding="utf-8")
    capsys.readouterr()
    assert main(["pute", "--project", str(project.root), "grammar-check"]) == 1
    assert "! [inflection.noun.tense] noun の時制 過去" in capsys.readouterr().out


def test_cli_check(project, capsys):
    capsys.readouterr()
    assert main(["check", str(project.root)]) == 0
    assert "誤り 0件" in capsys.readouterr().out
    d = project.load_dictionary()
    etymology(d, 3, "kabo-tchi\n節点-外")
    project.save_dictionary(d)
    assert main(["check", str(project.root), "--errors-only"]) == 1
    out = capsys.readouterr().out
    assert "誤り 2件(語 1個)" in out and "[誤り] #3 語源と見出し語" in out


def test_grammar_import_backs_up(project):
    bak = project.import_grammar(FIXTURES / "mini-grammar.md")
    assert bak is not None and bak.exists()


def test_check_rules_hook_registered():
    assert PUTE.check_dictionary is C.check_dictionary
    assert PUTE.grammar_table_checks is G.TABLE_CHECKS
    assert PUTE.check_grammar(G_TEXT_EMPTY, Rules({})) == []  # 目印も ref もなければ食い違いはない
    assert PUTE.check_rules is PR.check_rules
