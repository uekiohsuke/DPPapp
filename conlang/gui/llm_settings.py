"""LLM の設定の画面。接続先・モデル・考える過程の量などを選び、%APPDATA%\\conlang\\llm.json に保存する

モデルの一覧の取得と接続の確認は、裏で動かす(画面は止まらない)。
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout,
)

from conlang.core import llm

from .tasks import Task, Ticker, run_task

EFFORTS = [("(モデルの既定。送らない)", ""), ("none(考える過程を止める。速い)", "none"),
           ("low", "low"), ("medium", "medium"), ("high", "high")]
TEST_PROMPT = "「りんご」を英語で一語だけ答えて"


class LLMSettingsDialog(QDialog):
    def __init__(self, parent=None, cfg: llm.LLMConfig | None = None):
        super().__init__(parent)
        self.setWindowTitle("LLM の設定")
        self.setMinimumWidth(620)
        self.cfg = cfg or llm.load_config()
        self.infos: dict[str, llm.ModelInfo] = {}
        self.tasks: list[Task] = []

        self.url = QLineEdit(self.cfg.url)
        self.url.setPlaceholderText("例: http://192.168.0.178:11434/v1(Ollama の OpenAI 互換 API)")
        self.fetch_button = QPushButton("モデルの一覧を取得")
        self.fetch_button.clicked.connect(self.fetch_models)
        self.model = QComboBox()
        self.model.setEditable(True)  # 一覧にないモデル名も書ける
        self.model.setInsertPolicy(QComboBox.NoInsert)
        if self.cfg.model:
            self.model.addItem(self.cfg.model, self.cfg.model)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.model.editTextChanged.connect(lambda _: self._model_changed())
        self.model_info = QLabel()
        self.model_info.setWordWrap(True)
        self.model_info.setStyleSheet("color: #666;")
        self.effort = QComboBox()
        for label, value in EFFORTS:
            self.effort.addItem(label, value)
        self.effort.setCurrentIndex(max(0, next((i for i, (_, v) in enumerate(EFFORTS) if v == self.cfg.reasoning_effort), 0)))
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(self.cfg.temperature)
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 7200)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(self.cfg.timeout)
        self.key = QLineEdit(self.cfg.key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("ローカルの Ollama なら空でよい")
        self.test_button = QPushButton("接続を試す")
        self.test_button.clicked.connect(self.test_connection)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ticker = Ticker(self, lambda s: self.status.setText(f"{self._busy_label}… {int(s)}秒"))
        self._busy_label = ""

        url_row = QHBoxLayout()
        url_row.addWidget(self.url, 1)
        url_row.addWidget(self.fetch_button)
        form = QFormLayout()
        form.addRow("接続先", url_row)
        form.addRow("モデル", self.model)
        form.addRow("", self.model_info)
        form.addRow("考える過程", self.effort)
        form.addRow("温度", self.temperature)
        form.addRow("待ち時間", self.timeout)
        form.addRow("API キー", self.key)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取り消し")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.status, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addLayout(test_row)
        lay.addWidget(QLabel(f"保存先: {llm.config_path()}"))
        lay.addWidget(buttons)
        self._model_changed()

    # ---------- 入力欄 → 設定 ----------

    def current_config(self) -> llm.LLMConfig:
        model = self.model.currentData() if self.model.currentText() == self.model.itemText(self.model.currentIndex()) else None
        return replace(self.cfg, url=self.url.text().strip(), model=(model or self.model.currentText()).strip(),
                       key=self.key.text(), temperature=round(self.temperature.value(), 2),
                       timeout=self.timeout.value(), reasoning_effort=self.effort.currentData() or "")

    def accept(self) -> None:
        self.cfg = self.current_config()
        llm.save_config(self.cfg)
        self._cancel_tasks()
        super().accept()

    def reject(self) -> None:
        self._cancel_tasks()
        super().reject()

    def _cancel_tasks(self) -> None:
        for t in self.tasks:
            t.cancel()
        self.ticker.stop()

    # ---------- モデルの一覧 ----------

    def fetch_models(self) -> None:
        cfg = self.current_config()
        self.fetch_button.setEnabled(False)
        self._start(run_task(lambda: llm.list_model_infos(cfg), self._models_fetched, self._failed), "一覧を取得している")

    def _models_fetched(self, infos: list[llm.ModelInfo]) -> None:
        self._stop()
        self.fetch_button.setEnabled(True)
        current = self.current_config().model
        chat = [m for m in infos if m.can_chat]
        self.infos = {m.id: m for m in infos}
        self.model.blockSignals(True)
        self.model.clear()
        for m in chat:
            self.model.addItem(m.label(), m.id)
        i = self.model.findData(current)
        if i >= 0:
            self.model.setCurrentIndex(i)
        elif current:
            self.model.setEditText(current)
        self.model.blockSignals(False)
        skipped = len(infos) - len(chat)
        self.status.setText(f"会話に使えるモデル {len(chat)}個" + (f"(埋め込み用など {skipped}個は除いた)" if skipped else ""))
        self._model_changed()

    def _model_changed(self, *_) -> None:
        m = self.infos.get(self.current_config().model)
        if m is None:
            self.model_info.setText("「モデルの一覧を取得」で、接続先のモデルから選べる")
            return
        text = m.label()
        if m.thinks:
            text += "\n考える過程を出すモデル。「考える過程」を none にすると、答えが速くなる(文法の照合で 10分超 → 1分半ほど)"
        self.model_info.setText(text)

    # ---------- 接続の確認 ----------

    def test_connection(self) -> None:
        cfg = self.current_config()
        self.test_button.setEnabled(False)
        task = run_task(lambda: llm.chat(TEST_PROMPT, cfg), self._tested, self._failed)
        self._start(task, f"{cfg.model} に問い合わせている")

    def _tested(self, answer: str) -> None:
        elapsed = self.tasks[-1].elapsed if self.tasks else 0
        self._stop()
        self.test_button.setEnabled(True)
        self.status.setText(f"つながった({elapsed:.1f}秒): {answer.strip()[:80]}")

    # ---------- 共通 ----------

    def _start(self, task: Task, label: str) -> None:
        self.tasks.append(task)
        self._busy_label = label
        self.ticker.start(task)

    def _stop(self) -> None:
        self.ticker.stop()

    def _failed(self, msg: str) -> None:
        self._stop()
        self.fetch_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.status.setText("失敗: " + msg.splitlines()[0])
