"""ミャミュ語の言語別機能(基本の部分)

- 音素への分割(sh・mj は1つの子音)と、音の連なりの規則(同じ子音は1つ、存在しない並びは最初の子音を落とす)
- 動詞の枠(時制-語幹-態-相-法-主語マーカー)での組み立てと分解。同形の接辞は枠の位置で区別する
- 数の語、接辞の一覧、文法 md と規則ファイルの照合、規則ファイルの中の点検
"""
from __future__ import annotations

from conlang.core import grammar_check as GC
from conlang.core.registry import Command, Context, LanguageModule, register
from conlang.core.rules import RulesError

from . import consistency, grammar_check
from .lang import MyamyuLang

USAGE = """\
conlang myamyu [--project DIR | --rules FILE] コマンド ...
  segment 語 …                      音素に分ける(sh・mj は1つの子音)
  sound 部品 部品 …                 部品をつなぎ、音の連なりの規則を当てる(同じ子音は1つ、存在しない並びは最初の子音を落とす)
  verb 語幹 [--tense 時制] [--voice 態] [--aspect 相] [--mood 法] [--subject 主語マーカー]
                                    動詞を組み立てる。接辞は形でも名前でもよい(例: --tense 未来 / ze / zez、--subject 三人称単数)
  parse 語 …                        動詞の形を、時制-語幹-態-相-法-主語マーカー の枠に分ける(ハイフンで区切ってもよい)
  affixes                           接辞の一覧(時制、態、相、法、主語マーカー、格)
  number 数 …                       数の語(0〜9)
  grammar-check ...                 文法 md と規則ファイルの食い違いを調べる(grammar-check --help)
"""

OPTIONS = {"--tense": "時制", "--voice": "態", "--aspect": "相", "--mood": "法", "--subject": "主語マーカー"}


def _show_parse(p: dict) -> str:
    bits = []
    t = p.get("時制")
    if t:
        bits.append(f"時制 {t[0]}({t[1]})")
    bits.append(f"語幹 {p['語幹']}")
    for slot in ("態", "相", "法", "主語マーカー"):
        a = p.get(slot)
        if a:
            bits.append(f"{slot} {a.form}({a.name})")
    return " / ".join(bits)


def _cli(argv: list[str], ctx: Context) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "grammar-check":
        return GC.run_cli(args, ctx, grammar_check.TABLE_CHECKS)
    try:
        lang = MyamyuLang.from_rules(ctx.rules)
    except RulesError as e:
        print(f"エラー: {e}")
        return 2
    if cmd == "segment":
        for w in args:
            seq = lang.segment(w)
            if seq is None:
                print(f"{w}: (音素に分けられない)")
                continue
            extra = []
            if lang.clusters(seq):
                extra.append("存在しない並び: " + "、".join(lang.clusters(seq)))
            if lang.same_runs(seq):
                extra.append("同じ子音の連続: " + "、".join(lang.same_runs(seq)))
            print(f"{w}: {'.'.join(seq)}" + (f"  ! {' / '.join(extra)}" if extra else ""))
        return 0
    if cmd == "sound":
        parts = [p for a in args for p in a.split("-") if p]
        word, notes = lang.apply_phonotactics("".join(parts))
        print(f"{'-'.join(parts)} → {word}")
        for n in notes:
            print(f"  注: {n}")
        return 0
    if cmd == "verb":
        if not args or args[0].startswith("--"):
            print("語幹を指定する。例: conlang myamyu verb gaz --tense 未来 --voice 能動態 --subject 三人称単数")
            return 2
        stem, chosen, i = args[0], {}, 1
        tense_forms = dict(lang.tense_forms())
        while i < len(args):
            slot = OPTIONS.get(args[i])
            if slot is None or i + 1 >= len(args):
                print(f"分からない指定: {args[i]}")
                return 2
            key = args[i + 1]
            a = lang.find(slot, key)
            if a is None and slot == "時制" and key in tense_forms:
                a = key  # 派生時制(zez など)
            if a is None:
                names = "、".join(f"{x.form}({x.name})" for x in lang.slots.get(slot, []))
                print(f"{slot}「{key}」は規則ファイルにない。使えるもの: {names}")
                return 2
            chosen[slot] = a
            i += 2
        hyphen, word, notes = lang.verb_form(stem, chosen)
        print(f"{hyphen} → {word}")
        for n in notes:
            print(f"  注: {n}")
        print("  (どの枠を省けるかは、文法 md に書かれていない。指定した枠だけを置いた)")
        return 0
    if cmd == "parse":
        for w in args:
            ps = lang.parse_verb(w)
            print(f"■ {w}")
            if not ps:
                print("  枠に分けられない")
            for i, p in enumerate(ps[:8], 1):
                print(f"  {i}. {_show_parse(p)}")
            if len(ps) > 1:
                print(f"  注: 辞書がないので語幹は決まらず、{len(ps)}通りに読める。同形の接辞は、付く位置で決まる")
        return 0
    if cmd == "affixes":
        for slot in [s for s in (lang.verb_structure or []) if s != "語幹"] + ["格"]:
            items = lang.cases if slot == "格" else lang.slots.get(slot, [])
            print(f"■ {slot}: " + "、".join(f"{a.form}({a.name})" for a in items))
        if lang.tense_suffix:
            print("■ 時制接辞(派生時制): " + "、".join(f"-{v}({k})" for k, v in lang.tense_suffix.items()))
        return 0
    if cmd == "number":
        for a in args:
            try:
                print(f"{a}: {lang.number_word(int(a))}(略形 {lang.digits[int(a)][1]})")
            except (ValueError, RulesError) as e:
                print(f"{a}: {e}")
        return 0
    print(USAGE)
    return 2


COMMANDS = (
    Command("verb", "動詞を組み立てる", "語幹と、枠ごとの接辞(形でも名前でもよい)",
            "gaz --tense 未来 --voice 受動態 --aspect 起動相 --mood 希求法 --subject 三人称単数"),
    Command("parse", "動詞を枠に分ける", "動詞の形(ハイフンで区切ってもよい。空白で区切って複数)", "ze-gaz-af-ol-esh-ol"),
    Command("sound", "音の連なりの規則を当てる", "部品(空白かハイフンで区切る)", "gaf baz ssa"),
    Command("segment", "音素に分ける", "語(空白で区切って複数)", "lemjgo ufzae"),
    Command("affixes", "接辞の一覧", "(引数なし)"),
    Command("number", "数の語", "数(0〜9。空白で区切って複数)", "3 7"),
)

register(LanguageModule(id="myamyu", name="ミャミュ語", cli=_cli, commands=COMMANDS, check_rules=grammar_check.check_rules,
                        check_dictionary=consistency.check_dictionary,
                        grammar_table_checks=grammar_check.TABLE_CHECKS))
