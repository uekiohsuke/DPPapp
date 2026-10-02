"""言語プロジェクト(1つの言語のデータ一式)

    言語プロジェクト/
      project.json        言語名、版、作成日、言語別機能の id
      rules.yaml          規則設定(YAML)
      dictionary.json     zpdic 形式の辞書
      grammar/            章ごとの Markdown
      examples.json       例文
      llm_log/            LLM 呼び出しの履歴
      backup/             編集前の自動バックアップ
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .backup import backup_file
from .rules import Rules
from .zpdic import Dictionary

PROJECT_FILE = "project.json"
DICTIONARY_FILE = "dictionary.json"
RULES_FILE = "rules.yaml"
SUBDIRS = ("grammar", "llm_log", "backup")


class ProjectError(Exception):
    pass


@dataclass
class Project:
    root: Path
    meta: dict

    # --- 作成・読み込み ---

    @classmethod
    def create(cls, root: str | Path, name: str, language: str | None = None) -> "Project":
        root = Path(root)
        if (root / PROJECT_FILE).exists():
            raise ProjectError(f"すでにプロジェクトがある: {root}")
        root.mkdir(parents=True, exist_ok=True)
        for d in SUBDIRS:
            (root / d).mkdir(exist_ok=True)
        meta = {"name": name, "language": language, "version": 1, "created": date.today().isoformat()}
        p = cls(root, meta)
        p._write_json(PROJECT_FILE, meta)
        if not (root / "examples.json").exists():
            p._write_json("examples.json", [])
        if not p.dictionary_path.exists():
            Dictionary.new().save(p.dictionary_path)
        return p

    @classmethod
    def open(cls, root: str | Path) -> "Project":
        root = Path(root)
        f = root / PROJECT_FILE
        if not f.exists():
            raise ProjectError(f"プロジェクトではない({PROJECT_FILE} がない): {root}")
        return cls(root, json.loads(f.read_text(encoding="utf-8")))

    def _write_json(self, name: str, obj) -> None:
        (self.root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- 場所 ---

    @property
    def name(self) -> str:
        return self.meta.get("name", "")

    @property
    def language(self) -> str | None:
        return self.meta.get("language")

    @property
    def dictionary_path(self) -> Path:
        return self.root / DICTIONARY_FILE

    @property
    def backup_dir(self) -> Path:
        return self.root / "backup"

    @property
    def rules_path(self) -> Path:
        return self.root / RULES_FILE

    # --- 規則 ---

    def import_rules(self, source: str | Path) -> Path | None:
        """規則ファイルをプロジェクトの rules.yaml としてコピーする。元のファイルには触れない。
        今の規則はバックアップしてから置き換える。戻り値はバックアップのパス"""
        source = Path(source)
        Rules.load(source)  # 読めることを先に確かめる
        if self.rules_path.exists() and source.resolve() == self.rules_path.resolve():
            raise ProjectError("取り込み元とプロジェクトの規則が同じファイル")
        bak = backup_file(self.rules_path, self.backup_dir)
        shutil.copyfile(source, self.rules_path)
        return bak

    def load_rules(self) -> Rules | None:
        """規則ファイルがなければ None"""
        return Rules.load(self.rules_path) if self.rules_path.exists() else None

    # --- 辞書 ---

    def import_dictionary(self, source: str | Path) -> Path | None:
        """zpdic 形式の辞書を、プロジェクトの辞書としてコピーする。元のファイルには触れない。
        今の辞書はバックアップしてから置き換える。戻り値はバックアップのパス"""
        source = Path(source)
        Dictionary.load(source)  # 読めることを先に確かめる
        if source.resolve() == self.dictionary_path.resolve():
            raise ProjectError("取り込み元とプロジェクトの辞書が同じファイル")
        bak = backup_file(self.dictionary_path, self.backup_dir)
        shutil.copyfile(source, self.dictionary_path)
        return bak

    def load_dictionary(self) -> Dictionary:
        return Dictionary.load(self.dictionary_path)

    def save_dictionary(self, d: Dictionary) -> Path | None:
        """保存の直前に、今の辞書をバックアップする。戻り値はバックアップのパス"""
        bak = backup_file(self.dictionary_path, self.backup_dir)
        d.save(self.dictionary_path)
        return bak
