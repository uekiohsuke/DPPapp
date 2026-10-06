"""文法文書の閲覧、プロジェクト(言語)の切り替え、見出し語の表示の切り替え"""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from conftest import FIXTURES  # noqa: E402

from conlang.core import grammar_doc as G  # noqa: E402
from conlang.core.project import Project  # noqa: E402
from conlang.gui.grammar_view import GrammarView  # noqa: E402
from conlang.gui.main_window import MainWindow  # noqa: E402

MD = """# 題

<!-- rule: a.b -->
- 決めたこと【決定】
- 推定【仮】と【仮】

## 1. 章

```
# コードの中は見出しではない
```

### 1.1 節【メモ】

本文
"""


# ---------- 共通の読み取り ----------

def test_headings_and_tags():
    hs = G.headings(MD)
    assert [(h.level, h.title) for h in hs] == [(1, "題"), (2, "1. 章"), (3, "1.1 節【メモ】")]
    assert G.tag_counts(MD) == {"決定": 1, "仮": 2, "メモ": 1}
    lines = G.tagged_lines(MD, "仮")
    assert len(lines) == 2 and lines[0].section == "題" and "推定" in lines[0].text


# ---------- 文法ビューア ----------

@pytest.fixture
def md_file(tmp_path):
    p = tmp_path / "g.md"
    p.write_text(MD, encoding="utf-8")
    return p


def test_grammar_view(qtbot, md_file):
    v = GrammarView()
    qtbot.addWidget(v)
    v.set_documents([md_file], None)
    assert v.doc_box.count() == 1
    plain = v.browser.toPlainText()
    assert "決めたこと【決定】" in plain and "rule:" not in plain  # 目印は既定では見せない
    assert v.toc.topLevelItemCount() == 1 and v.toc.topLevelItem(0).child(0).text(0) == "1. 章"
    assert "決定 1、仮 2、メモ 1" in v.summary.text() and "規則の目印 1" in v.summary.text()
    assert v.go_to_heading("1.1 節")
    assert v.browser.textCursor().block().text() == "1.1 節【メモ】"
    v.show_anchors.setChecked(True)
    assert "〔規則: a.b〕" in v.browser.toPlainText()
    v.search.setText("本文")
    assert v.find_next() and v.browser.textCursor().selectedText() == "本文"
    v.search.setText("ない言葉")
    assert not v.find_next() and "見つからない" in v.summary.text()


def test_grammar_view_reloads_on_change(qtbot, md_file):
    v = GrammarView()
    qtbot.addWidget(v)
    v.set_documents([md_file], md_file)
    md_file.write_text(MD + "\n## 2. 追加した章\n", encoding="utf-8")
    qtbot.waitUntil(lambda: "追加した章" in v.browser.toPlainText(), timeout=5000)


def test_grammar_view_empty(qtbot):
    v = GrammarView()
    qtbot.addWidget(v)
    assert "文法文書がない" in v.browser.toPlainText() and not v.open_button.isEnabled()


# ---------- 画面全体 ----------

def make_project(tmp_path, name, lang, dictionary, rules=None, grammar=None):
    p = Project.create(tmp_path / name, name, lang)
    p.import_dictionary(dictionary)
    if rules:
        p.import_rules(rules)
    if grammar:
        p.import_grammar(grammar)
    return p


@pytest.fixture
def win(qtbot, tmp_path):
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    w.ask = lambda *a, **k: QMessageBox.Yes
    w.error = lambda text: pytest.fail(f"エラー表示: {text}")
    yield w
    w._end_edit()
    w.dirty = False
    w.close()
    w.deleteLater()


def test_switch_projects_and_views(win, tmp_path, mini_pute):
    pute = make_project(tmp_path, "ピュテ語", "pute", mini_pute, FIXTURES / "mini_rules.yaml", FIXTURES / "mini-grammar.md")
    uri = make_project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json")
    assert win.open_project(pute.root)
    assert win.views.tabText(1) == "文法(1)"
    assert win.grammar_view.doc_box.currentText() == "mini-grammar.md"
    assert ("pute", "造語") in win.language_docks
    assert win.display_box.isHidden()  # ピュテ語には表示の切り替えがない
    assert win.open_project(uri.root)
    assert win.views.tabText(1) == "文法"   # ウリ語のプロジェクトには文法文書がまだない
    assert ("pute", "造語") not in win.language_docks  # ピュテ語の欄は消える
    # 最近のプロジェクトから切り替える
    items = [win.project_box.itemData(i) for i in range(win.project_box.count())]
    assert items[:2] == [str(uri.root.resolve()), str(pute.root.resolve())] and items[-1] is None
    win._project_chosen(1)
    assert win.project.name == "ピュテ語"
    assert win.project_box.currentData() == str(pute.root.resolve())


def test_uri_display_switch(win, tmp_path):
    uri = make_project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json")
    win.open_project(uri.root)
    assert not win.display_box.isHidden()
    assert [win.display_box.itemText(i) for i in range(win.display_box.count())] == ["辞書の綴り", "現代の転写"]
    win.select_word(3)
    assert win.model.data(win.model.index(2, 0)) == "ToKOPan"
    win.display_box.setCurrentIndex(1)
    assert win.model.data(win.model.index(2, 0)) == "tokoopan"
    html = win.viewer.toHtml()
    assert "tokoopan" in html and "辞書の綴り: ToKOPan" in html
    assert win.dictionary.get(3)["entry"]["form"] == "ToKOPan"  # 辞書の綴りは変えない
    issues = [win.issue_list.item(i).text() for i in range(win.issue_list.count())]
    assert any("近現代の形" in t for t in issues)


def test_empty_project(win, tmp_path):
    """辞書が空のプロジェクト(新しく作ったばかり)でも、一覧・警告・保存が動く。空の辞書を「辞書がない」と取り違えない"""
    p = Project.create(tmp_path / "空", "ミャミュ語", "myamyu")
    p.import_rules(FIXTURES / "mini_myamyu_rules.yaml")
    assert win.open_project(p.root)
    assert win.count_label.text() == "0 / 0 項目"
    assert win.issue_dock.windowTitle() == "警告(誤り 0件・注意 0件)"
    assert "ミャミュ語の規則としての点検: 問題なし" in win.rules_panel.summary.text()
    win.new_word()
    win.editor.form.setText("kapta")  # 存在しない並び pt
    win.editor.translations.add_row("", "架空")
    win.editor.apply_button.click()
    assert win.count_label.text() == "1 / 1 項目"
    assert any("存在しない並び pt" in win.issue_list.item(i).text() for i in range(win.issue_list.count()))
    assert win.save()
    from conlang.core.zpdic import Dictionary
    assert [w["entry"]["form"] for w in Dictionary.load(p.dictionary_path).words] == ["kapta"]


def test_import_grammar_from_menu(win, tmp_path):
    uri = make_project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json")
    win.open_project(uri.root)
    md = tmp_path / "uri-grammar.md"
    md.write_text("# ウリ語\n\n## 1. 音韻\n", encoding="utf-8")
    assert win.import_grammar(md)
    assert win.views.currentWidget() is win.grammar_view and win.views.tabText(1) == "文法(1)"
    assert "1. 音韻" in win.grammar_view.browser.toPlainText()
