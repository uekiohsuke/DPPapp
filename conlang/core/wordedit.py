"""項目の編集。画面の入力欄と zpdic の項目を相互に変換する

画面は WordFields を表示・編集し、apply_fields() で項目に戻す。
知らないフィールドや、一覧の要素にある知らないキーは、そのまま残す。
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .zpdic import Dictionary


@dataclass
class WordFields:
    form: str = ""
    translations: list[tuple[str, str]] = field(default_factory=list)  # (区分, 訳語を区切り文字でつないだもの)
    tags: str = ""  # 区切り文字でつないだもの
    contents: list[tuple[str, str]] = field(default_factory=list)  # (見出し, 本文)
    variations: list[tuple[str, str]] = field(default_factory=list)  # (区分, 綴り)
    relations: list[tuple[str, str]] = field(default_factory=list)  # (区分, 関連先の見出し語)


def punctuations(d: Dictionary) -> list[str]:
    p = (d.data.get("zpdic") or {}).get("punctuations") or []
    return [x for x in p if x] or [","]


def separator(d: Dictionary) -> str:
    """つなぐときの区切り。読点が使えるなら読点、なければ最初の区切り文字"""
    p = punctuations(d)
    return "、" if "、" in p else p[0]


def split_list(text: str, puncts: list[str]) -> list[str]:
    pattern = "|".join(re.escape(p) for p in puncts)
    return [s.strip() for s in re.split(pattern, text) if s.strip()]


def to_fields(w: dict, d: Dictionary) -> WordFields:
    sep = separator(d)
    return WordFields(
        form=w["entry"].get("form", ""),
        translations=[(t.get("title", ""), sep.join(t.get("forms", []))) for t in w.get("translations", [])],
        tags=sep.join(w.get("tags", [])),
        contents=[(c.get("title", ""), c.get("text", "")) for c in w.get("contents", [])],
        variations=[(v.get("title", ""), v.get("form", "")) for v in w.get("variations", [])],
        relations=[(r.get("title", ""), (r.get("entry") or {}).get("form", "")) for r in w.get("relations", [])],
    )


def _rebuild(old: list, rows: list, make) -> list:
    """rows から一覧を作り直す。同じ位置の古い要素を土台にして、知らないキーを残す"""
    out = []
    for i, row in enumerate(rows):
        base = copy.deepcopy(old[i]) if i < len(old) and isinstance(old[i], dict) else {}
        out.append(make(base, row))
    return out


def apply_fields(w: dict, f: WordFields, d: Dictionary) -> tuple[dict, list[str]]:
    """f の内容を反映した新しい項目と、注意の一覧を返す。w は変えない"""
    puncts, sep = punctuations(d), separator(d)
    notes: list[str] = []
    orig = to_fields(w, d)
    new = copy.deepcopy(w)
    new.setdefault("entry", {})["form"] = f.form.strip()
    if f.form == orig.form:
        new["entry"]["form"] = w["entry"].get("form", "")

    def tr(base, row):
        title, text = row
        base["title"] = title.strip()
        old_forms = base.get("forms", [])
        # 表示と同じ文字列なら、元の訳語をそのまま使う(訳語に区切り文字が入っていても壊さない)
        base["forms"] = old_forms if sep.join(old_forms) == text else split_list(text, puncts)
        return base
    new["translations"] = _rebuild(w.get("translations", []), [r for r in f.translations if r[0].strip() or r[1].strip()], tr)

    old_tags = w.get("tags", [])
    new["tags"] = old_tags if sep.join(old_tags) == f.tags else split_list(f.tags, puncts)

    def ct(base, row):
        base["title"], base["text"] = row[0].strip(), row[1]
        return base
    new["contents"] = _rebuild(w.get("contents", []), [r for r in f.contents if r[0].strip() or r[1].strip()], ct)

    def va(base, row):
        base["title"], base["form"] = row[0].strip(), row[1].strip()
        return base
    new["variations"] = _rebuild(w.get("variations", []), [r for r in f.variations if r[0].strip() or r[1].strip()], va)

    def re_(base, row):
        title, target = row[0].strip(), row[1].strip()
        base["title"] = title
        hit = next((x for x in d.words if x["entry"].get("form") == target), None)
        if hit is None:
            notes.append(f"関連語 {target} は辞書にない(綴りだけ記録した)")
            base["entry"] = {"id": (base.get("entry") or {}).get("id", -1), "form": target}
        else:
            base["entry"] = {"id": hit["entry"].get("id"), "form": target}
        return base
    new["relations"] = _rebuild(w.get("relations", []), [r for r in f.relations if r[0].strip() or r[1].strip()], re_)

    # 触っていない欄は、元の項目のまま残す(空の欄なども消さない)
    for key in ("translations", "contents", "variations", "relations"):
        if getattr(f, key) == getattr(orig, key) and key in w:
            new[key] = copy.deepcopy(w[key])
            if key == "relations":
                notes.clear()
    return new, notes
