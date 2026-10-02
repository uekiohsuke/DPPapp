"""規則の欄。規則ファイル(YAML)の各規則の状態と、言語別の点検の結果を出す"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from conlang.core import registry
from conlang.core.rules import SETTLED, Rules


class RulesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: Rules | None = None
        self.language: str | None = None
        self.grammar: tuple[str, str] | None = None
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.only_unsettled = QCheckBox("「決定」以外だけ")
        self.only_unsettled.setChecked(True)
        self.only_unsettled.toggled.connect(self.refresh)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["規則", "状態", "注"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 60)
        lay = QVBoxLayout(self)
        lay.addWidget(self.summary)
        lay.addWidget(self.only_unsettled)
        lay.addWidget(self.tree)

    def set_rules(self, rules: Rules | None, language: str | None, grammar: tuple[str, str] | None = None) -> None:
        """grammar: (文法文書の名前, 本文)。あれば、表の食い違いをコードで照合して出す"""
        self.rules, self.language, self.grammar = rules, language, grammar
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
        lang = registry.get(self.language) if self.language else None
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
