"""Independent render pieces side by side (slot encodes, Remotion graphic chunks).

Each piece gets its own runner (own process, own temporary stderr file); the
first real failure stops the others and is the one reported.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_EXCEPTION
from threading import Lock


def run_parallel(count, job, workers, runner):
    """job(index, runner) for index in range(count); `runner` may be None / lack spawn() → one after another."""
    spawn = getattr(runner, 'spawn', None)
    if workers <= 1 or count <= 1 or spawn is None:
        return [job(i, runner) for i in range(count)]
    pieces, gate = [], Lock()

    def task(i):
        piece = spawn()
        with gate:
            pieces.append(piece)
        return job(i, piece)

    with ThreadPoolExecutor(max_workers=min(workers, count)) as pool:
        futures = [pool.submit(task, i) for i in range(count)]
        finished, _ = wait(futures, return_when=FIRST_EXCEPTION)
        failed = next((f for f in futures if f in finished and f.exception()), None)
        if failed:
            with gate:
                running = list(pieces)
            for piece in running:
                piece.cancel()
            for f in futures:
                f.cancel()
            wait(futures)
            raise failed.exception()
        wait(futures)
        return [f.result() for f in futures]
