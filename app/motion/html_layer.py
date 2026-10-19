"""Static HTML/CSS overlay layers from an external AI, rendered once and reused.

Flow: the manual plan's ``html_katmanlari`` records are sanitized here, rendered
to transparent PNG frames by the user's own OpenMontage/Remotion install (one
browser render per unique layer), packed into the same qtrle/argb ``.mov`` the
local animation renderer already produces for alpha clips, and cached in the
project's stock folder.  Program preview, draft preview and the final render all
read that single cached file, so preview and export cannot drift apart.

Nothing here executes AI-supplied code: no script, no event handler, no URL, no
external file.  Unsafe input is rejected with a reason (never silently cleaned),
so the user can send the correction back to the AI.
"""
from html.parser import HTMLParser
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import uuid4

FPS = 30
WIDTH, HEIGHT = 1920, 1080
VERSION = 1
MAX_SECONDS = 30
MAX_HTML = 30_000
MAX_CSS = 30_000
MAX_ELEMENTS = 2_000
MAX_DEPTH = 64
MAX_LAYERS = 40
TRACKS = ('layers', 'infographics', 'maps', 'emphasis')
FIELDS = {'scene_id', 'start', 'end', 'object_id', 'track', 'html', 'css'}
CACHE = 'html-layers'

HTML_TAGS = {'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'b', 'i', 'u', 'small',
             'sub', 'sup', 'br', 'hr', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
             'caption', 'figure', 'figcaption', 'blockquote', 'section', 'header', 'footer', 'article'}
SVG_TAGS = {'svg', 'g', 'defs', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text',
            'tspan', 'lineargradient', 'radialgradient', 'stop', 'clippath', 'mask'}
VOID = {'br', 'hr'}
GLOBAL_ATTRS = {'class', 'id', 'style'}
TABLE_ATTRS = {'colspan', 'rowspan'}
SVG_ATTRS = {'viewbox', 'width', 'height', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'fx', 'fy',
             'd', 'points', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
             'stroke-dasharray', 'stroke-dashoffset', 'stroke-opacity', 'fill-opacity', 'fill-rule', 'clip-rule',
             'opacity', 'transform', 'transform-origin', 'offset', 'stop-color', 'stop-opacity', 'gradientunits',
             'gradienttransform', 'text-anchor', 'dominant-baseline', 'font-size', 'font-family', 'font-weight',
             'letter-spacing', 'clip-path', 'mask', 'preserveaspectratio', 'xmlns', 'pathlength', 'dx', 'dy'}
LONG_ATTRS = {'d', 'points'}
ID = re.compile(r'^[A-Za-z][\w-]{0,60}$')
CLASSES = re.compile(r'^[A-Za-z_][\w -]{0,300}$')
LOCAL_URL = re.compile(r'url\(\s*#[A-Za-z][\w-]{0,60}\s*\)', re.I)
AT_RULE = re.compile(r'@([A-Za-z-]+)')
_lock = RLock()
_errors = {}


class LayerError(ValueError):
    """Unsafe or unsupported layer content. The message lists the reasons."""


def _css_reasons(text, *, inline):
    reasons = []
    body = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    lower = body.lower()
    if '/*' in body or '*/' in body:
        reasons.append('kapatılmamış CSS yorumu')
    if '\\' in body:
        reasons.append('CSS kaçış dizisi (\\) kullanılamaz')
    if '<' in body:
        reasons.append('CSS içinde < işareti kullanılamaz')
    for word in ('expression(', 'javascript:', 'behavior:', '-moz-binding', 'vbscript:'):
        if word in lower:
            reasons.append(f'yasak CSS ifadesi: {word}')
    if 'url(' in LOCAL_URL.sub('', lower):
        reasons.append('url(...) yalnız aynı katmandaki #kimlik için kullanılabilir; dış resim/font yasak')
    if inline:
        if '{' in body or '}' in body or '@' in body:
            reasons.append('style özniteliğinde yalnız özellik: değer; listesi olabilir')
    else:
        for rule in AT_RULE.findall(body):
            if rule.lower() not in ('keyframes', '-webkit-keyframes'):
                reasons.append(f'@{rule} desteklenmiyor; yalnız @keyframes kullanılabilir')
        if body.count('{') != body.count('}'):
            reasons.append('CSS süslü parantezleri eşleşmiyor')
    return reasons


def _attr_reasons(tag, name, value):
    if name.startswith('on'):
        return [f'<{tag}> {name}: olay öznitelikleri (on...) yasak']
    if name in ('href', 'xlink:href', 'src', 'srcset', 'action', 'formaction', 'background', 'poster', 'data'):
        return [f'<{tag}> {name}: bağlantı/dosya öznitelikleri yasak']
    allowed = GLOBAL_ATTRS | (TABLE_ATTRS if tag in ('td', 'th') else set()) | (SVG_ATTRS if tag in SVG_TAGS else set())
    if name not in allowed:
        return [f'<{tag}> {name} özniteliği desteklenmiyor']
    value = value or ''
    if len(value) > (20_000 if name in LONG_ATTRS else 300):
        return [f'<{tag}> {name} değeri çok uzun']
    if name == 'style':
        return [f'<{tag}> style: {r}' for r in _css_reasons(value, inline=True)]
    if name == 'id' and not ID.match(value):
        return [f'<{tag}> id harf ile başlayan kısa bir kimlik olmalı']
    if name == 'class' and value and not CLASSES.match(value):
        return [f'<{tag}> class adları yalnız harf, rakam, - ve _ içerebilir']
    if name in TABLE_ATTRS and not (value.isdigit() and 1 <= int(value) <= 20):
        return [f'<{tag}> {name} 1–20 arası bir sayı olmalı']
    lower = value.lower()
    if 'javascript:' in lower or 'expression(' in lower or '<' in value:
        return [f'<{tag}> {name} değeri güvenli değil']
    if 'url(' in LOCAL_URL.sub('', lower):
        return [f'<{tag}> {name}: url(...) yalnız #kimlik gösterebilir']
    return []


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.reasons, self.count = [], [], [], 0

    def _start(self, tag, attrs, closed):
        self.count += 1
        if tag not in HTML_TAGS | SVG_TAGS:
            self.reasons.append(f'<{tag}> etiketi desteklenmiyor')
            return
        if self.count > MAX_ELEMENTS or len(self.stack) >= MAX_DEPTH:
            self.reasons.append('çok fazla veya çok derin öğe')
            return
        parts = []
        for name, value in attrs:
            problems = _attr_reasons(tag, name, value)
            if problems:
                self.reasons += problems
                continue
            parts.append(f' {name}="{escape(value or "", quote=True)}"')
        self.out.append(f'<{tag}{"".join(parts)}' + ('/>' if closed and tag in SVG_TAGS else '>'))
        if tag in VOID or (closed and tag in SVG_TAGS):
            return
        if closed:
            self.out.append(f'</{tag}>')
            return
        self.stack.append(tag)

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag not in HTML_TAGS | SVG_TAGS:
            return  # already reported at its start tag
        if tag not in self.stack:
            self.reasons.append(f'</{tag}> açılmadan kapatılmış')
            return
        while self.stack:
            open_tag = self.stack.pop()
            self.out.append(f'</{open_tag}>')
            if open_tag == tag:
                break

    def handle_data(self, data):
        self.out.append(escape(data, quote=False))

    def handle_comment(self, data):
        pass  # comments are dropped; they never reach the page

    def handle_decl(self, decl):
        pass

    def unknown_decl(self, data):
        self.reasons.append('CDATA/özel bildirim desteklenmiyor')

    def handle_pi(self, data):
        self.reasons.append('işleme talimatı (<?...?>) desteklenmiyor')


def sanitize(html, css=''):
    """Return (html, css) safe to render, or raise LayerError with every reason."""
    reasons = []
    if not isinstance(html, str) or not html.strip():
        raise LayerError('html alanı boş olmayan bir metin olmalı.')
    if css is None:
        css = ''
    if not isinstance(css, str):
        raise LayerError('css alanı metin olmalı.')
    if len(html) > MAX_HTML:
        reasons.append(f'html en fazla {MAX_HTML} karakter olabilir')
    if len(css) > MAX_CSS:
        reasons.append(f'css en fazla {MAX_CSS} karakter olabilir')
    if reasons:
        raise LayerError('; '.join(reasons))
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    reasons += parser.reasons
    reasons += _css_reasons(css, inline=False)
    if reasons:
        unique = list(dict.fromkeys(reasons))
        more = f' (+{len(unique) - 8} sorun daha)' if len(unique) > 8 else ''
        raise LayerError('; '.join(unique[:8]) + more)
    clean = ''.join(parser.out) + ''.join(f'</{t}>' for t in reversed(parser.stack))
    clean_css = re.sub(r'/\*.*?\*/', '', css, flags=re.S).strip()
    return clean, clean_css


def frames_for(duration):
    return max(1, round(float(duration) * FPS))


def layer_key(data, duration):
    from app.motion.fonts import signature
    identity = {'v': VERSION, 'html': data['html'], 'css': data.get('css', ''), 'frames': frames_for(duration),
                'size': [WIDTH, HEIGHT], 'fonts': signature()}
    return sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cache_path(folder, data, duration):
    return Path(folder) / CACHE / (layer_key(data, duration) + '.mov')


def remember_error(folder, key, message):
    with _lock:
        if len(_errors) > 500:
            _errors.clear()
        _errors[(str(Path(folder)), key)] = message


def last_error(folder, key):
    with _lock:
        return _errors.get((str(Path(folder)), key))


def cached(folder, data, duration):
    """Path of the prepared layer, or a RenderError explaining why it is missing."""
    from app.projects import linked
    from app.rendering.models import RenderError
    path = cache_path(folder, data, duration)
    if path.is_file() and not linked(path) and path.stat().st_size > 0:
        return path
    reason = last_error(folder, path.stem)
    raise RenderError('html_layer_missing', 'HTML katmanı bu içerik ve süre için hazırlanmamış'
                      + (f': {reason}' if reason else '.') +
                      ' Planı Manuel Plan penceresinden yeniden içe aktararak katmanı hazırlayın.')


def sample(folder, path, time, ffmpeg):
    """One exact frame of a prepared layer, as a 1-frame alpha clip (draft/still previews)."""
    from app.projects import linked
    from app.rendering.runner import ProcessRunner
    frame = max(0, round(float(time) * FPS))
    target = Path(folder) / CACHE / f'{path.stem}-f{frame}.mov'
    if target.is_file() and not linked(target) and target.stat().st_size > 0:
        return target
    temporary = target.with_name('.sample-' + uuid4().hex + '.mov')
    try:
        ProcessRunner().run([ffmpeg, '-v', 'error', '-y', '-i', str(path), '-vf', f'select=eq(n\\,{frame})',
                             '-frames:v', '1', '-c:v', 'qtrle', '-pix_fmt', 'argb', str(temporary)], target.parent)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError('html_layer_sample')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def scene_stub(duration):
    """Minimal scene for callers that inspect a motion scene; nothing is drawn locally."""
    return {'version': 1, 'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'duration': float(duration),
            'elements': [], 'sfx': [], 'alpha': True, 'html_layer': True}


def render(bridge, folder, data, duration, ffmpeg, *, runner=None, progress=lambda fraction: None):
    """Render once through Remotion; return the cached qtrle/argb .mov path."""
    from app.projects import linked
    from app.rendering.models import RenderError
    from app.rendering.runner import ProcessRunner
    folder = Path(folder)
    target = cache_path(folder, data, duration)
    if target.is_file() and not linked(target) and target.stat().st_size > 0:
        return target
    if bridge is None:
        raise RenderError('openmontage_unavailable', 'HTML katmanı için OpenMontage (Remotion) gerekli; bu kurulumda bulunamadı.')
    status = bridge.status()
    if not status.get('ready'):
        raise RenderError('openmontage_unavailable', 'HTML katmanı için OpenMontage (Remotion) hazır olmalı: ' + status.get('message', ''))
    cache = target.parent
    if linked(cache):
        raise RenderError('input_invalid', 'HTML katmanı önbelleği güvenli bir yerel klasör olmalıdır.')
    cache.mkdir(parents=True, exist_ok=True)
    root = bridge.root()
    parent = root / 'remotion-composer' / 'projects'
    if linked(parent) or not parent.resolve().is_relative_to(root):
        raise RenderError('openmontage_path', 'OpenMontage proje klasörü güvenli değil.')
    parent.mkdir(exist_ok=True)
    staging = parent / ('naman-html-' + uuid4().hex)
    frames_dir = cache / ('frames-' + uuid4().hex)
    temporary = cache / ('.html-' + uuid4().hex + '.mov')
    frames = frames_for(duration)
    staging.mkdir()
    frames_dir.mkdir()
    try:
        from app.motion.fonts import font_css
        (staging / 'props.json').write_text(json.dumps({'html': data['html'], 'css': data.get('css', ''), 'frames': frames,
                                                        'fonts': font_css()}, ensure_ascii=False), encoding='utf-8')
        shutil.copyfile(Path(__file__).with_name('html_layer.tsx'), staging / 'index.tsx')
        bridge.call('html_layer', {'entry': str(staging / 'index.tsx'), 'props_path': str(staging / 'props.json'),
                                   'output_dir': str(frames_dir), 'frames': frames}, cache, runner=runner, progress=progress)
        pictures = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() == '.png' and not linked(p))
        if len(pictures) != frames:
            raise RenderError('html_layer_failed', f'Remotion {len(pictures)} kare üretti; {frames} kare gerekiyordu. Katman eksik bırakılmadı, hazırlanmadı.')
        for index, picture in enumerate(pictures, 1):
            picture.rename(frames_dir / f'f{index:06d}.png')
        (runner or ProcessRunner()).run([ffmpeg, '-v', 'error', '-y', '-framerate', str(FPS), '-i', str(frames_dir / 'f%06d.png'),
                                         '-frames:v', str(frames), '-c:v', 'qtrle', '-pix_fmt', 'argb', str(temporary)], cache)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RenderError('html_layer_failed', 'HTML katmanı videoya dönüştürülemedi.')
        temporary.replace(target)
        return target
    finally:
        if not linked(staging):
            shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(frames_dir, ignore_errors=True)
        temporary.unlink(missing_ok=True)


def validate_shape(item, known):
    """Fields, scene, lock, track and HTML/CSS safety; no time window."""
    if not isinstance(item, dict):
        raise LayerError('Her HTML katmanı bir nesne olmalı.')
    extra = set(item) - FIELDS
    if extra:
        raise LayerError('Desteklenmeyen alan: ' + ', '.join(sorted(extra)) + '. Yalnız scene_id, start, end, object_id, track, html, css.')
    if not isinstance(item.get('scene_id'), str) or item['scene_id'] not in known:
        raise LayerError('Geçerli scene_id gerekir.')
    if known[item['scene_id']].get('locked'):
        raise LayerError('Sahne kilitli; değiştirilemez.')
    if item.get('track', 'layers') not in TRACKS:
        raise LayerError('track layers/infographics/maps/emphasis olmalıdır.')
    return sanitize(item.get('html'), item.get('css', ''))


def item_window(item, scene):
    start = item.get('start', scene['start'])
    end = item.get('end', scene['end'])
    return start, end


def validate_item(item, scenes):
    """Shape/safety check of one html_katmanlari record; returns (scene, start, end, data)."""
    html, css = validate_shape(item, scenes)
    scene = scenes[item['scene_id']]
    start, end = item_window(item, scene)
    if any(type(v) not in (int, float) for v in (start, end)) or scene['start'] is None or not scene['start'] <= start < end <= scene['end']:
        raise LayerError(f"start/end kendi sahnesinin aralığında olmalı ({scene['start']}–{scene['end']} sn).")
    if end - start > MAX_SECONDS:
        raise LayerError(f'Bir HTML katmanı en fazla {MAX_SECONDS} sn olabilir; start/end vererek kısaltın.')
    return scene, float(start), float(end), {'html': html, 'css': css}


def prerender(bridge, folder, items, scenes, ffmpeg, *, progress=lambda done, total, message: None):
    """Render every valid layer of an incoming plan before review. Failures are
    remembered per layer and reported by the review as issues; nothing is lost."""
    folder = Path(folder)
    todo = []
    for item in (items or [])[:MAX_LAYERS]:
        try:
            _, start, end, data = validate_item(item, scenes)
        except (LayerError, TypeError, KeyError):
            continue  # the review reports the exact reason for this record
        todo.append((data, end - start))
    for index, (data, duration) in enumerate(todo):
        progress(index, len(todo), f'HTML katmanı {index + 1}/{len(todo)} hazırlanıyor')
        key = layer_key(data, duration)
        try:
            render(bridge, folder, data, duration, ffmpeg)
        except Exception as error:  # every failure becomes a visible, per-layer reason
            message = str(error) if getattr(error, 'category', None) else 'Remotion bu katmanı çizemedi; HTML/CSS içeriğini sadeleştirip yeniden deneyin.'
            remember_error(folder, key, message)
    if todo:
        progress(len(todo), len(todo), 'HTML katmanları hazır')
    return len(todo)


def clip_for(item, scene, start, end, slots, source_key, folder):
    """Editor clip for a validated record; requires the prepared layer file."""
    from uuid import uuid4 as new_id
    from app.editor.models import EditorError
    from app.rendering.models import RenderError
    if any(s.get('locked') and start < s['end'] and end > s['start'] for s in slots):
        raise EditorError('locked', 'HTML katmanı aralığında kilitli görüntü yuvası var; üzerine eklenmedi.', 409)
    try:
        _, _, _, data = validate_item(item, {scene['scene_id']: scene})
    except LayerError as error:
        raise EditorError('invalid_html_layer', str(error)) from None
    try:
        cached(folder, data, end - start)
    except RenderError as error:
        raise EditorError('html_layer_not_ready', str(error)) from None
    return {'id': new_id().hex, 'kind': 'motion', 'track': item.get('track', 'layers'), 'start': start, 'end': end,
            'animation_duration': end - start, 'motion': {'template': 'html', 'data': data, 'emphasis': ''},
            'origin': 'json', 'source_key': source_key}


def contract():
    """What the external AI may send; included verbatim in the task package."""
    return {
        'optional': True,
        'fields': ['scene_id', 'start', 'end', 'object_id', 'track', 'html', 'css'],
        'tracks': list(TRACKS),
        'canvas': {'width': WIDTH, 'height': HEIGHT, 'fps': FPS, 'background': 'şeffaf'},
        'limits': {'seconds': MAX_SECONDS, 'layers_per_plan': MAX_LAYERS, 'html_chars': MAX_HTML, 'css_chars': MAX_CSS},
        'allowed_html': sorted(HTML_TAGS), 'allowed_svg': sorted(SVG_TAGS),
        'rules': [
            'Katman 1920×1080 şeffaf bir sahnedir ve mevcut videonun üstüne biner. Arka planı boyamayın; yalnız gereken grafik/yazıyı çizin.',
            'Hareketi yalnız CSS @keyframes animasyonlarıyla yazın. Zaman 0, katmanın start saniyesidir. NAMAN her kareyi bu saate göre dondurur; transition, :hover ve JavaScript çalışmaz.',
            'Yasak: script, iframe, img, video, audio, link, a, form, on... olayları, href/src, url(...) ile dış dosya, @import, @font-face. Yasak içerikli katman reddedilir, düzeltme mesajıyla geri gelir.',
            'Yazı tipi olarak sistem fontları kullanın (Arial, Helvetica, Georgia, sans-serif, serif).',
            'Yazılar proje dilinde ve anlatımdaki bilgiyle olmalı; sayı, tarih, yer uydurmayın. Haritanın üstüne konacaksa track=maps verin ve yalnız gerekli etiketi çizin.',
            'Her katman taslağa düşer; kullanıcı seçip onaylamadan kurguya işlenmez.'],
        'example': {'scene_id': 'SAHNE_KIMLIGI', 'start': 12.0, 'end': 18.0, 'track': 'infographics',
                    'html': '<div class="kart"><span class="sayi">1945</span><span class="etiket">ANLATIMDAKİ ETİKET</span></div>',
                    'css': '.kart{position:absolute;left:120px;bottom:160px;padding:24px 36px;background:rgba(10,10,12,.78);'
                           'border-left:6px solid #F28C28;color:#fff;font-family:Arial,sans-serif;animation:gir .6s ease-out both}'
                           '.sayi{display:block;font-size:72px;font-weight:700}.etiket{font-size:28px;letter-spacing:2px}'
                           '@keyframes gir{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:none}}'}}
