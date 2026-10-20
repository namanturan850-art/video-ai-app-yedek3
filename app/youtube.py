"""YouTube preparation: titles, description (hook, summary, chapters, stock
credits, hashtags) and tags. Nothing is uploaded and no thumbnail is made.

Text comes from the AI engine (Gemini by default) and is checked here with
hard rules: title ≤ 97 characters (the AI shortens it; words are never cut),
tags ≤ 500 characters counted like YouTube (commas count, a tag with a space
costs +2 for its quotes), no “#” in tags; then one AI language check.
"""
import json
import re
from uuid import uuid4

from app.projects import ProjectError, linked, now

LANG = {'de': {'chapters': 'Kapitel', 'credits': 'Stockmaterial', 'intro': 'Einleitung', 'sources': 'Bildquellen'},
        'en': {'chapters': 'Chapters', 'credits': 'Stock footage', 'intro': 'Intro', 'sources': 'Image sources'},
        'es': {'chapters': 'Capítulos', 'credits': 'Material de archivo', 'intro': 'Introducción', 'sources': 'Fuentes de las imágenes'},
        'fr': {'chapters': 'Chapitres', 'credits': 'Images d’archives', 'intro': 'Introduction', 'sources': 'Sources des images'},
        'tr': {'chapters': 'Bölümler', 'credits': 'Stok görüntüler', 'intro': 'Giriş', 'sources': 'Görsel kaynakları'}}
TEXT_SCHEMA = {'type': 'object', 'additionalProperties': False,
               'required': ['titles', 'hook', 'summary', 'tags', 'hashtags', 'chapter_titles'],
               'properties': {'titles': {'type': 'array', 'items': {'type': 'string'}}, 'hook': {'type': 'string'}, 'summary': {'type': 'string'},
                              'tags': {'type': 'array', 'items': {'type': 'string'}}, 'hashtags': {'type': 'array', 'items': {'type': 'string'}},
                              'chapter_titles': {'type': 'array', 'items': {'type': 'string'}}}}
SHORTEN_SCHEMA = {'type': 'object', 'required': ['titles'], 'properties': {'titles': {'type': 'array', 'items': {'type': 'string'}}}}
CHECK_SCHEMA = {'type': 'object', 'required': ['titles', 'hook', 'summary', 'chapter_titles', 'tags', 'issues'],
                'properties': {'titles': {'type': 'array', 'items': {'type': 'string'}}, 'hook': {'type': 'string'}, 'summary': {'type': 'string'},
                               'chapter_titles': {'type': 'array', 'items': {'type': 'string'}}, 'tags': {'type': 'array', 'items': {'type': 'string'}},
                               'issues': {'type': 'array', 'items': {'type': 'string'}}}}
TITLE_MAX = 97
TAGS_MAX = 500


def stamp(seconds):
    seconds = int(seconds)
    return f'{seconds // 3600}:{seconds % 3600 // 60:02}:{seconds % 60:02}' if seconds >= 3600 else f'{seconds // 60}:{seconds % 60:02}'


def one_line(value, limit=10000):
    return ' '.join(str(value or '').split())[:limit]


def tags_length(tags):
    """Length as YouTube counts it: commas between tags count, and a tag that
    contains a space is quoted (+2 characters)."""
    return sum(len(t) + (2 if ' ' in t else 0) for t in tags) + max(0, len(tags) - 1)


def clean_tags(values, limit=TAGS_MAX):
    """Comma-separated, no '#', no duplicates (case-insensitive), order kept
    (most searched first); the weakest (last) tags are dropped until ≤ 500."""
    out, seen = [], set()
    for value in values if isinstance(values, list) else []:
        for part in str(value).split(','):
            tag = one_line(part.replace('#', ''), 100).strip(' "\'')
            if tag and tag.casefold() not in seen:
                seen.add(tag.casefold()); out.append(tag)
    while limit and out and tags_length(out) > limit:
        out.pop()
    return out


def cut_title(title):
    """Last resort only: end at a whole word within 97 characters and drop a
    dangling separator, so no word is ever cut in the middle."""
    title = one_line(title)
    if len(title) <= TITLE_MAX:
        return title
    cut = title[:TITLE_MAX + 1].rsplit(' ', 1)[0] if ' ' in title[:TITLE_MAX + 1] else title[:TITLE_MAX]
    return re.sub(r'[\s,;:|–—-]+$', '', cut)


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
        title = package.get('chosen_title', '')
        return {'project_id': pid, 'language': project['language'], 'package': package, 'video_ready': bool(render.get('ready')),
                'engine': engine, 'engine_label': {'claude': 'Claude (ücretli)', 'gemini': 'Gemini (ücretsiz kota)'}.get(engine, ''),
                'limits': {'title': TITLE_MAX, 'tags': TAGS_MAX},
                'counts': {'title': len(title), 'tags': tags_length(package.get('tags', []))},
                'ready': bool(package.get('titles')) and (package.get('proofread') or {}).get('status') == 'done' and not package['proofread'].get('stale')}

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
            if m.get('provider') == 'wikimedia':  # CC BY / BY-SA need author, licence and link: one line per file
                meta = m.get('source_metadata') or {}
                key = ('wikimedia', m.get('media_id'))
                if key in seen: continue
                seen.add(key); out.append({'provider': 'Wikimedia Commons', 'creator': meta.get('author') or m.get('creator_name', ''),
                                           'title': meta.get('title', ''), 'license': meta.get('license', ''), 'url': m.get('page_url', '')})
                continue
            if m.get('provider') == 'archive':  # PD / CC0 / CC BY / BY-SA: author, licence and link, one line per film
                meta = m.get('source_metadata') or {}
                key = ('archive', m.get('media_id'))
                if key in seen: continue
                seen.add(key); out.append({'provider': 'Internet Archive', 'creator': meta.get('author') or m.get('creator_name', ''),
                                           'title': meta.get('title', ''), 'license': meta.get('license', ''), 'url': m.get('page_url', '')})
                continue
            if m.get('provider') == 'nasa':  # not copyrighted; NASA still asks for a simple credit
                meta = m.get('source_metadata') or {}
                key = ('nasa', m.get('media_id'))
                if key in seen: continue
                seen.add(key); out.append({'provider': 'NASA', 'creator': meta.get('center') or 'NASA',
                                           'title': meta.get('title', ''), 'license': '', 'url': m.get('page_url', '')})
                continue
            template = ((m.get('source_metadata') or {}).get('motion') or {}).get('template')
            if m.get('provider') == 'generated' and template in ('map', 'route', 'empire', 'zoom') and ('geonames',) not in seen:
                seen.add(('geonames',))  # place data of the map infographics: CC BY 4.0 asks for this credit
                out.append({'provider': 'GeoNames', 'creator': 'GeoNames', 'title': 'Place data / Yer verisi', 'license': 'CC BY 4.0', 'url': 'https://www.geonames.org'})
                continue
            if m.get('provider') not in ('pexels', 'pixabay'): continue
            key = (m['provider'], m.get('creator_name', ''))
            if key in seen: continue
            seen.add(key); out.append({'provider': m['provider'].title(), 'creator': m.get('creator_name', ''), 'url': m.get('page_url', '')})
        return out[:40]

    def _ai(self):
        engine = self.settings.ai_engine()
        if not engine: raise ProjectError('YouTube metinleri için Ayarlar → Gemini bölümünde ücretsiz anahtarınızı kaydedip bir model seçin.', 422)
        from app.providers.factory import make_script_provider
        return engine, make_script_provider(engine, self.settings)

    def fit_titles(self, ai, titles, language):
        """Titles over 97 characters go back to the AI once to be rewritten
        shorter (meaning kept, whole words); a word-boundary end is the last
        resort, never a cut inside a word."""
        long = [t for t in titles if len(t) > TITLE_MAX]
        if long:
            try:
                data = ai.complete_json('youtube_title_shorten', f'Shorten each YouTube title to AT MOST {TITLE_MAX} characters (spaces and emoji count). '
                                        f'Keep the language ({language}), the meaning and the hook; write a complete, natural title, never cut a word or '
                                        'leave a half sentence. Return them in the same order.\nTITLES:\n' + '\n'.join(long), SHORTEN_SCHEMA, effort='low', max_tokens=1500)
                short = [one_line(t) for t in data.get('titles', []) if isinstance(t, str)]
            except Exception:
                short = []
            fixed = dict(zip(long, short)) if len(short) == len(long) else {}
            titles = [fixed.get(t, t) if len(fixed.get(t, t)) <= TITLE_MAX else t for t in titles]
        return [cut_title(t) for t in titles]

    def generate_text(self, pid):
        project = self.projects.get(pid)
        current = self.scripts.repository.view(pid)['current']
        if not current: raise ProjectError('Önce Metin ekranında metninizi yapıştırıp kaydedin.', 409)
        engine, ai = self._ai()
        chapters = self.chapters(pid)
        channel = self.channels.for_project(pid)
        language = project['language']
        sources = getattr(self.scripts, 'sources', None)
        reference = sources.title_hint(pid) if sources else ''
        prompt = (f'Prepare YouTube metadata for this video. Write EVERYTHING in the video language "{language}": natural, grammatical, '
                  'no literal translations, no half sentences.\n'
                  f'Channel: {channel["name"]} ({channel["niche"]}). Topic: {project["topic"]}.\n'
                  f'titles: exactly 5 different titles with a high click-through rate: curiosity, a clear promise and a strong hook, but honest '
                  f'(no false claims, no ALL CAPS). Each title AT MOST {TITLE_MAX} characters including spaces and emoji (aim for 55-90).\n'
                  + (f'{reference}\nUse that strategy as an example only; never translate the reference title.\n' if reference else '') +
                  'hook: 2 short lines (separated by a newline) that make people want to watch. summary: 2-4 sentences about the content.\n'
                  'tags: 12-25 relevant, distinct search keywords, the most searched first; NO "#" characters; together under 450 characters.\n'
                  'hashtags: 3 hashtags with # (they go in the description, not in the tags).\n'
                  f'chapter_titles: exactly {len(chapters)} short chapter titles (2-5 words) for these chapters in order.\n'
                  'Use only facts from the script.\n\nCHAPTERS:\n' + '\n'.join(f'{i + 1}. {c["narration"][:300]}' for i, c in enumerate(chapters))
                  + '\n\nSCRIPT:\n' + current['text'][:12000])
        data = ai.complete_json('youtube_text', prompt, TEXT_SCHEMA, effort='low', max_tokens=3000)
        titles = [one_line(t, 300) for t in data.get('titles', []) if isinstance(t, str) and t.strip()][:5]
        if not titles: raise ProjectError('Yapay zekâ başlık döndürmedi; tekrar deneyin.', 502)
        hashtags = ['#' + re.sub(r'\W', '', one_line(h, 40).lstrip('#')) for h in data.get('hashtags', []) if isinstance(h, str) and re.sub(r'\W', '', h)][:3]
        names = [one_line(n, 60) for n in data.get('chapter_titles', []) if isinstance(n, str)]
        for i, c in enumerate(chapters):
            c['title'] = names[i] if i < len(names) and names[i] else c['fallback']
        package = self._load(pid)
        for old in ('thumbnail_texts', 'thumbnail_text', 'thumbnail_frame', 'thumbnails', 'thumbnail_warning', 'frames'):
            package.pop(old, None)  # thumbnail feature removed
        package.update(titles=[], hook='\n'.join(one_line(line, 150) for line in str(data.get('hook', '')).replace(' / ', '\n').splitlines() if line.strip())[:300],
                       summary=one_line(data.get('summary', ''), 1200), tags=data.get('tags', []), hashtags=hashtags,
                       chapters=[{k: c[k] for k in ('start', 'title')} for c in chapters], credits=self.credits(pid), engine=engine,
                       generated_at=now(), proofread=None)
        self._apply(package, titles, ai, language)
        self._save(pid, package)
        return self.proofread(pid)  # one language check before it is shown as ready

    def _apply(self, package, titles, ai, language):
        titles = self.fit_titles(ai, titles, language)
        package['titles'] = [{'text': t, 'length': len(t)} for t in titles]
        if package.get('chosen_title') not in titles: package['chosen_title'] = titles[0]
        package['tags'] = clean_tags(package.get('tags', []))
        package['description'] = self.description(package, language)

    def proofread(self, pid):
        """Final AI check of titles, hook, summary, chapter titles and tags for
        meaning and grammar in the video language; fixes are applied and the
        hard rules re-checked. Chapter times and credits are never sent."""
        project = self.projects.get(pid)
        package = self._load(pid)
        if not package.get('titles'): raise ProjectError('Önce “Önerileri oluştur” deyin.', 409)
        engine, ai = self._ai()
        language = project['language']
        titles = [t['text'] for t in package['titles']]
        chosen = package.get('chosen_title', '')
        if chosen and chosen not in titles: titles = [chosen] + titles[:4]
        chapter_titles = [c['title'] for c in package.get('chapters', [])]
        data = ai.complete_json('youtube_check', f'Proofread this YouTube metadata written in "{language}". Fix ONLY real problems: grammar, spelling, '
                                'wrong or unnatural wording, literal translations, half sentences, meaning errors. Keep meaning, tone and length; '
                                f'titles stay at most {TITLE_MAX} characters; tags stay plain keywords without "#". Return the same number of titles, '
                                'chapter_titles and tags in the same order (corrected), and list each change in issues (Turkish, short); empty issues if all is fine.\n'
                                + json.dumps({'titles': titles, 'hook': package.get('hook', ''), 'summary': package.get('summary', ''),
                                              'chapter_titles': chapter_titles, 'tags': package.get('tags', [])}, ensure_ascii=False),
                                CHECK_SCHEMA, effort='low', max_tokens=3000)
        same = lambda key, old: [one_line(x, 300) for x in data.get(key, [])] if isinstance(data.get(key), list) and len(data[key]) == len(old) and all(isinstance(x, str) and x.strip() for x in data[key]) else old
        new_titles = same('titles', titles)
        if chosen in titles: package['chosen_title'] = new_titles[titles.index(chosen)]
        if isinstance(data.get('hook'), str) and data['hook'].strip():
            package['hook'] = '\n'.join(one_line(line, 150) for line in data['hook'].splitlines() if line.strip())[:300]
        if isinstance(data.get('summary'), str) and data['summary'].strip(): package['summary'] = one_line(data['summary'], 1200)
        for c, name in zip(package.get('chapters', []), same('chapter_titles', chapter_titles)): c['title'] = one_line(name, 60)
        package['tags'] = same('tags', package.get('tags', []))
        issues = [one_line(x, 200) for x in data.get('issues', []) if isinstance(x, str) and x.strip()][:12]
        self._apply(package, new_titles, ai, language)
        if len(package['chosen_title']) > TITLE_MAX: package['chosen_title'] = cut_title(package['chosen_title'])
        package['proofread'] = {'status': 'done', 'checked_at': now(), 'issues': issues, 'engine': engine, 'stale': False}
        self._save(pid, package)
        return self.view(pid)

    @staticmethod
    def description(package, language):
        labels = LANG.get(language, LANG['en'])
        hook = str(package.get('hook', '')).replace('\\n', '\n')
        parts = [hook.strip(), package.get('summary', '').strip()]
        if package.get('chapters'):
            parts.append(labels['chapters'] + ':\n' + '\n'.join(f'{stamp(c["start"])} {c["title"]}' for c in package['chapters']))
        stock = [c for c in package.get('credits') or [] if not c.get('license')]
        sources = [c for c in package.get('credits') or [] if c.get('license')]
        if stock:
            parts.append(labels['credits'] + ': ' + ', '.join(sorted({c['provider'] for c in stock}))
                         + '\n' + '\n'.join(f'{c["provider"]} — {c["creator"]}' for c in stock if c['creator']))
        if sources:  # “Görsel kaynakları”: title — author, licence (Wikimedia Commons) link
            parts.append(labels['sources'] + ':\n' + '\n'.join(
                f'{(c.get("title") or "")[:70]} — {c["creator"][:60]}, {c["license"]} ({c["provider"]}) {c["url"]}' for c in sources[:25]))
        if package.get('hashtags'):
            parts.append(' '.join(package['hashtags']))
        return '\n\n'.join(p for p in parts if p)[:5000]

    def update(self, pid, payload):
        allowed = {'chosen_title', 'description', 'tags', 'hook', 'summary'}
        if not isinstance(payload, dict) or not payload or set(payload) - allowed:
            raise ProjectError('YouTube bilgilerini kontrol edin.')
        package = self._load(pid)
        notes = []
        if 'chosen_title' in payload:
            title = one_line(payload['chosen_title'])
            if not title: raise ProjectError('YouTube başlığı boş olamaz.')
            if len(title) > TITLE_MAX: raise ProjectError(f'Başlık en fazla {TITLE_MAX} karakter olabilir (şu an {len(title)}). Kısaltın.')
            package['chosen_title'] = title
        if 'description' in payload:
            if len(str(payload['description'])) > 5000: raise ProjectError('Açıklama en fazla 5000 karakter olabilir.')
            package['description'] = str(payload['description'])
        if 'tags' in payload:
            raw = payload['tags'] if isinstance(payload['tags'], list) else str(payload['tags']).split(',')
            tags, every = clean_tags(raw), clean_tags(raw, limit=None)
            if any('#' in str(t) for t in raw): notes.append('Etiketlerdeki # işaretleri kaldırıldı.')
            if len(tags) < len(every): notes.append(f'Etiketler {TAGS_MAX} karakteri aştığı için sondaki en zayıf {len(every) - len(tags)} etiket çıkarıldı.')
            package['tags'] = tags
        if package.get('proofread'): package['proofread']['stale'] = True  # owner edits: check again before “ready”
        self._save(pid, package)
        return {**self.view(pid), 'notes': notes}
