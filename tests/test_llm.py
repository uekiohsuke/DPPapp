"""LLM の接続(OpenAI 互換)と、目印・ref の対応づけ(共通部分)"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conlang.cli import main
from conlang.core import llm
from conlang.core import rule_docs as RD
from conlang.core.rules import Rules


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    """利用者の本当の設定を使わない"""
    monkeypatch.setenv("CONLANG_CONFIG_DIR", str(tmp_path / "config"))
    for name in ("URL", "MODEL", "KEY"):
        monkeypatch.delenv(f"CONLANG_LLM_{name}", raising=False)
        monkeypatch.delenv(f"PUTE_LLM_{name}", raising=False)
    return tmp_path / "config"


class FakeServer:
    """OpenAI 互換の /models と /chat/completions だけを返す"""

    def __init__(self, reply="こんにちは", status=200):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                outer.requests.append(("GET", self.path, None, dict(self.headers)))
                self._send(200, {"data": [{"id": "b-model"}, {"id": "a-model"}]})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n))
                outer.requests.append(("POST", self.path, body, dict(self.headers)))
                if status != 200:
                    self._send(status, {"error": "だめ"})
                else:
                    self._send(200, {"choices": [{"message": {"content": reply}}]})

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


def test_config_save_load_and_env(config_dir, monkeypatch):
    assert llm.load_config() == llm.LLMConfig()
    path = llm.save_config(llm.LLMConfig(url="http://192.168.0.178:11434/v1", model="qwen3.5:27b"))
    assert path == config_dir / "llm.json"
    cfg = llm.load_config()
    assert (cfg.url, cfg.model, cfg.ready) == ("http://192.168.0.178:11434/v1", "qwen3.5:27b", True)
    monkeypatch.setenv("PUTE_LLM_MODEL", "old")
    assert llm.load_config().model == "old"
    monkeypatch.setenv("CONLANG_LLM_MODEL", "new")
    assert llm.load_config().model == "new"  # CONLANG_ が優先


def test_chat_and_models(server):
    cfg = llm.LLMConfig(url=server.url, model="m", key="secret")
    assert llm.chat("質問", cfg, json_mode=True) == "こんにちは"
    method, path, body, headers = server.requests[-1]
    assert (method, path) == ("POST", "/v1/chat/completions")
    assert body["model"] == "m" and body["messages"] == [{"role": "user", "content": "質問"}]
    assert body["response_format"] == {"type": "json_object"}
    assert headers["Authorization"] == "Bearer secret"
    assert llm.list_models(cfg) == ["a-model", "b-model"]


def test_chat_errors(tmp_path):
    with pytest.raises(llm.LLMError, match="モデルが決まっていない"):
        llm.chat("x", llm.LLMConfig(model=""))
    s = FakeServer(status=500)
    try:
        with pytest.raises(llm.LLMError, match="500"):
            llm.chat("x", llm.LLMConfig(url=s.url, model="m"))
    finally:
        s.close()
    with pytest.raises(llm.LLMError, match="接続できない"):
        llm.chat("x", llm.LLMConfig(url="http://127.0.0.1:9/v1", model="m", timeout=2))


def test_cli_llm(server, capsys):
    assert main(["llm", "config", "--url", server.url, "--model", "a-model"]) == 0
    assert "保存した" in capsys.readouterr().out
    assert main(["llm", "models"]) == 0
    assert "* a-model" in capsys.readouterr().out
    assert main(["llm", "ask", "やあ"]) == 0
    assert "こんにちは" in capsys.readouterr().out


def test_grammar_check_calls_llm(server, tmp_path, mini_pute, capsys):
    """grammar-check --llm が、設定した接続先に問い合わせ、履歴を残す"""
    from conftest import FIXTURES
    from conlang.core import llm_log
    from conlang.core.project import Project
    answer = {"candidates": [{"anchor": "compounding.rules", "rule": "compounding.vowel_merge",
                              "problem": "状態が違う", "confidence": "低"}]}
    server_with_answer = FakeServer(reply=json.dumps(answer, ensure_ascii=False))
    try:
        llm.save_config(llm.LLMConfig(url=server_with_answer.url, model="m"))
        proj = tmp_path / "x"
        main(["new", str(proj), "--name", "架空語", "--language", "pute"])
        main(["rules", "import", str(proj), str(FIXTURES / "mini_rules.yaml")])
        main(["grammar", "import", str(proj), str(FIXTURES / "mini-grammar.md")])
        capsys.readouterr()
        assert main(["pute", "--project", str(proj), "grammar-check", "--llm"]) == 1
        out = capsys.readouterr().out
        assert "LLM が挙げた食い違いの候補(1件" in out and "m @ " in out
        sent = server_with_answer.requests[-1][2]["messages"][0]["content"]
        assert "【目印: compounding.rules】" in sent
        log = json.loads(llm_log.list_calls(Project.open(proj).llm_log_dir)[0].read_text(encoding="utf-8"))
        assert log["model"].startswith("m @ ") and log["answer"] == json.dumps(answer, ensure_ascii=False)
    finally:
        server_with_answer.close()


# ---------- 目印と ref ----------

def test_read_anchors():
    md = "# 見出し\n<!-- rule: a.b -->\n| x |\n| y |\n\n本文\n<!-- rule: c -->\n- 1\n- 2\n## 次\n- 3\n"
    assert RD.read_anchors(md) == {"a.b": ["| x |", "| y |"], "c": ["- 1", "- 2"]}


def test_collect_refs_and_rule_at():
    r = Rules({"x": {"ref": "x.all", "y": {"ref": {"k": "a1", "m.n": "a2"}, "k": 1, "m": {"n": 2}}},
               "list": [{"ref": "ignored"}]})
    refs = RD.collect_refs(r.data)
    assert refs == [RD.Ref("x", "x.all"), RD.Ref("x.y.k", "a1"), RD.Ref("x.y.m.n", "a2")]
    assert RD.rule_at(r, "x.y.m.n") == 2
    r2 = Rules({"a": {"b.c": 5}})
    assert RD.rule_at(r2, "a.b.c") == 5
    assert RD.rule_at(r2, "a.z") is None
    assert RD.check_links({"x.all": [], "a1": [], "extra": []}, refs) == [
        "規則ファイルの x.y.m.n の ref「a2」が、文法文書に見つからない",
        "文法文書の目印「extra」に対応する規則が、規則ファイルにない"]
