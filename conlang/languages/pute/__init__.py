"""ピュテ語の言語別機能"""
from conlang.core.registry import LanguageModule, register
from conlang.core.zpdic import Dictionary

from . import zougo


def _cli(argv: list[str], d: Dictionary) -> None:
    zougo.main(argv, zougo.parts_from_words(d.words))


register(LanguageModule(id="pute", name="ピュテ語", cli=_cli))
