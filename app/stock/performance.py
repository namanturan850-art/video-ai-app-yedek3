"""Aggregate timings only: no prompts, URLs or keys in performance records."""
from functools import wraps
from time import monotonic


def timed(stage):
    def decorate(fn):
        @wraps(fn)
        def measured(self, *args, **kwargs):
            start = monotonic()
            try:
                return fn(self, *args, **kwargs)
            finally:
                progress = getattr(self, 'progress', None)
                if isinstance(progress, dict):
                    row = progress.setdefault('timings', {}).setdefault(stage, {'calls': 0, 'seconds': 0.})
                    row['calls'] += 1
                    row['seconds'] = round(row['seconds'] + monotonic() - start, 3)
        return measured
    return decorate


def update_wall(job, progress):
    # Keep only monotonic session clock in memory; resumed runs accumulate
    # active wall seconds, excluding time while the application was stopped.
    start = job.setdefault('_performance_start', monotonic())
    base = job.setdefault('_performance_base', progress.get('performance', {}).get('active_wall_seconds', 0.))
    progress['performance'] = {
        'active_wall_seconds': round(base + monotonic() - start, 3),
        'nested_stages': {'clip': 'judging'},
        'note': 'CLIP, judging süresinin içindedir. Aşama süreleri toplanmaz; aramalar paralel çalışabilir.'}
