"""「言語の機能」の欄。言語別の CLI のコマンド(registry の commands)を、画面から呼ぶ

どの言語にも共通の部品。処理は裏で動かし(LLM を使うものもあるため)、出力をそのまま表示する。
"""
from __future__ import annotations

import copy
import shlex

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from conlang.core import registry
from conlang.core.registry import Context

from .tasks import Task, Ticker, capture, run_task


class LanguageToolsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang: registry.LanguageModule | None = None
        self.ctx = Context()
        self.task: Task | None = None
        self.command = QComboBox()
        self.command.currentIndexChanged.connect(self._update_hint)
        self.input = QLineEdit()
        self.input.returnPressed.connect(self.run)
        self.example_button = QPushButton("例を入れる")
        self.example_button.clicked.connect(self.fill_example)
        self.run_button = QPushButton("実行")
        self.run_button.clicked.connect(self._run_or_cancel)
        self.hint = QLabel()
        self.hint.setStyleSheet("color: #666;")
        self.hint.setWordWrap(True)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumHeight(12)
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.status = QLabel()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)
        self.ticker = Ticker(self, lambda s: self.status.setText(f"処理している… {int(s)}秒"))

        row = QHBoxLayout()
        row.addWidget(self.command)
        row.addWidget(self.input, 1)
        row.addWidget(self.example_button)
        row.addWidget(self.run_button)
        status = QHBoxLayout()
        status.addWidget(self.status)
        status.addWidget(self.busy, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.hint)
        lay.addLayout(status)
        lay.addWidget(self.output)
        self.set_context(None, Context())

    @property
    def running(self) -> bool:
        return self.task is not None

    def commands(self) -> tuple[registry.Command, ...]:
        return self.lang.commands if self.lang else ()

    def set_context(self, lang: registry.LanguageModule | None, ctx: Context) -> None:
        changed = (lang.id if lang else None) != (self.lang.id if self.lang else None)
        if changed and self.running:  # 言語が替わったら、前の言語の処理の結果は捨てる
            self.task.cancel()
            self._finish()
        self.lang, self.ctx = lang, ctx
        if changed:
            current = self.command.currentData()
            self.command.blockSignals(True)
            self.command.clear()
            for c in self.commands():
                self.command.addItem(c.label, c.name)
            i = self.command.findData(current)
            self.command.setCurrentIndex(max(i, 0))
            self.command.blockSignals(False)
            self.output.clear()
        self._update_hint()

    def current(self) -> registry.Command | None:
        name = self.command.currentData()
        return next((c for c in self.commands() if c.name == name), None)

    def select(self, name: str) -> bool:
        i = self.command.findData(name)
        if i >= 0:
            self.command.setCurrentIndex(i)
        return i >= 0

    def _update_hint(self, *_) -> None:
        c = self.current()
        enabled = c is not None and (not c.needs_dictionary or self.ctx.dictionary is not None)
        self.run_button.setEnabled(enabled or self.running)
        self.example_button.setEnabled(bool(c and c.example))
        if self.lang is None:
            self.hint.setText("この言語には、画面から呼べる機能がない(プロジェクトの言語別機能が決まっていない)")
        elif not self.commands():
            self.hint.setText(f"{self.lang.name}には、画面から呼べる機能がまだない")
        elif c is not None:
            text = f"conlang {self.lang.id} {c.name} … : {c.hint}"
            if c.example:
                text += f"  例: {c.example}"
            if self.ctx.rules is None:
                text += "\n(規則ファイルがない。規則ファイルから動く機能は、初期値で動くか、規則ファイルを求める)"
            self.hint.setText(text)

    def fill_example(self) -> None:
        c = self.current()
        if c and c.example:
            self.input.setText(c.example)

    def _run_or_cancel(self) -> None:
        if self.running:
            self.task.cancel()
            self._finish()
            self.status.setText("中止した(結果は捨てる)")
        else:
            self.run()

    def run(self) -> None:
        c = self.current()
        if self.running or c is None or self.lang is None or self.lang.cli is None:
            return
        try:
            args = shlex.split(self.input.text())
        except ValueError:
            args = self.input.text().split()
        # 裏で動くあいだに辞書を編集しても乱れないように、写しを渡す
        ctx = Context(copy.deepcopy(self.ctx.dictionary), self.ctx.rules, self.ctx.project)
        cli = self.lang.cli
        argv = [c.name, *args]
        self.task = run_task(lambda: capture(cli, argv, ctx)[1], self._done, self._failed)
        self.run_button.setText("中止")
        self.busy.show()
        self.ticker.start(self.task)

    def _done(self, text: str) -> None:
        elapsed = self.task.elapsed if self.task else 0
        self._finish()
        self.output.setPlainText(text)
        self.status.setText(f"終わった({elapsed:.1f}秒)")

    def _failed(self, msg: str) -> None:
        self._finish()
        self.output.setPlainText(msg)
        self.status.setText("エラーで止まった")

    def _finish(self) -> None:
        self.task = None
        self.ticker.stop()
        self.busy.hide()
        self.run_button.setText("実行")
        self._update_hint()
