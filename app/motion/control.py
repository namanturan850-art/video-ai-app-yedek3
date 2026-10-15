"""Cooperative cancellation for both local graphics and their subprocesses."""
from contextvars import ContextVar
from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic

CANCELLED = ContextVar('motion_cancelled', default=lambda: False)


class MotionCancelled(RuntimeError):
    pass


def check():
    if CANCELLED.get()():raise MotionCancelled('Grafik hazırlığı durduruldu; tamamlanan dosyalar korundu.')


@contextmanager
def guard(process):
    done, cancelled = Event(), CANCELLED.get()
    started=monotonic()
    def watch():
        while not done.wait(.2):
            if cancelled() or monotonic()-started>600:
                if process.poll() is None:process.kill()
                return
    thread = Thread(target=watch, daemon=True, name='motion-cancel')
    thread.start()
    try:
        check()
        yield
    finally:
        done.set();thread.join(1)
        if process.poll() is None:process.kill()
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                try:stream.close()
                except OSError:pass
        check()


@contextmanager
def guard_runner(runner):
    done, cancelled = Event(), CANCELLED.get()
    def watch():
        while not done.wait(.2):
            if cancelled():runner.cancel();return
    thread=Thread(target=watch,daemon=True,name='motion-engine-cancel');thread.start()
    try:
        check();yield
    finally:
        done.set();thread.join(4);check()
