"""編集前の自動バックアップ"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_file(path: str | Path, backup_dir: str | Path) -> Path | None:
    """path を backup_dir に `名前-日時.拡張子` で複製する。path がなければ何もしない"""
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = backup_dir / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def list_backups(backup_dir: str | Path, stem: str) -> list[Path]:
    """古い順"""
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob(f"{stem}-*"))
