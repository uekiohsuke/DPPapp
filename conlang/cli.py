"""conlang の CLI

  conlang new DIR --name ピュテ語 [--language pute]   言語プロジェクトを作る
  conlang import DIR FILE                            zpdic 辞書を取り込む(元のファイルはコピーするだけ)
  conlang info DIR|FILE                              辞書の項目数などを出す
  conlang save DIR                                   辞書を読んで書き戻す(保存前にバックアップする)
  conlang verify FILE                                読んで書き戻したときに、元と同じになるかを確かめる(書き込まない)
  conlang rules import DIR FILE                      規則ファイル(YAML)を取り込む(元のファイルはコピーするだけ)
  conlang rules show DIR|FILE [--all]                「決定」以外の規則の一覧と、言語別の点検
  conlang grammar import DIR FILE                    文法文書(Markdown)をプロジェクトの grammar/ に取り込む
  conlang check DIR|FILE [--rules FILE] [--language ID] [--errors-only]
                                                     辞書の整合性チェック(誤記、旧用語、音素、似た綴り など)
  conlang llm config [--url URL] [--model M]         LLM の接続先(OpenAI 互換)を見る・設定する
  conlang llm models | ask "質問"                    接続先のモデルの一覧 / 1回だけ問い合わせる
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


def cmd_grammar_import(a) -> int:
    p = Project.open(a.dir)
    bak = p.import_grammar(a.file)
    print(f"取り込んだ: {a.file} → {p.grammar_dir / Path(a.file).name}")
    if bak:
        print(f"  前の文書のバックアップ: {bak}")
    return 0


def cmd_check(a) -> int:
    from .core.validate import ERROR, check_all
    path = Path(a.target)
    rules, lang_id = None, a.language
    if path.is_dir():
        p = Project.open(path)
        d, rules = p.load_dictionary(), p.load_rules()
        lang_id = lang_id or p.language
        path = p.dictionary_path
    else:
        d = Dictionary.load(path)
    if a.rules:
        rules = Rules.load(a.rules)
    lang = registry.get(lang_id)
    issues = check_all(d, rules, lang)
    errors = [i for i in issues if i.level == ERROR]
    shown = errors if a.errors_only else issues
    print(f"{path}({len(d)}項目、規則 {rules.path if rules else 'なし'}、言語別の検査 {lang.name if lang else 'なし'})")
    print(f"  誤り {len(errors)}件(語 {len({i.word_id for i in errors})}個)、注意 {len(issues) - len(errors)}件")
    for i in sorted(shown, key=lambda i: (i.level != ERROR, i.word_id if i.word_id is not None else -1)):
        print(f"  [{i.level}] #{i.word_id} {i.kind}: {i.message}")
    return 1 if errors else 0


def cmd_llm_config(a) -> int:
    from .core import llm
    cfg = llm.load_config()
    changed = False
    for name in ("url", "model", "key", "reasoning_effort"):
        v = getattr(a, name)
        if v is not None:
            setattr(cfg, name, v)
            changed = True
    if a.temperature is not None:
        cfg.temperature, changed = a.temperature, True
    if a.timeout is not None:
        cfg.timeout, changed = a.timeout, True
    if changed:
        print(f"保存した: {llm.save_config(cfg)}")
    print(f"  接続先: {cfg.url}")
    print(f"  モデル: {cfg.model or '(未設定)'}")
    print(f"  キー: {'あり' if cfg.key else 'なし'}  温度: {cfg.temperature}  待ち時間: {cfg.timeout}秒"
          f"  考える過程: {cfg.reasoning_effort or '(モデルの既定)'}")
    return 0


def cmd_llm_models(a) -> int:
    from .core import llm
    cfg = llm.load_config()
    try:
        models = llm.list_model_infos(cfg)
    except llm.LLMError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    chat = [m for m in models if m.can_chat]
    print(f"{cfg.url} の会話に使えるモデル({len(chat)}個。* は今の設定):")
    for m in chat:
        print(f"  {'*' if m.id == cfg.model else ' '} {m.label()}")
    others = [m.id for m in models if not m.can_chat]
    if others:
        print(f"  (埋め込み用など、会話に使えないもの: {', '.join(others)})")
    if any(m.thinks for m in chat):
        print("  注: 「考える過程あり」のモデルは、--reasoning-effort none にすると速く答える")
    return 0


def cmd_llm_ask(a) -> int:
    from .core import llm
    try:
        print(llm.chat(a.prompt))
    except llm.LLMError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_language(lang: registry.LanguageModule, argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=f"conlang {lang.id}", add_help=False)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--project")
    g.add_argument("--dict")
    ap.add_argument("--rules")
    a, rest = ap.parse_known_args(argv)
    ctx = registry.Context()
    if a.project:
        ctx.project = Project.open(a.project)
        ctx.dictionary = ctx.project.load_dictionary()
        ctx.rules = ctx.project.load_rules()
    elif a.dict or os.environ.get("PUTE_DICT"):
        ctx.dictionary = Dictionary.load(a.dict or os.environ["PUTE_DICT"])
    if a.rules:
        ctx.rules = Rules.load(a.rules)
    return lang.cli(rest, ctx) or 0


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
    s = sub.add_parser("grammar", help="文法文書")
    gsub = s.add_subparsers(dest="grammar_cmd", required=True)
    t = gsub.add_parser("import", help="文法文書をプロジェクトに取り込む")
    t.add_argument("dir")
    t.add_argument("file")
    t.set_defaults(func=cmd_grammar_import)
    s = sub.add_parser("check", help="辞書の整合性チェック")
    s.add_argument("target", help="プロジェクトのフォルダか、辞書ファイル")
    s.add_argument("--rules", help="規則ファイル(プロジェクトなら省ける)")
    s.add_argument("--language", help="言語別の検査の id(プロジェクトなら省ける)")
    s.add_argument("--errors-only", action="store_true", help="「誤り」だけ出す")
    s.set_defaults(func=cmd_check)
    s = sub.add_parser("llm", help="LLM の接続")
    lsub = s.add_subparsers(dest="llm_cmd", required=True)
    t = lsub.add_parser("config", help="接続先とモデルを見る・設定する")
    t.add_argument("--url", help="OpenAI 互換 API の URL(例: http://192.168.0.178:11434/v1)")
    t.add_argument("--model")
    t.add_argument("--key")
    t.add_argument("--temperature", type=float)
    t.add_argument("--timeout", type=int, help="待ち時間(秒)")
    t.add_argument("--reasoning-effort", dest="reasoning_effort",
                   help="考える過程の量(none / low / medium / high。none で止める。空文字で送らない)")
    t.set_defaults(func=cmd_llm_config)
    t = lsub.add_parser("models", help="接続先のモデルの一覧")
    t.set_defaults(func=cmd_llm_models)
    t = lsub.add_parser("ask", help="1回だけ問い合わせる(接続の確認用)")
    t.add_argument("prompt")
    t.set_defaults(func=cmd_llm_ask)
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
