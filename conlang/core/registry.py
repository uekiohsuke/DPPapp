"""言語別機能の登録口

言語別の機能は conlang/languages/<id>/ に置き、ここに LanguageModule を登録する。
土台は、登録された言語の id で機能を呼ぶだけで、中身を知らない。
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

from .rules import Rules
from .zpdic import Dictionary


@dataclass(frozen=True)
class LanguageModule:
    id: str
    name: str
    # CLI のサブコマンド: (引数, 辞書, 規則[なければ None]) を受け取る
    cli: Callable[[list[str], Dictionary, Rules | None], None] | None = None
    # 規則ファイルそのものの点検。問題を文の一覧で返す
    check_rules: Callable[[Rules], list[str]] | None = None


_modules: dict[str, LanguageModule] = {}

# 同梱の言語別機能。import するとそれぞれが register() を呼ぶ
BUILTIN = ("conlang.languages.pute",)


def register(module: LanguageModule) -> None:
    _modules[module.id] = module


def load_builtin() -> None:
    for name in BUILTIN:
        importlib.import_module(name)


def get(lang_id: str) -> LanguageModule | None:
    return _modules.get(lang_id)


def all_modules() -> list[LanguageModule]:
    return list(_modules.values())
