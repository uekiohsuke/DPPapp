import os
from pathlib import Path

import pytest

# 画面のテストは、ウィンドウを出さずに動かす
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DATA = ROOT / "data"

# 実データ(git 管理外)。置いてあるときだけ動くテストに使う
REAL_PUTE = DATA / "secondpute.json"
REAL_PUTE_TYPO = DATA / "secondpute_q_with_typos.json"  # 誤記6件と旧用語1件を含むままの辞書
REAL_RULES = DATA / "pute-rules.yaml"
REAL_GRAMMAR = DATA / "pute2-grammar.md"
REAL_URI = DATA / "uri.json"

needs_real_pute = pytest.mark.skipif(not REAL_PUTE.exists(), reason="data/secondpute.json がない")
needs_real_uri = pytest.mark.skipif(not REAL_URI.exists(), reason="data/uri.json がない")


@pytest.fixture(autouse=True)
def isolated_llm_config(tmp_path, monkeypatch):
    """利用者の本当の LLM の設定(%APPDATA%\\conlang\\llm.json)を読まない・書かない"""
    monkeypatch.setenv("CONLANG_CONFIG_DIR", str(tmp_path / "conlang-config"))
    for name in ("URL", "MODEL", "KEY"):
        monkeypatch.delenv(f"CONLANG_LLM_{name}", raising=False)
        monkeypatch.delenv(f"PUTE_LLM_{name}", raising=False)


@pytest.fixture
def mini_pute():
    return FIXTURES / "mini_pute.json"


@pytest.fixture
def mini_jackson():
    return FIXTURES / "mini_jackson.json"
