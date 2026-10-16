"""Bounded search sharing. Results are copied: judges annotate their candidates."""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import RLock, BoundedSemaphore
from time import monotonic
import unicodedata

from app.stock.models import StockError


def canonical_query(query, provider):
    text = ' '.join(unicodedata.normalize('NFC', str(query)).split()).casefold()
    return text[:100] if provider in ('pixabay', 'magnific') else text


class SearchSession:
    def __init__(self, limit=512, ttl=86400):
        self.lock, self.entries = RLock(), OrderedDict()
        self.limit, self.ttl = limit, ttl
        self.hits = self.shared = self.misses = 0

    def call(self, key, operation):
        with self.lock:
            entry = self.entries.get(key)
            if entry and entry[0].done() and monotonic() - entry[1] >= self.ttl:
                self.entries.pop(key); entry = None
            if entry:
                future = entry[0]
                self.hits += 1
                if not future.done(): self.shared += 1
                self.entries.move_to_end(key)
                owner = False
            else:
                future = Future()
                self.entries[key] = (future, monotonic())
                self.misses += 1
                owner = True
        if owner:
            try:
                value = operation()
                future.set_result(deepcopy(value))
            except BaseException as error:
                future.set_exception(error)
                with self.lock: self.entries.pop(key, None)
            finally:
                with self.lock:
                    # Never evict an in-flight request. Completed entries only.
                    for old in list(self.entries):
                        if len(self.entries) <= self.limit: break
                        if self.entries[old][0].done(): self.entries.pop(old)
        value = deepcopy(future.result())
        if not owner and isinstance(value, tuple) and len(value) == 3:
            value = (value[0], value[1], True)
        return value


class ProviderGate:
    """Per-service provider limit and cooldown, including concurrent projects.

    A 429 is never immediately retried. Transient errors back off across
    subsequent calls; the director disables failed providers for this run.
    """
    def __init__(self):
        self.lock, self.gates, self.failures = RLock(), {}, {}

    def call(self, name, operation):
        with self.lock: gate = self.gates.setdefault(name, BoundedSemaphore(2))
        with gate:
            with self.lock:
                observed = self.failures.get(name)
                category, until, count = observed or ('', 0, 0)
            if monotonic() < until:
                raise StockError(category, 'Stok sağlayıcısı kısa süre bekletiliyor; tamamlanan seçimler korundu.')
            try:
                value = operation()
            except StockError as error:
                if error.category in ('rate_limit', 'timeout', 'connection_error', 'upstream_error', 'key_rejected', 'invalid_response'):
                    with self.lock:
                        previous = self.failures.get(name, ('', 0, 0))
                        count = previous[2] + 1
                        delay = getattr(error, 'retry_after', 60) if error.category == 'rate_limit' else min(60, 2 ** min(count, 6))
                        deadline = monotonic() + delay
                        # A parallel response must not shorten a Retry-After.
                        self.failures[name] = ((previous[0], previous[1], count) if previous[1] > deadline
                                               else (error.category, deadline, count))
                raise
            with self.lock:
                # Only clear the failure state this request actually observed.
                if self.failures.get(name) == observed: self.failures.pop(name, None)
            return value
