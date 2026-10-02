"""M0: 試作の機能(find / check / suggest / decompose)が、アプリの造語支援で動く

M5 で、試作のロジックは規則ファイルから動く造語エンジン(conlang.languages.pute.coining)に移した。
"""
import json

from conftest import REAL_PUTE, needs_real_pute

from conlang.cli import main
from conlang.core.zpdic import Dictionary
from conlang.languages.pute.coining import AFFIX, HEAD, SHORT, Coiner


def coiner(path):
    return Coiner(Dictionary.load(path))


def run(capsys, path, *argv):
    code = main(["pute", "--dict", str(path), *argv])
    return code, capsys.readouterr().out


# ---------- 架空の辞書 ----------

def test_parts(mini_pute):
    c = coiner(mini_pute)
    kinds = {p.form: p.kind for p in c.parts}
    assert kinds["kabo"] == HEAD and kinds["jeta"] == SHORT
    assert c.resolve("節点").form == "kabo"
    assert c.resolve("jeta").head == "jetavo"


def test_find(capsys, mini_pute):
    code, out = run(capsys, mini_pute, "find", "外")
    assert code == 0 and "tchu" in out


def test_find_none(capsys, mini_pute):
    assert "該当する語はない" in run(capsys, mini_pute, "find", "宇宙")[1]


def test_check_detects_existing_word(mini_pute):
    res = coiner(mini_pute).check(["kabo", "tchu"])
    assert res.word == "kabotchu" and res.existing.form == "kabotchu"
    assert any(w.startswith("すでに辞書にある語と同じ綴り") for w in res.warnings)


def test_check_cli_resolves_meanings(capsys, mini_pute):
    out = run(capsys, mini_pute, "check", "節点", "外")[1]
    assert "kabotchu" in out and "すでに辞書にある語" in out


def test_check_unknown_phoneme(mini_pute):
    res = coiner(mini_pute).check(["kabo", "xyz"])
    assert "ピュテ語の音素に分けられない文字を含む" in res.warnings


def test_join_merges_same_vowel(mini_pute):
    assert coiner(mini_pute).join(["thai", "idra"])[0] == "thaidra"


def test_suggest_finds_existing_combination(capsys, mini_pute):
    out = run(capsys, mini_pute, "suggest", "辺", "数")[1]
    assert "すでに辞書にある語になっている" in out and "dresijeta" in out


def test_decompose_prompt_only(capsys, mini_pute):
    out = run(capsys, mini_pute, "decompose", "孤立点", "--prompt-only")[1]
    assert "【造語したい概念】孤立点" in out and "kabo | 節点" in out


def test_decompose_grounds_llm_answer(capsys, mini_pute, tmp_path):
    answer = {"concept": "外の道", "elements": [
        {"role": "核", "meaning": "道", "existing": "dresi", "reason": "道"},
        {"role": "修飾", "meaning": "外", "existing": "qqq", "reason": "辞書にない語を主張"},
    ]}
    f = tmp_path / "answer.txt"
    f.write_text("```json\n" + json.dumps(answer, ensure_ascii=False) + "\n```", encoding="utf-8")
    out = run(capsys, mini_pute, "decompose", "外の道", "--response", str(f))[1]
    assert "qqq は辞書にないので、未収録として扱う" in out
    assert "「外」 は既存語にない" in out


def test_parts_lists_affixes_only_with_rules(capsys, mini_pute):
    """規則ファイルがなければ接辞は分からないので、部品は辞書の語だけ"""
    out = run(capsys, mini_pute, "parts")[1]
    assert "kabo\t見出し語" in out and AFFIX not in out


# ---------- 実辞書(data/secondpute.json があるとき) ----------

@needs_real_pute
def test_real_known_words():
    """仕様 §8 の既知例: 辺-数 = 次数、節点-外 = 孤立点 は辞書にある語になる"""
    c = coiner(REAL_PUTE)
    for forms, word in [(["thjadrwoqaku", "jeta"], "thjadrwoqakujeta"),
                        (["diqakusuboth", "tcheb"], "diqakusubothtcheb")]:
        res = c.check(forms)
        assert res.word == word and res.existing is not None


@needs_real_pute
def test_real_all_commands(capsys):
    for argv in (["find", "力"], ["check", "節点", "外"], ["suggest", "辺", "数"],
                 ["decompose", "重力加速度", "--prompt-only"]):
        code, out = run(capsys, REAL_PUTE, *argv)
        assert code == 0 and out.strip()
