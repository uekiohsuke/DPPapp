"""ピュテ語の造語支援の画面(言語別の画面部品)。表示の中身は cli_coining と同じものを使う

処理は裏(別のスレッド)で動かすので、LLM の答えを待つあいだも画面は止まらない。
"""
from __future__ import annotations

import copy
import shlex

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from conlang.core import llm
from conlang.core.registry import Context
from conlang.gui.tasks import Task, Ticker, capture, run_task

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
LLM_COMMANDS = {"decompose"}


class CoiningPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ctx = Context()
        self.task: Task | None = None
        self.action = QComboBox()
        for name, _, _ in ACTIONS:
            self.action.addItem(name)
        self.input = QLineEdit()
        self.run_button = QPushButton("実行")
        self.hint = QLabel()
        self.hint.setStyleSheet("color: #666;")
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # 終わりの見えない処理中の表示
        self.busy.setMaximumHeight(12)
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.status = QLabel()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)
        self.ticker = Ticker(self, self._tick)
        self.action.currentIndexChanged.connect(self._update_hint)
        self.run_button.clicked.connect(self._run_or_cancel)
        self.input.returnPressed.connect(self.run)
        row = QHBoxLayout()
        row.addWidget(self.action)
        row.addWidget(self.input, 1)
        row.addWidget(self.run_button)
        status = QHBoxLayout()
        status.addWidget(self.status)
        status.addWidget(self.busy, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.hint)
        lay.addLayout(status)
        lay.addWidget(self.output)
        self._update_hint()

    @property
    def running(self) -> bool:
        return self.task is not None

    def set_context(self, ctx: Context) -> None:
        self.ctx = ctx
        self.run_button.setEnabled(ctx.dictionary is not None or self.running)
        self._update_hint()

    def _update_hint(self) -> None:
        name, cmd, text = ACTIONS[self.action.currentIndex()]
        if cmd in LLM_COMMANDS:
            cfg = llm.load_config()
            text += f"\nLLM: {cfg.model or '(未設定。設定 → LLM の設定)'}"
        if self.ctx.dictionary is not None and self.ctx.rules is None:
            text += "\n(規則ファイルがないので、初期値の規則で動く)"
        self.hint.setText(text)

    def _run_or_cancel(self) -> None:
        if self.running:
            self.cancel()
        else:
            self.run()

    def run(self) -> None:
        """入力欄の内容で、選んだ処理を裏で動かす"""
        if self.running or self.ctx.dictionary is None:
            return
        _, cmd, _ = ACTIONS[self.action.currentIndex()]
        try:
            args = shlex.split(self.input.text())
        except ValueError:
            args = self.input.text().split()
        # 裏で動くあいだに辞書を編集しても乱れないように、写しを渡す
        ctx = Context(copy.deepcopy(self.ctx.dictionary), self.ctx.rules, self.ctx.project)

        def work():
            _, text = capture(cli_coining.main, [cmd, *args], ctx)
            return text

        self.task = run_task(work, self._done, self._failed)
        self.run_button.setText("中止")
        self.busy.show()
        self.label = "LLM に問い合わせている" if cmd in LLM_COMMANDS and "--prompt-only" not in args else "処理している"
        self.ticker.start(self.task)

    def cancel(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self._finish()
            self.status.setText("中止した(LLM の処理は、裏で終わるまで続く。結果は捨てる)")

    def _tick(self, elapsed: float) -> None:
        self.status.setText(f"{self.label}… {int(elapsed)}秒")

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
        self.run_button.setEnabled(self.ctx.dictionary is not None)


def make_panel() -> CoiningPanel:
    return CoiningPanel()
