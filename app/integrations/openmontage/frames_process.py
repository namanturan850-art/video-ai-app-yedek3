"""Bounded, job-independent CLIP worker. No HTTP and no credentials in IPC."""
import json
import queue
import subprocess
import threading


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

    def call(self, args, cwd, env, inputs, timeout=120):
        with self.lock:
            if self.closed.is_set():raise ValueError('semantic_worker_closed')
            signature = (tuple(args), str(cwd))
            if self.process is None or self.process.poll() is not None or self.signature != signature:
                self._stop()
                child = subprocess.Popen(args, cwd=cwd, env=env, shell=False, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True, encoding='utf-8', bufsize=1)
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
                if self.closed.is_set():raise ValueError('semantic_worker_closed')
                self.process.stdin.write(json.dumps(inputs) + '\n')
                self.process.stdin.flush()
                line = self.replies.get(timeout=timeout)
                if line is None: raise ValueError('semantic_worker_stopped')
                result = json.loads(line)
                if not isinstance(result, dict) or result.get('success') is not True:
                    raise ValueError('semantic_worker_failed')
                return result
            except (OSError, ValueError, queue.Empty):
                self._stop()
                raise ValueError('semantic_worker_failed') from None
