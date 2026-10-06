"""ピュテ語の言語別機能"""
from __future__ import annotations

from conlang.core import grammar_check as GC
from conlang.core.registry import Command, Context, LanguageModule, register
from conlang.core.rules import Rules, RulesError

from . import cli_coining, consistency, grammar_check
from . import rules as pute_rules

GRAMMAR_CHECK = "grammar-check"


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


def _grammar_check(argv: list[str], ctx: Context) -> int:
    return GC.run_cli(argv, ctx, grammar_check.TABLE_CHECKS)


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


def _gui_panels():
    from . import gui_coining
    return [("造語", gui_coining.make_panel)]


COMMANDS = (
    Command("inflect", "活用表を作る", "品詞(noun / verb / adjective / adverb。省くと全部)と語幹", "noun verb sasxa"),
    Command("analyze", "形態素分解", "語(空白で区切って複数)", "thaidra kethjadrwoqakushavo", True),
    Command("check", "組み合わせの検査", "部品(見出し語・短縮形・訳語・接辞)", "節点 外", True),
    Command("suggest", "組み合わせの提案", "キーワードを大本の概念から順に(--any-order で並べ替える)", "辺 数", True),
    Command("find", "訳語・語義・語源から探す", "キーワード", "力", True),
    Command("shorten", "短縮の候補", "部品", "eshkiki judra", True),
    Command("long", "長大語と短縮案", "文字数(省くと 20)", "", True),
    Command("gen", "基本詞の候補", "個数など(--len N、--seed N、--min-vowels N)", "10 --seed 1", True),
    Command("parts", "部品の一覧", "(引数なし)", "", True),
)

register(LanguageModule(id="pute", name="ピュテ語", cli=_cli, commands=COMMANDS, check_rules=pute_rules.check_rules,
                        check_dictionary=consistency.check_dictionary,
                        grammar_table_checks=grammar_check.TABLE_CHECKS, gui_panels=_gui_panels))
