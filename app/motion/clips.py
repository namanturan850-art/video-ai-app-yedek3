"""Motion clips as ordinary project media (MP4 in the stock folder).

OpenMontage (Remotion) renders first when it is installed and ready; any
failure or absence falls back to the local Pillow + FFmpeg renderer, which
needs no external service and does not fail on missing fonts. The same scene
(app/motion/templates.py) drives both, and clips are cached by content.
"""
import hashlib
import json
import logging
import shutil
import wave
from threading import RLock
from functools import wraps
from pathlib import Path
from uuid import uuid4

from app.motion import layouts, templates
from app.motion.raster import render as raster_render
from app.projects import linked, now

LOG = logging.getLogger('uvicorn.error.motion')
ENGINE_VERSION = 'motion-v6'  # animated safe-area guard + distinct route layouts; v5 files are not reused


def scene_key(scene):
    return hashlib.sha256((ENGINE_VERSION + json.dumps(scene, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:32]


def for_remotion(scene, public):
    """Remotion props: fonts copied next to the composition, counter texts
    precomputed per frame (identical to the local renderer), land polygons."""
    scene = json.loads(json.dumps(scene))
    families = {}
    for element in scene['elements']:
        file = element['props'].get('font')
        if file and file not in families and (templates.FONT_DIR / file).is_file():
            shutil.copyfile(templates.FONT_DIR / file, public / file)
            families[file] = 'AVS' + Path(file).stem.replace('-', '')
        if element['type'] == 'counter':
            frames = max(1, round(scene['duration'] * scene['fps']))
            p = element['props']
            element['texts'] = [templates.counter_text(p['target'], templates.value_at(element['tracks']['value'], i / scene['fps'], scene['ease']),
                                                       p.get('language', 'de'), p.get('from_year', False)) for i in range(frames)]
    scene['font_families'] = families
    boxes = [templates.map_box(e['props']) for e in scene['elements'] if e['type'] == 'map']
    if boxes:  # only the coastlines near the views: small props, fast SVG
        scene['land'] = templates.land((min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)))
    return scene


def silent_wav(path, seconds):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * int(16000 * seconds))


def openmontage(scene, output, bridge, ffmpeg, folder):
    status = bridge.status()
    if not status.get('ready'):
        raise RuntimeError('openmontage_unavailable')
    root = bridge.root(); parent = root / 'remotion-composer' / 'projects'
    if linked(parent) or not parent.resolve().is_relative_to(root):
        raise RuntimeError('openmontage_path')
    parent.mkdir(exist_ok=True)
    staging = parent / ('avs-motion-' + uuid4().hex); staging.mkdir()
    public = folder / ('om-motion-' + uuid4().hex); public.mkdir()
    try:
        props = for_remotion(scene, public)
        (staging / 'props.json').write_text(json.dumps(props, ensure_ascii=False), encoding='utf-8')
        entry = staging / 'index.tsx'; shutil.copyfile(Path(__file__).with_name('motion.tsx'), entry)
        audio = public / 'silence.wav'; silent_wav(audio, scene['duration'])
        raw = public / 'motion-raw.mp4'
        from app.rendering.runner import ProcessRunner
        from app.motion.control import guard_runner
        runner=ProcessRunner()
        with guard_runner(runner):
            bridge.call('compose', {'operation': 'render', 'output_path': str(raw), 'audio_path': str(audio),
                                'edit_decisions': {'render_runtime': 'remotion', 'composition_mode': 'atelier', 'renderer_family': 'bespoke',
                                                   'bespoke': {'entry': str(entry), 'composition_id': 'AVSMotion', 'props_path': str(staging / 'props.json'),
                                                               'public_dir': str(public), 'crf': 18, 'concurrency': 1}}}, folder, runner=runner)
        if not raw.is_file():
            raise RuntimeError('openmontage_output')
        frames = max(1, round(scene['duration'] * templates.FPS))
        # Same delivery format as the local renderer: exact frames, no audio.
        with guard_runner(runner):
            runner.run([ffmpeg, '-v', 'error', '-y', '-i', str(raw), '-an', '-vf', 'fps=30,scale=1920:1080,setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=1',
                        '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-movflags', '+faststart',
                        '-progress', 'pipe:1', '-nostats', str(output)], folder)
    finally:
        if not linked(staging): shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(public, ignore_errors=True)


def with_pictures(spec, folder):
    """İŞARETLE / ÖNCESONRA: the spec keeps picture file names (project stock
    folder); drawing needs their full paths. Other templates are unchanged."""
    if spec['template'] not in ('mark', 'beforeafter', 'archive'): return spec
    spec = {**spec, 'data': {**spec['data']}}
    names = [spec['data'].get('image')] if spec['template'] in ('mark', 'archive') else list(spec['data'].get('images') or [])
    paths = [Path(folder) / Path(str(n)).name for n in names if n]
    if not paths or not all(p.is_file() and not linked(p) for p in paths): raise RuntimeError('picture_missing')
    if spec['template'] in ('mark', 'archive'): spec['data']['image_path'] = str(paths[0])
    else: spec['data']['image_paths'] = [str(p) for p in paths]
    return spec


# Fixed stripes bound synchronization memory. Only identical content/folder
# must share a lock; selection and checkpoints remain on their job thread.
_RENDER_LOCKS = [RLock() for _ in range(64)]


def shared_render(fn):
    @wraps(fn)
    def render(folder, spec, kit, duration, emphasis_offset, **kwargs):
        value = json.dumps([str(Path(folder).resolve()), spec, kit, duration, emphasis_offset,
                            kwargs.get('language', 'de'), ENGINE_VERSION], sort_keys=True, ensure_ascii=False)
        index = int(hashlib.sha256(value.encode()).hexdigest()[:8], 16) % len(_RENDER_LOCKS)
        lock = _RENDER_LOCKS[index]
        from app.motion.control import MotionCancelled
        cancelled = kwargs.get('cancelled') or (lambda: False)
        while not lock.acquire(timeout=.2):
            if cancelled(): raise MotionCancelled('Grafik hazırlığı durduruldu; tamamlanan dosyalar korundu.')
        try:
            if cancelled(): raise MotionCancelled('Grafik hazırlığı durduruldu; tamamlanan dosyalar korundu.')
            return fn(folder, spec, kit, duration, emphasis_offset, **kwargs)
        finally:
            lock.release()
    return render


@shared_render

def render_clip(folder, spec, kit, duration, emphasis_offset, *, language='de', bridge=None, ffmpeg=None, prefer_openmontage=True, cancelled=None, sample_time=None, element_edits=None, render_window=None, render_size=None):
    """Render (or reuse) a clip in `folder` (the project's stock folder).
    Returns (path, scene, engine)."""
    from app.rendering.tools import discover
    ffmpeg = ffmpeg or discover().get('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg_missing')
    if spec.get('template') == 'html':
        # Prepared once at import by Remotion; preview and export share this file.
        from app.motion import html_layer
        path = html_layer.cached(folder, spec['data'], duration)
        if sample_time is not None:
            path = html_layer.sample(folder, path, max(0, min(duration, float(sample_time))), ffmpeg)
        return path, html_layer.scene_stub(duration), 'html'
    spec = with_pictures(spec, folder)
    scene = templates.build(spec, kit, duration, emphasis_offset, language)
    if element_edits:
        from app.editor.motion_objects import validate_edits
        validate_edits(scene,element_edits)
        scene['_editor_elements']=element_edits
    if render_window is not None:
        start,length=render_window
        if start<0 or length<=0 or start+length>duration+1/30:raise ValueError('Geçersiz animasyon önizleme aralığı.')
        if not any(e['type'] in ('relief','archive') for e in scene['elements']):
            scene['_render_start']=start;scene['_render_duration']=length
    if render_size is not None and spec['template']=='documentary':
        width,height=render_size
        if type(width) is not int or type(height) is not int or not 160<=width<=1920 or width*9!=height*16:raise ValueError('Geçersiz önizleme çözünürlüğü.')
        scene['_render_size']=[width,height]
    if sample_time is not None:scene['_sample_time']=max(0,min(duration,float(sample_time)))
    suffix='.mov' if scene.get('alpha') else '.mp4'
    target = folder / (scene_key(scene) + suffix)
    if sample_time is not None or render_window is not None:
        cache=folder/'editor-cache'
        if linked(cache):raise RuntimeError('Önizleme önbelleği güvenli bir yerel klasör olmalıdır.')
        cache.mkdir(exist_ok=True)
        target=cache/(('motion-window-' if render_window is not None else 'motion-sample-')+scene_key(scene)+suffix)
    from app.motion import relief
    relief.LAST_WARNING = relief.LAST_INFO = ''  # only this clip's satellite problem / view is reported
    if target.is_file() and not linked(target) and target.stat().st_size > 0:
        if sample_time is not None or render_window is not None:target.touch()
        return target, scene, 'cache'
    temporary = folder / ('.motion-' + uuid4().hex + suffix)
    engine = 'local'
    from app.motion.control import CANCELLED, check
    token = CANCELLED.set(cancelled or (lambda:False))
    try:
        check()
        if render_window is None and not element_edits and prefer_openmontage and bridge is not None and spec['template'] in templates.BASIC and not any(e['type'] == 'relief' for e in scene['elements']):  # the nine marker templates: local renderer only
            try:
                openmontage(scene, temporary, bridge, ffmpeg, folder)
                engine = 'openmontage'
            except Exception as error:  # absence or any failure: local fallback
                check()
                LOG.info('motion engine=openmontage result=fallback category=%s', type(error).__name__)
                temporary.unlink(missing_ok=True)
        if engine == 'local':
            raster_render(scene, temporary, ffmpeg)
        check()
        if relief.LAST_WARNING and any(e['type'] == 'relief' for e in scene['elements']):  # satellite fell back to the drawn map: not cached
            # Not under the satellite key (retried next time). The name must stay 32 hex characters: the media
            # screen and the render only accept stock/<32 hex>.mp4 (a “-fallback-” name read as “Yerel dosya eksik”).
            target = folder / (uuid4().hex + '.mp4')
        temporary.replace(target)
    finally:
        CANCELLED.reset(token)
        temporary.unlink(missing_ok=True)
    if sample_time is not None or render_window is not None:
        # Only disposable sampled previews, never archived source media.
        prefix='motion-window-' if render_window is not None else 'motion-sample-'
        cached=sorted([*target.parent.glob(prefix+'*.mp4'),*target.parent.glob(prefix+'*.mov')],key=lambda p:p.stat().st_mtime)
        for stale in cached[:-(48 if render_window is not None else 240)]:
            if stale!=target and not linked(stale):
                try:stale.unlink(missing_ok=True)
                except OSError:pass  # Windows may still have this preview open.
    return target, scene, engine


def media_record(path, spec, scene, engine):
    data = path.read_bytes()
    from app.motion.templates_extra import TEMPLATES_EXTRA, summary as extra_summary
    summary = extra_summary(spec) if spec['template'] in TEMPLATES_EXTRA else {
        'stat': lambda d: d['value'] + ' ' + d['label'], 'map': lambda d: d['place'], 'quote': lambda d: d['text'],
        'timeline': lambda d: ' · '.join(e['date'] for e in d['events']), 'compare': lambda d: ' vs '.join(i['label'] for i in d['items']),
        'list': lambda d: ', '.join(d['items'])}[spec['template']](spec['data'])
    return {'provider': 'generated', 'media_id': 'motion-' + path.stem[:16], 'media_type': 'video', 'source_url': '', 'page_url': '',
            'creator_name': 'AI Video Studio', 'creator_url': '', 'width': 1920, 'height': 1080, 'duration': scene['duration'],
            'preview_url': '', 'download_url': '', 'query_used': '', 'provider_query': None, 'description': summary[:300],
            'source_metadata': {'generated': True, 'kind': 'motion', 'motion': spec, 'template_label': templates.TEMPLATES[spec['template']],
                                'layout_label': layouts.label(spec),
                                'emphasis_time': scene['emphasis_time'], 'sfx': scene['sfx'], 'engine': engine},
            'search_tier': None, 'relevance_score': None, 'relevance_label': None, 'relevance_basis': None,
            'local_path': 'stock/' + path.name, 'file_size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'downloaded_at': now(), 'content_type': 'video/mp4'}


def is_motion(media):
    return bool(media and media.get('provider') == 'generated' and (media.get('source_metadata') or {}).get('kind') == 'motion')
