"""文法文書の閲覧(仕様書 4.5)。プロジェクトの grammar/ にある Markdown を表示する

- 目次(見出し)から移動、文書の中の検索
- 状態タグ(【決定】【仮】など)に色を付け、数を出す
- 規則の目印(<!-- rule: ID -->)は、表示するかどうかを選べる
- ファイルが書き換えられたら、読み直す(外部のエディタで直すため)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSplitter, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from conlang.core import grammar_doc as G
from conlang.core.rule_docs import ANCHOR

TAG_COLORS = {"決定": "#1b7a3a", "仮": "#c06000", "メモ": "#3b5f8a", "辞書": "#7a3b8a",
              "保留": "#a02020", "要確認": "#a02020", "アイデア": "#2a7a7a"}


class GrammarView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.text = ""
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed)

        self.doc_box = QComboBox()
        self.doc_box.currentIndexChanged.connect(self._doc_selected)
        self.open_button = QPushButton("エディタで開く")
        self.open_button.clicked.connect(self.open_external)
        self.show_anchors = QCheckBox("規則の目印を表示")
        self.show_anchors.toggled.connect(lambda _: self.render())
        self.search = QLineEdit()
        self.search.setPlaceholderText("文書の中を検索(Enter で次へ)")
        self.search.returnPressed.connect(self.find_next)
        self.prev_button = QPushButton("前へ")
        self.prev_button.clicked.connect(lambda: self.find_next(backward=True))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.summary.setStyleSheet("color: #666;")

        self.toc = QTreeWidget()
        self.toc.setHeaderHidden(True)
        self.toc.itemClicked.connect(self._toc_clicked)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)

        top = QHBoxLayout()
        top.addWidget(QLabel("文書"))
        top.addWidget(self.doc_box, 1)
        top.addWidget(self.show_anchors)
        top.addWidget(self.open_button)
        find = QHBoxLayout()
        find.addWidget(self.search, 1)
        find.addWidget(self.prev_button)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(find)
        rl.addWidget(self.browser)
        split = QSplitter()
        split.addWidget(self.toc)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.summary)
        lay.addWidget(split, 1)
        self.set_documents([], None)

    # ---------- 文書の一覧 ----------

    def set_documents(self, paths: list[Path], preferred: Path | None) -> None:
        self.doc_box.blockSignals(True)
        self.doc_box.clear()
        for p in paths:
            self.doc_box.addItem(p.name, str(p))
        self.doc_box.blockSignals(False)
        if not paths:
            self.load(None)
            return
        i = self.doc_box.findData(str(preferred)) if preferred else -1
        self.doc_box.setCurrentIndex(max(i, 0))
        self._doc_selected()

    def _doc_selected(self, *_) -> None:
        data = self.doc_box.currentData()
        self.load(Path(data) if data else None)

    # ---------- 読み込みと表示 ----------

    def load(self, path: Path | None) -> None:
        if self.watcher.files():
            self.watcher.removePaths(self.watcher.files())
        self.path = path
        self.open_button.setEnabled(path is not None)
        if path is None:
            self.text = ""
            self.browser.setMarkdown("*文法文書がない。プロジェクトの grammar/ に Markdown を置くか、"
                                     "conlang grammar import で取り込む*")
            self.toc.clear()
            self.summary.setText("")
            return
        try:
            self.text = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            self.text = ""
            self.browser.setPlainText(f"読めなかった: {e}")
            return
        self.watcher.addPath(str(path))
        self.render()

    def _display_markdown(self) -> str:
        """表示用の Markdown。目印は、表示するときだけ小さな段落にする"""
        if not self.show_anchors.isChecked():
            return self.text
        out = []
        for line in self.text.splitlines():
            m = ANCHOR.match(line.strip())
            out += ["", f"`〔規則: {m.group(1)}〕`", ""] if m else [line]
        return "\n".join(out)

    def render(self) -> None:
        if self.path is None:
            return
        bar = self.browser.verticalScrollBar()
        pos = bar.value()
        self.browser.setMarkdown(self._display_markdown())
        self._color_tags()
        self._build_toc()
        bar.setValue(pos)
        counts = G.tag_counts(self.text)
        tags = "、".join(f"{t} {counts[t]}" for t in G.TAGS if counts.get(t))
        anchors = sum(1 for l in self.text.splitlines() if ANCHOR.match(l.strip()))
        self.summary.setText(f"{self.path}  見出し {len(G.headings(self.text))}・状態タグ: {tags or 'なし'}"
                             + (f"・規則の目印 {anchors}" if anchors else ""))

    def _color_tags(self) -> None:
        doc = self.browser.document()
        for tag, color in TAG_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            fmt.setFontWeight(QFont.Bold)
            cur = QTextCursor(doc)
            while True:
                cur = doc.find(f"【{tag}】", cur)
                if cur.isNull():
                    break
                cur.mergeCharFormat(fmt)

    # ---------- 目次 ----------

    def heading_blocks(self) -> list[tuple[int, str, int]]:
        """(見出しの階層, 見出し, ブロックの番号)"""
        out = []
        b = self.browser.document().begin()
        while b.isValid():
            level = b.blockFormat().headingLevel()
            if level:
                out.append((level, b.text(), b.blockNumber()))
            b = b.next()
        return out

    def _build_toc(self) -> None:
        self.toc.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, title, number in self.heading_blocks():
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, number)
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.toc.addTopLevelItem(item)
            stack.append((level, item))
        self.toc.expandToDepth(1)

    def _toc_clicked(self, item: QTreeWidgetItem, _col=0) -> None:
        self.go_to_block(item.data(0, Qt.UserRole))

    def go_to_block(self, number: int) -> None:
        doc = self.browser.document()
        block = doc.findBlockByNumber(number)
        if not block.isValid():
            return
        cur = QTextCursor(block)
        self.browser.setTextCursor(cur)
        top = doc.documentLayout().blockBoundingRect(block).top()
        self.browser.verticalScrollBar().setValue(int(top))

    def go_to_heading(self, title: str) -> bool:
        for _, t, number in self.heading_blocks():
            if t == title or t.startswith(title):
                self.go_to_block(number)
                return True
        return False

    # ---------- 検索 ----------

    def find_next(self, backward: bool = False) -> bool:
        text = self.search.text()
        if not text:
            return False
        flags = QTextDocument.FindBackward if backward else QTextDocument.FindFlag(0)
        doc = self.browser.document()
        cur = doc.find(text, self.browser.textCursor(), flags)
        if cur.isNull():  # 端まで来たら、反対の端から
            start = QTextCursor(doc)
            if backward:
                start.movePosition(QTextCursor.End)
            cur = doc.find(text, start, flags)
        if cur.isNull():
            self.summary.setText(f"「{text}」は見つからない")
            return False
        self.browser.setTextCursor(cur)
        self.browser.ensureCursorVisible()
        return True

    # ---------- 外部のエディタ ----------

    def open_external(self) -> None:
        if self.path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def _file_changed(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            self.load(p)  # 書き換えられた。保存のしかたによっては監視が外れるので、付け直す
