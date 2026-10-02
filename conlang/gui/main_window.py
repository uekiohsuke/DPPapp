"""辞書の画面(M2)。辞書の一覧・検索・閲覧・編集と、zpdic 形式での保存

画面はコア(conlang.core)を呼ぶだけで、検索や警告の中身はここに書かない。
"""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QStackedWidget, QTableView, QTextBrowser, QVBoxLayout, QWidget,
)

from conlang.core import registry
from conlang.core import search as S
from conlang.core.backup import backup_file
from conlang.core.project import Project, ProjectError
from conlang.core.rules import RulesError
from conlang.core.validate import check_dictionary
from conlang.core.wordedit import apply_fields, separator, to_fields
from conlang.core.zpdic import Dictionary, ZpdicError, form, meanings

from . import word_view
from .rules_panel import RulesPanel
from .word_editor import WordEditor

APP_TITLE = "人工言語創作アプリ"


class WordTableModel(QAbstractTableModel):
    HEADERS = ("見出し語", "訳語", "タグ", "id")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.words: list[dict] = []

    def set_words(self, words: list[dict]) -> None:
        self.beginResetModel()
        self.words = words
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.words)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        w = self.words[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return (form(w), "、".join(meanings(w)), "、".join(w.get("tags", [])), w["entry"].get("id"))[col]
        if role == Qt.UserRole:
            return w["entry"].get("id")
        return None

    def row_of(self, word_id) -> int:
        return next((i for i, w in enumerate(self.words) if w["entry"].get("id") == word_id), -1)


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        registry.load_builtin()
        self.settings = settings or QSettings("conlang", "conlang")
        self.project: Project | None = None
        self.dictionary: Dictionary | None = None
        self.dirty = False
        self.current_id = None
        self.editing_new: dict | None = None  # 新しい語を編集中のときの、まだ辞書にない項目
        self._build()
        self._update_title()
        self.resize(1200, 760)
        self.resizeDocks([self.issue_dock], [130], Qt.Vertical)

    # ---------- 画面を作る ----------

    def _build(self) -> None:
        # 検索
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("検索(見出し語・訳語・内容・タグ)")
        self.search_box.setClearButtonEnabled(True)
        self.mode_box = QComboBox()
        self.mode_box.addItems(S.MODES)
        self.target_checks = {t: QCheckBox(t) for t in S.ALL_TARGETS}
        for t in (S.FORM, S.TRANSLATION):
            self.target_checks[t].setChecked(True)
        self.content_title_box = QComboBox()
        self.count_label = QLabel()

        self.search_box.textChanged.connect(self.refresh_list)
        self.mode_box.currentIndexChanged.connect(self.refresh_list)
        self.content_title_box.currentIndexChanged.connect(self.refresh_list)
        for c in self.target_checks.values():
            c.toggled.connect(self.refresh_list)

        targets = QHBoxLayout()
        for c in self.target_checks.values():
            targets.addWidget(c)
        targets.addWidget(self.content_title_box)
        targets.addStretch()

        # 一覧
        self.model = WordTableModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)  # 最初は検索の順(近い順)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col, width in ((0, 160), (2, 90), (3, 48)):
            self.table.setColumnWidth(col, width)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.table.doubleClicked.connect(lambda _: self.edit_current())

        left = QWidget()
        ll = QVBoxLayout(left)
        row = QHBoxLayout()
        row.addWidget(self.search_box)
        row.addWidget(self.mode_box)
        ll.addLayout(row)
        ll.addLayout(targets)
        ll.addWidget(self.table)
        ll.addWidget(self.count_label)
        self.left_panel = left

        # 閲覧
        self.viewer = QTextBrowser()
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_link)
        self.edit_button = QPushButton("編集")
        self.delete_button = QPushButton("削除")
        self.edit_button.clicked.connect(self.edit_current)
        self.delete_button.clicked.connect(self.delete_current)
        view_page = QWidget()
        vl = QVBoxLayout(view_page)
        vl.addWidget(self.viewer)
        vb = QHBoxLayout()
        vb.addStretch()
        vb.addWidget(self.delete_button)
        vb.addWidget(self.edit_button)
        vl.addLayout(vb)

        # 編集
        self.editor = WordEditor()
        self.editor.applied.connect(self._on_apply)
        self.editor.cancelled.connect(self._end_edit)

        self.stack = QStackedWidget()
        self.stack.addWidget(view_page)
        self.stack.addWidget(self.editor)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)

        # 警告
        self.issue_list = QListWidget()
        self.issue_list.itemActivated.connect(self._on_issue)
        self.issue_list.itemDoubleClicked.connect(self._on_issue)
        dock = QDockWidget("警告", self)
        dock.setObjectName("issues")
        dock.setWidget(self.issue_list)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.issue_dock = dock

        # 規則
        self.rules_panel = RulesPanel()
        rdock = QDockWidget("規則", self)
        rdock.setObjectName("rules")
        rdock.setWidget(self.rules_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, rdock)
        self.tabifyDockWidget(dock, rdock)
        dock.raise_()
        self.rules_dock = rdock

        self._build_menu()
        self._set_enabled(False)

    def _action(self, menu, text, slot, shortcut=None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("ファイル(&F)")
        self._action(m, "新しいプロジェクト…", self.new_project_dialog)
        self._action(m, "プロジェクトを開く…", self.open_project_dialog, QKeySequence.Open)
        m.addSeparator()
        self.import_action = self._action(m, "zpdic 辞書を取り込む…", self.import_dialog)
        self.import_rules_action = self._action(m, "規則ファイルを取り込む…", self.import_rules_dialog)
        self.save_action = self._action(m, "保存", self.save, QKeySequence.Save)
        self.export_action = self._action(m, "zpdic 形式で書き出す…", self.export_dialog)
        m.addSeparator()
        self._action(m, "終了", self.close, QKeySequence.Quit)
        m = self.menuBar().addMenu("辞書(&D)")
        self.new_word_action = self._action(m, "新しい語", self.new_word, QKeySequence.New)
        self.edit_action = self._action(m, "編集", self.edit_current, "F2")
        self.delete_action = self._action(m, "削除", self.delete_current, QKeySequence.Delete)
        m.addSeparator()
        self._action(m, "検索欄へ", lambda: self.search_box.setFocus(), QKeySequence.Find)
        m = self.menuBar().addMenu("表示(&V)")
        m.addAction(self.issue_dock.toggleViewAction())
        m.addAction(self.rules_dock.toggleViewAction())

    def _set_enabled(self, on: bool) -> None:
        for w in (self.left_panel, self.stack, self.import_action, self.import_rules_action,
                  self.save_action, self.export_action,
                  self.new_word_action, self.edit_action, self.delete_action):
            w.setEnabled(on)

    # ---------- 確認(テストで差し替えられるように、ここに集める) ----------

    def ask(self, title: str, text: str, buttons=QMessageBox.Yes | QMessageBox.No, default=QMessageBox.No):
        return QMessageBox.question(self, title, text, buttons, default)

    def inform(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def error(self, text: str) -> None:
        QMessageBox.warning(self, APP_TITLE, text)

    # ---------- プロジェクト ----------

    def open_project(self, path: str | Path) -> bool:
        if not self.maybe_save():
            return False
        try:
            project = Project.open(path)
            d = project.load_dictionary()
        except (ProjectError, ZpdicError, OSError) as e:
            self.error(f"プロジェクトを開けなかった:\n{e}")
            return False
        self.project, self.dictionary = project, d
        self.settings.setValue("last_project", str(project.root))
        self._set_dirty(False)
        self._set_enabled(True)
        self._end_edit()
        self._reload_content_titles()
        self.refresh_list()
        self.refresh_issues()
        self.reload_rules()
        self.statusBar().showMessage(f"開いた: {project.root}({len(d)}項目)", 5000)
        return True

    def reload_rules(self) -> None:
        try:
            rules = self.project.load_rules()
        except (RulesError, OSError) as e:
            rules = None
            self.error(f"規則ファイルを読めなかった:\n{e}")
        self.rules_panel.set_rules(rules, self.project.language)

    def import_rules_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "規則ファイルを取り込む", "", "規則ファイル (*.yaml *.yml)")
        if path:
            self.import_rules(path)

    def import_rules(self, path: str | Path) -> bool:
        if self.ask("規則の取り込み", f"今の規則をバックアップしてから、次の規則に置き換える。\n{path}\n"
                    "元のファイルは書き換えない。") != QMessageBox.Yes:
            return False
        try:
            bak = self.project.import_rules(path)
        except (ProjectError, RulesError, OSError) as e:
            self.error(f"取り込めなかった:\n{e}")
            return False
        self.reload_rules()
        self.rules_dock.raise_()
        self.statusBar().showMessage("規則を取り込んだ" + (f"。前の規則のバックアップ: {bak}" if bak else ""), 8000)
        return True

    def open_project_dialog(self) -> None:
        start = self.settings.value("last_project", "") or ""
        path = QFileDialog.getExistingDirectory(self, "プロジェクトのフォルダを選ぶ", start)
        if path:
            self.open_project(path)

    def new_project_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "新しいプロジェクトのフォルダを選ぶ(空のフォルダ)")
        if not path:
            return
        name, ok = QInputDialog.getText(self, "新しいプロジェクト", "言語名:")
        if not ok or not name.strip():
            return
        lang, ok = QInputDialog.getText(self, "新しいプロジェクト", "言語別機能の id(ピュテ語なら pute。なければ空):")
        try:
            Project.create(path, name.strip(), lang.strip() or None)
        except ProjectError as e:
            self.error(str(e))
            return
        self.open_project(path)

    def import_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "zpdic 辞書を取り込む", "", "zpdic 辞書 (*.json)")
        if path:
            self.import_dictionary(path)

    def import_dictionary(self, path: str | Path) -> bool:
        if self.dirty and self.ask("取り込み", "保存していない変更がある。破棄して取り込むか?") != QMessageBox.Yes:
            return False
        if self.ask("取り込み", f"今の辞書をバックアップしてから、次の辞書に置き換える。\n{path}\n"
                    "元のファイルは書き換えない。") != QMessageBox.Yes:
            return False
        try:
            bak = self.project.import_dictionary(path)
        except (ProjectError, ZpdicError, OSError) as e:
            self.error(f"取り込めなかった:\n{e}")
            return False
        self._set_dirty(False)
        self.open_project(self.project.root)
        if bak:
            self.statusBar().showMessage(f"取り込んだ。前の辞書のバックアップ: {bak}", 8000)
        return True

    def save(self) -> bool:
        if not self.project or not self.dictionary:
            return False
        if self.stack.currentWidget() is self.editor:
            self.error("編集中の項目がある。適用するか取り消してから保存する")
            return False
        try:
            bak = self.project.save_dictionary(self.dictionary)
        except OSError as e:
            self.error(f"保存できなかった:\n{e}")
            return False
        self._set_dirty(False)
        self.statusBar().showMessage(f"保存した({len(self.dictionary)}項目)。バックアップ: {bak}", 8000)
        return True

    def export_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "zpdic 形式で書き出す", "", "zpdic 辞書 (*.json)")
        if path:
            self.export(path)

    def export(self, path: str | Path) -> Path | None:
        """プロジェクトの外へ書き出す。同じ名前のファイルがあれば、プロジェクトの backup に退避する"""
        bak = backup_file(path, self.project.backup_dir)
        self.dictionary.save(path)
        self.statusBar().showMessage(f"書き出した: {path}", 8000)
        return bak

    def maybe_save(self) -> bool:
        """保存していない変更があれば聞く。続けてよければ True"""
        if not self.dirty:
            return True
        r = self.ask("保存", "保存していない変更がある。保存するか?",
                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def closeEvent(self, event) -> None:
        if self.stack.currentWidget() is self.editor:
            if self.ask("終了", "編集中の項目がある。破棄して終了するか?") != QMessageBox.Yes:
                event.ignore()
                return
            self._end_edit()
        if self.maybe_save():
            event.accept()
        else:
            event.ignore()

    def _set_dirty(self, on: bool) -> None:
        self.dirty = on
        self._update_title()

    def _update_title(self) -> None:
        if self.project:
            self.setWindowTitle(f"{'*' if self.dirty else ''}{self.project.name} — {APP_TITLE}")
        else:
            self.setWindowTitle(APP_TITLE)

    # ---------- 一覧と検索 ----------

    def _reload_content_titles(self) -> None:
        self.content_title_box.blockSignals(True)
        cur = self.content_title_box.currentText()
        self.content_title_box.clear()
        self.content_title_box.addItem("すべての内容")
        self.content_title_box.addItems([t for t in S.content_titles(self.dictionary) if t])
        i = self.content_title_box.findText(cur)
        self.content_title_box.setCurrentIndex(max(i, 0))
        self.content_title_box.blockSignals(False)

    def query(self) -> S.Query:
        title = self.content_title_box.currentText()
        return S.Query(
            text=self.search_box.text(),
            targets=tuple(t for t, c in self.target_checks.items() if c.isChecked()),
            mode=self.mode_box.currentText(),
            content_titles=() if self.content_title_box.currentIndex() <= 0 else (title,),
        )

    def refresh_list(self) -> None:
        if not self.dictionary:
            return
        self.content_title_box.setEnabled(self.target_checks[S.CONTENT].isChecked())
        keep = self.current_id
        hits = S.search(self.dictionary, self.query())
        self.model.set_words([h.word for h in hits])
        self.count_label.setText(f"{len(hits)} / {len(self.dictionary)} 項目")
        if keep is not None and self.select_word(keep):
            return
        if hits:
            self.table.selectRow(0)
        else:
            self._show(None)

    def select_word(self, word_id) -> bool:
        row = self.model.row_of(word_id)
        if row < 0:
            return False
        idx = self.proxy.mapFromSource(self.model.index(row, 0))
        self.table.selectRow(idx.row())
        self.table.scrollTo(idx)
        self._show(word_id)
        return True

    def _on_row_changed(self, current, _previous) -> None:
        if current.isValid():
            self._show(self.proxy.index(current.row(), 0).data(Qt.UserRole))

    def _show(self, word_id) -> None:
        self.current_id = word_id
        w = self.dictionary.get(word_id) if (self.dictionary and word_id is not None) else None
        self.viewer.setHtml(word_view.render(w, self.dictionary) if w else "<p style='color:#999'>項目を選ぶ</p>")
        self.edit_button.setEnabled(w is not None)
        self.delete_button.setEnabled(w is not None)

    def _on_link(self, url: QUrl) -> None:
        s = url.toString()
        if s.startswith("word:"):
            wid = int(s[5:])
            if not self.select_word(wid):
                self.search_box.clear()
                self.select_word(wid)

    # ---------- 編集 ----------

    def edit_current(self) -> None:
        w = self.dictionary.get(self.current_id) if self.dictionary and self.current_id is not None else None
        if w is None:
            return
        self.editing_new = None
        self._begin_edit(w, f"編集: {form(w)}(id {w['entry'].get('id')})")

    def new_word(self) -> None:
        if not self.dictionary:
            return
        template = (self.dictionary.data.get("zpdic") or {}).get("defaultWord") or {}
        w = copy.deepcopy(template) or {"entry": {}}
        w.setdefault("entry", {})
        w["entry"]["id"], w["entry"]["form"] = self.dictionary.next_id(), ""
        for k in ("translations", "tags", "contents", "variations", "relations"):
            w.setdefault(k, [])
        self.editing_new = w
        self._begin_edit(w, "新しい語")

    def _begin_edit(self, w: dict, heading: str) -> None:
        self.editor.load(to_fields(w, self.dictionary), heading, separator(self.dictionary))
        self.stack.setCurrentWidget(self.editor)
        self.left_panel.setEnabled(False)
        for a in (self.new_word_action, self.edit_action, self.delete_action, self.import_action):
            a.setEnabled(False)

    def _end_edit(self) -> None:
        self.editing_new = None
        self.stack.setCurrentIndex(0)
        on = self.dictionary is not None
        self.left_panel.setEnabled(on)
        for a in (self.new_word_action, self.edit_action, self.delete_action, self.import_action):
            a.setEnabled(on)

    def _on_apply(self, fields) -> None:
        base = self.editing_new or self.dictionary.get(self.current_id)
        new, notes = apply_fields(base, fields, self.dictionary)
        if not new["entry"]["form"]:
            self.error("見出し語が空")
            return
        wid = new["entry"]["id"]
        if self.editing_new is not None:
            self.dictionary.words.append(new)
        else:
            self.dictionary.replace(wid, new)
        self._set_dirty(True)
        self._end_edit()
        self._reload_content_titles()
        self.current_id = wid
        self.refresh_list()
        if not self.select_word(wid):  # 検索に当たらなくなったときは、検索を消して出す
            self.search_box.clear()
            self.select_word(wid)
        issues = self.refresh_issues()
        mine = [i.message for i in issues if i.word_id == wid]
        msg = notes + mine
        self.statusBar().showMessage("適用した(まだ保存していない)" + ("。注意: " + " / ".join(msg) if msg else ""), 10000)

    def delete_current(self) -> None:
        w = self.dictionary.get(self.current_id) if self.dictionary and self.current_id is not None else None
        if w is None:
            return
        if self.ask("削除", f"{form(w)}(id {w['entry'].get('id')})を削除するか?") != QMessageBox.Yes:
            return
        self.dictionary.remove(w["entry"].get("id"))
        self.current_id = None
        self._set_dirty(True)
        self.refresh_list()
        self.refresh_issues()
        self.statusBar().showMessage(f"{form(w)} を削除した(まだ保存していない)", 8000)

    # ---------- 警告 ----------

    def refresh_issues(self):
        self.issue_list.clear()
        if not self.dictionary:
            return []
        issues = check_dictionary(self.dictionary)
        for i in issues:
            item = QListWidgetItem(f"[{i.kind}] {i.message}")
            item.setData(Qt.UserRole, i.word_id)
            self.issue_list.addItem(item)
        self.issue_dock.setWindowTitle(f"警告({len(issues)}件)")
        return issues

    def _on_issue(self, item: QListWidgetItem) -> None:
        wid = item.data(Qt.UserRole)
        if wid is not None and not self.select_word(wid):
            self.search_box.clear()
            self.select_word(wid)
