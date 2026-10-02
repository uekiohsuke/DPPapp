"""規則設定(YAML)の読み込み。言語に依存しない

規則の中身(音素、接辞、活用など)の意味づけは、言語別機能がする。
土台は、ファイルを読むことと、各規則の状態(status)の一覧を作ることだけをする。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# 「決定」以外を、確認が要るものとして一覧にする
SETTLED = "決定"


class RulesError(ValueError):
    """規則ファイルとして読めない"""


@dataclass(frozen=True)
class RuleStatus:
    path: str          # 例: compounding.vowel_merge、checks[3]
    status: str
    ref: str | None = None
    note: str | None = None
    id: str | None = None


@dataclass
class Rules:
    data: dict
    path: Path | None = None

    @classmethod
    def from_text(cls, text: str, path: Path | None = None) -> "Rules":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise RulesError(f"YAML として読めない: {e}") from e
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise RulesError("規則ファイルの一番上は、キーと値の組(マッピング)にする")
        return cls(data, path)

    @classmethod
    def load(cls, path: str | os.PathLike) -> "Rules":
        path = Path(path)
        return cls.from_text(path.read_text(encoding="utf-8-sig"), path)

    @property
    def language(self) -> str:
        return str(self.data.get("language", ""))

    def get(self, *keys, default=None):
        """rules.get("phonology", "vowels") のように、入れ子をたどる"""
        cur = self.data
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def statuses(self) -> list[RuleStatus]:
        """status を持つ規則を、ファイルに出てくる順に一覧にする"""
        out: list[RuleStatus] = []

        def walk(node, path):
            if isinstance(node, dict):
                if "status" in node:
                    out.append(RuleStatus(path, str(node["status"]), _opt(node.get("ref")),
                                          _opt(node.get("note")), _opt(node.get("id"))))
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else str(k))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        walk(self.data, "")
        return out

    def unsettled(self) -> list[RuleStatus]:
        """「決定」以外の規則(仮、メモ、未確認 など)"""
        return [s for s in self.statuses() if s.status != SETTLED]


def _opt(v):
    return None if v is None else str(v)
