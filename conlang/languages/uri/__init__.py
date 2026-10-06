"""ウリ語の言語別機能(基本の部分)

- 辞書の旧表記を、現代の転写にする(表示の切り替えにも使う)
- 音節(CV、CVn、CVng)への分割と、意味範疇の接頭辞(su-、xu-、vora-、gara-、ra-、lo-)
- 辞書の検査(音節に分けられない語、旧表記の大文字の位置)
"""
from __future__ import annotations

from conlang.core import grammar_check as GC
from conlang.core.registry import Command, Context, LanguageModule, register
from conlang.core.zpdic import form, meanings

from . import consistency, grammar_check
from .lang import UriLang

USAGE = """\
conlang uri [--project DIR | --dict FILE] [--rules FILE] コマンド ...
  modern 語 …          辞書の旧表記(SuKaHuDu、FoTONe)を、現代の転写(sukahudu、fotoone)にする
  syllables 語 …       音節(CV、CVn、CVng)に分ける。旧表記でも現代の転写でもよい
  analyze 語 …         接頭辞(su- など)と残りに分け、辞書の語と照らす
  find キーワード …    訳語に含む語を、現代の転写と一緒に出す
  particles            規則ファイルの情詞の一覧(辞書にあるかも出す)
  grammar-check ...    文法 md と規則ファイルの食い違いを調べる(grammar-check --help)
"""


def _syllables(lang: UriLang, word: str) -> str:
    alls = lang.syllabify_all(word)
    if not alls:
        return "(音節に分けられない)"
    shown = " / ".join(".".join(s.text for s in a) for a in alls[:3])
    return shown + (f"(分け方が{len(alls)}通り)" if len(alls) > 1 else "")


def _index(ctx: Context, lang: UriLang) -> dict[str, list[dict]]:
    """現代の転写 → 辞書の項目(旧表記が違っても、現代の転写が同じなら同じ所に入る)"""
    out: dict[str, list[dict]] = {}
    if ctx.dictionary is not None:
        for w in ctx.dictionary.words:
            if form(w):
                out.setdefault(lang.to_modern(form(w)), []).append(w)
    return out


def _entries(ws: list[dict]) -> str:
    return " / ".join(f"{form(w)}  {'/'.join(meanings(w))}" for w in ws)


def _cli(argv: list[str], ctx: Context) -> int:
    lang = UriLang.from_rules(ctx.rules)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "grammar-check":
        return GC.run_cli(args, ctx, grammar_check.TABLE_CHECKS)
    if cmd == "particles":
        if not lang.particles:
            print("規則ファイルに情詞の一覧がない(--project か --rules で規則を指定する)")
            return 2
        index = _index(ctx, lang)
        cats = (ctx.rules.get("particles", "categories", default={}) or {}) if ctx.rules else {}
        for cat, words in cats.items():
            print(f"■ {cat}")
            for p, meaning in (words or {}).items():
                found = _entries(index[p]) if p in index else "(辞書にない)"
                print(f"  {p}  {meaning}    辞書: {found}")
        return 0
    if cmd == "modern":
        for a in args:
            print(f"{a}\t{lang.to_modern(a)}")
        return 0
    if cmd == "syllables":
        for a in args:
            m = lang.to_modern(a)
            print(f"{a}{f'({m})' if m != a else ''}: {_syllables(lang, m)}")
        return 0
    if cmd == "analyze":
        index = _index(ctx, lang)
        for a in args:
            m = lang.to_modern(a)
            print(f"■ {a}{f'({m})' if m != a else ''}")
            print(f"  音節: {_syllables(lang, m)}")
            if m in index:
                print(f"  辞書: {_entries(index[m])}")
            prefix, rest = lang.split_prefix(m)
            if prefix:
                print(f"  接頭辞: {prefix}-({lang.prefixes[prefix]}) + {rest}")
                if rest in index:
                    print(f"    {rest} は辞書にある: {_entries(index[rest])}")
        return 0
    if cmd == "find":
        if ctx.dictionary is None:
            print("辞書を --project DIR か --dict FILE で指定する")
            return 2
        for kw in args:
            print(f"■ {kw}")
            hits = [w for w in ctx.dictionary.words if any(kw in m for m in meanings(w))]
            for w in hits[:20]:
                print(f"  {lang.to_modern(form(w))}  ({form(w)})  {'/'.join(meanings(w))}")
            if not hits:
                print("  該当する語はない")
        return 0
    print(USAGE)
    return 2


def _modern(rules):
    lang = UriLang.from_rules(rules)
    return lang.to_modern


COMMANDS = (
    Command("analyze", "接頭辞と辞書で読む", "語(旧表記でも現代の転写でもよい。空白で区切って複数)", "LoRoPu SuKaHuDu", True),
    Command("modern", "現代の転写にする", "辞書の旧表記の語", "SuKaHuDu FoTONe"),
    Command("syllables", "音節に分ける", "語(旧表記でも現代の転写でもよい)", "KanTi ReWing"),
    Command("find", "訳語から探す", "キーワード", "女装", True),
    Command("particles", "情詞の一覧", "(引数なし)", "", True),
)

register(LanguageModule(id="uri", name="ウリ語", cli=_cli, commands=COMMANDS, check_dictionary=consistency.check_dictionary,
                        similar_min_length=7,  # CV の短い語が多く、4文字で1文字違いは普通にある
                        grammar_table_checks=grammar_check.TABLE_CHECKS,
                        transcriptions={"現代の転写": _modern}))
