"""アイコンとショートカット(Windows)、ショートカットから起動したときのエラーの扱い"""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PySide6")

from conlang.cli import main  # noqa: E402
from conlang.gui import icon, shortcut  # noqa: E402


def test_icon_draw_and_save(qtbot, tmp_path):
    img = icon.draw(64)
    assert (img.width(), img.height()) == (64, 64)
    assert img.pixelColor(32, 32).alpha() == 255 and img.pixelColor(0, 0).alpha() == 0  # 角は透明
    assert not icon.app_icon().isNull()
    p = icon.save_ico(tmp_path / "a" / "x.ico")
    assert p.exists() and p.read_bytes()[:4] == b"\x00\x00\x01\x00"  # ICO の先頭


def test_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut, "folders", lambda desktop=True, start_menu=True:
                        [tmp_path / "desk"] * desktop + [tmp_path / "menu"] * start_menu)
    items = shortcut.plan()
    assert [s.path for s in items] == [tmp_path / "desk" / "人工言語創作アプリ.lnk", tmp_path / "menu" / "人工言語創作アプリ.lnk"]
    assert items[0].target.name in ("conlang-gui.exe", "pythonw.exe")
    assert items[0].icon == shortcut.icon_path() and items[0].icon.suffix == ".ico"
    proj = tmp_path / "my project"
    proj.mkdir()
    one = shortcut.plan("ウリ語", proj, start_menu=False)
    assert len(one) == 1 and one[0].path.name == "ウリ語.lnk"
    assert str(proj.resolve()) in one[0].arguments and one[0].arguments.endswith('"')  # 空白を含むので引用符で囲む
    assert one[0].working_dir == proj.resolve()


@pytest.mark.skipif(os.name != "nt", reason="ショートカットは Windows だけ")
def test_create_shortcut(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(shortcut, "folders", lambda desktop=True, start_menu=True: [tmp_path / "デスクトップ"])
    assert main(["shortcut", "--name", "テスト用", "--no-start-menu"]) == 0
    lnk = tmp_path / "デスクトップ" / "テスト用.lnk"
    assert lnk.exists() and shortcut.icon_path().exists()
    assert "ショートカットを作った" in capsys.readouterr().out
    # 中身を Windows に読ませて確かめる
    ps = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n"
          f"$l=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); $l.TargetPath; $l.IconLocation")
    script = tmp_path / "read.ps1"
    script.write_text(ps, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    target, icon_loc = r.stdout.strip().splitlines()[:2]
    assert target.lower() == str(shortcut.gui_launcher()).lower()
    assert icon_loc.lower().startswith(str(shortcut.icon_path()).lower())


def test_cli_shortcut_needs_a_place(capsys):
    assert main(["shortcut", "--no-desktop", "--no-start-menu"]) == 2


def test_error_hook_logs_and_shows(qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from conlang.gui import app as gui_app
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append((self.text(), self.detailedText())))
    old = sys.excepthook
    try:
        gui_app._install_excepthook(QApplication.instance())
        try:
            raise ValueError("試しのエラー")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old
    assert "思わぬエラーが起きた: 試しのエラー" in shown[0][0] and "ValueError" in shown[0][1]
    log = gui_app.error_log_path().read_text(encoding="utf-8")
    assert "試しのエラー" in log
