"""ピュテ語の造語支援の画面(言語別の画面部品)。表示の中身は cli_coining と同じものを使う"""
from __future__ import annotations

import contextlib
import io
import shlex

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from conlang.core.registry import Context

from . import cli_coining

# (表示名, コマンド, 入力欄の説明)
ACTIONS = [
    ("検索", "find", "キーワード(空白で区切る)  例: 力 数"),
    ("組み合わせの検査", "check", "部品(見出し語・短縮形・訳語)を空白で区切る  例: 節点 外"),
    ("提案", "suggest", "キーワードを、大本の概念から順に  例: 辺 数"),
    ("形態素分解", "analyze", "語(空白で区切って複数)  例: thjadrwoqakujeta"),
    ("短縮の候補", "shorten", "部品を空白で区切る  例: eshkiki judra"),
    ("長大語", "long", "文字数(省くと 20)"),
    ("基本詞の候補", "gen", "個数など  例: 10 --seed 1"),
    ("LLM による分解", "decompose", "造語したい概念  例: 重力加速度(--prompt-only でプロンプトだけ)"),
]


class CoiningPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ctx = Context()
        self.action = QComboBox()
        for name, _, _ in ACTIONS:
            self.action.addItem(name)
        self.input = QLineEdit()
        self.run_button = QPushButton("実行")
        self.hint = QLabel()
        self.hint.setStyleSheet("color: #666;")
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)
        self.action.currentIndexChanged.connect(self._update_hint)
        self.run_button.clicked.connect(self.run)
        self.input.returnPressed.connect(self.run)
        row = QHBoxLayout()
        row.addWidget(self.action)
        row.addWidget(self.input, 1)
        row.addWidget(self.run_button)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.hint)
        lay.addWidget(self.output)
        self._update_hint()

    def set_context(self, ctx: Context) -> None:
        self.ctx = ctx
        ok = ctx.dictionary is not None
        self.run_button.setEnabled(ok)
        if ctx.rules is None and ok:
            self.hint.setText(self.hint.text().split("\n")[0] + "\n(規則ファイルがないので、初期値の規則で動く)")

    def _update_hint(self) -> None:
        self.hint.setText(ACTIONS[self.action.currentIndex()][2])

    def run(self) -> str:
        _, cmd, _ = ACTIONS[self.action.currentIndex()]
        try:
            args = shlex.split(self.input.text())
        except ValueError:
            args = self.input.text().split()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli_coining.main([cmd, *args], self.ctx)
        text = buf.getvalue()
        self.output.setPlainText(text)
        return text


def make_panel() -> CoiningPanel:
    return CoiningPanel()
