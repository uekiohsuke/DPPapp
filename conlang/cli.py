"""conlang の CLI

  conlang new DIR --name ピュテ語 [--language pute]   言語プロジェクトを作る
  conlang import DIR FILE                            zpdic 辞書を取り込む(元のファイルはコピーするだけ)
  conlang info DIR|FILE                              辞書の項目数などを出す
  conlang save DIR                                   辞書を読んで書き戻す(保存前にバックアップする)
  conlang verify FILE                                読んで書き戻したときに、元と同じになるかを確かめる(書き込まない)
  conlang rules import DIR FILE                      規則ファイル(YAML)を取り込む(元のファイルはコピーするだけ)
  conlang rules show DIR|FILE [--all]                「決定」以外の規則の一覧と、言語別の点検
  conlang gui [DIR]                                  画面を開く(DIR を省くと、前に開いたプロジェクト)
  conlang <言語> [--project DIR | --dict FILE] ...    言語別機能(例: conlang pute find 力)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from .core import registry
from .core.project import Project, ProjectError
from .core.rules import Rules, RulesError
from .core.zpdic import Dictionary, ZpdicError


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def cmd_new(a) -> int:
    p = Project.create(a.dir, a.name, a.language)
    print(f"プロジェクトを作った: {p.root}({p.name})")
    return 0


def cmd_import(a) -> int:
    p = Project.open(a.dir)
    before = _sha(Path(a.file).read_bytes())
    bak = p.import_dictionary(a.file)
    after = _sha(Path(a.file).read_bytes())
    d = p.load_dictionary()
    print(f"取り込んだ: {a.file} → {p.dictionary_path}({len(d)}項目)")
    if bak:
        print(f"  前の辞書のバックアップ: {bak}")
    print(f"  元のファイルは変わっていない: {before == after}(sha256 {after})")
    return 0


def _load_any(target: str) -> tuple[Dictionary, Path]:
    path = Path(target)
    if path.is_dir():
        path = Project.open(path).dictionary_path
    return Dictionary.load(path), path


def cmd_info(a) -> int:
    d, path = _load_any(a.target)
    tags = Counter(t for w in d.words for t in w.get("tags", []))
    titles = Counter(c.get("title") for w in d.words for c in w.get("contents", []))
    print(f"{path}")
    print(f"  項目数: {len(d)}")
    print(f"  書式: {d.style.kind}(字下げ {d.style.indent}、改行 {d.style.newline!r}、末尾改行 {d.style.trailing_newline})")
    print(f"  タグ: " + "、".join(f"{k}({v})" for k, v in tags.most_common()))
    print(f"  内容の見出し: " + "、".join(f"{k}({v})" for k, v in titles.most_common()))
    return 0


def cmd_save(a) -> int:
    p = Project.open(a.dir)
    before = p.dictionary_path.read_bytes()
    d = p.load_dictionary()
    bak = p.save_dictionary(d)
    after = p.dictionary_path.read_bytes()
    print(f"保存した: {p.dictionary_path}({len(d)}項目)")
    print(f"  バックアップ: {bak}")
    print(f"  保存前と同じバイト列: {before == after}")
    return 0


def cmd_verify(a) -> int:
    raw = Path(a.file).read_bytes()
    d = Dictionary.from_bytes(raw)
    out = d.to_bytes()
    same_content = json.loads(out.decode("utf-8-sig")) == json.loads(raw.decode("utf-8-sig"))
    print(f"{a.file}({len(d)}項目、書式 {d.style.kind})")
    print(f"  内容が一致: {same_content}")
    print(f"  バイト列も一致: {out == raw}")
    return 0 if same_content else 1


def cmd_rules_import(a) -> int:
    p = Project.open(a.dir)
    bak = p.import_rules(a.file)
    r = p.load_rules()
    print(f"取り込んだ: {a.file} → {p.rules_path}({r.language or '言語名なし'})")
    if bak:
        print(f"  前の規則のバックアップ: {bak}")
    return 0


def cmd_rules_show(a) -> int:
    path = Path(a.target)
    lang_id = a.language
    if path.is_dir():
        p = Project.open(path)
        r = p.load_rules()
        if r is None:
            print(f"規則ファイルがない: {p.rules_path}(conlang rules import で取り込む)")
            return 1
        lang_id = lang_id or p.language
    else:
        r = Rules.load(path)
    print(f"{r.path}({r.language or '言語名なし'})")
    items = r.statuses() if a.all else r.unsettled()
    counts = Counter(s.status for s in r.statuses())
    print("  状態: " + "、".join(f"{k} {v}件" for k, v in counts.items()))
    print(f"  {'すべての規則' if a.all else '「決定」以外の規則'}:")
    for s in items:
        extra = "".join(f"  {label}: {v}" for label, v in (("ref", s.ref), ("id", s.id), ("注", s.note)) if v)
        print(f"    [{s.status}] {s.path}{extra}")
    lang = registry.get(lang_id) if lang_id else None
    if lang and lang.check_rules:
        problems = lang.check_rules(r)
        print(f"  {lang.name}の規則としての点検: " + ("問題なし" if not problems else f"{len(problems)}件"))
        for msg in problems:
            print(f"    ! {msg}")
        return 1 if problems else 0
    return 0


def cmd_language(lang: registry.LanguageModule, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=f"conlang {lang.id}", add_help=False)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--project")
    g.add_argument("--dict")
    ap.add_argument("--rules")
    a, rest = ap.parse_known_args(argv)
    r = None
    if a.project:
        p = Project.open(a.project)
        d = p.load_dictionary()
        r = p.load_rules()
    elif a.dict or os.environ.get("PUTE_DICT"):
        d = Dictionary.load(a.dict or os.environ["PUTE_DICT"])
    else:
        print(f"辞書を --project DIR か --dict FILE で指定する")
        return 2
    if a.rules:
        r = Rules.load(a.rules)
    lang.cli(rest, d, r)
    return 0


def cmd_gui(a) -> int:
    try:
        from .gui.app import main as gui_main
    except ImportError:
        print('画面には PySide6 が要る: pip install -e ".[gui]"', file=sys.stderr)
        return 1
    return gui_main([a.dir] if a.dir else [])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="conlang", description="人工言語創作アプリ",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="言語プロジェクトを作る")
    s.add_argument("dir")
    s.add_argument("--name", required=True)
    s.add_argument("--language", help="言語別機能の id(例: pute)")
    s.set_defaults(func=cmd_new)
    s = sub.add_parser("import", help="zpdic 辞書を取り込む")
    s.add_argument("dir")
    s.add_argument("file")
    s.set_defaults(func=cmd_import)
    s = sub.add_parser("info", help="辞書の情報")
    s.add_argument("target")
    s.set_defaults(func=cmd_info)
    s = sub.add_parser("save", help="辞書を書き戻す")
    s.add_argument("dir")
    s.set_defaults(func=cmd_save)
    s = sub.add_parser("verify", help="往復で壊れないか確かめる")
    s.add_argument("file")
    s.set_defaults(func=cmd_verify)
    s = sub.add_parser("rules", help="規則ファイル(YAML)")
    rsub = s.add_subparsers(dest="rules_cmd", required=True)
    t = rsub.add_parser("import", help="規則ファイルをプロジェクトに取り込む")
    t.add_argument("dir")
    t.add_argument("file")
    t.set_defaults(func=cmd_rules_import)
    t = rsub.add_parser("show", help="規則の状態の一覧と点検")
    t.add_argument("target", help="プロジェクトのフォルダか、規則ファイル")
    t.add_argument("--all", action="store_true", help="「決定」の規則も出す")
    t.add_argument("--language", help="点検に使う言語別機能の id(プロジェクトなら省ける)")
    t.set_defaults(func=cmd_rules_show)
    s = sub.add_parser("gui", help="画面を開く")
    s.add_argument("dir", nargs="?")
    s.set_defaults(func=cmd_gui)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry.load_builtin()
    try:
        if argv and (lang := registry.get(argv[0])):
            return cmd_language(lang, argv[1:])
        a = build_parser().parse_args(argv)
        return a.func(a)
    except (ProjectError, ZpdicError, RulesError, FileNotFoundError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
