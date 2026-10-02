"""時間のかかる処理(LLM の問い合わせなど)を、画面を止めずに裏で動かす

- run_task(fn, on_done, on_error): fn を別のスレッドで動かし、終わったら画面のスレッドで on_done(結果) を呼ぶ
- 中止(cancel)すると、結果を捨てる。HTTP の問い合わせそのものは止められないので、裏では終わるまで続く
- capture(fn): fn が print した内容を、そのスレッドの分だけ集める(ほかのスレッドの出力と混ざらない)
fn の中では、画面の部品に触らない。
"""
from __future__ import annotations

import io
import sys
import threading
import time
import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal


class _ThreadLocalStdout(io.TextIOBase):
    """sys.stdout の代わり。capture 中のスレッドの出力だけを、そのスレッドの入れ物に入れる"""

    def __init__(self, original):
        self.original = original
        self.local = threading.local()

    def write(self, s):
        buf = getattr(self.local, "buf", None)
        if buf is not None:
            return buf.write(s)
        if self.original is not None:
            return self.original.write(s)
        return len(s)

    def flush(self):
        if self.original is not None and getattr(self.local, "buf", None) is None:
            self.original.flush()


_lock = threading.Lock()


def _proxy() -> _ThreadLocalStdout:
    with _lock:
        if not isinstance(sys.stdout, _ThreadLocalStdout):
            sys.stdout = _ThreadLocalStdout(sys.stdout)
        return sys.stdout


def capture(fn: Callable, *args, **kwargs) -> tuple[object, str]:
    """(fn の戻り値, fn が print した内容)"""
    proxy = _proxy()
    buf = io.StringIO()
    proxy.local.buf = buf
    try:
        result = fn(*args, **kwargs)
    finally:
        proxy.local.buf = None
    return result, buf.getvalue()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Runnable(QRunnable):
    def __init__(self, fn, signals):
        super().__init__()
        self.fn, self.signals = fn, signals

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # 画面に出すので、ここで受け止める
            self.signals.failed.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
        else:
            self.signals.done.emit(result)


class Task:
    """裏で動いている処理1つ"""

    def __init__(self):
        self.cancelled = False
        self.finished = False
        self.started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def cancel(self) -> None:
        self.cancelled = True


_alive: set = set()  # 終わるまで、シグナルの入れ物を消さないように持っておく


def run_task(fn: Callable[[], object], on_done: Callable[[object], None],
             on_error: Callable[[str], None] | None = None) -> Task:
    task = Task()
    signals = _Signals()
    _alive.add(signals)

    def done(result):
        task.finished = True
        _alive.discard(signals)
        if not task.cancelled:
            on_done(result)

    def failed(msg):
        task.finished = True
        _alive.discard(signals)
        if not task.cancelled and on_error is not None:
            on_error(msg)

    signals.done.connect(done)
    signals.failed.connect(failed)
    QThreadPool.globalInstance().start(_Runnable(fn, signals))
    return task


class Ticker:
    """処理中、1秒ごとに経過時間を知らせる"""

    def __init__(self, parent, callback: Callable[[float], None]):
        self.timer = QTimer(parent)
        self.timer.setInterval(1000)
        self.callback = callback
        self.task: Task | None = None
        self.timer.timeout.connect(self._tick)

    def start(self, task: Task) -> None:
        self.task = task
        self.callback(0.0)
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()
        self.task = None

    def _tick(self):
        if self.task is not None:
            self.callback(self.task.elapsed)
