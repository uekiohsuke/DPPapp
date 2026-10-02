"""M0: 試作の整理。find / check / suggest / decompose が動く"""
import json

from conftest import REAL_PUTE, needs_real_pute

from conlang.languages.pute import zougo


def run(capsys, parts, *argv):
    zougo.main(list(argv), parts)
    return capsys.readouterr().out


# ---------- 架空の辞書 ----------

def test_load_parts(mini_pute):
    parts = zougo.load(mini_pute)
    forms = {p["form"]: p["kind"] for p in parts}
    assert forms["kabo"] == "見出し語"
    assert forms["jeta"] == "短縮形"


def test_find(capsys, mini_pute):
    out = run(capsys, zougo.load(mini_pute), "find", "外")
    assert "tchu" in out


def test_find_none(capsys, mini_pute):
    out = run(capsys, zougo.load(mini_pute), "find", "宇宙")
    assert "該当する語はない" in out


def test_check_detects_existing_word(mini_pute):
    parts = zougo.load(mini_pute)
    res = zougo.check(["kabo", "tchu"], parts)
    assert res["word"] == "kabotchu"
    assert any(w.startswith("すでに辞書にある語と同じ綴り") for w in res["warnings"])


def test_check_cli_resolves_meanings(capsys, mini_pute):
    out = run(capsys, zougo.load(mini_pute), "check", "節点", "外")
    assert "kabotchu" in out and "すでに辞書にある語" in out


def test_check_unknown_phoneme(mini_pute):
    res = zougo.check(["kabo", "xyz"], zougo.load(mini_pute))
    assert "ピュテ語の音素に分けられない文字を含む" in res["warnings"]


def test_join_merges_same_vowel():
    assert zougo.join_parts(["thai", "idra"])[0] == "thaidra"


def test_suggest_finds_existing_combination(capsys, mini_pute):
    out = run(capsys, zougo.load(mini_pute), "suggest", "辺", "数")
    assert "すでに辞書にある語になっている" in out
    assert "dresijeta" in out


def test_decompose_prompt_only(capsys, mini_pute):
    out = run(capsys, zougo.load(mini_pute), "decompose", "孤立点", "--prompt-only")
    assert "【造語したい概念】孤立点" in out
    assert "kabo | 節点" in out


def test_decompose_grounds_llm_answer(capsys, mini_pute, tmp_path):
    answer = {"concept": "外の道", "elements": [
        {"role": "核", "meaning": "道", "existing": "dresi", "reason": "道"},
        {"role": "修飾", "meaning": "外", "existing": "qqq", "reason": "辞書にない語を主張"},
    ]}
    f = tmp_path / "answer.txt"
    f.write_text("```json\n" + json.dumps(answer, ensure_ascii=False) + "\n```", encoding="utf-8")
    out = run(capsys, zougo.load(mini_pute), "decompose", "外の道", "--response", str(f))
    assert "qqq は辞書にないので、未収録として扱う" in out
    assert "「外」 は既存語にない" in out


def test_cli_entry(capsys, mini_pute):
    from conlang.cli import main
    assert main(["pute", "--dict", str(mini_pute), "find", "数"]) == 0
    assert "jetavo" in capsys.readouterr().out


# ---------- 実辞書(data/secondpute.json があるとき) ----------

@needs_real_pute
def test_real_known_words():
    """仕様 §8 の既知例: 辺-数 = 次数、節点-外 = 孤立点 は辞書にある語になる"""
    parts = zougo.load(REAL_PUTE)
    for keys, word in [(["thjadrwoqaku", "jeta"], "thjadrwoqakujeta"),
                       (["diqakusuboth", "tcheb"], "diqakusubothtcheb")]:
        res = zougo.check(keys, parts)
        assert res["word"] == word
        assert any(w.startswith("すでに辞書にある語と同じ綴り") for w in res["warnings"])


@needs_real_pute
def test_real_all_commands(capsys):
    parts = zougo.load(REAL_PUTE)
    for argv in (["find", "力"], ["check", "節点", "外"], ["suggest", "辺", "数"],
                 ["decompose", "重力加速度", "--prompt-only"]):
        out = run(capsys, parts, *argv)
        assert out.strip()
