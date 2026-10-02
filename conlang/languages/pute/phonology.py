"""ピュテ語の音素の分割と、部品のつなぎ方(規則ファイルから読んだ値を引数で受ける)"""
from __future__ import annotations


def parse_count(s: str, phonemes: list[str]) -> int:
    """s を音素に分ける方法の数(0 なら分けられない)"""
    count = [0] * (len(s) + 1)
    count[0] = 1
    for i in range(len(s)):
        if count[i]:
            for p in phonemes:
                if s.startswith(p, i):
                    count[i + len(p)] += count[i]
    return count[len(s)]


def parse(s: str, phonemes: list[str]) -> list[str] | None:
    """最長一致で音素に分ける。分けられなければ None。phonemes は長い順に並べておく"""
    out, i = [], 0
    while i < len(s):
        for p in phonemes:
            if s.startswith(p, i):
                out.append(p)
                i += len(p)
                break
        else:
            return None
    return out


def join(segments: list[str], merge: list[bool], vowels: list[str], phonemes: list[str]) -> str:
    """部品をつなぐ。merge[i] が真の境目(segments[i] と segments[i+1] のあいだ)で、
    前の語末と次の語頭が同じ母音なら1つにまとめる(文法 2.5。wo を含む)"""
    s = segments[0] if segments else ""
    for i, f in enumerate(segments[1:]):
        a, b = parse(s, phonemes), parse(f, phonemes)
        if merge[i] and a and b and a[-1] in vowels and a[-1] == b[0]:
            s += f[len(b[0]):]
        else:
            s += f
    return s


def readable_as(s: str, lexicon: set[str]) -> bool:
    """s を lexicon の語の連なりとして読めるか"""
    ok = [False] * (len(s) + 1)
    ok[0] = True
    lens = sorted({len(w) for w in lexicon if w})
    for i in range(len(s)):
        if ok[i]:
            for n in lens:
                if i + n <= len(s) and s[i:i + n] in lexicon:
                    ok[i + n] = True
    return ok[len(s)]
