"""画面の起動: conlang gui [プロジェクトのフォルダ]、または conlang-gui.exe(ショートカットから)

ショートカットから起動するとコンソールがないので、思わぬエラーは画面に出し、
%APPDATA%\\conlang\\error.log にも残す。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from conlang.core.llm import config_dir
from conlang.core.project import PROJECT_FILE

from .icon import app_icon
from .main_window import APP_TITLE, MainWindow
from .shortcut import APP_ID


def error_log_path() -> Path:
    return config_dir() / "error.log"


def _set_app_id() -> None:
    """タスクバーで、python ではなくこのアプリとしてまとめ、アイコンを出す(Windows)"""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass


def _install_excepthook(app: QApplication) -> None:
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            path = error_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{text}\n")
        except OSError:
            path = None
        if sys.stderr is not None:
            sys.stderr.write(text)
        box = QMessageBox(QMessageBox.Warning, APP_TITLE,
                          f"思わぬエラーが起きた: {exc}\n" + (f"詳しくは {path} に残した" if path else ""))
        box.setDetailedText(text)
        box.exec()

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    _set_app_id()
    app = QApplication.instance() or QApplication([sys.argv[0], *argv])
    app.setApplicationName("conlang")
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(app_icon())
    _install_excepthook(app)
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
