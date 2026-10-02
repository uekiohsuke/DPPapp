"""規則の欄。規則ファイル(YAML)の各規則の状態と、言語別の点検の結果を出す

文章の記述を LLM に調べさせる検査は、裏で動かす(画面は止まらない)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from conlang.core import llm, registry
from conlang.core.rules import SETTLED, Rules

from .tasks import Task, Ticker, capture, run_task


class RulesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: Rules | None = None
        self.language: str | None = None
        self.grammar: tuple[str, str] | None = None
        self.ctx = registry.Context()
        self.task: Task | None = None
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.only_unsettled = QCheckBox("「決定」以外だけ")
        self.only_unsettled.setChecked(True)
        self.only_unsettled.toggled.connect(self.refresh)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["規則", "状態", "注"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 60)

        # LLM による検査
        self.llm_button = QPushButton("文章の記述を LLM で調べる")
        self.llm_button.clicked.connect(self._run_or_cancel)
        self.force = QCheckBox("前回から変わっていなくても調べる")
        self.llm_status = QLabel()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumHeight(12)
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.llm_output = QPlainTextEdit()
        self.llm_output.setReadOnly(True)
        self.llm_output.setPlaceholderText("LLM の答えは、食い違いの「候補」。見落としがありうるので、問題がないことの保証ではない")
        self.ticker = Ticker(self, lambda s: self.llm_status.setText(f"{self._model} に問い合わせている… {int(s)}秒"))
        self._model = ""

        row = QHBoxLayout()
        row.addWidget(self.llm_button)
        row.addWidget(self.force)
        row.addWidget(self.llm_status, 1)
        row.addWidget(self.busy)
        llm_box = QWidget()
        llm_lay = QVBoxLayout(llm_box)
        llm_lay.setContentsMargins(0, 0, 0, 0)
        llm_lay.addLayout(row)
        llm_lay.addWidget(self.llm_output)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tree)
        split.addWidget(llm_box)
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addWidget(self.only_unsettled)
        lay.addWidget(split)

    def set_rules(self, rules: Rules | None, language: str | None, grammar: tuple[str, str] | None = None,
                  ctx: registry.Context | None = None) -> None:
        """grammar: (文法文書の名前, 本文)。あれば、表の食い違いをコードで照合して出す"""
        self.rules, self.language, self.grammar = rules, language, grammar
        self.ctx = ctx or registry.Context(rules=rules)
        self.refresh()

    def _add_problems(self, title: str, problems: list[str]) -> None:
        root = QTreeWidgetItem([title, "", ""])
        for msg in problems:
            child = QTreeWidgetItem([msg, "", ""])
            child.setToolTip(0, msg)
            root.addChild(child)
        self.tree.insertTopLevelItem(0, root)
        root.setExpanded(True)

    def refresh(self) -> None:
        self.tree.clear()
        lang = registry.get(self.language) if self.language else None
        can_llm = bool(lang and lang.llm_grammar_check and self.rules is not None and self.grammar is not None)
        self.llm_button.setEnabled(can_llm or self.task is not None)
        if self.rules is None:
            self.summary.setText("規則ファイルがない(ファイル → 規則ファイルを取り込む)")
            return
        all_items = self.rules.statuses()
        items = [s for s in all_items if s.status != SETTLED] if self.only_unsettled.isChecked() else all_items
        for s in items:
            note = " / ".join(x for x in (s.id and f"id: {s.id}", s.ref and f"ref: {s.ref}", s.note) if x)
            item = QTreeWidgetItem([s.path, s.status, note])
            item.setToolTip(2, note)
            if s.status != SETTLED:
                item.setForeground(1, Qt.darkYellow)
            self.tree.addTopLevelItem(item)
        lines = [f"{self.rules.language or '言語名なし'}: 規則 {len(all_items)}件"
                 f"(「決定」以外 {sum(1 for s in all_items if s.status != SETTLED)}件)"]
        if lang and lang.check_grammar:
            if self.grammar is None:
                lines.append("文法文書との照合: 文法文書がない(grammar/ に置く)")
            else:
                name, text = self.grammar
                diffs = lang.check_grammar(text, self.rules)
                lines.append(f"文法文書({name})との表の照合: " + (f"食い違い {len(diffs)}件" if diffs else "食い違いなし"))
                if diffs:
                    self._add_problems("文法文書との表の食い違い(表の正は規則ファイル)", diffs)
        if lang and lang.check_rules:
            problems = lang.check_rules(self.rules)
            if problems:
                lines.append(f"{lang.name}の規則としての点検: {len(problems)}件")
                self._add_problems("点検で見つかった問題", problems)
            else:
                lines.append(f"{lang.name}の規則としての点検: 問題なし")
        self.summary.setText("\n".join(lines))

    # ---------- LLM による検査(裏で動かす) ----------

    @property
    def running(self) -> bool:
        return self.task is not None

    def _run_or_cancel(self) -> None:
        if self.running:
            self.task.cancel()
            self._finish()
            self.llm_status.setText("中止した(LLM の処理は、裏で終わるまで続く。結果は捨てる)")
        else:
            self.run_llm_check()

    def run_llm_check(self) -> None:
        lang = registry.get(self.language)
        if self.running or lang is None or lang.llm_grammar_check is None:
            return
        ctx, force = self.ctx, self.force.isChecked()
        self._model = llm.load_config().model or "LLM"
        self.task = run_task(lambda: capture(lang.llm_grammar_check, ctx, force)[1], self._done, self._failed)
        self.llm_button.setText("中止")
        self.busy.show()
        self.ticker.start(self.task)

    def _done(self, text: str) -> None:
        elapsed = self.task.elapsed if self.task else 0
        self._finish()
        self.llm_output.setPlainText(text)
        self.llm_status.setText(f"終わった({elapsed:.1f}秒)")

    def _failed(self, msg: str) -> None:
        self._finish()
        self.llm_output.setPlainText(msg)
        self.llm_status.setText("エラーで止まった")

    def _finish(self) -> None:
        self.task = None
        self.ticker.stop()
        self.busy.hide()
        self.llm_button.setText("文章の記述を LLM で調べる")
