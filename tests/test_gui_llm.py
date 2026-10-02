"""画面での LLM: 設定の画面と、LLM を待つあいだに画面が止まらないこと"""
import json
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from conftest import FIXTURES  # noqa: E402
from test_llm import FakeServer  # noqa: E402

from conlang.core import llm  # noqa: E402
from conlang.core.project import Project  # noqa: E402
from conlang.gui import tasks  # noqa: E402
from conlang.gui.llm_settings import LLMSettingsDialog  # noqa: E402
from conlang.gui.main_window import MainWindow  # noqa: E402

DECOMPOSE = {"concept": "外の道", "elements": [
    {"role": "核", "meaning": "道", "existing": "dresi", "reason": "道"},
    {"role": "修飾", "meaning": "外側", "existing": None, "reason": "ない"}]}
GRAMMAR = {"candidates": [{"anchor": "compounding.rules", "rule": "compounding.vowel_merge",
                           "problem": "状態が違う", "confidence": "低"}]}


@pytest.fixture
def slow_server():
    s = FakeServer(reply=json.dumps(DECOMPOSE, ensure_ascii=False), delay=1.5)
    llm.save_config(llm.LLMConfig(url=s.url, model="think-model:27b"))
    yield s
    s.close()


@pytest.fixture
def win(qtbot, tmp_path, mini_pute):
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    p.import_dictionary(mini_pute)
    p.import_rules(FIXTURES / "mini_rules.yaml")
    p.import_grammar(FIXTURES / "mini-grammar.md")
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    w.ask = lambda *a, **k: QMessageBox.Yes
    w.error = lambda text: pytest.fail(f"エラー表示: {text}")
    assert w.open_project(p.root)
    yield w
    w._end_edit()
    w.dirty = False
    w.close()
    w.deleteLater()


def test_decompose_does_not_block(qtbot, win, slow_server):
    """LLM の答え(1.5秒かかる)を待つあいだも、画面の操作ができる"""
    panel = win.language_docks[("pute", "造語")].widget()
    panel.action.setCurrentIndex(7)  # LLM による分解
    panel.input.setText("外の道 --seed 1")
    started = time.monotonic()
    panel.run()
    assert time.monotonic() - started < 0.5  # すぐ戻る
    assert panel.running and panel.run_button.text() == "中止"
    # 待っているあいだに、辞書を検索できる
    win.search_box.setText("外")
    assert [win.model.words[i]["entry"]["form"] for i in range(win.model.rowCount())] == ["tchu"]
    qtbot.waitUntil(lambda: "LLM に問い合わせている" in panel.status.text(), timeout=3000)
    qtbot.waitUntil(lambda: not panel.running, timeout=10000)
    out = panel.output.toPlainText()
    assert "dresi(道)" in out and "「外側」 は既存語にない" in out and "基本詞の候補" in out
    assert panel.status.text().startswith("終わった")
    assert len(list((win.project.llm_log_dir).glob("*-decompose.json"))) == 1  # 履歴が残る


def test_decompose_cancel(qtbot, win, slow_server):
    panel = win.language_docks[("pute", "造語")].widget()
    panel.output.setPlainText("前の結果")
    panel.action.setCurrentIndex(7)
    panel.input.setText("外の道")
    panel.run()
    panel.run_button.click()  # 中止
    assert not panel.running and panel.status.text().startswith("中止した")
    qtbot.wait(2500)  # 裏の問い合わせが終わっても
    assert panel.output.toPlainText() == "前の結果"  # 結果は捨てる


def test_rules_panel_llm_check(qtbot, win):
    s = FakeServer(reply=json.dumps(GRAMMAR, ensure_ascii=False), delay=0.5)
    try:
        llm.save_config(llm.LLMConfig(url=s.url, model="plain-model:12b"))
        rp = win.rules_panel
        assert rp.llm_button.isEnabled()
        rp.run_llm_check()
        assert rp.running and rp.llm_button.text() == "中止"
        qtbot.waitUntil(lambda: not rp.running, timeout=10000)
        assert "LLM が挙げた食い違いの候補(1件" in rp.llm_output.toPlainText()
        # 変わっていないので、2回目は問い合わせない
        n = len(s.requests)
        rp.run_llm_check()
        qtbot.waitUntil(lambda: not rp.running, timeout=10000)
        assert "前回 LLM に調べさせたときから変わっていない" in rp.llm_output.toPlainText()
        assert len(s.requests) == n
        rp.force.setChecked(True)
        rp.run_llm_check()
        qtbot.waitUntil(lambda: not rp.running, timeout=10000)
        assert len(s.requests) == n + 1
    finally:
        s.close()


def test_settings_dialog(qtbot):
    s = FakeServer(reply="apple")
    try:
        llm.save_config(llm.LLMConfig(url=s.url, model="plain-model:12b"))
        dlg = LLMSettingsDialog()
        qtbot.addWidget(dlg)
        dlg.fetch_models()
        qtbot.waitUntil(lambda: dlg.model.count() == 2, timeout=5000)
        assert [dlg.model.itemData(i) for i in range(2)] == ["plain-model:12b", "think-model:27b"]  # 埋め込み用は除く
        assert dlg.current_config().model == "plain-model:12b"  # 今の設定が選ばれたまま
        assert "埋め込み用など 1個は除いた" in dlg.status.text()
        dlg.model.setCurrentIndex(1)
        assert "考える過程を出すモデル" in dlg.model_info.text()
        dlg.effort.setCurrentIndex(1)  # none
        dlg.timeout.setValue(120)
        dlg.test_connection()
        qtbot.waitUntil(lambda: dlg.status.text().startswith("つながった"), timeout=5000)
        assert "apple" in dlg.status.text()
        dlg.accept()
        cfg = llm.load_config()
        assert (cfg.model, cfg.reasoning_effort, cfg.timeout, cfg.url) == ("think-model:27b", "none", 120, s.url)
    finally:
        s.close()


def test_settings_dialog_custom_model_and_failure(qtbot):
    llm.save_config(llm.LLMConfig(url="http://127.0.0.1:9/v1", model="m"))
    dlg = LLMSettingsDialog()
    qtbot.addWidget(dlg)
    dlg.model.setEditText("自分で書いたモデル")
    assert dlg.current_config().model == "自分で書いたモデル"
    dlg.fetch_models()
    qtbot.waitUntil(lambda: dlg.status.text().startswith("失敗"), timeout=10000)
    assert dlg.fetch_button.isEnabled()
    dlg.reject()
    assert llm.load_config().model == "m"  # 取り消せば保存しない


def test_main_window_shows_llm(win):
    llm.save_config(llm.LLMConfig(url="http://x/v1", model="qwen3.5:27b", reasoning_effort="none"))
    win._update_llm_label()
    assert win.llm_label.text() == "LLM: qwen3.5:27b(考える過程 none)"


def test_capture_is_per_thread():
    """裏のスレッドの print は、そのスレッドの分だけ集まり、混ざらない"""
    results = {}

    def worker(name):
        def body():
            for i in range(50):
                print(f"{name}{i}")
                time.sleep(0.001)
        results[name] = tasks.capture(body)[1]

    ts = [threading.Thread(target=worker, args=(n,)) for n in "ab"]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert results["a"].split() == [f"a{i}" for i in range(50)]
    assert results["b"].split() == [f"b{i}" for i in range(50)]
