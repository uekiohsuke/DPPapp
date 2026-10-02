"""ピュテ語の言語別機能"""
from __future__ import annotations

from pathlib import Path

from conlang.core import llm, llm_log
from conlang.core.registry import Context, LanguageModule, register
from conlang.core.rules import Rules, RulesError

from . import cli_coining, consistency, grammar_check
from . import rules as pute_rules

GRAMMAR_CHECK = "grammar-check"
USAGE_GRAMMAR = """\
conlang pute [--project DIR] [--rules FILE] grammar-check [--grammar FILE] [--prompt-only | --llm | --response FILE] [--force]
  表(音素、接辞、語尾、活用表)の食い違いをコードで調べる。
  --prompt-only   文章の記述を LLM に調べさせるためのプロンプトを出す(好きなチャットに貼る)
  --llm           LLM の API を呼ぶ(接続先は conlang llm config で設定する)
  --response FILE 別のチャットの答えを読み込む
  --force         文法文書と規則ファイルが前回から変わっていなくても、LLM に調べさせる
"""


def _inflect(argv: list[str], r: Rules | None) -> int:
    if r is None:
        print("活用の表は規則ファイルから作る。--project か --rules で規則を指定する")
        return 2
    classes = [a for a in argv if a in pute_rules.WORD_CLASSES] or list(pute_rules.WORD_CLASSES)
    stems = [a for a in argv if a not in pute_rules.WORD_CLASSES] or ["X"]
    for c in classes:
        print(pute_rules.format_table(r, c, stems[0]))
        print()
    return 0


def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _grammar_check(argv: list[str], ctx: Context) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE_GRAMMAR)
        return 0
    r = ctx.rules
    if r is None:
        print("規則ファイルがない。--project か --rules で指定する")
        return 2
    gpath = _opt(argv, "--grammar")
    path = Path(gpath) if gpath else (ctx.project.grammar_path(r) if ctx.project else None)
    if path is None or not path.exists():
        print("文法文書が見つからない。--grammar FILE で指定するか、conlang grammar import で取り込む")
        return 2
    grammar = path.read_text(encoding="utf-8-sig")
    rules_text = r.path.read_text(encoding="utf-8-sig") if r.path else repr(r.data)

    rep = grammar_check.run(grammar, r)
    diffs = rep.problems
    print(f"{path} と {r.path or '規則'} の照合(目印 {rep.anchors}個、ref {rep.refs}個。表の正は規則ファイル):")
    if diffs:
        for d in diffs:
            print(f"  ! {d}")
    else:
        print("  食い違いはない")
    if rep.prose_anchors:
        print("  文章の記述なので LLM に調べさせる目印: " + "、".join(rep.prose_anchors))
    print()

    pairs = grammar_check.llm_pairs(grammar, r)
    prompt = grammar_check.build_llm_prompt(pairs)
    if "--prompt-only" in argv:
        print(prompt)
        return 1 if diffs else 0
    resp = _opt(argv, "--response")
    if "--llm" not in argv and resp is None:
        print("文章の記述の検査は、--prompt-only / --llm / --response で LLM に調べさせる")
        return 1 if diffs else 0

    log_dir = ctx.project.llm_log_dir if ctx.project else None
    inputs = {"grammar": grammar, "rules": rules_text}
    if resp is None and log_dir and "--force" not in argv and not llm_log.inputs_changed(log_dir, GRAMMAR_CHECK, inputs):
        print("文法文書と規則ファイルは、前回 LLM に調べさせたときから変わっていない。もう一度調べるときは --force")
        return 1 if diffs else 0
    model = "(貼り付けた答え)"
    if resp:
        answer = Path(resp).read_text(encoding="utf-8-sig")
    else:
        cfg = llm.load_config()
        model = f"{cfg.model} @ {cfg.url}"
        print(f"LLM に問い合わせている: {model}(目印 {len(pairs)}個)")
        try:
            answer = llm.chat(prompt, cfg, json_mode=True)
        except llm.LLMError as e:
            print(f"エラー: {e}")
            return 1
    if log_dir:
        saved = llm_log.save_call(log_dir, GRAMMAR_CHECK, prompt, answer, model=model,
                                  grammar=str(path), rules=str(r.path or ""))
        print(f"(履歴: {saved})")
    try:
        cands = grammar_check.parse_llm_answer(answer)
    except ValueError as e:
        print(f"LLM の答えを読めなかった: {e}\n--- 答え ---\n{answer}")
        return 1
    if log_dir:
        llm_log.remember_inputs(log_dir, GRAMMAR_CHECK, inputs)
    print(grammar_check.format_candidates(cands))
    return 1 if diffs or cands else 0


USAGE = """\
conlang pute [--project DIR | --dict FILE] [--rules FILE] コマンド ...
  造語支援: find / check / suggest / analyze / shorten / long / gen / parts / decompose(conlang pute --help-coining)
  inflect [noun|verb|adjective|adverb] [語幹]   規則ファイルから活用表を作る
  grammar-check ...                            文法 md と規則ファイルの食い違いを調べる(grammar-check --help)
"""


def _cli(argv: list[str], ctx: Context) -> int:
    r = ctx.rules
    try:
        if not argv or argv[0] in ("-h", "--help"):
            print(USAGE)
            return 0
        if argv[0] == "--help-coining":
            print(cli_coining.__doc__)
            return 0
        if argv[0] == "inflect":
            return _inflect(argv[1:], r)
        if argv[0] == GRAMMAR_CHECK:
            return _grammar_check(argv[1:], ctx)
        return cli_coining.main(argv, ctx)
    except RulesError as e:
        print(f"エラー: {e}")
        return 1


def _llm_grammar_check(ctx: Context, force: bool) -> int:
    return _grammar_check(["--llm"] + (["--force"] if force else []), ctx)


def _gui_panels():
    from . import gui_coining
    return [("造語", gui_coining.make_panel)]


register(LanguageModule(id="pute", name="ピュテ語", cli=_cli, check_rules=pute_rules.check_rules,
                        check_dictionary=consistency.check_dictionary, check_grammar=grammar_check.check_tables,
                        llm_grammar_check=_llm_grammar_check, gui_panels=_gui_panels))
