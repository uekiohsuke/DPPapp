"""M2 のコア部分: 検索、空の項目・重複の警告、項目の編集"""
from conftest import REAL_PUTE, needs_real_pute

from conlang.core import search as S
from conlang.core.validate import check_dictionary
from conlang.core.wordedit import WordFields, apply_fields, split_list, to_fields
from conlang.core.zpdic import Dictionary


def forms(hits):
    return [h.word["entry"]["form"] for h in hits]


# ---------- 検索 ----------

def test_empty_query_returns_all(mini_pute):
    d = Dictionary.load(mini_pute)
    assert len(S.search(d, S.Query(""))) == len(d)


def test_search_translation_exact_first(mini_pute):
    d = Dictionary.load(mini_pute)
    # 「数」は jetavo の訳語と完全一致、dresijeta の「次数」に部分一致
    assert forms(S.search(d, S.Query("数")))[:2] == ["jetavo", "dresijeta"]


def test_search_form_and_variation(mini_pute):
    d = Dictionary.load(mini_pute)
    assert forms(S.search(d, S.Query("kabo", (S.FORM,), S.PREFIX))) == ["kabo", "kabotchu"]
    assert forms(S.search(d, S.Query("jeta", (S.FORM,), S.EXACT))) == ["jetavo"]  # 短縮形で当たる


def test_search_contents_by_title(mini_pute):
    d = Dictionary.load(mini_pute)
    q = S.Query("節点", (S.CONTENT,), content_titles=("語源",))
    assert forms(S.search(d, q)) == ["kabotchu"]
    q = S.Query("点", (S.CONTENT,), content_titles=("語義",))
    assert forms(S.search(d, q)) == ["kabo"]


def test_search_tag(mini_pute):
    d = Dictionary.load(mini_pute)
    assert len(S.search(d, S.Query("基本詞", (S.TAG,), S.EXACT))) == 4


def test_content_titles(mini_pute):
    assert S.content_titles(Dictionary.load(mini_pute)) == ["語義", "語源"]


# ---------- 警告 ----------

def test_clean_dictionary_has_no_issues(mini_pute):
    assert check_dictionary(Dictionary.load(mini_pute)) == []


def test_issues_empty_and_duplicate(mini_pute):
    d = Dictionary.load(mini_pute)
    d.add("")  # 空の見出し語、訳語なし
    w = d.add("kabo")  # 同じ綴り
    w["translations"] = [{"title": "", "forms": ["点"]}]
    w["contents"] = [{"title": "語義", "text": "  "}]
    kinds = [i.kind for i in check_dictionary(d)]
    assert "空の見出し語" in kinds
    assert "訳語なし" in kinds
    assert kinds.count("同じ綴り") == 2
    assert "空の内容" in kinds


def test_duplicate_id(mini_pute):
    d = Dictionary.load(mini_pute)
    d.words[1]["entry"]["id"] = 1
    assert "id の重複" in [i.kind for i in check_dictionary(d)]


# ---------- 項目の編集 ----------

def test_fields_roundtrip_keeps_word(mini_pute):
    """何も変えずに戻すと、元の項目と同じになる"""
    d = Dictionary.load(mini_pute)
    for w in d.words:
        new, notes = apply_fields(w, to_fields(w, d), d)
        assert new == w and notes == []


def test_edit_fields(mini_pute):
    d = Dictionary.load(mini_pute)
    w = d.get(5)
    f = to_fields(w, d)
    assert f.translations == [("数理概念", "数、量")]
    f.form = " jetavu "
    f.translations = [("数理概念", "数、量, 個数"), ("", "")]
    f.tags = "基本詞、数学"
    f.contents = [("語義", "ものの多さ。")]
    f.relations = [("類義", "dresijeta"), ("類義", "nainai")]
    new, notes = apply_fields(w, f, d)
    assert new["entry"] == {"id": 5, "form": "jetavu"}
    assert new["translations"] == [{"title": "数理概念", "forms": ["数", "量", "個数"]}]
    assert new["tags"] == ["基本詞", "数学"]
    assert new["contents"] == [{"title": "語義", "text": "ものの多さ。"}]
    assert new["variations"] == w["variations"]
    assert new["relations"][0] == {"title": "類義", "entry": {"id": 6, "form": "dresijeta"}}
    assert new["relations"][1]["entry"]["form"] == "nainai"
    assert notes == ["関連語 nainai は辞書にない(綴りだけ記録した)"]
    assert d.get(5)["entry"]["form"] == "jetavo"  # 元の項目は変わらない


def test_unchanged_text_keeps_forms_with_separator(mini_pute):
    """訳語に区切り文字が入っていても、触らなければ分割しない"""
    d = Dictionary.load(mini_pute)
    w = d.get(1)
    w["translations"][0]["forms"] = ["点、節"]
    new, _ = apply_fields(w, to_fields(w, d), d)
    assert new["translations"][0]["forms"] == ["点、節"]


def test_unknown_keys_in_items_kept(mini_pute):
    d = Dictionary.load(mini_pute)
    w = d.get(6)
    w["translations"][0]["extra"] = 1
    f = to_fields(w, d)
    f.translations = [("数理概念", "次数、度数")]
    new, _ = apply_fields(w, f, d)
    assert new["translations"][0]["extra"] == 1
    assert new["unknownField"] == {"keep": "未知のフィールドも残す"}


def test_split_list():
    assert split_list("a、b,c ,, d", [",", "、"]) == ["a", "b", "c", "d"]


@needs_real_pute
def test_real_fields_roundtrip():
    d = Dictionary.load(REAL_PUTE)
    for w in d.words:
        assert apply_fields(w, to_fields(w, d), d)[0] == w
