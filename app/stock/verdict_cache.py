"""AI verdicts shared across projects: the same stock clip judged for the same
kind of shot is not sent to the AI again (fewer requests, less quota).

Key: provider/media id + a fingerprint of what the shot must show (scene
visual goal, MUST show / MUST NOT). Stored next to the projects folder as
one small JSON file; at most MAX entries (oldest dropped). Never raises."""
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from uuid import uuid4

MAX = 20000
_lock = threading.Lock()


def context(scene, slot=None):
    text = ' '.join(str(x or '') for x in ((slot or {}).get('visual_goal'), scene.get('visual_intent'), scene.get('must_show'), scene.get('must_not_show')))
    words = sorted(set(re.findall(r'[a-z0-9äöüß]+', text.casefold())))
    return hashlib.sha256(' '.join(words).encode()).hexdigest()[:16]


def cache_key(media, fingerprint):
    return f'{media["provider"]}:{media["media_type"]}:{media["media_id"]}|{fingerprint}'


class VerdictCache:
    def __init__(self, folder):
        self.path = Path(folder) / 'ai_verdict_cache.json'
        self.data = None

    def _load(self):
        if self.data is None:
            try: self.data = json.loads(self.path.read_text(encoding='utf-8'))
            except (OSError, ValueError): self.data = {}
            if not isinstance(self.data, dict): self.data = {}
        return self.data

    def get(self, key):
        with _lock:
            value = self._load().get(key)
            return dict(value) if isinstance(value, dict) else None

    def put(self, entries):
        if not entries: return
        with _lock:
            data = self._load()
            data.update(entries)
            while len(data) > MAX: data.pop(next(iter(data)))
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_name('.verdicts-' + uuid4().hex)
                temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, self.path)
            except OSError:
                pass
