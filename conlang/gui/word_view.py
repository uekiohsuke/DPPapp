"""項目の閲覧(HTML で表示する)"""
from __future__ import annotations

from html import escape

from conlang.core.zpdic import Dictionary

CSS = """
<style>
h1 { font-size: 20pt; margin: 0 0 4px 0; }
.id { color: #888; font-size: 9pt; }
.tag { background: #e8eef7; color: #335; padding: 1px 6px; margin-right: 4px; }
h3 { font-size: 11pt; margin: 12px 0 2px 0; color: #444; border-bottom: 1px solid #ccc; }
.title { color: #666; }
.empty { color: #999; }
</style>
"""


def _text(s: str) -> str:
    return escape(s).replace("\n", "<br>")


def render(w: dict, d: Dictionary, display=None) -> str:
    """display: 見出し語の表示を変える関数(ウリ語の現代の転写など)。変えたときは、辞書の綴りも併記する"""
    e = w["entry"]
    f = e.get("form", "")
    shown = display(f) if (display and f) else f
    out = [CSS, f"<h1>{escape(shown) or '<span class=empty>(見出し語なし)</span>'}</h1>"]
    if shown != f:
        out.append(f"<div class=id>辞書の綴り: {escape(f)}</div>")
    out.append(f"<div class=id>id {e.get('id')}</div>")
    tags = w.get("tags", [])
    if tags:
        out.append("<p>" + "".join(f"<span class=tag>{escape(t)}</span>" for t in tags) + "</p>")
    out.append("<h3>訳語</h3>")
    trs = w.get("translations", [])
    if not trs:
        out.append("<p class=empty>なし</p>")
    for t in trs:
        title = escape(t.get("title", "")) or "区分なし"
        out.append(f"<p><span class=title>【{title}】</span> {escape('、'.join(t.get('forms', [])))}</p>")
    for c in w.get("contents", []):
        out.append(f"<h3>{escape(c.get('title', '')) or '(見出しなし)'}</h3><p>{_text(c.get('text', ''))}</p>")
    vs = w.get("variations", [])
    if vs:
        out.append("<h3>変化形</h3>")
        for v in vs:
            out.append(f"<p><span class=title>{escape(v.get('title', ''))}</span>: {escape(v.get('form', ''))}</p>")
    rs = w.get("relations", [])
    if rs:
        out.append("<h3>関連語</h3>")
        for r in rs:
            target = r.get("entry") or {}
            link = escape(target.get("form", ""))
            if d.get(target.get("id")) is not None:
                link = f"<a href='word:{target.get('id')}'>{link}</a>"
            out.append(f"<p><span class=title>{escape(r.get('title', ''))}</span>: {link}</p>")
    return "\n".join(out)
