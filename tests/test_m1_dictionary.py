"""M1: コアと辞書。ピュテ語の辞書を読み込み、保存できる。元のデータが壊れない"""
import hashlib
import json

import pytest
from conftest import REAL_PUTE, REAL_URI, needs_real_pute, needs_real_uri

from conlang.cli import main
from conlang.core.backup import list_backups
from conlang.core.project import Project, ProjectError
from conlang.core.zpdic import Dictionary, JsonStyle, ZpdicError, detect_style, dumps


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- 読み書き ----------

@pytest.mark.parametrize("name", ["mini_pute", "mini_jackson"])
def test_roundtrip_is_byte_identical(request, name):
    path = request.getfixturevalue(name)
    raw = path.read_bytes()
    assert Dictionary.from_bytes(raw).to_bytes() == raw


def test_style_detection(mini_pute, mini_jackson):
    assert Dictionary.load(mini_pute).style.kind == "python"
    assert Dictionary.load(mini_jackson).style.kind == "jackson"


@pytest.mark.parametrize("style", [
    JsonStyle("python", 2, "\r\n", False),
    JsonStyle("python", 4, "\n", True),
    JsonStyle("jackson", 2, "\r\n", False),
    JsonStyle("compact", 0, "\n", True),
    JsonStyle("python", 2, "\n", False, bom=True),
])
def test_roundtrip_each_style(mini_pute, style):
    data = Dictionary.load(mini_pute).data
    raw = (b"\xef\xbb\xbf" if style.bom else b"") + dumps(data, style).encode("utf-8")
    d = Dictionary.from_bytes(raw)
    assert d.style == style
    assert d.to_bytes() == raw


def test_unknown_keys_kept(mini_pute, tmp_path):
    d = Dictionary.load(mini_pute)
    out = tmp_path / "out.json"
    d.save(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["extraTopLevel"] == [1, 2.5, True]
    assert data["words"][5]["unknownField"] == {"keep": "未知のフィールドも残す"}


def test_japanese_not_escaped(mini_pute, tmp_path):
    out = tmp_path / "out.json"
    Dictionary.load(mini_pute).save(out)
    text = out.read_text(encoding="utf-8")
    assert "節点" in text and "\\u" not in text


def test_edit_and_save(mini_pute, tmp_path):
    d = Dictionary.load(mini_pute)
    w = d.add("sasxa")
    assert w["entry"]["id"] == 7 and w["translations"] == []
    w["translations"].append({"title": "動作概念", "forms": ["書く"]})
    assert d.remove(2)
    out = tmp_path / "out.json"
    d.save(out)
    d2 = Dictionary.load(out)
    assert len(d2) == 6
    assert d2.get(7)["translations"][0]["forms"] == ["書く"]
    assert d2.get(2) is None
    assert d2.style == d.style


def test_invalid_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ZpdicError):
        Dictionary.load(bad)
    bad.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(ZpdicError):
        Dictionary.load(bad)


def test_detect_style_ignores_colon_in_values():
    text = json.dumps({"words": [{"entry": {"id": 1, "form": "a"}, "t": 'x" : y'}]}, ensure_ascii=False, indent=2)
    assert detect_style(text).kind == "python"


# ---------- プロジェクトとバックアップ ----------

def test_project_layout(tmp_path):
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    for name in ("project.json", "dictionary.json", "examples.json", "rules", "grammar", "llm_log", "backup"):
        assert (p.root / name).exists()
    assert Project.open(p.root).meta["name"] == "ピュテ語"
    with pytest.raises(ProjectError):
        Project.create(p.root, "二重")


def test_import_copies_and_keeps_source(mini_pute, tmp_path):
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    before = sha(mini_pute)
    bak = p.import_dictionary(mini_pute)
    assert sha(mini_pute) == before
    assert p.dictionary_path.read_bytes() == mini_pute.read_bytes()
    assert bak is not None and bak.exists()  # 空の辞書をバックアップしてから置き換えた


def test_save_makes_backup_first(mini_pute, tmp_path):
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    p.import_dictionary(mini_pute)
    original = p.dictionary_path.read_bytes()
    d = p.load_dictionary()
    d.add("tekito")
    bak = p.save_dictionary(d)
    assert bak.read_bytes() == original
    assert len(p.load_dictionary()) == len(Dictionary.from_bytes(original)) + 1
    assert len(list_backups(p.backup_dir, "dictionary")) == 2


# ---------- CLI ----------

def test_cli_flow(mini_pute, tmp_path, capsys):
    proj = tmp_path / "pute"
    assert main(["new", str(proj), "--name", "ピュテ語", "--language", "pute"]) == 0
    assert main(["import", str(proj), str(mini_pute)]) == 0
    assert main(["save", str(proj)]) == 0
    assert main(["verify", str(proj / "dictionary.json")]) == 0
    assert main(["info", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "元のファイルは変わっていない: True" in out
    assert "保存前と同じバイト列: True" in out
    assert "バイト列も一致: True" in out
    assert "項目数: 6" in out
    assert main(["pute", "--project", str(proj), "find", "外"]) == 0
    assert "tchu" in capsys.readouterr().out


def test_cli_errors(tmp_path, capsys):
    assert main(["info", str(tmp_path)]) == 1
    assert "プロジェクトではない" in capsys.readouterr().err


# ---------- 実辞書 ----------

@needs_real_pute
def test_real_pute_roundtrip(tmp_path):
    raw = REAL_PUTE.read_bytes()
    d = Dictionary.from_bytes(raw)
    assert len(d) == 82
    assert d.to_bytes() == raw
    p = Project.create(tmp_path / "pute", "ピュテ語", "pute")
    before = sha(REAL_PUTE)
    p.import_dictionary(REAL_PUTE)
    p.save_dictionary(p.load_dictionary())
    assert sha(REAL_PUTE) == before
    assert p.dictionary_path.read_bytes() == raw


@needs_real_uri
def test_real_uri_roundtrip():
    raw = REAL_URI.read_bytes()
    d = Dictionary.from_bytes(raw)
    assert d.style.kind == "jackson"
    assert d.to_bytes() == raw
