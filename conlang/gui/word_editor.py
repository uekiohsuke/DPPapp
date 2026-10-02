"""項目の編集画面。入力欄の中身は conlang.core.wordedit.WordFields でやりとりする"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from conlang.core.wordedit import WordFields


class RowTable(QWidget):
    """2列の表と、行の追加・削除ボタン"""

    def __init__(self, headers: tuple[str, str], parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(90)
        add, rm = QPushButton("行を追加"), QPushButton("選んだ行を削除")
        add.clicked.connect(lambda: self.add_row())
        rm.clicked.connect(self.remove_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(rm)
        buttons.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table)
        lay.addLayout(buttons)

    def add_row(self, a: str = "", b: str = "") -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(a))
        self.table.setItem(r, 1, QTableWidgetItem(b))

    def remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def set_rows(self, rows) -> None:
        self.table.setRowCount(0)
        for a, b in rows:
            self.add_row(a, b)

    def rows(self) -> list[tuple[str, str]]:
        out = []
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c) for c in (0, 1)]
            out.append(tuple(c.text() if c else "" for c in cells))
        return out


class ContentBox(QFrame):
    """内容欄1つ(見出しと本文)"""

    def __init__(self, title: str, text: str, on_remove, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.title = QLineEdit(title)
        self.title.setPlaceholderText("見出し(例: 語義、語源)")
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

    def add_content(self, title: str = "", text: str = "") -> ContentBox:
        box = ContentBox(title, text, self._remove_content)
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
            contents=[(b.title.text(), b.text.toPlainText()) for b in self.content_boxes],
            variations=self.variations.rows(),
            relations=self.relations.rows(),
        )
