"""Job-local preview cache; includes failures, never stores source URLs on disk."""
from collections import OrderedDict
from copy import deepcopy


class PreviewCache:
    def __init__(self, max_bytes=32_000_000, max_entries=512):
        self.entries, self.bytes = OrderedDict(), 0
        self.max_bytes, self.max_entries = max_bytes, max_entries

    def get(self, key, fetch):
        if key in self.entries:
            self.entries.move_to_end(key)
            return deepcopy(self.entries[key][0]), True
        value = fetch()
        size = sum(len(b.get('source', {}).get('data', '')) for b in value)
        if size <= self.max_bytes:
            self.entries[key] = (deepcopy(value), size)
            self.bytes += size
            while self.bytes > self.max_bytes or len(self.entries) > self.max_entries:
                _, (_, old) = self.entries.popitem(last=False)
                self.bytes -= old
        return value, False
