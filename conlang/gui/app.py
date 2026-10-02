"""画面の起動: conlang gui [プロジェクトのフォルダ]"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from conlang.core.project import PROJECT_FILE

from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    app = QApplication.instance() or QApplication([sys.argv[0], *argv])
    app.setApplicationName("conlang")
    win = MainWindow()
    win.show()
    if argv:
        win.open_project(argv[0])
    else:
        last = win.settings.value("last_project", "") or ""
        if last and (Path(last) / PROJECT_FILE).exists():
            win.open_project(last)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
