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
