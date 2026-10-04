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
    QStackedWidget, QTableView, QTabWidget, QTextBrowser, QToolBar, QVBoxLayout, QWidget,
)

from conlang.core import registry
from conlang.core import search as S
from conlang.core.backup import backup_file
from conlang.core.project import Project, ProjectError
from conlang.core.rules import RulesError
from conlang.core.validate import ERROR, check_all
from conlang.core.wordedit import apply_fields, separator, to_fields
from conlang.core.zpdic import Dictionary, ZpdicError, form, meanings

from . import word_view
from .grammar_view import GrammarView
from .rules_panel import RulesPanel
from .word_editor import WordEditor

APP_TITLE = "人工言語創作アプリ"


class WordTableModel(QAbstractTableModel):
    HEADERS = ("見出し語", "訳語", "タグ", "id")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.words: list[dict] = []
        self.display = None  # 見出し語の表示を変える関数(なければ辞書の綴りのまま)

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
            f = self.display(form(w)) if self.display else form(w)
            return (f, "、".join(meanings(w)), "、".join(w.get("tags", [])), w["entry"].get("id"))[col]
        if role == Qt.ToolTipRole and col == 0 and self.display:
            return f"辞書の綴り: {form(w)}"
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
        self.rules = None
        self.language_docks: dict[tuple[str, str], QDockWidget] = {}
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
        self.display_box = QComboBox()
        self.display_box.setToolTip("見出し語の表示(辞書の綴りは変えない)")
        self.display_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.display_box.currentIndexChanged.connect(self._display_changed)
        row = QHBoxLayout()
        row.addWidget(self.search_box)
        row.addWidget(self.mode_box)
        row.addWidget(self.display_box)
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

        # 辞書と文法を、タブで切り替える
        self.grammar_view = GrammarView()
        self.views = QTabWidget()
        self.views.addTab(splitter, "辞書")
        self.views.addTab(self.grammar_view, "文法")
        self.setCentralWidget(self.views)

        # プロジェクト(言語)の切り替え
        bar = QToolBar("プロジェクト", self)
        bar.setObjectName("projects")
        bar.setMovable(False)
        bar.addWidget(QLabel(" プロジェクト: "))
        self.project_box = QComboBox()
        self.project_box.setMinimumWidth(320)
        self.project_box.activated.connect(self._project_chosen)
        bar.addWidget(self.project_box)
        self.addToolBar(bar)
        self._reload_project_box()

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
        self.import_grammar_action = self._action(m, "文法文書を取り込む…", self.import_grammar_dialog)
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
        self.view_menu = m
        m = self.menuBar().addMenu("設定(&S)")
        self._action(m, "LLM の設定…", self.llm_settings_dialog)
        m.addSeparator()
        self._action(m, "デスクトップとスタートメニューにショートカットを作る", self.create_shortcuts)
        self.llm_label = QLabel()
        self.statusBar().addPermanentWidget(self.llm_label)
        self._update_llm_label()

    def _update_llm_label(self) -> None:
        from conlang.core import llm
        cfg = llm.load_config()
        self.llm_label.setText(f"LLM: {cfg.model or '(未設定)'}" + (f"(考える過程 {cfg.reasoning_effort})"
                                                                   if cfg.reasoning_effort else ""))
        self.llm_label.setToolTip(cfg.url)

    def create_shortcuts(self) -> list[Path]:
        """前に開いたプロジェクトを開くショートカット(プロジェクトは決め打ちしない)"""
        from . import shortcut
        try:
            made = shortcut.create(shortcut.plan())
        except OSError as e:
            self.error(str(e))
            return []
        self.inform("ショートカット", "ショートカットを作った:\n" + "\n".join(str(p) for p in made))
        return made

    def llm_settings_dialog(self) -> None:
        from .llm_settings import LLMSettingsDialog
        dlg = LLMSettingsDialog(self)
        if dlg.exec():
            self._update_llm_label()
            for dock in self.language_docks.values():
                if hasattr(dock.widget(), "_update_hint"):
                    dock.widget()._update_hint()
            self.statusBar().showMessage(f"LLM の設定を保存した: {dlg.cfg.model}", 5000)

    def _set_enabled(self, on: bool) -> None:
        for w in (self.left_panel, self.stack, self.import_action, self.import_rules_action, self.import_grammar_action,
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
        self._remember_project(project)
        self.current_id = None
        self._set_dirty(False)
        self._set_enabled(True)
        self._end_edit()
        self._reload_content_titles()
        self.refresh_list()
        self.reload_rules()
        self.statusBar().showMessage(f"開いた: {project.root}({len(d)}項目)", 5000)
        return True

    # --- 最近のプロジェクト(言語の切り替え) ---

    RECENT_KEY = "recent_projects"
    RECENT_MAX = 12

    def recent_projects(self) -> list[str]:
        v = self.settings.value(self.RECENT_KEY, []) or []
        items = [v] if isinstance(v, str) else list(v)
        return [p for p in items if (Path(p) / "project.json").exists()]

    def _remember_project(self, project: Project) -> None:
        root = str(project.root.resolve())
        items = [root] + [p for p in self.recent_projects() if str(Path(p).resolve()) != root]
        self.settings.setValue(self.RECENT_KEY, items[:self.RECENT_MAX])
        self._reload_project_box()

    def _reload_project_box(self) -> None:
        self.project_box.blockSignals(True)
        self.project_box.clear()
        current = str(self.project.root.resolve()) if self.project else None
        for p in self.recent_projects():
            try:
                meta = Project.open(p).meta
            except (ProjectError, OSError, ValueError):
                continue
            lang = registry.get(meta.get("language"))
            label = f"{meta.get('name', '')}  —  {p}" + (f"  [{lang.name}の機能]" if lang else "")
            self.project_box.addItem(label, p)
        self.project_box.addItem("ほかのプロジェクトを開く…", None)
        i = self.project_box.findData(current) if current else -1
        self.project_box.setCurrentIndex(i if i >= 0 else self.project_box.count() - 1)
        self.project_box.blockSignals(False)

    def _project_chosen(self, index: int) -> None:
        path = self.project_box.itemData(index)
        if path is None:
            self.open_project_dialog()
        elif not self.project or str(self.project.root.resolve()) != path:
            self.open_project(path)
        self._reload_project_box()  # 開けなかったときや取り消したときは、選択を元に戻す

    def reload_rules(self) -> None:
        """規則と文法文書を読み直し、規則の欄と警告を出し直す"""
        try:
            self.rules = self.project.load_rules()
        except (RulesError, OSError) as e:
            self.rules = None
            self.error(f"規則ファイルを読めなかった:\n{e}")
        grammar = None
        gpath = self.project.grammar_path(self.rules)
        if gpath is not None:
            try:
                grammar = (gpath.name, gpath.read_text(encoding="utf-8-sig"))
            except OSError:
                grammar = None
        self.rules_panel.set_rules(self.rules, self.project.language, grammar,
                                   registry.Context(self.dictionary, self.rules, self.project))
        self.refresh_issues()
        self._sync_language_panels()
        self._sync_display_box()
        self.reload_grammar_view(gpath)

    def reload_grammar_view(self, preferred: Path | None = None) -> None:
        g = self.project.grammar_dir
        docs = sorted(g.glob("*.md")) if g.is_dir() else []
        self.grammar_view.set_documents(docs, preferred)
        self.views.setTabText(1, f"文法({len(docs)})" if docs else "文法")

    DICT_FORM = "辞書の綴り"

    def _sync_display_box(self) -> None:
        """言語に表示の切り替え(ウリ語の現代の転写など)があれば、選べるようにする"""
        lang = registry.get(self.project.language if self.project else None)
        names = list((lang.transcriptions or {}).keys()) if lang else []
        current = self.display_box.currentText()
        self.display_box.blockSignals(True)
        self.display_box.clear()
        self.display_box.addItem(self.DICT_FORM)
        self.display_box.addItems(names)
        i = self.display_box.findText(current)
        self.display_box.setCurrentIndex(max(i, 0))
        self.display_box.blockSignals(False)
        self.display_box.setVisible(bool(names))
        self._display_changed()

    def display_function(self):
        lang = registry.get(self.project.language if self.project else None)
        name = self.display_box.currentText()
        if not lang or not lang.transcriptions or name not in lang.transcriptions:
            return None
        return lang.transcriptions[name](self.rules)

    def _display_changed(self, *_) -> None:
        self.model.beginResetModel()
        self.model.display = self.display_function()
        self.model.endResetModel()
        if self.current_id is not None:
            self.select_word(self.current_id)

    def _sync_language_panels(self) -> None:
        """言語別の欄(ピュテ語の造語など)を、プロジェクトの言語に合わせて出す"""
        lang = registry.get(self.project.language if self.project else None)
        for key, dock in list(self.language_docks.items()):
            if lang is None or key[0] != lang.id:
                if getattr(dock.widget(), "running", False):
                    dock.widget().cancel()  # 裏の処理の結果は捨てる
                self.removeDockWidget(dock)
                dock.deleteLater()
                del self.language_docks[key]
        if lang is not None and lang.gui_panels is not None:
            for title, factory in lang.gui_panels():
                key = (lang.id, title)
                if key not in self.language_docks:
                    dock = QDockWidget(f"{title}({lang.name})", self)
                    dock.setObjectName(f"lang-{lang.id}-{title}")
                    dock.setWidget(factory())
                    self.addDockWidget(Qt.BottomDockWidgetArea, dock)
                    self.tabifyDockWidget(self.issue_dock, dock)
                    self.view_menu.addAction(dock.toggleViewAction())
                    self.language_docks[key] = dock
        ctx = registry.Context(self.dictionary, self.rules, self.project)
        for dock in self.language_docks.values():
            dock.widget().set_context(ctx)
        self.issue_dock.raise_()

    def import_grammar_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "文法文書を取り込む", "", "Markdown (*.md)")
        if path:
            self.import_grammar(path)

    def import_grammar(self, path: str | Path) -> bool:
        try:
            bak = self.project.import_grammar(path)
        except (ProjectError, OSError) as e:
            self.error(f"取り込めなかった:\n{e}")
            return False
        self.reload_rules()
        self.views.setCurrentWidget(self.grammar_view)
        self.statusBar().showMessage("文法文書を取り込んだ" + (f"。前の文書のバックアップ: {bak}" if bak else ""), 8000)
        return True

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
        busy = [d.windowTitle() for d in self.language_docks.values() if getattr(d.widget(), "running", False)]
        if self.rules_panel.running:
            busy.append("規則(LLM による検査)")
        if busy and self.ask("終了", "LLM の処理が終わっていない: " + "、".join(busy) + "\n結果を捨てて終了するか?") != QMessageBox.Yes:
            event.ignore()
            return
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
        self.viewer.setHtml(word_view.render(w, self.dictionary, self.model.display) if w
                            else "<p style='color:#999'>項目を選ぶ</p>")
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
        """辞書の警告と整合性チェック(共通と言語別)。誤りを先に出す"""
        self.issue_list.clear()
        if not self.dictionary:
            return []
        issues = check_all(self.dictionary, self.rules, registry.get(self.project.language if self.project else None))
        issues.sort(key=lambda i: i.level != ERROR)
        for i in issues:
            item = QListWidgetItem(f"[{i.level}][{i.kind}] {i.message}")
            item.setData(Qt.UserRole, i.word_id)
            if i.level == ERROR:
                item.setForeground(Qt.red)
            self.issue_list.addItem(item)
        errors = sum(1 for i in issues if i.level == ERROR)
        self.issue_dock.setWindowTitle(f"警告(誤り {errors}件・注意 {len(issues) - errors}件)")
        return issues

    def _on_issue(self, item: QListWidgetItem) -> None:
        wid = item.data(Qt.UserRole)
        if wid is not None and not self.select_word(wid):
            self.search_box.clear()
            self.select_word(wid)
