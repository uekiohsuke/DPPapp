"""M2: アプリの上で、辞書を一覧・検索・編集・閲覧できて、zpdic 形式で保存できる"""
import hashlib
import json

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from conlang.core.project import Project  # noqa: E402
from conlang.core.zpdic import Dictionary  # noqa: E402
from conlang.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def project(tmp_path, mini_pute):
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    p.import_dictionary(mini_pute)
    return p


@pytest.fixture
def win(qtbot, tmp_path, project):
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    w.answers = []  # ask() に返す答え(先頭から使う)
    w.ask = lambda *a, **k: w.answers.pop(0)
    w.error = lambda text: pytest.fail(f"エラー表示: {text}")
    assert w.open_project(project.root)
    yield w
    # 閉じるとき、保存の確認を出さない
    w._end_edit()
    w.dirty = False
    w.close()
    w.deleteLater()


def listed(win):
    return [win.model.words[i]["entry"]["form"] for i in range(win.model.rowCount())]


def test_list_and_view(win):
    assert len(listed(win)) == 6
    assert win.count_label.text() == "6 / 6 項目"
    win.select_word(3)
    html = win.viewer.toHtml()
    assert "kabotchu" in html and "孤立点" in html and "kabo-tchu" in html


def test_search(win):
    win.search_box.setText("外")
    assert listed(win) == ["tchu"]
    win.target_checks["内容"].setChecked(True)
    win.search_box.setText("節点")
    assert listed(win) == ["kabo", "kabotchu"]
    win.search_box.setText("")
    assert len(listed(win)) == 6


def test_edit_and_save(win, project, mini_pute):
    source_hash = hashlib.sha256(mini_pute.read_bytes()).hexdigest()
    win.select_word(2)
    win.edit_current()
    assert win.stack.currentWidget() is win.editor
    win.editor.form.setText("tchuo")
    win.editor.translations.set_rows([("修飾概念", "外、外側")])
    win.editor.apply_button.click()
    assert win.dirty and win.windowTitle().startswith("*")
    assert "tchuo" in win.viewer.toHtml()
    assert win.save()
    assert not win.dirty
    d = Dictionary.load(project.dictionary_path)
    assert d.get(2)["entry"]["form"] == "tchuo"
    assert d.get(2)["translations"] == [{"title": "修飾概念", "forms": ["外", "外側"]}]
    assert d.style.kind == "python"  # zpdic 形式のまま、元の書式で保存
    assert len(list(project.backup_dir.iterdir())) == 2  # 取り込み時と保存時
    assert hashlib.sha256(mini_pute.read_bytes()).hexdigest() == source_hash


def test_cancel_edit(win, project):
    win.select_word(1)
    win.edit_current()
    win.editor.form.setText("zzz")
    win.editor.cancel_button.click()
    assert not win.dirty
    assert win.dictionary.get(1)["entry"]["form"] == "kabo"


def test_new_word(win, project):
    win.new_word()
    win.editor.form.setText("sasxa")
    win.editor.translations.add_row("動作概念", "書く")
    win.editor.add_content("語義", "記録を残すこと。")
    win.editor.apply_button.click()
    assert win.current_id == 7
    assert "sasxa" in listed(win)
    win.save()
    w = Dictionary.load(project.dictionary_path).get(7)
    assert w["entry"]["form"] == "sasxa"
    assert w["contents"] == [{"title": "語義", "text": "記録を残すこと。"}]
    assert set(w) == {"entry", "translations", "tags", "contents", "variations", "relations"}


def test_new_word_cancel_adds_nothing(win):
    win.new_word()
    win.editor.form.setText("sasxa")
    win.editor.cancel_button.click()
    assert len(win.dictionary) == 6


def test_delete_word(win, project):
    win.select_word(4)
    win.answers = [QMessageBox.No]
    win.delete_current()
    assert len(win.dictionary) == 6
    win.answers = [QMessageBox.Yes]
    win.delete_current()
    assert win.dictionary.get(4) is None and "dresi" not in listed(win)
    win.save()
    assert len(Dictionary.load(project.dictionary_path)) == 5


def test_issues_panel(win):
    assert win.issue_list.count() == 0
    win.select_word(2)
    win.edit_current()
    win.editor.form.setText("kabo")  # 同じ綴りにする
    win.editor.apply_button.click()
    texts = [win.issue_list.item(i).text() for i in range(win.issue_list.count())]
    assert any("同じ綴り" in t for t in texts)
    # tchu が辞書からなくなったので、kabotchu の語源欄(kabo-tchu)の部品も読めなくなる(M4 の検査)
    assert any("語源欄の部品 tchu" in t for t in texts)
    assert "警告(誤り 3件・注意 0件)" == win.issue_dock.windowTitle()
    assert texts[0].startswith("[誤り]")


def test_export(win, tmp_path, project):
    out = tmp_path / "export.json"
    win.export(out)
    assert out.read_bytes() == project.dictionary_path.read_bytes()
    json.loads(out.read_text(encoding="utf-8"))["words"]


def test_unsaved_changes_prompt(win):
    win.select_word(1)
    win.answers = [QMessageBox.Yes]
    win.delete_current()
    win.answers = [QMessageBox.Cancel]
    assert not win.maybe_save()
    win.answers = [QMessageBox.Discard]
    assert win.maybe_save()


def test_rules_panel(win, project):
    assert "規則ファイルがない" in win.rules_panel.summary.text()
    from conftest import FIXTURES
    win.answers = [QMessageBox.Yes]
    assert win.import_rules(FIXTURES / "mini_rules.yaml")
    assert "架空語: 規則" in win.rules_panel.summary.text()
    assert "ピュテ語の規則としての点検: 問題なし" in win.rules_panel.summary.text()
    paths = [win.rules_panel.tree.topLevelItem(i).text(0) for i in range(win.rules_panel.tree.topLevelItemCount())]
    assert "compounding.vowel_merge" in paths and "phonology" not in paths
    win.rules_panel.only_unsettled.setChecked(False)
    assert win.rules_panel.tree.topLevelItemCount() > len(paths)
    assert project.rules_path.exists()
    assert "文法文書がない" in win.rules_panel.summary.text()


def test_rules_panel_grammar_check(win, project):
    from conftest import FIXTURES
    project.import_rules(FIXTURES / "mini_rules.yaml")
    g = (FIXTURES / "mini-grammar.md").read_text(encoding="utf-8")
    (project.grammar_dir / "mini-grammar.md").write_text(g.replace("| 過去 | -es |", "| 過去 | -is |"), encoding="utf-8")
    win.reload_rules()
    assert "文法文書(mini-grammar.md)との表の照合: 食い違い 1件" in win.rules_panel.summary.text()
    top = win.rules_panel.tree.topLevelItem(0)
    assert top.text(0).startswith("文法文書との表の食い違い") and "過去" in top.child(0).text(0)


def test_issues_use_rules(win, project):
    """規則ファイルの旧用語の対応が、警告に使われる"""
    from conftest import FIXTURES
    project.import_rules(FIXTURES / "mini_rules.yaml")
    w = win.dictionary.get(1)
    w["contents"][0]["text"] = "旧称の説明"
    win.reload_rules()
    texts = [win.issue_list.item(i).text() for i in range(win.issue_list.count())]
    assert any("[誤り][旧用語]" in t for t in texts)


def run_panel(qtbot, panel, action: int, text: str) -> str:
    """造語の欄で実行し、裏の処理が終わるまで待って、出力を返す"""
    panel.action.setCurrentIndex(action)
    panel.input.setText(text)
    panel.run()
    qtbot.waitUntil(lambda: not panel.running, timeout=10000)
    return panel.output.toPlainText()


def test_coining_panel(qtbot, win, project):
    """ピュテ語のプロジェクトでは、造語の欄が出て、編集中の辞書で動く"""
    from conftest import FIXTURES
    panel = win.language_docks[("pute", "造語")].widget()
    assert "1. kabo + tchu" in run_panel(qtbot, panel, 3, "kabotchu")      # 形態素分解
    assert "すでに辞書にある語" in run_panel(qtbot, panel, 1, "節点 外")     # 組み合わせの検査
    # 規則を取り込むと、規則に従って動く(動詞化の sa が部品になる)
    win.answers = [QMessageBox.Yes]
    win.import_rules(FIXTURES / "mini_rules.yaml")
    assert "kabosatchu" in run_panel(qtbot, panel, 1, "kabo sa tchu")
    # 未保存の編集も使う
    win.new_word()
    win.editor.form.setText("vosa")
    win.editor.translations.add_row("", "新語")
    win.editor.apply_button.click()
    assert "vosa" in run_panel(qtbot, panel, 0, "新語")
    assert panel.status.text().startswith("終わった")


def test_relation_link(win):
    win.select_word(5)
    win.edit_current()
    win.editor.relations.add_row("類義", "dresijeta")
    win.editor.apply_button.click()
    assert "word:6" in win.viewer.toHtml()
    from PySide6.QtCore import QUrl
    win._on_link(QUrl("word:6"))
    assert win.current_id == 6
