"""ウリ語の言語別機能(基本の部分)

- 辞書の旧表記を、現代の転写にする(表示の切り替えにも使う)
- 音節(CV、CVn、CVng)への分割と、意味範疇の接頭辞(su-、xu-、vora-、gara-、ra-、lo-)
- 辞書の検査(音節に分けられない語、旧表記の大文字の位置)
"""
from __future__ import annotations

from conlang.core.registry import Context, LanguageModule, register
from conlang.core.zpdic import form, meanings

from . import consistency
from .lang import UriLang

USAGE = """\
conlang uri [--project DIR | --dict FILE] [--rules FILE] コマンド ...
  modern 語 …          辞書の旧表記(SuKaHuDu、FoTONe)を、現代の転写(sukahudu、fotoone)にする
  syllables 語 …       音節(CV、CVn、CVng)に分ける。旧表記でも現代の転写でもよい
  analyze 語 …         接頭辞(su- など)と残りに分け、辞書の語と照らす
  find キーワード …    訳語に含む語を、現代の転写と一緒に出す
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


register(LanguageModule(id="uri", name="ウリ語", cli=_cli, check_dictionary=consistency.check_dictionary,
                        similar_min_length=7,  # CV の短い語が多く、4文字で1文字違いは普通にある
                        transcriptions={"現代の転写": _modern}))
