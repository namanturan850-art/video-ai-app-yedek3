"""Offline 900-second workload replay; NEVER a production latency estimate.

Run this same file with each checkout as the working directory, e.g.:
  python /absolute/path/to/benchmark_media_preparation.py
Only mocked providers/embedders and TemporaryDirectory files are used.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
from copy import deepcopy

sys.path.insert(0, str(Path.cwd()))
from app.stock.director_media import MediaDirector
from app.stock.models import make_slots
from app.integrations.openmontage import visual_engine as visual
import numpy as np


def replay():
    counts = {'search_reads': 0, 'provider_searches': 0, 'preview_reads': 0,
              'clip_evaluations': 0, 'image_model_batches': 0, 'text_model_batches': 0,
              'quality_validations': 0, 'selected_suitable': 0}
    cache = {}
    def search(pid, name, kind, query, page=1):
        counts['search_reads'] += 1
        key = (name, kind, query, page)
        if key in cache: return deepcopy(cache[key]), {'raw_count': 6}, True
        counts['provider_searches'] += 1; time.sleep(.002)
        values = [{'provider': name, 'media_type': kind, 'media_id': str(i)} for i in range(6)]
        cache[key] = values
        return deepcopy(values), {'raw_count': 6}, False
    service = SimpleNamespace(_cache_search=search, _checkpoint=lambda *a, **k: None)
    director = MediaDirector(service, {'project_id': 'synthetic', 'progress': {}})
    director.language = 'en'; director.providers = lambda scene=None: ['pixabay']
    def frames(media):
        counts['preview_reads'] += 1; time.sleep(.0001)
        return [{'source': {'data': 'synthetic-frame'}}]
    director._frames = frames
    # Baseline has frames() without the job-local wrapper. Replace its I/O
    # with the identical synthetic operation used under the new wrapper.
    if not hasattr(MediaDirector, '_frames'): director.frames = frames
    quality_cache = set()
    start = time.perf_counter()
    # The reported 280-slot job: 834 search invocations, 40 semantic queries
    # with case/whitespace variants. Every provider is fake.
    for i in range(834):
        q = f'ocean waves subject{chr(97 + (i % 40) // 26)}{chr(97 + (i % 40) % 26)}'
        if (i // 40) % 2: q = q.upper()
        if (i // 40) % 3: q = '  ' + q.replace(' ', '   ') + '  '
        director.search({'order': i % 280 + 1}, ['video'], q, {'searches': []})
    with tempfile.TemporaryDirectory(prefix='avs-benchmark-') as tmp:
        root = Path(tmp); weight = root/'weight'; weight.write_bytes(b'synthetic-model')
        version = hashlib.sha256(weight.read_bytes()).hexdigest()
        visual.model_status = lambda r: {'weight': weight, 'folder': root, 'version': version}
        lib, clip, torch = ModuleType('lib'), ModuleType('lib.clip_embedder'), ModuleType('torch')
        clip._MODEL = clip._PROCESSOR = None; clip._DEVICE = 'cpu'
        def text(values):
            counts['text_model_batches'] += 1; time.sleep(.0005)
            return np.array([[1., 0.] if str(v).startswith('ocean') else [0., 1.] for v in values], dtype=np.float32)
        def images(values):
            counts['image_model_batches'] += 1; time.sleep(.002)
            return np.array([[1., 0.] if b'ocean' in Path(v).read_bytes() else [0., 1.] for v in values], dtype=np.float32)
        clip.embed_texts, clip.embed_images = text, images
        torch.set_num_threads = lambda n: None
        sys.modules.update({'lib': lib, 'lib.clip_embedder': clip, 'torch': torch})
        lib.clip_embedder = clip
        visual._EMBEDDINGS.clear()
        for i in range(617):
            candidates = []
            for j in range(6):
                media = {'provider': 'pixabay', 'media_type': 'video', 'media_id': str(i % 40 * 6 + j)}
                director.frames(media)
                paths = []
                for frame in range(3):
                    path = root/f'{i % 40}-{j}-{frame}.jpg'
                    if not path.exists(): path.write_bytes(f'{"ocean" if j % 2 == 0 else "noise"} {i % 40} {j} {frame}'.encode())
                    paths.append(str(path))
                candidates.append({'key': str(j), 'frames': paths})
            results = visual.score_frames(root, {'descriptor': f'ocean waves context{i % 140}', 'candidates': candidates})
            counts['clip_evaluations'] += 1
            expected = [r['key'] for r in results['results'] if r['verdict'] == 'match' and r['score'] >= 7]
            if expected != ['0', '2', '4']: raise AssertionError('Synthetic matching quality changed')
            counts['selected_suitable'] += 1
        # Existing quality cache also memoizes the same segment; do not claim
        # the implementation reduced validations already deduplicated by main.
        for i in range(179):
            identity = (i % 61, 0.)
            if identity not in quality_cache:
                time.sleep(.0001); counts['quality_validations'] += 1; quality_cache.add(identity)
        visual._EMBEDDINGS.clear()
    elapsed = time.perf_counter() - start
    scene = {'scene_id': 's', 'start_estimate': 0., 'end_estimate': 30.,
             'narration_text': 'The ocean waves move toward the rocky shore. ' * 6,
             'primary_stock_query': 'ocean waves', 'alternative_stock_queries': ['rocky shore'],
             'visual_intent': 'ocean', 'preferred_media_type': 'stock_video', 'composition': 'wide'}
    import inspect
    adaptive = 'adaptive' in inspect.signature(make_slots).parameters
    slots = make_slots(scene, **({'adaptive': True} if adaptive else {}))
    return {'synthetic_video_seconds': 900, 'legacy_workload_slots': 280, 'search_invocations': 834,
            'unique_normalized_queries': 40, 'wall_seconds': round(elapsed, 4), **counts,
            'new_plan_slots_for_30_repeated_scenes': len(slots) * 30,
            'limitations': 'Fake provider (2 ms), fake embedding model (2 ms/batch), no real video/CLIP/API/render; quality is deterministic fixture agreement only.'}


if __name__ == '__main__': print(json.dumps(replay(), indent=2))
