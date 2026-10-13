"""Local picture check for Medyayı Tamamla: the CLIP model that
INSTALL_OPENMONTAGE_SEMANTIC.bat installs (openai/clip-vit-base-patch32, in
the separate OpenMontage environment) compares each stock candidate's
start/middle/end preview frames with an English description of the
sentence (+ the owner's [GÖRSEL] note). No internet, no AI quota.

score() returns per candidate key {'verdict': match|mismatch|uncertain,
'score': 0-10, 'similarity', 'contrast_margin'[, 'conflict']}; {} when the
model is not installed or fails (the job then goes on with the other checks).
`penalties` (app/stock/setting.py) are things that contradict the video's
period/place; a candidate that resembles one more than its own description
comes back as a mismatch with 'conflict': {'kind', 'label', …}."""
from io import BytesIO
import logging
import inspect
import shutil
from uuid import uuid4

LOG = logging.getLogger('uvicorn.error.stock')
MISSING = 'Daha doğru seçim için INSTALL_OPENMONTAGE_SEMANTIC.bat ile yerel modeli kurun (yerel görüntü modeli CLIP kurulu değil; medya etiket/kelime eşleşmesiyle seçildi).'
BATCH = 24  # candidates per model load


class ClipCheck:
    def __init__(self, service):
        self.service, self.broken = service, False
        self.fake = getattr(service, 'clip_scorer', None)  # tests: callable(descriptor, [(key, [jpeg bytes])]) → {key: result}
        self.bridge = getattr(service, 'openmontage', None)

    def ready(self):
        if self.broken: return False
        if self.fake is not None: return True
        try:
            return bool(self.bridge and self.bridge.status().get('semantic_ready'))
        except Exception:
            return False

    def score(self, descriptor, items, folder, penalties=()):
        if not items or not self.ready(): return {}
        if self.fake is not None:
            try:
                takes = 'penalties' in inspect.signature(self.fake).parameters
                return dict(self.fake(descriptor, items, penalties=list(penalties)) if takes else self.fake(descriptor, items))
            except Exception: self.broken = True; return {}
        out = {}
        for start in range(0, len(items), BATCH):
            work = folder / ('.clip-' + uuid4().hex)
            try:
                work.mkdir(parents=True)
                candidates = []
                for number, (key, frames) in enumerate(items[start:start + BATCH]):
                    paths = []
                    for index, data in enumerate(frames[:3]):
                        path = work / f'c{number}-f{index}.jpg'
                        path.write_bytes(jpeg(data)); paths.append(str(path.resolve()))
                    if paths: candidates.append({'key': key, 'frames': paths})
                if not candidates: continue
                result = self.bridge.call('frames', {'descriptor': descriptor[:300], 'candidates': candidates, 'penalties': list(penalties)[:40]}, work)
                for item in result.get('results', []):
                    if item.get('verdict') in ('match', 'mismatch', 'uncertain') and isinstance(item.get('score'), int):
                        out[item['key']] = {k: item[k] for k in ('verdict', 'score', 'similarity', 'contrast_margin', 'conflict', 'setting_margin', 'setting_closest') if k in item}
            except Exception as error:  # the model failed: this job goes on without it
                LOG.warning('stock operation=clip_frames category=failed exception_class=%s', type(error).__name__)
                self.broken = True
                return out
            finally:
                shutil.rmtree(work, ignore_errors=True)
        return out


def jpeg(data):
    """Any preview picture as a ≤512 px JPEG file body."""
    try:
        from PIL import Image
        image = Image.open(BytesIO(data)).convert('RGB')
        if image.width > 512: image = image.resize((512, max(1, round(image.height * 512 / image.width))))
        out = BytesIO(); image.save(out, 'JPEG', quality=85)
        return out.getvalue()
    except Exception:
        return data
