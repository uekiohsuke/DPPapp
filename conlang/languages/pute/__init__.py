"""ピュテ語の言語別機能"""
from __future__ import annotations

from conlang.core.registry import LanguageModule, register
from conlang.core.rules import Rules, RulesError
from conlang.core.zpdic import Dictionary

from . import rules as pute_rules
from . import zougo


def _inflect(argv: list[str], r: Rules | None) -> None:
    if r is None:
        print("活用の表は規則ファイルから作る。--project か --rules で規則を指定する")
        return
    classes = [a for a in argv if a in pute_rules.WORD_CLASSES] or list(pute_rules.WORD_CLASSES)
    stems = [a for a in argv if a not in pute_rules.WORD_CLASSES] or ["X"]
    for c in classes:
        print(pute_rules.format_table(r, c, stems[0]))
        print()


def _cli(argv: list[str], d: Dictionary, r: Rules | None) -> None:
    zougo.apply_rules(r.data if r else None)
    if argv and argv[0] == "inflect":
        try:
            _inflect(argv[1:], r)
        except RulesError as e:
            print(f"エラー: {e}")
        return
    zougo.main(argv, zougo.parts_from_words(d.words))


register(LanguageModule(id="pute", name="ピュテ語", cli=_cli, check_rules=pute_rules.check_rules))
