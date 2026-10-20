"""Bounded, job-independent CLIP worker. No HTTP and no credentials in IPC."""
import json
import queue
import subprocess
import threading


class FramesError(ValueError):
    """The CLIP side process failed. `reason` is a short code; `detail` is the
    real technical cause (exception class, message, exit code) that only goes
    to the diagnostics file, never into a prompt or a request."""

    def __init__(self, reason, detail=''):
        super().__init__(reason)
        self.reason = reason
        self.detail = ' '.join(str(detail).split())[:360]


class FramesProcess:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.signature = None
        self.closed = threading.Event()

    def _stop(self):
        child, self.process = self.process, None
        if child is None:
            return
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=3)
        for stream in (child.stdin, child.stdout):
            if stream: stream.close()

    def close(self):
        self.closed.set()
        # Wake an inference waiting on its reply; do not wait for the 120 s
        # request deadline merely to acquire the request serialization lock.
        child=self.process
        if child and child.poll() is None:
            try:child.terminate()
            except OSError:pass
        with self.lock:
            self._stop()

    def _exit_code(self):
        child = self.process
        if child is None:
            return None
        try: return child.wait(timeout=2)
        except subprocess.TimeoutExpired: return child.poll()

    def call(self, args, cwd, env, inputs, timeout=120):
        with self.lock:
            if self.closed.is_set():raise FramesError('semantic_worker_closed')
            signature = (tuple(args), str(cwd))
            if self.process is None or self.process.poll() is not None or self.signature != signature:
                self._stop()
                try:
                    child = subprocess.Popen(args, cwd=cwd, env=env, shell=False, stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             text=True, encoding='utf-8', bufsize=1)
                except OSError as error:
                    raise FramesError('semantic_worker_start_failed', f'{type(error).__name__}: {error}') from None
                self.process, self.signature = child, signature
                replies = queue.Queue(maxsize=1)
                self.replies = replies
                def read():
                    try:
                        while True:
                            line=child.stdout.readline(2_000_001)
                            if not line:break
                            if len(line) > 2_000_000: break
                            replies.put(line)
                    except (OSError, ValueError):
                        pass
                    finally:
                        try: replies.put_nowait(None)
                        except queue.Full: pass
                threading.Thread(target=read, daemon=True, name='clip-replies').start()
            try:
                if self.closed.is_set():raise FramesError('semantic_worker_closed')
                self.process.stdin.write(json.dumps(inputs) + '\n')
                self.process.stdin.flush()
                line = self.replies.get(timeout=timeout)
                if line is None:
                    code = self._exit_code()
                    raise FramesError('semantic_worker_stopped', f'Yan program kapandı (çıkış kodu: {code})')
                result = json.loads(line)
                if not isinstance(result, dict) or result.get('success') is not True:
                    cause = result if isinstance(result, dict) else {}
                    raise FramesError('semantic_worker_failed', f"{cause.get('error_class', '')}: {cause.get('detail', '')}".strip(': '))
                return result
            except FramesError:
                self._stop()
                raise
            except queue.Empty:
                self._stop()
                raise FramesError('semantic_worker_timeout', f'{timeout} sn içinde yanıt gelmedi') from None
            except (OSError, ValueError) as error:
                self._stop()
                raise FramesError('semantic_worker_failed', f'{type(error).__name__}: {error}') from None
