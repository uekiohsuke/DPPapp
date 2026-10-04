"""アプリのアイコン。画像ファイルを持たず、Qt で描く(ウィンドウ、タスクバー、ショートカットの .ico)"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = "#2f4f7f"
ACCENT = "#e8a33d"


_app = None


def _ensure_gui_app() -> None:
    """文字を描くには QGuiApplication が要る(CLI から呼ばれたときは、ここで作る)"""
    global _app
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        _app = QGuiApplication([])


def draw(size: int) -> QImage:
    """角の丸い四角に、辞書の「辞」と、造語のつなぎ目を表す線を描く"""
    _ensure_gui_app()
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    m = size * 0.04
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.2, size * 0.2)
    p.fillPath(path, QColor(BACKGROUND))
    # 下の帯(部品をつなぐハイフンの見立て)
    band = QRectF(rect.left() + size * 0.18, rect.bottom() - size * 0.2, rect.width() - size * 0.36, size * 0.07)
    bp = QPainterPath()
    bp.addRoundedRect(band, size * 0.035, size * 0.035)
    p.fillPath(bp, QColor(ACCENT))
    font = QFont("Yu Gothic UI")
    font.setPixelSize(int(size * 0.56))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(rect.left(), rect.top() - size * 0.06, rect.width(), rect.height()), Qt.AlignCenter, "辞")
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for s in SIZES:
        icon.addPixmap(QPixmap.fromImage(draw(s)))
    return icon


def save_ico(path: str | Path, size: int = 256) -> Path:
    """ショートカット用の .ico を書き出す"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not draw(size).save(str(path), "ICO"):
        raise OSError(f"アイコンを書き出せなかった: {path}")
    return path
