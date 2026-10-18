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
    slot = slot or {}
    value = {'policy': 6, 'narration': scene.get('narration_text'), 'visual': scene.get('visual_intent'),
             'must': scene.get('must_show'), 'must_not': scene.get('must_not_show'),
             'entities': scene.get('entities'), 'goal': scene.get('visual_intent') if scene.get('_shot_bound') else slot.get('visual_goal'),
             'setting': slot.get('quality_setting'),
             'evaluator': slot.get('quality_evaluator')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def cache_key(media, fingerprint):
    meta = media.get('source_metadata') or {}
    revision = [media.get('sha256'), media.get('preview_url'), meta.get('preview_frames'),
                meta.get('sample_url'), media.get('duration')]
    version = hashlib.sha256(json.dumps(revision, sort_keys=True).encode()).hexdigest()[:16]
    return f'{media["provider"]}:{media["media_type"]}:{media["media_id"]}|{fingerprint}|{version}'


class VerdictCache:
    def __init__(self, folder):
        self.path = Path(folder) / 'ai_verdict_cache.json'
        self.data = None
        self.signature = None

    def _load(self, refresh=False):
        try:
            stat = self.path.stat(); signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        except OSError:
            signature = None
        if self.data is None or refresh or signature != self.signature:
            try: self.data = json.loads(self.path.read_text(encoding='utf-8'))
            except (OSError, ValueError): self.data = {}
            if not isinstance(self.data, dict): self.data = {}
            self.signature = signature
        return self.data

    def get(self, key):
        with _lock:
            value = self._load().get(key)
            return dict(value) if isinstance(value, dict) else None

    def put(self, entries):
        if not entries: return
        with _lock:
            # Other jobs may have saved since this instance was constructed.
            data = self._load(refresh=True)
            data.update(entries)
            while len(data) > MAX: data.pop(next(iter(data)))
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_name('.verdicts-' + uuid4().hex)
                temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, self.path)
            except OSError:
                pass
            finally:
                if 'temporary' in locals():
                    try:temporary.unlink(missing_ok=True)
                    except OSError:pass
