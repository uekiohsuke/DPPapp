"""項目の編集画面。入力欄の中身は conlang.core.wordedit.WordFields でやりとりする"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from conlang.core.wordedit import WordFields


def title_combo(options: list[str], current: str = "", placeholder: str = "") -> QComboBox:
    """既にある見出し(区分)から選べ、新しいものも書ける入力欄"""
    box = QComboBox()
    box.setEditable(True)
    box.setInsertPolicy(QComboBox.NoInsert)
    box.addItems([o for o in options if o])
    box.setCurrentIndex(-1)
    box.setEditText(current)
    if placeholder:
        box.lineEdit().setPlaceholderText(placeholder)
    return box


class ComboDelegate(QStyledItemDelegate):
    """表の列を、既にある値から選べる(新しい値も書ける)入力欄にする"""

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options  # () → list[str]
        self.open_editor: QComboBox | None = None  # 開いている入力欄(適用のときに、内容を書き込むため)

    def createEditor(self, parent, option, index):
        box = title_combo(self.options())
        box.setParent(parent)
        self.open_editor = box
        return box

    def destroyEditor(self, editor, index):
        if editor is self.open_editor:
            self.open_editor = None
        super().destroyEditor(editor, index)

    def setEditorData(self, editor, index):
        editor.setEditText(index.data(Qt.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText().strip(), Qt.EditRole)


class RowTable(QWidget):
    """2列の表と、行の追加・削除ボタン。options があれば、1列目は既にある値から選べる"""

    def __init__(self, headers: tuple[str, str], parent=None, options: list[str] | None = None):
        super().__init__(parent)
        self.options: list[str] = list(options or [])
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(list(headers))
        # 区分の列は、空でもプルダウンが使える幅にする(幅は手でも変えられる)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(90)
        self.delegate = ComboDelegate(lambda: self.options, self.table)
        self.table.setItemDelegateForColumn(0, self.delegate)
        add, rm = QPushButton("行を追加"), QPushButton("選んだ行を削除")
        add.clicked.connect(self._add_and_edit)
        rm.clicked.connect(self.remove_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(rm)
        buttons.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)
        lay.addLayout(buttons)

    def commit_open_editor(self) -> None:
        """開いている入力欄(区分を選んでいる途中)の内容を、表に書き込んで閉じる"""
        editor = self.delegate.open_editor
        if editor is not None and self.table.state() == QAbstractItemView.State.EditingState:
            self.table.commitData(editor)
            self.table.closeEditor(editor, QStyledItemDelegate.EndEditHint.NoHint)

    def set_options(self, options: list[str]) -> None:
        self.options = [o for o in options if o]

    def add_row(self, a: str = "", b: str = "") -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(a))
        self.table.setItem(r, 1, QTableWidgetItem(b))

    def _add_and_edit(self) -> None:
        """行を足し、1列目(区分)の入力欄をすぐ開く(既にある区分から選べる)"""
        self.add_row()
        item = self.table.item(self.table.rowCount() - 1, 0)
        self.table.setCurrentItem(item)
        self.table.editItem(item)

    def remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def set_rows(self, rows) -> None:
        self.table.setRowCount(0)
        for a, b in rows:
            self.add_row(a, b)

    def rows(self) -> list[tuple[str, str]]:
        self.commit_open_editor()
        out = []
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c) for c in (0, 1)]
            out.append(tuple(c.text() if c else "" for c in cells))
        return out


class ContentBox(QFrame):
    """内容欄1つ(見出しと本文)"""

    def __init__(self, title: str, text: str, on_remove, parent=None, options: list[str] | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.title = title_combo(options or [], title, "見出し(例: 語義、語源)。既にあるものから選ぶか、新しく書く")
        self.text = QPlainTextEdit(text)
        self.text.setMinimumHeight(70)
        rm = QPushButton("削除")
        rm.clicked.connect(lambda: on_remove(self))
        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addWidget(rm)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.text)


class WordEditor(QWidget):
    applied = Signal(object)  # WordFields
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.heading = QLabel()
        self.form = QLineEdit()
        self.tags = QLineEdit()
        self.content_options: list[str] = []
        self.translations = RowTable(("区分", "訳語"))
        self.variations = RowTable(("区分", "綴り"))
        self.relations = RowTable(("区分", "関連先の見出し語"))
        self.contents_layout = QVBoxLayout()
        self.content_boxes: list[ContentBox] = []
        add_content = QPushButton("内容を追加")
        add_content.clicked.connect(lambda: self.add_content())
        self.hint = QLabel()
        self.hint.setStyleSheet("color: #666;")

        form = QFormLayout()
        form.addRow("見出し語", self.form)
        form.addRow("訳語", self.translations)
        form.addRow("タグ", self.tags)
        contents = QVBoxLayout()
        contents.addLayout(self.contents_layout)
        contents.addWidget(add_content)
        form.addRow("内容", contents)
        form.addRow("変化形", self.variations)
        form.addRow("関連語", self.relations)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(self.heading)
        inner_lay.addLayout(form)
        inner_lay.addWidget(self.hint)
        inner_lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        self.apply_button = QPushButton("適用")
        self.apply_button.setDefault(True)
        self.cancel_button = QPushButton("取り消し")
        self.apply_button.clicked.connect(lambda: self.applied.emit(self.fields()))
        self.cancel_button.clicked.connect(self.cancelled.emit)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)

        lay = QVBoxLayout(self)
        lay.addWidget(scroll)
        lay.addLayout(buttons)

    def set_title_options(self, translation_titles: list[str], content_titles: list[str],
                          variation_titles: list[str] = (), relation_titles: list[str] = ()) -> None:
        """区分・見出しの選択肢(辞書に既にあるもの)"""
        self.translations.set_options(translation_titles)
        self.variations.set_options(list(variation_titles))
        self.relations.set_options(list(relation_titles))
        self.content_options = [t for t in content_titles if t]
        for box in self.content_boxes:
            current = box.title.currentText()
            box.title.clear()
            box.title.addItems(self.content_options)
            box.title.setEditText(current)

    def add_content(self, title: str = "", text: str = "") -> ContentBox:
        box = ContentBox(title, text, self._remove_content, options=self.content_options)
        self.content_boxes.append(box)
        self.contents_layout.addWidget(box)
        return box

    def _remove_content(self, box: ContentBox) -> None:
        self.content_boxes.remove(box)
        box.setParent(None)
        box.deleteLater()

    def load(self, f: WordFields, heading: str, separator: str) -> None:
        self.heading.setText(f"<b>{heading}</b>")
        self.form.setText(f.form)
        self.tags.setText(f.tags)
        self.translations.set_rows(f.translations)
        self.variations.set_rows(f.variations)
        self.relations.set_rows(f.relations)
        for box in list(self.content_boxes):
            self._remove_content(box)
        for title, text in f.contents:
            self.add_content(title, text)
        self.hint.setText(f"訳語とタグは「{separator}」などの区切り文字で区切る。空の行は保存しない。")
        self.form.setFocus()

    def fields(self) -> WordFields:
        return WordFields(
            form=self.form.text(),
            translations=self.translations.rows(),
            tags=self.tags.text(),
            contents=[(b.title.currentText(), b.text.toPlainText()) for b in self.content_boxes],
            variations=self.variations.rows(),
            relations=self.relations.rows(),
        )
