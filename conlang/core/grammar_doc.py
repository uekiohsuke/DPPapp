"""文法文書(Markdown)の読み取り。言語に依存しない(仕様書 4.5)

- 見出しの一覧(目次)
- 状態タグ(【決定】【仮】【メモ】【辞書】など)の数と、タグの付いた行
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# 状態タグ。仕様書の凡例と文法文書で使われているもの
TAGS = ("決定", "仮", "メモ", "辞書", "保留", "要確認", "アイデア")
TAG_RE = re.compile(r"【(" + "|".join(TAGS) + r")】")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    line: int  # 0 から数えた行番号


@dataclass(frozen=True)
class TaggedLine:
    tag: str
    line: int
    text: str
    section: str  # その行が入っている、いちばん近い見出し


def headings(text: str) -> list[Heading]:
    """見出しの一覧(コードブロックの中は除く)"""
    out, in_code = [], False
    for i, line in enumerate(text.splitlines()):
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING_RE.match(line)
        if m:
            out.append(Heading(len(m.group(1)), m.group(2).strip(), i))
    return out


def tag_counts(text: str) -> Counter:
    return Counter(TAG_RE.findall(text))


def tagged_lines(text: str, tag: str | None = None) -> list[TaggedLine]:
    """状態タグの付いた行(tag を指定すると、そのタグだけ)"""
    out, section = [], ""
    hs = {h.line: h.title for h in headings(text)}
    for i, line in enumerate(text.splitlines()):
        if i in hs:
            section = hs[i]
        for t in TAG_RE.findall(line):
            if tag is None or t == tag:
                out.append(TaggedLine(t, i, line.strip(), section))
    return out
