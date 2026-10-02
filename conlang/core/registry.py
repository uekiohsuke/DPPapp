"""言語別機能の登録口

言語別の機能は conlang/languages/<id>/ に置き、ここに LanguageModule を登録する。
土台は、登録された言語の id で機能を呼ぶだけで、中身を知らない。
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .rules import Rules
from .zpdic import Dictionary

if TYPE_CHECKING:
    from .project import Project


@dataclass
class Context:
    """言語別機能に渡すもの。指定されなかったものは None"""
    dictionary: Dictionary | None = None
    rules: Rules | None = None
    project: "Project | None" = None


@dataclass(frozen=True)
class LanguageModule:
    id: str
    name: str
    # CLI のサブコマンド: (引数, Context)
    cli: Callable[[list[str], Context], int | None] | None = None
    # 規則ファイルそのものの点検。問題を文の一覧で返す
    check_rules: Callable[[Rules], list[str]] | None = None
    # 辞書の言語別の整合性チェック。validate.Issue の一覧を返す
    check_dictionary: Callable[[Dictionary, Rules | None], list] | None = None
    # 文法文書と規則ファイルの、表の食い違い(コードでの検査)。(文法文書の本文, 規則) → 食い違いの文の一覧
    check_grammar: Callable[[str, Rules], list[str]] | None = None
    # 画面に足す欄: [(題, 部品を作る関数)]。部品は set_context(Context) を持つ QWidget。
    # PySide6 を import するので、画面を開くときだけ呼ばれる
    gui_panels: Callable[[], list[tuple[str, Callable]]] | None = None


_modules: dict[str, LanguageModule] = {}

# 同梱の言語別機能。import するとそれぞれが register() を呼ぶ
BUILTIN = ("conlang.languages.pute",)


def register(module: LanguageModule) -> None:
    _modules[module.id] = module


def load_builtin() -> None:
    for name in BUILTIN:
        importlib.import_module(name)


def get(lang_id: str | None) -> LanguageModule | None:
    return _modules.get(lang_id) if lang_id else None


def all_modules() -> list[LanguageModule]:
    return list(_modules.values())
