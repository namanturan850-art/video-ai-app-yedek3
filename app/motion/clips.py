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
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

from app.motion import layouts, templates
from app.motion.raster import render as raster_render
from app.projects import linked, now

LOG = logging.getLogger('uvicorn.error.motion')
ENGINE_VERSION = 'motion-v3'  # v2: 1:50m coastlines, timing limits, layouts; v3: 2-5 word texts, opaque boxes


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
        bridge.call('compose', {'operation': 'render', 'output_path': str(raw), 'audio_path': str(audio),
                                'edit_decisions': {'render_runtime': 'remotion', 'composition_mode': 'atelier', 'renderer_family': 'bespoke',
                                                   'bespoke': {'entry': str(entry), 'composition_id': 'AVSMotion', 'props_path': str(staging / 'props.json'),
                                                               'public_dir': str(public), 'crf': 18, 'concurrency': 1}}}, folder)
        if not raw.is_file():
            raise RuntimeError('openmontage_output')
        frames = max(1, round(scene['duration'] * templates.FPS))
        # Same delivery format as the local renderer: exact frames, no audio.
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(raw), '-an', '-vf', 'fps=30,scale=1920:1080,setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=1',
                        '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-movflags', '+faststart', str(output)],
                       check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
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


def render_clip(folder, spec, kit, duration, emphasis_offset, *, language='de', bridge=None, ffmpeg=None, prefer_openmontage=True):
    """Render (or reuse) a clip in `folder` (the project's stock folder).
    Returns (path, scene, engine)."""
    from app.rendering.tools import discover
    ffmpeg = ffmpeg or discover().get('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg_missing')
    spec = with_pictures(spec, folder)
    scene = templates.build(spec, kit, duration, emphasis_offset, language)
    target = folder / (scene_key(scene) + '.mp4')
    from app.motion import relief
    relief.LAST_WARNING = relief.LAST_INFO = ''  # only this clip's satellite problem / view is reported
    if target.is_file() and not linked(target) and target.stat().st_size > 0:
        return target, scene, 'cache'
    temporary = folder / ('.motion-' + uuid4().hex + '.mp4')
    engine = 'local'
    try:
        if prefer_openmontage and bridge is not None and spec['template'] in templates.BASIC and not any(e['type'] == 'relief' for e in scene['elements']):  # the nine marker templates: local renderer only
            try:
                openmontage(scene, temporary, bridge, ffmpeg, folder)
                engine = 'openmontage'
            except Exception as error:  # absence or any failure: local fallback
                LOG.info('motion engine=openmontage result=fallback category=%s', type(error).__name__)
                temporary.unlink(missing_ok=True)
        if engine == 'local':
            raster_render(scene, temporary, ffmpeg)
        if relief.LAST_WARNING and any(e['type'] == 'relief' for e in scene['elements']):  # satellite fell back to the drawn map: not cached
            # Not under the satellite key (retried next time). The name must stay 32 hex characters: the media
            # screen and the render only accept stock/<32 hex>.mp4 (a “-fallback-” name read as “Yerel dosya eksik”).
            target = folder / (uuid4().hex + '.mp4')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
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
