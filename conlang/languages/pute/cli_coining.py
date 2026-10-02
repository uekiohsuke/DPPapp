"""造語支援の CLI(表示)。中身は coining.Coiner

  conlang pute find 力 数              訳語・語義・語源にキーワードを含む語を探す
  conlang pute check 節点 外            部品をつないだ形を検査する(部品は 見出し語・短縮形・訳語・接辞 のどれでもよい)
  conlang pute suggest 辺 数            キーワードごとに部品の候補を出し、組み合わせを検査して順位づけする(--any-order で並べ替える)
  conlang pute analyze 語 [語…]         形態素分解。語を部品に分ける(辞書の語なら、語源欄の構成と照らす)
  conlang pute shorten 部品 部品…       部品を短縮形に替えた、短い組み合わせを出す
  conlang pute long [文字数]            辞書の長大語(既定 20文字以上)と、短縮の候補
  conlang pute gen [個数] [--len N] [--seed N] [--min-vowels N]   新しい基本詞の候補
  conlang pute parts                    部品(見出し語・短縮形・接辞)の一覧
  conlang pute decompose 概念 [--description 意味・説明] [--field 分野] [--distinguish 区別したい意味]
                         [--memo 補足] [--prompt-only | --response FILE] [--seed N]
                                        LLM に、ピュテ語でその概念をどう組み立てるかを考えさせ、辞書と照らす
                                        (日本語の語を字面で分けるのではない。接続先は conlang llm config)
      例: conlang pute decompose 次数 --field グラフ理論 --description 頂点に接続する辺の数 --distinguish 多項式の次数
"""
from __future__ import annotations

from pathlib import Path

from conlang.core import llm, llm_log
from conlang.core.registry import Context

from . import coining as K


def _show(r: K.CheckResult, parts_info: list[str] | None = None) -> None:
    print(f"  {r.word}   ({r.hyphen}, {r.length}文字)")
    if parts_info:
        print("    部品: " + " + ".join(parts_info))
    for n in r.notes:
        print("    注: " + n)
    for w in r.warnings:
        print("    ! " + w)
    if not r.warnings:
        print("    問題は見つからなかった")


def cmd_find(args, c: K.Coiner, ctx) -> int:
    for kw in args:
        print(f"■ {kw}")
        hits = c.search(kw)
        if not hits:
            print("  該当する語はない。近い意味の語で探すか、新しく基本詞を作る必要がある")
        for p in hits[:12]:
            forms = [q.form for q in c.forms_of(p)]
            sh = f"  短縮形: {', '.join(f for f in forms if f != p.form)}" if len(forms) > 1 else ""
            kinds = "・".join(p.kinds) or "区分なし"
            print(f"  {p.form}  {'/'.join(p.meanings)}  [{kinds}]{sh}")
            if p.ety:
                print("      語源: " + p.ety.replace("\n", " ＝ "))
    return 0


def cmd_check(args, c: K.Coiner, ctx) -> int:
    forms, info = [], []
    for t in args:
        p = c.resolve(t)
        if p is None:
            print(f"部品 {t!r} は辞書にない。見出し語・短縮形・訳語・接辞のどれかで指定する")
            return 2
        forms.append(p.form)
        info.append(p.describe())
    _show(c.check(forms), info)
    return 0


def cmd_suggest(args, c: K.Coiner, ctx, top: int = 10) -> int:
    any_order = "--any-order" in args
    kws = [a for a in args if a != "--any-order"]
    if not kws:
        print("キーワードを指定する。例: conlang pute suggest 辺 数")
        return 2
    res = c.suggest(kws, any_order)
    for kw, hits in res.candidates:
        if hits:
            print(f"「{kw}」の候補: " + "、".join(p.describe() for p in hits))
    if res.missing:
        for kw in res.missing:
            print(f"「{kw}」に当たる語が辞書にない。基本詞を新しく作るか、別の語で言い換える")
        return 1
    print()
    if res.existing:
        print("★ この組み合わせは、すでに辞書にある語になっている(新しく作る必要がないかもしれない):")
        for r, ps in res.existing:
            _show(r, [p.describe() for p in ps])
        print()
    print(f"組み合わせ案(警告が少なく、短いものから。全{len(res.ranked)}案のうち{min(top, len(res.ranked))}案):")
    for r, ps in res.ranked[:top]:
        _show(r, [p.describe() for p in ps])
    print("\n注: 造語は、大本の概念を先頭に置き、後ろへ伸ばしていく。最初のキーワードを大本として扱った。並べ替えて見るときは --any-order")
    return 0


def _describe_reading(r: K.Reading) -> str:
    return " + ".join(s.describe() for s in r.segments)


def cmd_analyze(args, c: K.Coiner, ctx, top: int = 8) -> int:
    if not args:
        print("語を指定する。例: conlang pute analyze thjadrwoqakujeta")
        return 2
    for word in args:
        a = c.analyze(word)
        title = f"{word}({'/'.join(a.existing.meanings)})" if a.existing else word
        print(f"■ {title}")
        if a.etymology:
            print(f"  語源欄の構成: {'-'.join(a.etymology)}")
        if not a.readings:
            print("  辞書の部品の連なりとしては読めない(基本詞か、辞書にない部品を含む)")
            continue
        for i, r in enumerate(a.readings[:top], 1):
            mark = "  ← 語源欄と一致" if r.matches_etymology else ""
            print(f"  {i}. {r.show()}{mark}")
            print(f"     {_describe_reading(r)}")
        rest = len(a.readings) - top
        if rest > 0:
            print(f"  ほか {rest}通り{'(以上。打ち切った)' if a.truncated else ''}")
        if a.etymology and not any(r.matches_etymology for r in a.readings):
            print("  ! 語源欄の構成どおりには読めない(conlang check で語源欄を確かめる)")
        elif len(a.readings) > 1:
            print(f"  注: 部品の連なりとして{len(a.readings)}通りに読める。'~' は母音をまとめて読んだ境目")
    return 0


def cmd_shorten(args, c: K.Coiner, ctx, top: int = 10) -> int:
    forms = []
    for t in args:
        p = c.resolve(t)
        if p is None:
            print(f"部品 {t!r} は辞書にない")
            return 2
        forms.append(p.form)
    if not forms:
        print("部品を指定する。例: conlang pute shorten eshkiki judra")
        return 2
    original = c.check(forms)
    print("元の形:")
    _show(original)
    alts = c.shorten(forms, top)
    print(f"\n短縮形を使った候補({len(alts)}件。既存語と重ならず、警告が少なく、短いものから):")
    for r in alts:
        _show(r)
    if not alts:
        print("  短くできる部品がない(短縮形のある部品がない)")
    return 0


def cmd_long(args, c: K.Coiner, ctx) -> int:
    threshold = int(args[0]) if args and args[0].isdigit() else K.LONG_WORD
    words = c.long_words(threshold)
    print(f"{threshold}文字以上の語({len(words)}語):")
    for p in words:
        best, alts = c.shorten_word(p.form, 3)
        print(f"■ {p.form}({len(p.form)}文字、{'/'.join(p.meanings)})")
        if best is None:
            continue
        print(f"  分解: {best.show()}")
        for r in alts:
            print(f"  短縮案: {r.word}({r.hyphen}、{r.length}文字)" + (f"  ! {' / '.join(r.warnings)}" if r.warnings else ""))
        if not alts:
            print("  短縮案なし(部品に短縮形がない)")
    return 0


def cmd_gen(args, c: K.Coiner, ctx) -> int:
    n, length, seed, min_vowels = 10, None, None, None
    it = iter(args)
    for a in it:
        if a == "--len":
            length = int(next(it))
        elif a == "--seed":
            seed = int(next(it))
        elif a == "--min-vowels":
            min_vowels = int(next(it))
        elif a.isdigit():
            n = int(a)
    words = c.generate(n, length, min_vowels, seed)
    print(f"新しい基本詞の候補({len(words)}個。音素の数 {'指定なし(重み付き)' if not length else length}):")
    for w in words:
        print(f"  {w}   ({len(c.lang.parse(w) or [])}音素)")
    f = c.lang.gen_filters
    print(f"\n注: 母音と子音を同じ確率で選び、母音が{f.get('min_vowels', 0)}個以上・子音が{f.get('min_consonants', 0)}個以上・"
          f"子音の連続が{f.get('max_consonant_run', '-')}個以下のものだけを残す(規則ファイルの word_generation.filters。最低限の条件)")
    return 0


def cmd_parts(args, c: K.Coiner, ctx) -> int:
    for p in c.parts:
        print(f"{p.form}\t{p.kind}\t{'/'.join(p.meanings)}\t{p.head if p.kind == K.SHORT else ''}")
    for a in c.affixes:
        print(f"{a.form}\t{K.AFFIX}\t{a.affix_kind}\t")
    return 0


def _opt(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return None


DECOMPOSE = "decompose"


def render_decompose(concept: str, els: list[K.Element], c: K.Coiner, note: str = "", per: int = 5,
                     seed: int | None = None, interpretation: str = "") -> None:
    if interpretation:
        print(f"LLM の解釈: {interpretation}")
        print("  (説明と違う意味に取っていたら、--description / --field / --distinguish で伝え直す)")
        print()
    names = [f"{e.form}({e.meaning})" if e.form else f"〈{e.meaning}〉" for e in els]
    missing = [e for e in els if not e.form]
    print(f"{concept} は、{','.join(names)} という{len(els)}要素に分解できる(大本の概念が先頭)。")
    print("そのうち、" + "、".join(f"「{e.meaning}」" for e in missing) + " は既存語にない。" if missing else "すべて既存語で表せる。")
    print()
    for i, e in enumerate(els, 1):
        print(f"  {i}. [{e.role}] {e.meaning}  → {e.form or '(未収録)'}  [{'既存' if e.form else '未収録'}]")
        if e.reason:
            print(f"       理由: {e.reason}")
        if e.fixed:
            print(f"       ! {e.fixed}")
    if note:
        print(f"\n分解についての補足(LLM): {note}")
    print()
    forms = [e.form for e in els if e.form]
    if len(forms) < 2:
        print("既存語の要素が1つ以下なので、つないだ形の検査は省く。")
    elif not missing:
        print("つないだ形の検査:")
        _show(c.check(forms), [e.part.describe() for e in els])
    else:
        print("既存語だけでつないだ部分の検査(未収録の要素は、新しい語ができてから足す):")
        _show(c.check(forms), [e.part.describe() for e in els if e.part])
    if missing:
        print("\n新しく作る候補の要素(基本詞にするか、別の言い方で既存語に寄せるかを決める)と、基本詞の候補:")
        for i, e in enumerate(missing):
            cands = c.generate(per, seed=None if seed is None else seed + i)
            print(f"  - {e.meaning}: " + "、".join(cands))
    print("\n注: 分解の仕方は LLM の提案で、ヒューリスティックなもの。要素と順序は人が決める。")


VALUE_OPTIONS = {
    "--response": "response", "--seed": "seed",
    "--description": "description", "--desc": "description",
    "--field": "field",
    "--distinguish": "distinguish", "--not": "distinguish",
    "--memo": "memo",
}


def parse_decompose_args(args: list[str]) -> tuple[K.ConceptRequest, dict, bool]:
    """(概念の依頼, そのほかの値, --prompt-only か)"""
    values, words, prompt_only = {}, [], False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--prompt-only":
            prompt_only = True
        elif a in VALUE_OPTIONS and i + 1 < len(args):
            values[VALUE_OPTIONS[a]] = args[i + 1]
            i += 1
        else:
            words.append(a)
        i += 1
    req = K.ConceptRequest(" ".join(words), values.get("description", ""), values.get("field", ""),
                           values.get("distinguish", ""), values.get("memo", ""))
    return req, values, prompt_only


def cmd_decompose(args, c: K.Coiner, ctx: Context) -> int:
    req, values, prompt_only = parse_decompose_args(args)
    resp, seed = values.get("response"), values.get("seed")
    if not req.concept:
        print("概念を指定する。例: conlang pute decompose 次数 --field グラフ理論 --description 頂点に接続する辺の数")
        return 2
    concept = req.concept
    prompt = K.build_decompose_prompt(c, req)
    prompt_only = prompt_only or "--prompt-only" in args
    if prompt_only:
        print(prompt)
        return 0
    model = "(貼り付けた答え)"
    if resp:
        text = Path(resp).read_text(encoding="utf-8-sig")
    else:
        cfg = llm.load_config()
        model = f"{cfg.model} @ {cfg.url}"
        print(f"LLM に問い合わせている: {model}")
        try:
            text = llm.chat(prompt, cfg, json_mode=True)
        except llm.LLMError as e:
            print(f"エラー: {e}")
            return 1
    if ctx.project is not None:
        saved = llm_log.save_call(ctx.project.llm_log_dir, DECOMPOSE, prompt, text, model=model, concept=concept,
                                  description=req.description, field=req.field, distinguish=req.distinguish,
                                  memo=req.memo)
        print(f"(履歴: {saved})")
    from .grammar_check import extract_json
    try:
        data = extract_json(text)
    except ValueError as err:
        print(f"LLM の答えを読めなかった: {err}\n--- 答え ---\n{text}")
        return 1
    render_decompose(data.get("concept", concept), K.ground(c, data), c, data.get("note", ""),
                     seed=int(seed) if seed else None, interpretation=str(data.get("interpretation", "") or ""))
    return 0


COMMANDS = dict(find=cmd_find, check=cmd_check, suggest=cmd_suggest, analyze=cmd_analyze, shorten=cmd_shorten,
                long=cmd_long, gen=cmd_gen, parts=cmd_parts, decompose=cmd_decompose)


def main(argv: list[str], ctx: Context) -> int:
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    if ctx.dictionary is None:
        print("辞書を --project DIR か --dict FILE で指定する")
        return 2
    c = K.Coiner(ctx.dictionary, ctx.rules)
    return COMMANDS[argv[0]](argv[1:], c, ctx) or 0
