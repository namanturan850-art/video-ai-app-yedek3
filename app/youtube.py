"""YouTube preparation: titles, description (hook, summary, chapters, tags,
stock credits) and a 1280x720 thumbnail. Nothing is uploaded to YouTube.

Text comes from the AI engine (Gemini by default) and is checked here; the
chapters come from the scene plan and the real subtitle timing. The default
thumbnail uses frames of the rendered video with the channel's style kit
(free); a Gemini-generated background is optional and off by default.
"""
from contextlib import closing
import hashlib
import json
import re
import subprocess
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.projects import ProjectError, linked, now

LANG = {'de': {'chapters': 'Kapitel', 'credits': 'Stockmaterial', 'intro': 'Einleitung'},
        'en': {'chapters': 'Chapters', 'credits': 'Stock footage', 'intro': 'Intro'},
        'es': {'chapters': 'Capítulos', 'credits': 'Material de archivo', 'intro': 'Introducción'},
        'fr': {'chapters': 'Chapitres', 'credits': 'Images d’archives', 'intro': 'Introduction'},
        'tr': {'chapters': 'Bölümler', 'credits': 'Stok görüntüler', 'intro': 'Giriş'}}
TEXT_SCHEMA = {'type': 'object', 'additionalProperties': False,
               'required': ['titles', 'hook', 'summary', 'tags', 'hashtags', 'chapter_titles', 'thumbnail_texts'],
               'properties': {'titles': {'type': 'array', 'items': {'type': 'string'}}, 'hook': {'type': 'string'}, 'summary': {'type': 'string'},
                              'tags': {'type': 'array', 'items': {'type': 'string'}}, 'hashtags': {'type': 'array', 'items': {'type': 'string'}},
                              'chapter_titles': {'type': 'array', 'items': {'type': 'string'}}, 'thumbnail_texts': {'type': 'array', 'items': {'type': 'string'}}}}
LAYOUTS = ('left', 'banner', 'frame')
LAYOUT_LABELS = {'left': 'Solda büyük yazı + ok', 'banner': 'Alt şerit + daire vurgu', 'frame': 'Çerçeve + köşe yazısı'}


def stamp(seconds):
    seconds = int(seconds)
    return f'{seconds // 3600}:{seconds % 3600 // 60:02}:{seconds % 60:02}' if seconds >= 3600 else f'{seconds // 60}:{seconds % 60:02}'


def words(text):
    return {w for w in re.findall(r'[\w’-]+', text.casefold()) if len(w) > 2}


def complements(text, title):
    """A thumbnail text must add to the title, not repeat it."""
    w = words(text)
    return bool(w) and len(w & words(title)) / len(w) < .5


class YouTubeService:
    def __init__(self, projects, scripts, production, rendering, stock, channels, settings):
        self.projects, self.scripts, self.production, self.rendering = projects, scripts, production, rendering
        self.stock, self.channels, self.settings = stock, channels, settings

    # ---- storage ---------------------------------------------------------
    def _folder(self, pid, *parts):
        root = self.projects._path(pid)
        folder = root.joinpath('youtube', *parts)
        for path in (root / 'youtube', folder):
            if linked(path): raise ProjectError('YouTube klasörü dış konuma bağlı; işlem durduruldu.', 409)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _load(self, pid):
        path = self._folder(pid) / 'package.json'
        try:
            return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except (OSError, ValueError):
            return {}

    def _save(self, pid, package):
        package['updated_at'] = now()
        target = self._folder(pid) / 'package.json'
        temporary = target.with_name('.package-' + uuid4().hex)
        temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(target)
        return package

    def view(self, pid):
        project = self.projects.get(pid)
        package = self._load(pid)
        render = self.rendering.handoff(pid)
        engine = self.settings.ai_engine()
        images = self.settings.image_config()
        return {'project_id': pid, 'language': project['language'], 'package': package, 'video_ready': bool(render.get('ready')),
                'engine': engine, 'engine_label': {'claude': 'Claude (ücretli)', 'gemini': 'Gemini (ücretsiz kota)'}.get(engine, ''),
                'layouts': [{'id': k, 'label': LAYOUT_LABELS[k]} for k in LAYOUTS],
                'ai_background': {'enabled': bool(images.get('thumbnail_ai')) and bool(images.get('gemini_model')),
                                  'note': 'Gemini görsel üretimi kotanızdan düşer veya ücretli olabilir; her üretim tek istek kullanır.'}}

    # ---- text ----------------------------------------------------------------
    def chapters(self, pid, count=None):
        """Chapter starts from the scene plan (real subtitle times when present)."""
        plan = self.production.view(pid)['plan']
        if not plan: raise ProjectError('Önce kurgu planını hazırlayın.', 409)
        blocks = plan['blocks']
        timing = {}
        try:
            for s in self.rendering.subtitles.handoff(pid).get('scenes', []): timing[s['scene_id']] = s['start']
        except Exception:
            timing = {}
        starts = [(timing.get(b.get('scene_id', b.get('id')), b.get('start_estimate', 0)), b) for b in blocks]
        total = max([b.get('end_estimate', 0) for b in blocks] + [1])
        count = count or max(3, min(8, round(total / 45)))
        if len(starts) < 3 or total < 30:
            return []
        size = len(starts) / count
        groups = [starts[round(i * size):round((i + 1) * size)] for i in range(count)]
        chapters = []
        for i, group in enumerate(g for g in groups if g):
            at = 0. if i == 0 else group[0][0]
            if chapters and at - chapters[-1]['start'] < 10: continue  # YouTube needs ≥10 s chapters
            narration = ' '.join(b['narration'] for _, b in group)
            chapters.append({'start': round(at, 1), 'narration': narration[:600],
                             'fallback': ' '.join(narration.split()[:6]).rstrip('.,;:')})
        return chapters if len(chapters) >= 3 else []

    def credits(self, pid):
        try:
            state = self.stock.view(pid)
        except Exception:
            return []
        seen, out = set(), []
        for slot in state['slots']:
            m = slot.get('selected_media') or {}
            if m.get('provider') not in ('pexels', 'pixabay'): continue
            key = (m['provider'], m.get('creator_name', ''))
            if key in seen: continue
            seen.add(key); out.append({'provider': m['provider'].title(), 'creator': m.get('creator_name', ''), 'url': m.get('page_url', '')})
        return out[:30]

    def generate_text(self, pid):
        project = self.projects.get(pid)
        current = self.scripts.repository.view(pid)['current']
        if not current: raise ProjectError('Önce senaryo oluşturun.', 409)
        engine = self.settings.ai_engine()
        if not engine: raise ProjectError('YouTube metinleri için Ayarlar → Gemini bölümünde ücretsiz anahtarınızı kaydedip bir model seçin.', 422)
        chapters = self.chapters(pid)
        channel = self.channels.for_project(pid)
        language = project['language']
        from app.providers.factory import make_script_provider
        ai = make_script_provider(engine, self.settings)
        prompt = (f'Prepare YouTube metadata for this video. Write EVERYTHING in the video language "{language}".\n'
                  f'Channel: {channel["name"]} ({channel["niche"]}). Topic: {project["topic"]}.\n'
                  'titles: exactly 5 different titles, curiosity-raising but honest (no clickbait, no ALL CAPS, no invented claims), each 55-70 characters.\n'
                  'hook: 2 short lines (separated by a newline) that make people want to watch. summary: 2-4 sentences about the content.\n'
                  'tags: 10-15 search keywords (no #). hashtags: 3 hashtags with #.\n'
                  f'chapter_titles: exactly {len(chapters)} short chapter titles (2-5 words) for these chapters in order.\n'
                  'thumbnail_texts: 4 very short thumbnail texts (2-4 words, big and punchy) that COMPLEMENT the titles instead of repeating them.\n'
                  'Use only facts from the script.\n\nCHAPTERS:\n' + '\n'.join(f'{i + 1}. {c["narration"][:300]}' for i, c in enumerate(chapters))
                  + '\n\nSCRIPT:\n' + current['text'][:12000])
        data = ai.complete_json('youtube_text', prompt, TEXT_SCHEMA, effort='low', max_tokens=3000)
        clean = lambda v, n: ' '.join(str(v).split())[:n]
        titles = [clean(t, 100) for t in data.get('titles', []) if isinstance(t, str) and t.strip()][:5]
        if not titles: raise ProjectError('Yapay zekâ başlık döndürmedi; tekrar deneyin.', 502)
        tags = list(dict.fromkeys(clean(t, 60).lstrip('#') for t in data.get('tags', []) if isinstance(t, str) and t.strip()))[:15]
        hashtags = ['#' + re.sub(r'\W', '', clean(h, 40).lstrip('#')) for h in data.get('hashtags', []) if isinstance(h, str) and re.sub(r'\W', '', h)][:3]
        names = [clean(n, 60) for n in data.get('chapter_titles', [])]
        for i, c in enumerate(chapters):
            c['title'] = names[i] if i < len(names) and names[i] else c['fallback']
        thumbs = [clean(t, 40) for t in data.get('thumbnail_texts', []) if isinstance(t, str) and 1 <= len(t.split()) <= 5]
        package = self._load(pid)
        package.update(titles=[{'text': t, 'length': len(t), 'in_range': 55 <= len(t) <= 72} for t in titles], chosen_title=titles[0],
                       hook='\n'.join(clean(line, 150) for line in str(data.get('hook', '')).replace(' / ', '\n').splitlines() if line.strip())[:300],
                       summary=clean(data.get('summary', ''), 1200),
                       tags=tags, hashtags=hashtags, chapters=[{k: c[k] for k in ('start', 'title')} for c in chapters],
                       credits=self.credits(pid), thumbnail_texts=thumbs, engine=engine, generated_at=now())
        package['description'] = self.description(package, language)
        return self._save(pid, package)

    @staticmethod
    def description(package, language):
        labels = LANG.get(language, LANG['en'])
        hook = str(package.get('hook', '')).replace('\\n', '\n')
        parts = [hook.strip(), package.get('summary', '').strip()]
        if package.get('chapters'):
            parts.append(labels['chapters'] + ':\n' + '\n'.join(f'{stamp(c["start"])} {c["title"]}' for c in package['chapters']))
        if package.get('credits'):
            parts.append(labels['credits'] + ': ' + ', '.join(sorted({c['provider'] for c in package['credits']}))
                         + '\n' + '\n'.join(f'{c["provider"]} — {c["creator"]}' for c in package['credits'] if c['creator']))
        if package.get('hashtags'):
            parts.append(' '.join(package['hashtags']))
        return '\n\n'.join(p for p in parts if p)[:5000]

    def update(self, pid, payload):
        allowed = {'chosen_title', 'description', 'tags', 'hook', 'summary'}
        if not isinstance(payload, dict) or not payload or set(payload) - allowed:
            raise ProjectError('YouTube bilgilerini kontrol edin.')
        package = self._load(pid)
        if 'chosen_title' in payload:
            title = ' '.join(str(payload['chosen_title']).split())
            if not 1 <= len(title) <= 100: raise ProjectError('YouTube başlığı 1–100 karakter olmalı.')
            package['chosen_title'] = title
        if 'description' in payload:
            if len(str(payload['description'])) > 5000: raise ProjectError('Açıklama en fazla 5000 karakter olabilir.')
            package['description'] = str(payload['description'])
        if 'tags' in payload:
            tags = [str(t).strip().lstrip('#') for t in payload['tags'] if str(t).strip()] if isinstance(payload['tags'], list) else []
            if len(', '.join(tags)) > 500: raise ProjectError('Etiketlerin toplamı 500 karakteri aşamaz.')
            package['tags'] = tags[:30]
        return self._save(pid, package)

    # ---- thumbnail -------------------------------------------------------------
    def frames(self, pid):
        """3-5 striking frames from the rendered video (sharp, colourful, well lit)."""
        from PIL import Image, ImageFilter, ImageStat
        from app.rendering.tools import discover
        ffmpeg = discover().get('ffmpeg')
        render = self.rendering.handoff(pid)
        sources = []
        if render.get('ready'):
            video = self.projects._path(pid) / render['video_local_path']
            duration = float(render.get('duration') or 0) or 60
            sources = [(video, duration * (i + .5) / 24) for i in range(24)]
        else:
            state = self.stock.view(pid)
            for slot in state['slots']:
                m = slot.get('selected_media')
                if m and m.get('provider') != 'generated':
                    sources.append((self.projects._path(pid) / m['local_path'], 1.0 if m['media_type'] == 'video' else None))
            sources = sources[:24]
        if not sources or not ffmpeg:
            raise ProjectError('Kapak için önce videoyu oluşturun (veya medya seçin).', 409)
        folder = self._folder(pid, 'frames')
        scored = []
        for index, (path, at) in enumerate(sources):
            out = folder / f'cand-{index}.jpg'
            args = [ffmpeg, '-v', 'error', '-y'] + (['-ss', f'{at:.2f}'] if at is not None else []) + ['-i', str(path), '-frames:v', '1', '-vf', 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720', str(out)]
            if subprocess.run(args, capture_output=True, timeout=60).returncode or not out.is_file(): continue
            image = Image.open(out).convert('RGB')
            small = image.resize((320, 180))
            edges = ImageStat.Stat(small.convert('L').filter(ImageFilter.FIND_EDGES)).mean[0]
            r, g, b = ImageStat.Stat(small).stddev
            brightness = ImageStat.Stat(small.convert('L')).mean[0]
            score = edges * 1.5 + (r + g + b) / 3 - abs(brightness - 120) * .4
            scored.append((score, at or 0, out))
        if not scored:
            raise ProjectError('Videodan kare alınamadı. Render dosyasını kontrol edin.', 409)
        picked = []
        for score, at, out in sorted(scored, reverse=True):
            if all(abs(at - p[1]) >= 6 for p in picked): picked.append((score, at, out))
            if len(picked) == 5: break
        result = []
        for i, (score, at, out) in enumerate(picked):
            name = f'frame-{i + 1}.jpg'; (folder / name).write_bytes(out.read_bytes())
            result.append({'id': name, 'time': round(at, 1), 'score': round(score, 1), 'url': f'/api/projects/{pid}/youtube/files/frames/{name}'})
        for leftover in folder.glob('cand-*.jpg'): leftover.unlink(missing_ok=True)
        package = self._load(pid); package['frames'] = result
        self._save(pid, package)
        return result

    def ai_background(self, pid, cost_confirmed):
        images = self.settings.image_config()
        if not images.get('thumbnail_ai') or not images.get('gemini_model'):
            raise ProjectError('Yapay zekâ arka planı kapalı. Ayarlar → Görsel bölümünde Gemini görsel modelini seçip “Kapak arka planı” seçeneğini açın.', 409)
        if cost_confirmed is not True:
            raise ProjectError('Gemini görsel üretimi kota/ücret kullanabilir. Açık onay gerekli.', 409)
        project = self.projects.get(pid)
        from app.providers.images import GeminiImageProvider
        provider = GeminiImageProvider(self.settings.gemini_config().get('api_key', ''), images['gemini_model'])
        image = provider.generate_image(f'Cinematic YouTube thumbnail background, no text, no logos, 16:9, about: {project["topic"]}', cost_confirmed=True)
        folder = self._folder(pid, 'frames')
        from PIL import Image
        picture = Image.open(BytesIO(image['data'])).convert('RGB').resize((1280, 720))
        name = 'ai-background.jpg'; picture.save(folder / name, 'JPEG', quality=92)
        package = self._load(pid)
        package['frames'] = [{'id': name, 'time': None, 'score': None, 'ai': True, 'url': f'/api/projects/{pid}/youtube/files/frames/{name}'}] + [f for f in package.get('frames', []) if not f.get('ai')]
        self._save(pid, package)
        return package['frames']

    def thumbnails(self, pid, payload):
        if not isinstance(payload, dict) or set(payload) - {'frame', 'text'}:
            raise ProjectError('Kapak seçimlerini kontrol edin.')
        package = self._load(pid)
        frame = next((f for f in package.get('frames', []) if f['id'] == payload.get('frame')), None)
        if not frame: raise ProjectError('Önce önerilen karelerden birini seçin.', 409)
        text = ' '.join(str(payload.get('text', '')).split())
        if not 1 <= len(text.split()) <= 4 or len(text) > 40:
            raise ProjectError('Kapak yazısı 1–4 kelime ve en fazla 40 karakter olmalı.')
        title = package.get('chosen_title', '')
        warning = '' if not title or complements(text, title) else 'Kapak yazısı başlığı tekrar ediyor; başlığı tamamlayan farklı kelimeler daha etkili olur.'
        kit = self.channels.for_project(pid)['style']
        base = self._folder(pid, 'frames') / frame['id']
        out = []
        for layout in LAYOUTS:
            data = compose(base, text, kit, layout)
            name = f'thumb-{layout}-{hashlib.sha256(data).hexdigest()[:10]}.png'
            (self._folder(pid, 'thumbnails') / name).write_bytes(data)
            out.append({'layout': layout, 'label': LAYOUT_LABELS[layout], 'id': name, 'size': len(data),
                        'url': f'/api/projects/{pid}/youtube/files/thumbnails/{name}'})
        package.update(thumbnail_text=text, thumbnail_frame=frame['id'], thumbnails=out, thumbnail_warning=warning)
        self._save(pid, package)
        return {'thumbnails': out, 'warning': warning}

    def file(self, pid, kind, name):
        if kind not in ('frames', 'thumbnails') or not re.fullmatch(r'[\w.-]{1,80}\.(jpg|png)', name):
            raise ProjectError('Dosya bulunamadı.', 404)
        path = self._folder(pid, kind) / name
        if linked(path) or not path.is_file(): raise ProjectError('Dosya bulunamadı.', 404)
        return path


def compose(base_path, text, kit, layout):
    """1280x720 PNG: frame + big short text + accent elements in kit style."""
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    from app.channels import FONTS
    from app.motion.templates import _font
    p = kit['palette']
    rgb = lambda h, a=255: (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)
    image = Image.open(base_path).convert('RGB').resize((1280, 720))
    image = ImageEnhance.Contrast(ImageEnhance.Color(image).enhance(1.25)).enhance(1.12)
    canvas = image.convert('RGBA')
    overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    file = FONTS[kit.get('heading_font', 'montserrat')][1]
    upper = text.upper() if kit.get('heading_font') in ('bebas', 'oswald', 'montserrat') else text
    if layout == 'left':
        for x in range(760):  # dark gradient behind the text
            draw.line([(x, 0), (x, 720)], fill=(0, 0, 0, int(200 * (1 - x / 760))))
        size = 150
        lines = upper.split()
        while size > 60 and max(_font(file, size, True).getlength(w) for w in lines) > 640: size -= 6
        font = _font(file, size, True)
        y = 360 - len(lines) * size * .55
        for i, w in enumerate(lines):
            fill = rgb(p['accent']) if i == len(lines) - 1 else rgb(p['text'])
            draw.text((64, y + i * size * 1.05), w, font=font, fill=fill, stroke_width=6, stroke_fill=(0, 0, 0, 230))
        draw.polygon([(790, 330), (900, 330), (900, 290), (990, 360), (900, 430), (900, 390), (790, 390)], fill=rgb(p['accent']), outline=(0, 0, 0, 200))
    elif layout == 'banner':
        draw.rectangle([0, 520, 1280, 720], fill=rgb(p['accent'], 235))
        size = 120
        while size > 50 and _font(file, size, True).getlength(upper) > 1180: size -= 6
        font = _font(file, size, True)
        draw.text((640, 620), upper, font=font, fill=rgb(p['background']), anchor='mm')
        draw.ellipse([820, 90, 1140, 410], outline=rgb(p['accent']), width=16)
    else:  # frame
        draw.rectangle([0, 0, 1279, 719], outline=rgb(p['accent']), width=26)
        size = 110
        lines = upper.split()
        while size > 50 and max(_font(file, size, True).getlength(w) for w in lines) > 560: size -= 6
        font = _font(file, size, True)
        for i, w in enumerate(lines):
            draw.text((1220, 70 + i * size * 1.05), w, font=font, fill=rgb(p['text']), anchor='ra', stroke_width=7, stroke_fill=(0, 0, 0, 235))
        draw.polygon([(380, 520), (470, 430), (440, 410), (560, 390), (540, 510), (510, 480), (420, 570)], fill=rgb(p['accent']), outline=(0, 0, 0, 200))
    canvas = Image.alpha_composite(canvas, overlay).convert('RGB')
    out = BytesIO(); canvas.save(out, 'PNG', optimize=True)
    return out.getvalue()
