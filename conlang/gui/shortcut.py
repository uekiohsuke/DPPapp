"""Windows のショートカット(.lnk)を作る。アイコンから、コンソールを出さずに画面を起動するため

ショートカットは venv の conlang-gui.exe(pyproject の gui-scripts。コンソールを出さない)を指す。
引数でプロジェクトのフォルダを渡すと、そのプロジェクトを開く(省くと、前に開いたプロジェクト)。
.lnk は Windows の WScript.Shell(PowerShell 経由)で作る。
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from conlang.core.llm import config_dir

APP_NAME = "人工言語創作アプリ"
APP_ID = "conlang.desktop.app"  # タスクバーで、python ではなくこのアプリとしてまとめるための ID


@dataclass
class Shortcut:
    path: Path
    target: Path
    arguments: str
    working_dir: Path
    icon: Path


def gui_launcher() -> Path:
    """venv の conlang-gui.exe(なければ pythonw.exe -m conlang.gui.app)"""
    scripts = Path(sys.executable).parent
    exe = scripts / "conlang-gui.exe"
    if exe.exists():
        return exe
    return scripts / "pythonw.exe"


def icon_path() -> Path:
    return config_dir() / "conlang.ico"


def folders(desktop: bool = True, start_menu: bool = True) -> list[Path]:
    out = []
    if desktop:
        out.append(Path(os.path.expanduser("~")) / "Desktop")
        one = os.environ.get("OneDrive")
        if one and (Path(one) / "Desktop").is_dir() and not out[0].is_dir():
            out[0] = Path(one) / "Desktop"
    if start_menu and os.environ.get("APPDATA"):
        out.append(Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return out


def plan(name: str = APP_NAME, project: str | Path | None = None, desktop: bool = True,
         start_menu: bool = True) -> list[Shortcut]:
    """作るショートカットの中身(まだ作らない)"""
    target = gui_launcher()
    args = []
    if target.name.lower() == "pythonw.exe":
        args += ["-m", "conlang.gui.app"]
    if project:
        args.append(str(Path(project).resolve()))
    arguments = " ".join(f'"{a}"' if " " in a else a for a in args)
    work = Path(project).resolve() if project else Path(__file__).resolve().parents[2]
    return [Shortcut(folder / f"{name}.lnk", target, arguments, work, icon_path()) for folder in folders(desktop, start_menu)]


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create(shortcuts: list[Shortcut]) -> list[Path]:
    """アイコンを書き出し、ショートカットを作る(同じ名前があれば上書き)"""
    if os.name != "nt":
        raise OSError("ショートカットは Windows でだけ作れる")
    from .icon import save_ico
    if shortcuts:
        save_ico(shortcuts[0].icon)
    lines = ["$ws = New-Object -ComObject WScript.Shell"]
    for s in shortcuts:
        s.path.parent.mkdir(parents=True, exist_ok=True)
        lines += [
            f"$l = $ws.CreateShortcut({_ps_quote(s.path)})",
            f"$l.TargetPath = {_ps_quote(s.target)}",
            f"$l.Arguments = {_ps_quote(s.arguments)}",
            f"$l.WorkingDirectory = {_ps_quote(s.working_dir)}",
            f"$l.IconLocation = {_ps_quote(str(s.icon) + ',0')}",
            f"$l.Description = {_ps_quote(APP_NAME)}",
            "$l.Save()",
        ]
    # 日本語のパスが化けないように、BOM 付き UTF-8 のスクリプトにして実行する(Windows PowerShell 5.1 向け)
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
        script = f.name
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-File", script], capture_output=True, text=True, errors="replace")
    finally:
        os.unlink(script)
    if r.returncode != 0:
        raise OSError(f"ショートカットを作れなかった: {r.stderr.strip()}")
    return [s.path for s in shortcuts]
