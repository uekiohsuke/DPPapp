"""画面の「言語の機能」(規則欄のタブ)と、訳語の区分・内容の見出しを選ぶ入力欄"""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QMessageBox, QStyleOptionViewItem  # noqa: E402

from conftest import FIXTURES  # noqa: E402

from conlang.core import registry  # noqa: E402
from conlang.core import search as S  # noqa: E402
from conlang.core.project import Project  # noqa: E402
from conlang.core.zpdic import Dictionary  # noqa: E402
from conlang.gui.main_window import MainWindow  # noqa: E402
from conlang.gui.word_editor import RowTable  # noqa: E402


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


def project(tmp_path, name, lang, dictionary=None, rules=None, grammar=None):
    p = Project.create(tmp_path / name, name, lang)
    if dictionary:
        p.import_dictionary(dictionary)
    if rules:
        p.import_rules(rules)
    if grammar:
        p.import_grammar(grammar)
    return p


def run_tool(qtbot, tools, name, args=""):
    assert tools.select(name), name
    tools.input.setText(args)
    tools.run()
    qtbot.waitUntil(lambda: not tools.running, timeout=10000)
    return tools.output.toPlainText()


# ---------- 言語の機能 ----------

def test_every_language_declares_commands():
    registry.load_builtin()
    for lang_id in ("pute", "uri", "myamyu"):
        lang = registry.get(lang_id)
        assert lang.commands, lang_id
        for c in lang.commands:
            assert c.label and c.name


def test_tools_myamyu(qtbot, win, tmp_path):
    p = project(tmp_path, "ミャミュ語", "myamyu", rules=FIXTURES / "mini_myamyu_rules.yaml")
    win.open_project(p.root)
    tools = win.rules_panel.tools
    assert [tools.command.itemData(i) for i in range(tools.command.count())] == \
        ["verb", "parse", "sound", "segment", "affixes", "number"]
    assert win.rules_panel.tabs.tabText(2) == "言語の機能"
    out = run_tool(qtbot, tools, "verb", "sum --tense 未来 --voice 受動態 --aspect ok --subject 三人称単数")
    assert "ma-sum-ak-ok-ok → masumakokok" in out
    assert "相 ok(起動相) / 主語マーカー ok(三人称単数)" in run_tool(qtbot, tools, "parse", "ma-sum-ak-ok-ok")
    assert "■ 格: ta(主格)、ak(処格)" in run_tool(qtbot, tools, "affixes")
    assert tools.status.text().startswith("終わった")
    # 例を入れる
    tools.select("sound")
    tools.fill_example()
    assert tools.input.text() == "gaf baz ssa"


def test_tools_uri_and_pute(qtbot, win, tmp_path, mini_pute):
    uri = project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json", FIXTURES / "mini_uri_rules.yaml")
    pute = project(tmp_path, "ピュテ語", "pute", mini_pute, FIXTURES / "mini_rules.yaml")
    win.open_project(uri.root)
    tools = win.rules_panel.tools
    assert "FoTONe\tfotoone" in run_tool(qtbot, tools, "modern", "FoTONe")
    assert "koruma は辞書にある" in run_tool(qtbot, tools, "analyze", "SuKoRuMa")
    win.open_project(pute.root)  # 言語を替えると、コマンドの一覧も替わる
    assert tools.command.itemData(0) == "inflect"
    out = run_tool(qtbot, tools, "inflect", "noun kabo")
    assert "| 高 | kabo-b | kabo-bas | kabo-bes |" in out
    assert "kabotchu" in run_tool(qtbot, tools, "check", "節点 外")


def test_tools_use_unsaved_edits(qtbot, win, tmp_path):
    uri = project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json", FIXTURES / "mini_uri_rules.yaml")
    win.open_project(uri.root)
    win.new_word()
    win.editor.form.setText("PaTaMo")
    win.editor.translations.add_row("名詞", "架空の新語")
    win.editor.apply_button.click()
    assert "patamo  (PaTaMo)  架空の新語" in run_tool(qtbot, win.rules_panel.tools, "find", "新語")


def test_tools_language_without_commands(qtbot, win, tmp_path, mini_pute):
    p = project(tmp_path, "名なし", None, mini_pute)
    win.open_project(p.root)
    tools = win.rules_panel.tools
    assert tools.command.count() == 0 and not tools.run_button.isEnabled()
    assert "画面から呼べる機能がない" in tools.hint.text()


# ---------- 区分・見出しの選択肢 ----------

def test_titles_by_frequency():
    d = Dictionary.load(FIXTURES / "mini_uri.json")
    assert S.titles(d, "translations") == ["名詞", "動詞", "接続詞"]
    d2 = Dictionary.load(FIXTURES / "mini_pute.json")
    assert S.translation_titles(d2) == ["存在概念", "数理概念", "修飾概念"]
    assert S.titles(d2, "contents") == ["語源", "語義"]  # 語源 2 回、語義 1 回
    assert S.titles(d2, "variations") == ["短縮形"]


def test_row_table_combo_delegate(qtbot):
    t = RowTable(("区分", "訳語"), options=["名詞", "動詞"])
    qtbot.addWidget(t)
    t.add_row("", "架空")
    index = t.table.model().index(0, 0)
    delegate = t.table.itemDelegateForColumn(0)
    editor = delegate.createEditor(t.table.viewport(), QStyleOptionViewItem(), index)
    assert isinstance(editor, QComboBox) and editor.isEditable()
    assert [editor.itemText(i) for i in range(editor.count())] == ["名詞", "動詞"]
    editor.setCurrentIndex(1)                     # 既にある区分を選ぶ
    delegate.setModelData(editor, t.table.model(), index)
    assert t.rows() == [("動詞", "架空")]
    editor.setEditText("被動詞 ")                 # 新しい区分を書く
    delegate.setModelData(editor, t.table.model(), index)
    assert t.rows() == [("被動詞", "架空")]


def test_new_word_offers_existing_titles(qtbot, win, tmp_path):
    uri = project(tmp_path, "ウリ語", "uri", FIXTURES / "mini_uri.json")
    win.open_project(uri.root)
    win.new_word()
    assert win.editor.translations.options == ["名詞", "動詞", "接続詞"]
    t = win.editor.translations.table
    win.editor.translations._add_and_edit()  # 「行を追加」: 区分の入力欄がすぐ開く
    assert t.state() == QAbstractItemView.State.EditingState
    editor = t.findChildren(QComboBox)[-1]
    assert editor.isEditable() and editor.itemText(0) == "名詞"
    editor.setEditText("動詞")
    t.item(0, 1).setText("架空の動き")
    win.editor.form.setText("MaNo")
    box = win.editor.add_content("", "説明")
    assert box.title.isEditable() and box.title.count() == 0  # mini_uri には内容欄がない
    box.title.setEditText("語法")
    win.editor.apply_button.click()
    w = win.dictionary.get(win.current_id)
    assert w["translations"] == [{"title": "動詞", "forms": ["架空の動き"]}]
    assert w["contents"] == [{"title": "語法", "text": "説明"}]
    # 次に編集するときは、新しく書いた見出しも選択肢に入る
    win.new_word()
    assert "語法" in win.editor.content_options
