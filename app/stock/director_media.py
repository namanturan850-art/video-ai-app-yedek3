"""“Medyayı Tamamla”: the AI (Gemini free tier by default, Claude if chosen)
chooses stock media and every slot gets filled.

Chain per slot (each stock step needs the AI's approval after it has looked
at the candidates' preview frames; irrelevant media is never used to fill):
  1. stock video with the planned queries
  2. stock video with queries the AI rewrites for this slot
  3. stock image (rendered with light camera motion)
  4. media for the broader topic (still approved by the AI)
  5. very short slots (<1.5 s): continue the neighbouring shot
  6. motion graphic from the narration (only when no stock fits)
Scenes the owner marked ([HARİTA], [SAYI], [ÇİZELGE], [KARŞILAŞTIR], [LİSTE])
and scenes the director planned as motion become infographics directly.
Stock provider errors only skip that provider. AI errors never turn the rest
of the video into motion: temporary ones are waited out and retried; a
quota/key problem stops the job (finished slots stay) with a plain message.
Every search, candidate, verdict and reason is kept per slot for the screen
and for the downloadable diagnostics file.
"""
import base64
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import logging
import re
from uuid import uuid4

import httpx

from app.ai_usage import CURRENT_PROJECT
from app.projects import linked, now
from app.providers.base import ScriptProviderError
from app.stock import relevance
from app.stock.cards import render_card
from app.stock.download import asset_path, directory, safe_url
from app.stock.identities import identity_keys
from app.stock.models import StockError

LOG = logging.getLogger('uvicorn.error.stock')
STAGES = {'locked': 'Kilitli (sizin seçiminiz)', 'kept': 'Mevcut seçim · yapay zekâ onayladı',
          'stock_video': '1 · Stok video (planlanan sorgu)', 'rewritten_video': '2 · Stok video (yapay zekânın yeni sorgusu)',
          'stock_image': '3 · Stok görsel + hafif kamera hareketi', 'broader': '4 · Daha geniş konu medyası',
          'merged': '6 · Komşu çekimin devamı (çok kısa yuva)', 'card': '5 · Üretilmiş kart',
          'motion': '5 · Motion grafik (anlatımdan)', 'motion_planned': 'Motion grafik (yönetmen planı)',
          'motion_edit': 'Motion grafik (sizin düzenlemeniz)', 'motion_owner': 'İnfografik (metindeki işaretiniz)',
          'motion_balance': 'Motion grafik (dengeli kurgu)'}  # older projects only
MOTION_WARN = 25        # % of slots: above this the screen warns (too little stock footage)
QUOTE_SHARE = .30       # at most this share of motion slots may be a plain text (quote) card
CANDIDATES = 6          # at most this many candidates go to the AI per look (after a metadata pre-filter)
APPROVE_SCORE = 7       # 0-10: only 7+ stock media is ever used
SIMILAR_FRAMING = 6     # dHash bits: closer than this to the previous shot of the scene = same framing
# Never-wanted signs in provider metadata (checked before the AI look).
RED_FLAGS = {'watermark', 'watermarked', 'logo', 'logos', 'subscribe', 'intro', 'outro', 'template', 'lower third', 'green screen', 'chroma key'}
MERGE_SECONDS = 1.5
WAIT_BUDGET = 900       # seconds of rate-limit waiting per job (free tier)
UNREACHABLE = 'Yapay zekâya ulaşılamadı'  # older motion picks made while the AI was down carry this; they are retried
REVIEW_MAX = 8
# Temporary AI problems: wait and ask again (never switch the engine off).
TRANSIENT = {'rate_limit', 'quota_limit', 'upstream_error', 'gemini_timeout', 'generation_timeout', 'timeout',
             'no_internet', 'network_error', 'connection_error'}
# One answer was unusable (the engine works): that look is skipped; this many in a row stops the job.
UNUSABLE = {'invalid_response', 'incomplete_response', 'response_schema_mismatch', 'empty_response', 'thought_only_response',
            'output_limit', 'unexpected_finish_reason', 'blocked_response', 'invalid_json', 'refusal'}
UNUSABLE_LIMIT = 4
PROVIDER_DOWN = {'rate_limit', 'key_rejected', 'missing_key', 'timeout', 'connection_error', 'upstream_error', 'invalid_request', 'invalid_response'}
ERROR_TEXT = {'rate_limit': 'kullanım sınırı', 'key_rejected': 'anahtar kabul edilmedi', 'missing_key': 'anahtar yok',
              'timeout': 'zaman aşımı', 'connection_error': 'bağlantı kurulamadı', 'upstream_error': 'sunucu hatası',
              'invalid_response': 'okunamayan yanıt', 'invalid_request': 'istek reddedildi', 'quota_limit': 'kota/hız sınırı',
              'gemini_timeout': 'zaman aşımı', 'generation_timeout': 'zaman aşımı', 'no_internet': 'internet bağlantısı yok',
              'network_error': 'bağlantı hatası'}
JUDGE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['verdicts'],
                'properties': {'verdicts': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['candidate', 'score', 'approved', 'reason'],
                    'properties': {'candidate': {'type': 'integer'}, 'score': {'type': 'integer'},
                                   'approved': {'type': 'boolean'}, 'reason': {'type': 'string'}}}}}}
PLACE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['found', 'lat', 'lon'],
                'properties': {'found': {'type': 'boolean'}, 'lat': {'type': 'number'}, 'lon': {'type': 'number'}}}
INFOGRAPHIC = ('map', 'number', 'timeline', 'compare', 'list')
QUERY_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['queries'],
                'properties': {'queries': {'type': 'array', 'items': {'type': 'string'}}}}
REVIEW_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['replace'],
                 'properties': {'replace': {'type': 'array', 'items': {
                     'type': 'object', 'additionalProperties': False, 'required': ['slot', 'reason'],
                     'properties': {'slot': {'type': 'integer'}, 'reason': {'type': 'string'}}}}}}


def _rejected_path(projects, project_id):
    folder = directory(projects, project_id)
    if linked(folder): raise StockError('local_storage', 'Medya klasörü dış konuma bağlı; işlem durduruldu.', 409)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / 'rejected.json'


def rejected_media(projects, project_id):
    """Stock picks the owner rejected with “Yeniden seçtir” (project-wide)."""
    try:
        path = _rejected_path(projects, project_id)
        data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
        return [r for r in data if isinstance(r, dict) and {'provider', 'media_type', 'media_id'} <= set(r)]
    except (OSError, ValueError, StockError):
        return []


def remember_rejection(projects, project_id, entry):
    current = [r for r in rejected_media(projects, project_id) if (r['provider'], r['media_type'], r['media_id']) != (entry['provider'], entry['media_type'], entry['media_id'])]
    path = _rejected_path(projects, project_id)
    temporary = path.with_name('.rejected-' + hashlib.sha256(path.as_posix().encode()).hexdigest()[:8])
    temporary.write_text(json.dumps((current + [entry])[-200:], ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def key(media):
    return (media['provider'], media['media_type'], media['media_id'])


def used_seconds(slot):
    return float(slot.get('actual_duration_hint') or slot['duration'])


def is_generated(media):
    return bool(media and media.get('provider') == 'generated')


def is_card(media):
    return bool(media and media.get('provider') == 'generated')


def technical(media, need):
    """Hard limits only; content is the AI's call. Portrait/square is allowed
    (rendered on a blurred background) but ranked after landscape."""
    short = min(media['width'], media['height'])
    if media['media_type'] == 'video':
        if short < 720: return 'resolution'
        if (media.get('duration') or 0) + .05 < need: return 'duration'
    elif short < 540:
        return 'resolution'
    return None


def sentence_at(text, fraction):
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', ' '.join(text.split())) if p.strip()]
    if not parts: return ''
    words = [len(p.split()) for p in parts]
    target, total = fraction * sum(words), 0
    for part, count in zip(parts, words):
        total += count
        if total >= target: return part
    return parts[-1]


def card_spec(slot, scene, used=frozenset()):
    """Card text is always a phrase from the narration (or the planned card).
    Prefers the sentence spoken during the slot, then a not-yet-shown one."""
    if scene.get('card_kind') and scene.get('card_text') and scene['card_text'] not in used:
        return scene['card_kind'], scene['card_text']
    span = max(.001, scene['end_estimate'] - scene['start_estimate'])
    middle = (slot['estimated_start'] + slot['estimated_end']) / 2
    fraction = min(1, max(0, (middle - scene['start_estimate']) / span))
    here = sentence_at(scene.get('narration_text', ''), fraction)
    others = [sentence_at(scene.get('narration_text', ''), f / 10) for f in sorted(range(11), key=lambda f: abs(f / 10 - fraction))]
    choices = [spec_for(s, scene) for s in dict.fromkeys([here, *others]) if s]
    return next((c for c in choices if c[1] not in used), choices[0] if choices else ('title', scene.get('visual_intent', '')[:60]))


def spec_for(sentence, scene):
    words = sentence.rstrip('.!?…').split()
    number = next((i for i, w in enumerate(words) if re.search(r'\d', w)), None)
    if number is not None:
        start = max(0, number - 3)
        return 'number', ' '.join(words[start:start + 7])
    if 3 <= len(words) <= 14:
        return 'quote', ' '.join(words)
    return 'title', ' '.join(words[:7]) or scene.get('visual_intent', '')[:60]


class MediaDirector:
    def __init__(self, service, job):
        self.service, self.job, self.pid = service, job, job['project_id']
        self.progress = job['progress']
        self.ai, self.ai_error, self.waited, self.unusable = None, '', 0, 0
        self.unavailable = dict(self.progress.get('unavailable_providers', {}))
        self.rejected, self.rejected_keys, self.rejected_hashes = [], set(), set()
        self.filtered_keys, self.ai_rejected_keys, self.looks, self.scene_last = set(), set(), {}, {}
        self.scene_order, self.scene_text, self.topic, self.owner = [], {}, '', {}

    # ---- AI engine---------------------------------------------------------
    def connect(self):
        engine = self.service.settings.ai_engine()
        self.engine = engine or 'gemini'
        self.label = 'Claude' if engine == 'claude' else 'Gemini'
        try:
            factory = getattr(self.service, 'ai_factory', None)
            if factory is None:
                from app.providers.factory import make_script_provider
                factory = lambda: make_script_provider(self.engine, self.service.settings)
            self.ai = factory()
        except ScriptProviderError as error:
            self._pause(error)

    def _pause(self, error, waited_out=False):
        """The AI cannot judge right now: the job stops instead of filling the
        remaining slots with motion. Finished slots stay; the rest stay
        pending, and Medyayı Tamamla / Devam Et continues from there."""
        category = getattr(error, 'category', '') or 'provider_error'
        retry = int(getattr(error, 'retry_after', 0) or 0)
        self.ai_error = str(error)
        self.progress['ai_failure'] = {'category': category, 'message': str(error)[:300], 'upstream_status': getattr(error, 'upstream_status', None),
                                       'stage': getattr(error, 'stage', ''), 'waited_seconds': self.waited, 'at': now(),
                                       'slot_id': self.progress.get('slot_id')}
        raise StockError('ai_paused', pause_message(self.label, category, retry, waited_out))

    def _ask(self, purpose, prompt, schema, images=(), max_tokens=2000):
        for attempt in range(6):
            try:
                answer = self.ai.complete_json(purpose, prompt, schema, images=list(images), effort='low', max_tokens=max_tokens)
                self.unusable = 0
                return answer
            except ScriptProviderError as error:
                category = getattr(error, 'category', '')
                if category in UNUSABLE:
                    # This one answer is unusable; the engine itself still works.
                    self.unusable += 1
                    if self.unusable >= UNUSABLE_LIMIT: self._pause(error)
                    return None
                if category not in TRANSIENT:
                    self._pause(error)  # daily quota, key or model problem: waiting here does not help
                # Temporary (per-minute limit, time-out, 5xx, network): wait and try again.
                pause = min(60, max(5, int(getattr(error, 'retry_after', 0) or 20)))
                if attempt >= 5 or self.waited + pause > WAIT_BUDGET:
                    self._pause(error, waited_out=True)
                self.progress['message'] = f'{self.label} geçici olarak yanıt vermiyor ({ERROR_TEXT.get(category, "geçici hata")}): {pause} sn bekleniyor, sonra devam edilecek'
                self.service._checkpoint(self.job, self.progress, light=True)
                getattr(self.service, 'ai_sleep', _sleep)(pause, self.service)
                if self.service.closed: raise StockError('interrupted', 'İşlem durdu; tamamlanan yuvalar korundu. Medyayı Tamamla ile sürdürün.')
                self.waited += pause
        return None

    # ---- previews ----------------------------------------------------------
    def frame_urls(self, media):
        frames = list((media.get('source_metadata') or {}).get('preview_frames') or [])
        if media.get('preview_url') and media['preview_url'] not in frames:
            frames.insert(0, media['preview_url'])
        return frames[:3 if media['media_type'] == 'video' else 1]

    def thumbnail(self, url, provider):
        """Cached preview bytes as an image block, or None. Never raises."""
        try:
            safe_url(url, provider)
            folder = directory(self.service.projects, self.pid) / 'thumbs'
            if linked(folder): return None
            folder.mkdir(exist_ok=True)
            path = folder / (hashlib.sha256(url.encode()).hexdigest()[:32] + '.img')
            if path.is_file():
                data = path.read_bytes()
            else:
                fetch = getattr(self.service, 'fetch_thumbnail', None) or fetch_thumbnail
                data = fetch(url)
                if not data: return None
                path.write_bytes(data)
            data = shrink(data)
            mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/webp' if data[8:12] == b'WEBP' else 'image/jpeg' if data.startswith(b'\xff\xd8') else None
            if not mime or len(data) > 3_000_000: return None
            return {'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': base64.b64encode(data).decode()}}
        except (StockError, OSError, ValueError):
            return None

    # ---- judging -----------------------------------------------------------
    def brief(self, slot, scene):
        index = self.scene_order.index(scene['scene_id']) if scene.get('scene_id') in self.scene_order else -1
        before = self.scene_text.get(self.scene_order[index - 1], '') if index > 0 else ''
        after = self.scene_text.get(self.scene_order[index + 1], '') if 0 <= index < len(self.scene_order) - 1 else ''
        hints = '; '.join(f'{h.get("type")}: {h.get("value")}' for h in scene.get('owner_hints') or [])
        owner = '; '.join(f'“{r.get("description", "")[:60]}” ({r.get("reason") or "neden yazılmadı"})' for r in self.rejected[-6:])
        return (f'Video topic: {self.topic}\n'
                f'Previous sentence: "{sentence_at(before, 1.0)}"\nNext sentence: "{sentence_at(after, 0.0)}"\n'
                + (f'Proper names (priority): {", ".join(scene.get("entities") or [])}\n' if scene.get('entities') else '')
                + (f'Owner’s own visual note (top priority): {hints}\n' if hints else '')
                + (f'The owner REJECTED these earlier picks (avoid similar footage): {owner}\n' if owner else '') +
                f'Narration of this shot (spoken language {scene.get("stock_query_language", "")}): '
                f'"{sentence_at(scene.get("narration_text", ""), .5) if used_seconds(slot) < 6 else scene.get("narration_text", "")[:600]}"\n'
                f'Scene narration: "{scene.get("narration_text", "")[:900]}"\n'
                f'Visual goal: {slot.get("visual_goal") or scene.get("visual_intent", "")}\n'
                f'MUST show: {scene.get("must_show") or "(not specified)"}\n'
                f'MUST NOT show: {scene.get("must_not_show") or "(not specified)"}\n'
                f'Shot length: {used_seconds(slot):.1f} s. Mood: {scene.get("mood", "")}.')

    def frames(self, media):
        """Start/middle/end frames of a video candidate (one picture for an
        image). Provider preview pictures first; a clip with fewer than three
        gets them from its smallest rendition."""
        blocks = [b for b in (self.thumbnail(u, media['provider']) for u in self.frame_urls(media)) if b]
        sample = (media.get('source_metadata') or {}).get('sample_url')
        if media['media_type'] == 'video' and len(blocks) < 3 and sample:
            extra = self.sample_frames(media, sample)
            if len(extra) >= len(blocks): blocks = extra
        return blocks[:3]

    def sample_frames(self, media, url):
        try:
            safe_url(url, media['provider'])
            folder = directory(self.service.projects, self.pid) / 'thumbs'
            if linked(folder): return []
            folder.mkdir(exist_ok=True)
            stem = hashlib.sha256(url.encode()).hexdigest()[:32]
            paths = [folder / f'{stem}-f{i}.img' for i in range(3)]
            if not all(p.is_file() for p in paths):
                fetch = getattr(self.service, 'fetch_video_frames', None) or extract_frames
                data = fetch(url, float(media.get('duration') or 0))
                if len(data) < 3: return []
                for path, item in zip(paths, data): path.write_bytes(item)
            out = []
            for path in paths:
                data = shrink(path.read_bytes())
                if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG'):
                    out.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg',
                                                            'data': base64.b64encode(data).decode()}})
            return out
        except (StockError, OSError, ValueError):
            return []

    def judge(self, slot, scene, pool):
        """The AI looks at up to six candidates (three frames each for video);
        returns verdicts by key."""
        blocks, listed = [], []
        for index, media in enumerate(pool, 1):
            frames = self.frames(media)
            if not frames:
                slot['director']['skipped_no_preview'] = slot['director'].get('skipped_no_preview', 0) + 1
                continue
            orientation = 'landscape' if media['width'] > media['height'] else 'portrait/square (will be shown on a blurred background)'
            blocks.append({'type': 'text', 'text': f'Candidate {index}: {media["media_type"]}, {media["width"]}x{media["height"]}, {orientation}'
                                                   + (f', {media["duration"]:.0f} s' if media.get('duration') else '')
                                                   + f'. Provider tags: {media.get("description", "")[:200]}'})
            blocks.extend(frames)
            listed.append(index)
        if not listed: return {}
        prompt = (self.brief(slot, scene) + '\n\nYou are choosing documentary B-roll for this shot. For EVERY candidate above '
                  '(video candidates show their start, middle and end frames), give score 0-10 using these criteria: '
                  '(1) does it show what the narration says right now (the visual goal / MUST show)? '
                  '(2) do the period, place and setting fit (no modern things in historical scenes, right environment, day/night)? '
                  '(3) is anything from the MUST-NOT list visible? (4) any text, watermark or logo on screen? (5) image quality. '
                  'A score of 7 or more means a viewer would see exactly what is being said; unrelated, generic-but-wrong, '
                  'anachronistic, watermarked or low-quality footage scores at most 4. approved=true only for 7+ with nothing from '
                  'the MUST-NOT list. reason: ONE short sentence in Turkish for the channel owner. '
                  f'Candidates to rate: {listed}.')
        answer = self._ask('media_select', prompt, JUDGE_SCHEMA, blocks)
        verdicts = {}
        for item in (answer or {}).get('verdicts', []):
            index = item.get('candidate')
            if isinstance(index, int) and index in listed:
                try: score = max(0, min(10, round(float(item.get('score', 0)))))
                except (TypeError, ValueError): score = 0
                verdicts[key(pool[index - 1])] = {'score': score,
                                                  'approved': item.get('approved') is not False and score >= APPROVE_SCORE,
                                                  'reason': ' '.join(str(item.get('reason', '')).split())[:300]}
        return verdicts

    def rewrite(self, slot, scene, tried, broader=False):
        if broader:
            ask = ('Stock searches for this shot found nothing usable. Give 3 BROADER English stock-footage queries for the '
                   'wider topic (setting, era, environment, related everyday activity) that still fit the narration and the '
                   'MUST/MUST-NOT notes. 2-4 words each, concrete and filmable.')
        else:
            ask = ('These stock queries found nothing usable for this shot. Write 3 NEW English stock-footage queries with '
                   'different angles: concrete objects, places, actions or atmosphere a camera could film. 2-4 words each, '
                   'no names of people unless famous public places/things, no abstract words.')
        answer = self._ask('media_queries', self.brief(slot, scene) + f'\nAlready tried: {", ".join(tried)[:600]}\n' + ask, QUERY_SCHEMA, max_tokens=600)
        queries = [' '.join(str(q).split())[:80] for q in (answer or {}).get('queries', []) if isinstance(q, str) and q.strip()]
        return [q for q in dict.fromkeys(queries) if q.casefold() not in {t.casefold() for t in tried}][:3]

    # ---- searching -----------------------------------------------------------
    def providers(self):
        names = [n for n in ('pexels', 'pixabay') if self.service.settings.stock_config(n).get('api_key')]
        return [n for n in names if n not in self.unavailable]

    def search(self, slot, kinds, query, log):
        found = []
        for kind in kinds:
            for name in self.providers():
                entry = {'provider': name, 'media_type': kind, 'query': query}
                self.progress['message'] = f'Yuva {slot["order"]} · {name.title()} {"video" if kind == "video" else "görsel"} aranıyor: “{query}”'
                self.service._checkpoint(self.job, self.progress, light=True)
                try:
                    results, _, cached = self.service._cache_search(self.pid, name, kind, query)
                except StockError as error:
                    entry.update(error=error.category, error_text=ERROR_TEXT.get(error.category, 'hata'))
                    if error.category in PROVIDER_DOWN:
                        self.unavailable[name] = error.category
                        self.progress['unavailable_providers'] = self.unavailable
                    log['searches'].append(entry)
                    continue
                except Exception:  # an unexpected provider answer never stops the chain
                    LOG.warning('stock operation=director_search category=unexpected provider=%s', name)
                    entry.update(error='unexpected', error_text='beklenmeyen yanıt')
                    log['searches'].append(entry)
                    continue
                if len(results) < 15:  # thin first page: one more page (cached the same way)
                    try:
                        more, _, _ = self.service._cache_search(self.pid, name, kind, query, page=2)
                        results = list(results) + [m for m in more if key(m) not in {key(r) for r in results}]
                    except Exception:
                        pass
                entry.update(results=len(results), cached=cached)
                log['searches'].append(entry)
                found.extend(results)
        return found

    def segment(self, media, need):
        """Same clip in a second slot: only a different, non-overlapping part."""
        taken = self.usage.get(key(media), [])
        if media['media_type'] != 'video' or not taken: return None if taken else 0.
        start = max(end for _, end in taken) + .5
        return round(start, 3) if start + need + .3 <= float(media.get('duration') or 0) else None

    def prefilter(self, media, scene):
        """Metadata check before any AI look: owner-rejected picks, watermark/
        logo signs and anything from the scene's MUST-NOT list in the tags."""
        if key(media) in self.rejected_keys or (media.get('sha256') and media['sha256'] in self.rejected_hashes):
            return 'owner_rejected'
        tags = ' ' + relevance.normalized(f'{media.get("description", "")} {media.get("query_used", "")}') + ' '
        if any(f' {flag} ' in tags for flag in RED_FLAGS):
            return 'watermark_or_logo'
        for phrase in re.split(r'[,;/]| or | and ', relevance.normalized(scene.get('must_not_show') or '')):
            words = [w for w in re.findall(r'[a-z0-9]+', phrase) if len(w) > 2 and w not in relevance.STOP and w not in ('any', 'modern', 'people')]
            if words and all(f' {w} ' in tags or f' {w}s ' in tags for w in words[-2:]):
                return 'must_not_show'
        return None

    def pool(self, slot, results, log, exclude, scene=None):
        need, seen, pool = used_seconds(slot), set(), []
        rejected = log.setdefault('rejected', {})
        for media in results:
            k = key(media)
            if k in seen or k in exclude: continue
            seen.add(k)
            reason = technical(media, need)
            if reason is None and self.segment(media, need) is None: reason = 'used_elsewhere'
            if reason is None and k in log['judged'] and not log['judged'][k]['approved']: reason = 'ai_rejected_before'
            if reason is None: reason = self.prefilter(media, scene or {})
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                if reason in ('owner_rejected', 'watermark_or_logo', 'must_not_show') and k not in self.filtered_keys:
                    self.filtered_keys.add(k); self.progress['irrelevant_filtered'] = len(self.filtered_keys) + self.progress.get('ai_rejected', 0)
                continue
            pool.append(relevance.annotate(media, slot['relevance_profile'], 1, media.get('query_used', '')))
        pool.sort(key=lambda m: (m['width'] > m['height'], key(m) not in self.usage, relevance.rank(m, slot)), reverse=True)
        return pool

    def look(self, media):
        """(average colour, dHash) of the first preview frame, or None."""
        if key(media) in self.looks: return self.looks[key(media)]
        result = None
        try:
            from io import BytesIO
            from PIL import Image
            urls = self.frame_urls(media)
            folder = directory(self.service.projects, self.pid) / 'thumbs'
            path = folder / (hashlib.sha256(urls[0].encode()).hexdigest()[:32] + '.img') if urls else None
            if path and path.is_file():
                image = Image.open(BytesIO(path.read_bytes())).convert('RGB')
                colour = image.resize((1, 1)).getpixel((0, 0))
                grey = image.convert('L').resize((9, 8))
                pixels = list(grey.tobytes())
                bits = sum(1 << i for i in range(64) if pixels[(i // 8) * 9 + i % 8] > pixels[(i // 8) * 9 + i % 8 + 1])
                result = (colour, bits)
        except Exception:
            result = None
        self.looks[key(media)] = result
        return result

    def order(self, slot, candidates, verdicts):
        """Best score first; within a scene prefer the same colour mood as the
        previous shot and drop near-identical framing of it."""
        previous = self.scene_last.get(slot['scene_id'])
        prev_look = self.look(previous) if previous else None
        ranked = []
        for media in candidates:
            here = self.look(media) if prev_look else None
            distance = sum(abs(a - b) for a, b in zip(prev_look[0], here[0])) if prev_look and here else 0
            textured = prev_look and here and all(8 <= bin(x[1]).count('1') <= 56 for x in (prev_look, here))  # flat sky/sea frames prove nothing
            if textured and bin(prev_look[1] ^ here[1]).count('1') < SIMILAR_FRAMING and distance < 30:
                verdicts[key(media)]['note'] = 'önceki çekimle neredeyse aynı kadraj'
                continue
            ranked.append((verdicts[key(media)]['score'], -distance // 60, media['width'] > media['height'], media))
        return [m for *_, m in sorted(ranked, key=lambda r: r[:3], reverse=True)]

    def try_step(self, slot, scene, stage, kinds, queries, log, exclude):
        """Queries are tiers (very specific → medium → general): each tier is
        searched, pre-filtered and judged on its own; only when no candidate
        reaches 7/10 does the next tier start."""
        step = {'stage': stage, 'label': STAGES[stage], 'queries': list(queries), 'judged': []}
        log['steps'].append(step)
        for query in queries:
            pool = self.pool(slot, self.search(slot, kinds, query, log), log, exclude, scene)
            # The AI already approved these for this scene (another slot):
            # reuse the verdict instead of paying for the same look again.
            known = [m for m in pool if log['judged'].get(key(m), {}).get('approved') and log['judged'][key(m)]['score'] >= APPROVE_SCORE]
            for media in self.order(slot, known, log['judged']):
                chosen = self.take(slot, media, log['judged'][key(media)], stage, log)
                if chosen:
                    step['judged'].append({'provider': media['provider'], 'media_type': media['media_type'], 'media_id': media['media_id'],
                                           'query': media.get('query_used'), **log['judged'][key(media)], 'reused_verdict': True})
                    return chosen
            fresh = [m for m in pool if key(m) not in log['judged']][:CANDIDATES]
            if not fresh:
                continue
            self.progress['message'] = f'Yuva {slot["order"]} · {self.label} {len(fresh)} adaya bakıyor (“{query}”)'
            self.service._checkpoint(self.job, self.progress, light=True)
            verdicts = self.judge(slot, scene, fresh)
            for media in fresh:
                verdict = verdicts.get(key(media))
                if verdict is None: continue
                log['judged'][key(media)] = verdict
                if not verdict['approved'] and key(media) not in self.ai_rejected_keys:
                    self.ai_rejected_keys.add(key(media))
                    self.progress['ai_rejected'] = len(self.ai_rejected_keys)
                    self.progress['irrelevant_filtered'] = len(self.filtered_keys) + len(self.ai_rejected_keys)
                step['judged'].append({'provider': media['provider'], 'media_type': media['media_type'], 'media_id': media['media_id'],
                                       'query': media.get('query_used'), 'width': media['width'], 'height': media['height'],
                                       'duration': media.get('duration'), **verdict})
            approved = [m for m in fresh if verdicts.get(key(m), {}).get('approved') and verdicts[key(m)]['score'] >= APPROVE_SCORE]
            for media in self.order(slot, approved, verdicts):
                chosen = self.take(slot, media, verdicts[key(media)], stage, log)
                if chosen: return chosen
        step['result'] = step.get('result') or 'no_approved_candidate'
        return None

    def take(self, slot, media, verdict, stage, log):
        need = used_seconds(slot)
        start = self.segment(media, need)
        if start is None: return None
        try:
            saved = self.service.downloader.download(self.pid, media)
        except StockError as error:
            log['steps'][-1].setdefault('download_errors', []).append(error.category)
            return None
        if any(identity_keys(saved) & identity_keys(other) for k, other in self.media_by_key.items() if k != key(media)):
            return None  # same bytes under another id: still a duplicate
        segment = start if key(media) in self.usage else None
        self.register(slot['slot_id'], saved, segment or 0., need)
        slot.update(selected_media=saved, status='complete', missing_reasons=[], warnings=[], local_validation={},
                    segment_start=segment, continuation_of=None,
                    ai_review={'approved': True, 'score': verdict['score'], 'reason': verdict['reason'], 'reviewed_at': now()},
                    message=verdict['reason'])
        if saved['width'] <= saved['height']:
            slot['warnings'].append('Dikey/kare kaynak: yatay videoda bulanık arka planla gösterilir.')
        if segment is not None:
            slot['warnings'].append('Aynı uzun klibin başka bir bölümü kullanılıyor (çakışma yok).')
        log['steps'][-1]['result'] = 'chosen'
        self.scene_last[slot['scene_id']] = media  # next shot of this scene: same mood, different framing
        return saved

    def register(self, slot_id, media, start, need):
        self.usage.setdefault(key(media), []).append((slot_id, start + need))
        self.media_by_key[key(media)] = media

    # ---- other steps -------------------------------------------------------
    def merge(self, slot, log, limit=MERGE_SECONDS):
        if used_seconds(slot) > limit: return False
        ordered = sorted(self.slots, key=lambda s: s['estimated_start'])
        index = next(i for i, s in enumerate(ordered) if s['slot_id'] == slot['slot_id'])
        for neighbour in (ordered[index - 1] if index else None, ordered[index + 1] if index + 1 < len(ordered) else None):
            media = neighbour and neighbour.get('selected_media')
            if not media or neighbour['status'] != 'complete' or media['media_type'] != 'video' or neighbour.get('continuation_of') or is_generated(media):
                continue
            chain = used_seconds(neighbour) + used_seconds(slot)
            if chain + .6 > float(media.get('duration') or 0): continue
            slot.update(selected_media=deepcopy(media), status='complete', continuation_of=neighbour['slot_id'], segment_start=None,
                        missing_reasons=[], warnings=[], ai_review=deepcopy(neighbour.get('ai_review')),
                        message='Çok kısa yuva: komşu çekim kesintisiz devam ediyor.' if limit <= MERGE_SECONDS else 'Komşu çekim kesintisiz devam ediyor (yazı kartı yerine).')
            log['steps'].append({'stage': 'merged', 'label': STAGES['merged'], 'result': 'chosen', 'neighbour': neighbour['order']})
            return True
        return False

    # ---- motion graphics ------------------------------------------------------
    def kit(self):
        from app.channels import DEFAULT_STYLE
        channels = getattr(self.service, 'channels', None)
        return channels.for_project(self.pid)['style'] if channels else DEFAULT_STYLE

    def emphasis_offset(self, slot, scene, spec):
        """Estimated moment (seconds into the slot) where the emphasis word is
        spoken; the render pass re-anchors it to the real subtitle timing."""
        need = used_seconds(slot)
        text = ' '.join(scene.get('narration_text', '').split())
        target = (spec.get('emphasis') or '').casefold()
        position = text.casefold().find(target) if target else -1
        if position < 0:
            return need * .6
        span = max(.001, scene['end_estimate'] - scene['start_estimate'])
        spoken = scene['start_estimate'] + span * len(text[:position].split()) / max(1, len(text.split()))
        return min(max(spoken - slot['estimated_start'], .6), max(.6, need - .35))

    # ---- the owner's infographic markers ---------------------------------------
    def owner_slots(self, scenes):
        """{slot_id: hint}: each infographic marker goes to the free slot nearest
        to the moment its sentence is spoken (same scene first, else a
        neighbouring slot within 8 s). Markers with no slot left are reported."""
        wanted = []
        for scene in scenes:
            words = ' '.join(scene.get('narration_text', '').split())
            span = max(.001, scene['end_estimate'] - scene['start_estimate'])
            for hint in scene.get('owner_hints') or []:
                if hint.get('type') not in INFOGRAPHIC or not hint.get('value'): continue
                where = words.find(' '.join(str(hint.get('sentence', '')).split())) if hint.get('sentence') else -1
                at = scene['start_estimate'] + span * (len(words[:where].split()) / max(1, len(words.split())) if where >= 0 else 0) + .3
                wanted.append((at, scene['scene_id'], hint))
        out, unplaced = {}, []
        for at, scene_id, hint in sorted(wanted, key=lambda w: w[0]):
            free = [s for s in self.slots if s['slot_id'] not in out and not s.get('locked') and not s.get('manual_stock')]
            gap = lambda s: 0 if s['estimated_start'] <= at < s['estimated_end'] else min(abs(at - s['estimated_start']), abs(at - s['estimated_end']))
            near = [s for s in free if s['scene_id'] == scene_id] or [s for s in free if gap(s) <= 8]
            if not near:
                unplaced.append(f'[{hint["type"]}: {hint["value"]}]'); continue
            out[min(near, key=gap)['slot_id']] = hint
        self.progress['owner_unplaced'] = unplaced
        return out

    def place(self, name):
        """(lat, lon) from the local place list, else from the AI, else None."""
        from app.motion.places import lookup
        found = lookup(name)
        if found: return found[:2]
        try:
            answer = self._ask('motion_place', f'Give the latitude and longitude (decimal degrees) of this place: "{name}". '
                               'If it is not a real, locatable place, set found=false.', PLACE_SCHEMA, max_tokens=200)
        except StockError as error:
            if error.category != 'ai_paused': raise
            return None
        if answer and answer.get('found') and isinstance(answer.get('lat'), (int, float)) and isinstance(answer.get('lon'), (int, float)) \
                and -85 <= answer['lat'] <= 85 and -180 <= answer['lon'] <= 180:
            return float(answer['lat']), float(answer['lon'])
        return None

    def owner_spec(self, hint, scene):
        """The marker's own values become the infographic (only the shape is checked)."""
        from app.motion.numbers import spoken_numbers
        from app.motion.templates import MotionError, short, validate
        kind, value = hint['type'], ' '.join(str(hint['value']).split())
        sentence = ' '.join(str(hint.get('sentence') or sentence_at(scene.get('narration_text', ''), 0)).split()).rstrip('.!?…')
        narration = scene.get('narration_text', '')
        split = lambda text, signs: [x.strip() for x in re.split(signs, text) if x.strip()]
        spec = None
        if kind == 'map':
            where = self.place(value)
            if where: spec = {'template': 'map', 'data': {'place': value[:60], 'label': '', 'lat': where[0], 'lon': where[1]}, 'emphasis': value.split()[0]}
        elif kind == 'number':
            if not re.search(r'\d', value):
                numbers = sorted(spoken_numbers(value))
                if numbers: value = f'{numbers[-1]} %' if re.search(r'(?i)prozent|percent|ciento|cent|yüzde', value) else str(numbers[-1])
            spec = {'template': 'stat', 'data': {'value': value[:24], 'label': short(sentence)}, 'emphasis': value}
        elif kind == 'timeline':
            events = []
            for item in split(value, r';' if ';' in value else r','):
                match = re.match(r'\s*(\S*\d\S*(?:\s+(?:v\.|n\.)\s*Chr\.|\s+(?:BC|AD|BCE|CE|MÖ|MS)\b)?)\s*[:\-–]?\s*(.*)', item)
                if not match: continue
                date, label = match.group(1)[:20], match.group(2)
                if not label:
                    at = narration.find(date)
                    label = ' '.join(w for w in narration[at + len(date):].split()[:3] if not re.search(r'\d', w)) if at >= 0 else ''
                events.append({'date': date, 'label': label.strip(' ,;:.')[:50]})
            if len(events) >= 2: spec = {'template': 'timeline', 'data': {'events': events[:5]}, 'emphasis': ''}
            elif events: spec = {'template': 'stat', 'data': {'value': events[0]['date'], 'label': short(sentence)}, 'emphasis': events[0]['date']}
        elif kind == 'compare':
            items = []
            for item in split(value, r'\||\bvs\.?\b|\bgegen\b|\bkarşı\b'):
                label, _, number = item.rpartition(':') if ':' in item else item.rpartition('=') if '=' in item else (item, '', '')
                items.append({'label': label.strip()[:40], 'value': number.strip()[:24] if re.search(r'\d', number) else ''})
            if len(items) > 2 and not all(i['value'] for i in items):
                spec = {'template': 'list', 'data': {'title': '', 'items': [i['label'] for i in items[:4]]}, 'emphasis': ''}
            elif len(items) >= 2:
                spec = {'template': 'compare', 'data': {'title': '', 'items': items[:5]}, 'emphasis': ''}
        elif kind == 'list':
            items = split(value, r';' if ';' in value else r',')
            if len(items) >= 2: spec = {'template': 'list', 'data': {'title': '', 'items': [i[:60] for i in items[:4]]}, 'emphasis': ''}
        try:
            if spec: return validate(spec, narration, scene.get('entities', []), trusted=True)
        except MotionError:
            pass
        return None  # unusable marker: the narration decides (see motion_spec)

    def motion_spec(self, slot, scene, repeat=False):
        """Last-resort motion from the narration spoken during the slot;
        a sentence not shown yet is preferred."""
        from app.motion.templates import from_narration, validate, MotionError
        span = max(.001, scene['end_estimate'] - scene['start_estimate'])
        middle = (slot['estimated_start'] + slot['estimated_end']) / 2
        fraction = min(1, max(0, (middle - scene['start_estimate']) / span))
        narration = scene.get('narration_text', '')
        sentences = list(dict.fromkeys(sentence_at(narration, f / 10) for f in sorted(range(11), key=lambda f: abs(f / 10 - fraction))))
        sentences.insert(0, sentence_at(narration, fraction))
        options = []
        for sentence in dict.fromkeys(sentences):
            if not sentence: continue
            try: options.append(validate(from_narration(sentence, scene.get('entities', [])), narration, scene.get('entities', [])))
            except MotionError: continue
        fresh = [o for o in options if json.dumps(o, sort_keys=True) not in self.card_texts]
        # A plain text card is the last choice; repeat=True: a graphic already shown beats a text card.
        ranked = sorted(options, key=lambda o: (o['template'] == 'quote', o not in fresh)) if repeat else sorted(fresh or options, key=lambda o: o['template'] == 'quote')
        return (ranked or [{'template': 'quote', 'data': {'text': narration.split('.')[0][:120] or scene.get('visual_intent', '')}, 'emphasis': ''}])[0]

    def quote_full(self):
        """At most ~30% of the motion graphics may be plain text cards."""
        motion = [s for s in self.slots if is_generated(s.get('selected_media')) and s['selected_media']['media_type'] == 'video' and not s.get('continuation_of')]
        quotes = sum(((s['selected_media'].get('source_metadata') or {}).get('motion') or {}).get('template') == 'quote' for s in motion)
        return quotes + 1 > max(1, QUOTE_SHARE * (len(motion) + 1))

    def motion(self, slot, scene, log, spec=None, stage='motion'):
        from app.motion.clips import render_clip, media_record
        spec = spec or self.motion_spec(slot, scene)
        marker = json.dumps(spec, sort_keys=True)
        if stage == 'motion' and marker in self.card_texts and self.continue_card(slot, marker, log):
            return True
        self.card_texts.add(marker)
        need = used_seconds(slot)
        self.progress['message'] = f'Yuva {slot["order"]} · motion grafik çiziliyor'
        self.service._checkpoint(self.job, self.progress, light=True)
        folder = directory(self.service.projects, self.pid)
        language = self.service._handoff(self.pid).get('language', 'de')
        try:
            path, scene_data, engine = render_clip(folder, spec, self.kit(), need, self.emphasis_offset(slot, scene, spec), language=language,
                                                   bridge=getattr(self.service, 'openmontage', None))
        except Exception:
            LOG.warning('stock operation=motion category=render_failed')
            return self.card(slot, scene, log)  # extreme fallback (e.g. FFmpeg missing): still a picture
        media = media_record(path, spec, scene_data, engine)
        from app.motion.templates import TEMPLATES
        why = {'motion_planned': 'yönetmen bu sahneyi motion grafik olarak planladı', 'motion_edit': 'sizin düzenlediğiniz motion grafik',
               'motion_owner': 'metindeki işaretinize göre'}.get(
            stage, 'onaylanan stok medya bulunamadı')
        slot.update(selected_media=media, status='complete', continuation_of=None, segment_start=None, missing_reasons=[], warnings=[],
                    ai_review=None, message=f'{TEMPLATES[spec["template"]]}: “{media["description"][:80]}” ({why}).')
        log['steps'].append({'stage': stage, 'label': STAGES[stage], 'result': 'chosen', 'template': spec['template'], 'engine': engine,
                             'because': 'no_approved_stock' if stage == 'motion' else stage})
        return True

    def card(self, slot, scene, log):
        kind, text = card_spec(slot, scene, self.card_texts)
        if text in self.card_texts and self.continue_card(slot, text, log):
            return True
        self.card_texts.add(text)
        folder = directory(self.service.projects, self.pid)
        name = uuid4().hex + '.png'
        drawn = render_card(folder / name, kind, text)
        data = (folder / name).read_bytes()
        media = {'provider': 'generated', 'media_id': 'card-' + name[:12], 'media_type': 'image', 'source_url': '', 'page_url': '',
                 'creator_name': 'AI Video Studio', 'creator_url': '', 'width': 1920, 'height': 1080, 'duration': None,
                 'preview_url': '', 'download_url': '', 'query_used': '', 'provider_query': None, 'description': text,
                 'source_metadata': {'generated': True, 'card_kind': kind, 'card_text': text, 'text_drawn': drawn == 'drawn'},
                 'search_tier': None, 'relevance_score': None, 'relevance_label': None, 'relevance_basis': None,
                 'local_path': 'stock/' + name, 'file_size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                 'downloaded_at': now(), 'content_type': 'image/png'}
        names = {'map': 'Konum kartı', 'number': 'Sayı kartı', 'quote': 'Alıntı kartı', 'title': 'Başlık kartı'}
        why = 'onaylanan stok medya bulunamadı'
        slot.update(selected_media=media, status='complete', continuation_of=None, segment_start=None, missing_reasons=[],
                    warnings=[] if drawn == 'drawn' else ['Yazı tipi bulunamadı; kart yazısız çizildi.'], ai_review=None,
                    message=f'{names[kind]}: “{text}” ({why}).')
        log['steps'].append({'stage': 'card', 'label': STAGES['card'], 'result': 'chosen', 'card_kind': kind, 'card_text': text,
                             'because': 'no_approved_stock'})
        return True

    # ---- per slot ----------------------------------------------------------
    def fill(self, slot, scene, exclude=frozenset(), *, keep_if_only_card=False):
        slot['relevance_profile'] = relevance.profile(scene, slot)
        # Slots of one scene share the AI's verdicts and rewritten queries.
        memo = self.memo.setdefault(slot['scene_id'], {'judged': {}})
        log = {'started_at': now(), 'steps': [], 'searches': [], 'judged': memo['judged'], 'rejected': {}}
        planned = list(dict.fromkeys(q for q in [slot.get('search_query'), *slot.get('fallback_queries', []),
                                                 scene.get('primary_stock_query'), *scene.get('alternative_stock_queries', [])] if q))[:4]
        video_first = ['video'] if slot.get('preferred_type') != 'stock_image' else ['image', 'video']
        chosen = self.try_step(slot, scene, 'stock_video', video_first, planned, log, exclude)
        rewritten = []
        if not chosen:
            if 'rewritten' not in memo: memo['rewritten'] = self.rewrite(slot, scene, planned)
            rewritten = memo['rewritten']
            log['rewritten_queries'] = rewritten
            if rewritten: chosen = self.try_step(slot, scene, 'rewritten_video', ['video'], rewritten, log, exclude)
        if not chosen:
            chosen = self.try_step(slot, scene, 'stock_image', ['image'], (rewritten + planned)[:5], log, exclude)
        if not chosen:
            if 'broader' not in memo: memo['broader'] = self.rewrite(slot, scene, planned + rewritten, broader=True)
            broader = memo['broader']
            log['broader_queries'] = broader
            if broader: chosen = self.try_step(slot, scene, 'broader', ['video', 'image'], broader, log, exclude)
        if not chosen and keep_if_only_card:
            log['steps'].append({'stage': 'kept', 'label': STAGES['kept'], 'result': 'kept_no_better_option'})
            return log
        if not chosen and used_seconds(slot) < MERGE_SECONDS and self.merge(slot, log):
            chosen = True
        if not chosen:
            spec = self.motion_spec(slot, scene)
            if spec['template'] == 'quote' and self.quote_full():
                # Enough text cards already: a longer neighbouring shot, another
                # nearby infographic or this scene's graphic again instead.
                if self.merge(slot, log, limit=6.0): return log
                spec = self.nearby_infographic(slot, scene) or self.motion_spec(slot, scene, repeat=True)
            self.motion(slot, scene, log, spec)
        return log

    def nearby_infographic(self, slot, scene):
        """A number/place/date infographic from the neighbouring scenes' narration."""
        from app.motion.templates import from_narration, validate, MotionError
        index = self.scene_order.index(scene['scene_id']) if scene['scene_id'] in self.scene_order else 0
        for other in sorted(range(len(self.scene_order)), key=lambda i: abs(i - index))[:5]:
            text = self.scene_text.get(self.scene_order[other], '')
            for f in range(11):
                sentence = sentence_at(text, f / 10)
                if not sentence: continue
                try: spec = validate(from_narration(sentence, scene.get('entities', [])), text, scene.get('entities', []))
                except MotionError: continue
                if spec['template'] != 'quote' and json.dumps(spec, sort_keys=True) not in self.card_texts: return spec
        return None

    def finish_slot(self, slot, log):
        stage = next((s['stage'] for s in reversed(log['steps']) if s.get('result') in ('chosen', 'kept', 'kept_no_better_option')), 'motion')
        slot['director'] = {'stage': stage, 'stage_label': STAGES[stage], 'reason': slot.get('message', ''),
                            'searches': log['searches'][-40:], 'steps': [{k: v for k, v in s.items()} for s in log['steps']],
                            'rejected': log.get('rejected', {}), 'rewritten_queries': log.get('rewritten_queries', []),
                            'broader_queries': log.get('broader_queries', []), 'updated_at': now(),
                            'judged': [{'media': '/'.join(k), **v} for k, v in list(log['judged'].items())[-15:]]}
        slot['candidates'] = []
        self.service._checkpoint(self.job, self.progress, slot=slot)

    def continue_card(self, slot, text, log):
        """Same sentence as the card just before: one longer card, not a repeat."""
        ordered = sorted(self.slots, key=lambda s: s['estimated_start'])
        index = next(i for i, s in enumerate(ordered) if s['slot_id'] == slot['slot_id'])
        previous = ordered[index - 1] if index else None
        media = previous and previous.get('selected_media')
        same = (is_card(media) and media['source_metadata'].get('card_text') == text) or (
            is_generated(media) and json.dumps((media.get('source_metadata') or {}).get('motion'), sort_keys=True) == text)
        if not same: return False
        root = previous.get('continuation_of') or previous['slot_id']
        chain = sum(used_seconds(s) for s in ordered if s['slot_id'] == root or s.get('continuation_of') == root)
        if chain + used_seconds(slot) > 10: return False
        slot.update(selected_media=deepcopy(media), status='complete', continuation_of=root, segment_start=None, missing_reasons=[],
                    warnings=[], ai_review=None, message='Önceki kart devam ediyor (aynı cümle).')
        log['steps'].append({'stage': 'motion' if media['media_type'] == 'video' else 'card', 'label': STAGES['motion' if media['media_type'] == 'video' else 'card'],
                             'result': 'chosen', 'continued': True})
        return True

    def valid(self, slot):
        if slot.get('status') != 'complete' or not slot.get('selected_media'): return False
        try:
            asset_path(self.service.projects, self.pid, slot['selected_media'])
            return True
        except (StockError, OSError):
            return False

    # ---- job ---------------------------------------------------------------
    def run(self):
        CURRENT_PROJECT.set(self.pid)
        service, job = self.service, self.job
        with service.projects.lock, closing(service.projects._connection()) as c:
            state = service._load(c, self.pid, job['plan_id'])
        handoff = service._handoff(self.pid)
        scenes = {s['scene_id']: s for s in handoff['scenes']}
        timing = (getattr(service, 'timing_handoff', lambda pid: None)(self.pid) or {}).get('stock_slots', [])
        actual = {s['slot_id']: s['duration'] for s in timing}
        self.slots = deepcopy(state['slots'])
        for slot in self.slots:
            if slot['slot_id'] in actual: slot['actual_duration_hint'] = actual[slot['slot_id']]
        self.usage, self.media_by_key, self.memo, self.card_texts = {}, {}, {}, set()
        self.rejected = rejected_media(service.projects, self.pid)
        self.rejected_keys = {(r['provider'], r['media_type'], str(r['media_id'])) for r in self.rejected}
        self.rejected_hashes = {r['sha256'] for r in self.rejected if r.get('sha256')}
        self.filtered_keys, self.ai_rejected_keys, self.looks, self.scene_last = set(), set(), {}, {}
        self.progress.setdefault('irrelevant_filtered', 0)
        ordered_scenes = sorted(handoff['scenes'], key=lambda sc: sc.get('start_estimate', 0))
        self.scene_order = [sc['scene_id'] for sc in ordered_scenes]
        self.scene_text = {sc['scene_id']: sc.get('narration_text', '') for sc in ordered_scenes}
        project = service.projects.get(self.pid)
        self.topic = project.get('topic') or project.get('name', '')
        self.connect()
        single = job.get('slot_id')
        action = {'reselect': 'reselect', 'to_motion': 'to_motion', 'to_stock': 'to_stock', 'motion_edit': 'motion_edit'}.get(job['action'], 'reselect')
        first = {}
        for slot in sorted(self.slots, key=lambda s: s['estimated_start']):
            first.setdefault(slot['scene_id'], slot['slot_id'])
        # The owner's infographic markers ([HARİTA], [SAYI], …) win over the director's motion plan.
        self.owner = self.owner_slots(handoff['scenes']) if not single else {}
        # Keep what is valid and already approved (or locked / generated).
        targets = []
        for slot in sorted(self.slots, key=lambda s: s['estimated_start']):
            media = slot.get('selected_media')
            if single and slot['slot_id'] == single:
                targets.append((slot, action))
                continue
            hint = self.owner.get(slot['slot_id'])
            if hint and not slot['locked'] and not slot.get('manual_stock') and not slot.get('motion_edited') and (
                    not self.valid(slot) or not is_generated(media) or (media.get('source_metadata') or {}).get('owner_hint') != hint
                    or UNREACHABLE in slot.get('message', '')):
                targets.append((slot, 'motion_owner'))
                continue
            planned = scenes[slot['scene_id']].get('motion_spec') if not any(h.get('type') in INFOGRAPHIC for h in scenes[slot['scene_id']].get('owner_hints') or []) else None
            if not single and not slot['locked'] and planned and first[slot['scene_id']] == slot['slot_id'] and not slot.get('manual_stock') and (
                    not self.valid(slot) or not is_generated(media) and not (slot.get('ai_review') or {}).get('approved')
                    or is_generated(media) and ((media.get('source_metadata') or {}).get('planned') or (media.get('source_metadata') or {}).get('motion')) != planned
                    and not slot.get('motion_edited')):
                targets.append((slot, 'motion_planned'))
                continue
            if not self.valid(slot):
                if not slot['locked']: targets.append((slot, 'missing'))
                continue
            if not single and not slot['locked'] and not is_generated(media) and (
                    key(media) in self.rejected_keys or (media.get('sha256') and media['sha256'] in self.rejected_hashes)):
                targets.append((slot, 'reselect'))  # the owner rejected this clip elsewhere: never kept anywhere
                continue
            if slot.get('continuation_of'):
                continue
            self.register(slot['slot_id'], media, float(slot.get('segment_start') or 0), used_seconds(slot))
            if single or slot['locked']: continue
            if is_generated(media):
                if UNREACHABLE in slot.get('message', ''): targets.append((slot, 'retry_card'))
            elif not (slot.get('ai_review') or {}).get('approved') or (slot['ai_review'].get('score') or 0) < APPROVE_SCORE:
                targets.append((slot, 'unreviewed'))  # below 7/10 is never kept
        # Infographics need no AI look: they are drawn first, so even if the AI
        # quota runs out later every marked/planned scene already has its graphic.
        targets.sort(key=lambda t: t[1] not in ('motion_owner', 'motion_planned'))
        total = max(1, len(targets))
        for done, (slot, why) in enumerate(targets):
            if service.closed: raise StockError('interrupted', 'İşlem durdu; tamamlanan yuvalar korundu. Medyayı Tamamla ile sürdürün.')
            scene = scenes[slot['scene_id']]
            self.progress.update(percent=int(done / total * 85), slot_id=slot['slot_id'],
                                 message=f'Yuva {slot["order"]} ({done + 1}/{total}) hazırlanıyor')
            service._checkpoint(self.job, self.progress)
            try:
                log = self.handle(slot, scene, why)
            except StockError as error:
                if error.category in ('stale_plan', 'interrupted', 'locked', 'ai_paused'): raise
                log = {'steps': [], 'searches': [], 'judged': {}, 'error': error.category}
                self.motion(slot, scene, log)
            self.finish_slot(slot, log)
        if targets and not single:  # nothing new chosen: nothing to re-review
            try:
                self.review(scenes)
            except StockError as error:
                if error.category != 'ai_paused': raise
                self.progress['review_skipped'] = str(error)  # every slot is already filled; only the extra look is skipped
        self.finalize()

    def handle(self, slot, scene, why):
        empty = lambda: {'steps': [], 'searches': [], 'judged': {}}
        if why == 'motion_owner':
            hint = self.owner[slot['slot_id']]
            spec = self.owner_spec(hint, scene)
            self._release(slot); log = empty()
            if spec is None:  # e.g. a place nobody could locate: the narration decides
                log = self.fill(slot, scene)
                slot['message'] = f'[{hint["type"]}: {hint["value"]}] işareti çizilemedi ({"yer haritada bulunamadı" if hint["type"] == "map" else "işaret biçimi okunamadı"}). ' + slot.get('message', '')
                return log
            self.motion(slot, scene, log, spec, 'motion_owner')
            slot['selected_media'].setdefault('source_metadata', {})['owner_hint'] = hint
            return log
        if why == 'motion_planned':
            planned, spec = scene['motion_spec'], scene['motion_spec']
            self._release(slot); log = empty()
            if planned['template'] == 'quote':  # a text card is the last choice
                other = self.motion_spec(slot, scene)
                if other['template'] != 'quote': spec = other
                elif self.quote_full(): return self.fill(slot, scene)  # enough text cards: stock footage instead
            self.motion(slot, scene, log, spec, 'motion_planned')
            if is_generated(slot.get('selected_media')): slot['selected_media'].setdefault('source_metadata', {})['planned'] = planned
            return log
        if why == 'to_motion':
            self._release(slot); slot.pop('manual_stock', None); log = empty()
            self.motion(slot, scene, log, scene.get('motion_spec') or None, 'motion_planned' if scene.get('motion_spec') else 'motion'); return log
        if why == 'motion_edit':
            self._release(slot); log = empty(); self.motion(slot, scene, log, self.progress['motion'], 'motion_edit'); slot['motion_edited'] = True; return log
        if why == 'to_stock':
            backup = deepcopy(slot); old = slot.get('selected_media')
            self._release(slot)
            log = self.fill(slot, scene, exclude={key(old)} if old and not is_generated(old) else set(), keep_if_only_card=True)
            if slot.get('status') != 'complete':
                slot.clear(); slot.update(backup)
                if old: self.register(slot['slot_id'], old, float(slot.get('segment_start') or 0), used_seconds(slot))
                slot['message'] = 'Onaylanan stok video bulunamadı; mevcut medya korundu.'
            else:
                slot['manual_stock'] = True
            return log
        if why == 'unreviewed':
            # An earlier automatic pick: the AI looks at it before it may stay.
            slot['relevance_profile'] = relevance.profile(scene, slot)
            media = slot['selected_media']
            log = {'steps': [{'stage': 'kept', 'label': STAGES['kept'], 'judged': []}], 'searches': [], 'judged': {}}
            verdict = self.judge(slot, scene, [media]).get(key(media))
            if verdict and verdict['approved'] and verdict['score'] >= APPROVE_SCORE:
                slot.update(ai_review={'approved': True, **verdict, 'reviewed_at': now()}, message=verdict['reason'])
                log['steps'][0]['result'] = 'kept'
                return log
            self._release(slot)
            log2 = self.fill(slot, scene, exclude={key(media)})
            log2['previous_rejected'] = verdict
            return log2
        if why == 'reselect':
            old = slot.get('selected_media')
            exclude = {key(old)} if old and not is_generated(old) else set()
            self._release(slot)
            return self.fill(slot, scene, exclude=exclude)
        if why == 'retry_card':
            self._release(slot)
        return self.fill(slot, scene)

    def _release(self, slot):
        media = slot.get('selected_media')
        if media and key(media) in self.usage:
            self.usage[key(media)] = [u for u in self.usage[key(media)] if u[0] != slot['slot_id']]
            if not self.usage[key(media)]: del self.usage[key(media)]
        slot.update(selected_media=None, status='pending', ai_review=None, segment_start=None, continuation_of=None)

    def review(self, scenes):
        """Whole-video look: repeated or too similar shots, tone breaks."""
        stock = [s for s in sorted(self.slots, key=lambda s: s['estimated_start'])
                 if s.get('status') == 'complete' and s.get('selected_media') and not is_generated(s['selected_media'])
                 and not s['locked'] and not s.get('continuation_of')]
        if len(stock) < 4: return
        blocks = []
        for s in stock:
            frame = next((b for b in (self.thumbnail(u, s['selected_media']['provider']) for u in self.frame_urls(s['selected_media'])[:1]) if b), None)
            if frame:
                blocks += [{'type': 'text', 'text': f'Slot {s["order"]} (scene {scenes[s["scene_id"]]["order"]}): '
                                                    f'{scenes[s["scene_id"]].get("visual_intent", "")[:80]}'}, frame]
        if len(blocks) < 8: return
        self.progress.update(percent=88, message=f'{self.label} videonun bütününe bakıyor (tekrar, benzer çekim, ton)')
        self.service._checkpoint(self.job, self.progress)
        prompt = ('These are the chosen shots of one documentary video in order (one frame each). List at most '
                  f'{REVIEW_MAX} slots that should be REPLACED because they repeat or look almost the same as a nearby '
                  'shot, or clearly break the tone of the video. Do not list shots that are fine. reason: one short Turkish sentence.')
        answer = self._ask('media_review', prompt, REVIEW_SCHEMA, blocks, max_tokens=1500) or {}
        by_order = {s['order']: s for s in stock}
        flagged = []
        for item in answer.get('replace', [])[:REVIEW_MAX]:
            slot = by_order.get(item.get('slot')) if isinstance(item.get('slot'), int) else None
            if slot and slot not in [f for f, _ in flagged]: flagged.append((slot, ' '.join(str(item.get('reason', '')).split())[:300]))
        self.progress['review'] = [{'slot': s['order'], 'reason': r} for s, r in flagged]
        for slot, reason in flagged:
            old = slot['selected_media']
            backup = deepcopy(slot)
            self._release(slot)
            log = self.fill(slot, scenes[slot['scene_id']], exclude={key(old)}, keep_if_only_card=True)
            if slot.get('status') != 'complete':  # nothing better: keep the approved shot
                slot.clear(); slot.update(backup)
                self.register(slot['slot_id'], old, float(slot.get('segment_start') or 0), used_seconds(slot))
                slot['message'] = f'{self.label} değiştirmeyi önerdi ({reason}); daha iyi aday bulunamadı, mevcut çekim korundu.'
            else:
                slot['message'] = f'Bütün video incelemesi: {reason} → {slot.get("message", "")}'
            log['review_reason'] = reason
            self.finish_slot(slot, log)

    def finalize(self):
        service, job = self.service, self.job
        with service.projects.lock, closing(service.projects._connection()) as c, c:
            state = service._load(c, self.pid, job['plan_id'])
            # Every raw slot is now filled: the old render-only reflow plan
            # (built for gaps) is obsolete and must not hide new selections.
            state.pop('recovery_plan', None)
            state['media_summary'] = summary(state['slots'])
            service._save(c, state)
            service._mirror(state)
        result = state['media_summary']
        self.progress.update(percent=100, category='none', media_summary=result,
                             message=result['text'] + (' · Bütün video incelemesi atlandı: ' + self.progress['review_skipped'].split('.')[0] if self.progress.get('review_skipped') else '')
                             + (' · Görüntü yeri kalmadığı için gösterilemeyen işaretler: ' + ', '.join(self.progress['owner_unplaced']) if self.progress.get('owner_unplaced') else ''))
        service._checkpoint(job, self.progress, status='completed')


TEMPLATE_WORDS = {'stat': 'sayı', 'map': 'harita', 'timeline': 'çizelge', 'compare': 'karşılaştırma', 'list': 'liste', 'quote': 'yazı'}


def pause_message(label, category, retry, waited_out):
    """Plain Turkish: what happened, what was kept and when to try again."""
    kept = ' Tamamlanan yuvalar korundu, kalanlar “Bekliyor” durumunda; Medyayı Tamamla’ya tekrar basınca kaldığı yerden devam eder.'
    if category == 'free_quota_exhausted':
        minutes = minutes_to_pacific_midnight()
        when = f'yaklaşık {minutes // 60} saat {minutes % 60} dk sonra' if minutes >= 60 else f'yaklaşık {minutes} dk sonra'
        return f'{label} günlük ücretsiz kotası doldu; kota her gün ABD Pasifik saatiyle gece yarısı yenilenir. {when.capitalize()} tekrar deneyin.' + kept
    if category in ('rate_limit', 'quota_limit'):
        minutes = max(1, -(-max(retry, 60) // 60))
        return f'{label} kotası doldu (dakikalık/kısa süreli sınır). {minutes} dk sonra tekrar deneyin.' + kept
    if category in TRANSIENT:
        return f'{label} şu anda yanıt vermiyor ({ERROR_TEXT.get(category, "geçici hata")}); bekleyip birkaç kez yeniden denendi. 5 dk sonra tekrar deneyin.' + kept
    if category in UNUSABLE:
        return f'{label} art arda okunamayan yanıt verdi. Birkaç dk sonra tekrar deneyin; sorun sürerse Ayarlar’dan başka bir model seçin.' + kept
    if category in ('key_rejected', 'missing_key', 'invalid_settings'):
        return f'{label} API anahtarı kabul edilmedi veya kayıtlı değil. Ayarlar → {label} bölümünde anahtarı kontrol edip Kaydet deyin.' + kept
    if category in ('model_unavailable', 'model_unsupported', 'invalid_request'):
        return f'Seçili {label} modeli bu isteği kabul etmedi. Ayarlar → {label} bölümünde Modelleri Getir ile başka bir model seçin.' + kept
    if category == 'billing_quota':
        return f'{label} hesabınızda bakiye/kota yok. Hesap bakiyesini kontrol edin.' + kept
    return f'{label} ile medya seçimi durdu ({category}). Birkaç dk sonra tekrar deneyin.' + kept


def minutes_to_pacific_midnight():
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo('America/Los_Angeles')
    except Exception:  # no time-zone data (some Windows installs): standard offset
        zone = timezone(timedelta(hours=-8))
    here = datetime.now(zone)
    midnight = (here + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, round((midnight - here).total_seconds() / 60))


def summary(slots):
    filled = [s for s in slots if s.get('status') == 'complete' and s.get('selected_media')]
    cards = sum(is_card(s['selected_media']) and s['selected_media']['media_type'] == 'image' for s in filled)
    motion = sum(is_generated(s['selected_media']) and s['selected_media']['media_type'] == 'video' for s in filled)
    merged = sum(bool(s.get('continuation_of')) for s in filled)
    videos = sum(s['selected_media']['media_type'] == 'video' and not is_generated(s['selected_media']) for s in filled)
    images = sum(s['selected_media']['media_type'] == 'image' and not is_generated(s['selected_media']) for s in filled)
    motion_seconds = round(sum(used_seconds(s) for s in filled if is_generated(s['selected_media']) and s['selected_media']['media_type'] == 'video'), 2)
    total_seconds = sum(used_seconds(s) for s in slots) or 1
    missing = [s for s in slots if s not in filled]
    seconds = round(sum(used_seconds(s) for s in missing), 2)
    templates = {}
    for s in filled:
        if is_generated(s['selected_media']) and s['selected_media']['media_type'] == 'video' and not s.get('continuation_of'):
            name = ((s['selected_media'].get('source_metadata') or {}).get('motion') or {}).get('template', 'quote')
            templates[name] = templates.get(name, 0) + 1
    kinds = ', '.join(f'{n} {TEMPLATE_WORDS.get(t, t)}' for t, n in sorted(templates.items(), key=lambda kv: -kv[1]))
    text = (f'{len(filled)}/{len(slots)} yuva dolu · {videos} stok video · {images} görsel · {motion} motion grafik'
            + (f' ({kinds})' if kinds else '') + (f' · {cards} kart' if cards else ''))
    if merged: text += f' (bunların {merged} tanesi önceki çekimin devamı)'
    if missing: text += f' · {len(missing)} eksik ({seconds} sn)'
    average = relevance_summary(filled)['relevance_average']
    if average is not None: text += f' · ortalama alaka {average}/10'
    return {'total': len(slots), 'filled': len(filled), 'videos': videos, 'images': images, 'cards': cards, 'motion': motion, 'merged': merged,
            'motion_templates': templates, 'motion_slot_percent': round(100 * (motion + cards) / len(slots)) if slots else 0,
            'motion_seconds': motion_seconds, 'motion_percent': round(100 * motion_seconds / total_seconds, 1),
            'missing': len(missing), 'missing_seconds': seconds, 'text': text,
            'ai_approved': sum(bool((s.get('ai_review') or {}).get('approved')) for s in filled if not is_generated(s['selected_media'])),
            **relevance_summary(filled)}


def relevance_summary(filled):
    """Average AI relevance (0-10) of the stock picks and the 7–8 slots worth a look first."""
    scores = [(s['ai_review'] or {}).get('score') for s in filled if not is_generated(s['selected_media']) and not s.get('continuation_of') and s.get('ai_review')]
    scores = [x for x in scores if isinstance(x, (int, float))]
    low = [s['slot_id'] for s in filled if not is_generated(s['selected_media']) and isinstance((s.get('ai_review') or {}).get('score'), (int, float)) and s['ai_review']['score'] < 9]
    return {'relevance_average': round(sum(scores) / len(scores), 1) if scores else None, 'relevance_low_slots': low}


def extract_frames(url, duration, limit=15_000_000):
    """Start/middle/end JPEG frames of a small preview rendition (temporary
    download, deleted afterwards). [] when anything fails."""
    import subprocess
    import tempfile
    from pathlib import Path
    from app.rendering.tools import discover
    ffmpeg = discover().get('ffmpeg')
    if not ffmpeg: return []
    with tempfile.TemporaryDirectory() as folder:
        clip = Path(folder) / 'sample.mp4'
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client, client.stream('GET', url) as response:
                if response.status_code != 200: return []
                size = 0
                with clip.open('wb') as out:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > limit: return []
                        out.write(chunk)
        except (httpx.HTTPError, OSError):
            return []
        frames = []
        length = duration if duration > 0 else 6
        for i, at in enumerate((.1, .5, .9)):
            target = Path(folder) / f'f{i}.jpg'
            try:
                subprocess.run([ffmpeg, '-v', 'error', '-y', '-ss', f'{length * at:.2f}', '-i', str(clip), '-frames:v', '1', '-vf', 'scale=640:-2', str(target)],
                               capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                return []
            if target.is_file(): frames.append(target.read_bytes())
        return frames


def shrink(data, width=640):
    """Vision APIs bill images by size: a 640 px preview is plenty to judge
    content and costs about a third of a 1280x720 cover. Unchanged on error."""
    try:
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(data))
        if image.width <= width: return data
        image = image.convert('RGB').resize((width, max(1, round(image.height * width / image.width))))
        out = BytesIO(); image.save(out, 'JPEG', quality=82)
        return out.getvalue()
    except Exception:
        return data


def _sleep(seconds, service):
    import time
    for _ in range(int(seconds * 2)):
        if service.closed: return
        time.sleep(.5)


def fetch_thumbnail(url):
    """Small preview image from the provider CDN (no API key is sent)."""
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=False) as client:
            response = client.get(url)
            if response.status_code != 200 or len(response.content) > 3_000_000: return None
            return response.content
    except httpx.HTTPError:
        return None


def diagnostics(service, project_id):
    """Everything about every slot's search and selection, for a support file."""
    state = service.view(project_id)
    slots = []
    for s in state['slots']:
        media = s.get('selected_media') or {}
        slots.append({'order': s['order'], 'scene_id': s['scene_id'], 'start': s['estimated_start'], 'end': s['estimated_end'],
                      'duration': s['duration'], 'status': s['status'], 'locked': s['locked'], 'message': s.get('message', ''),
                      'stage': (s.get('director') or {}).get('stage_label'), 'ai_review': s.get('ai_review'),
                      'media': {k: media.get(k) for k in ('provider', 'media_type', 'media_id', 'width', 'height', 'duration', 'page_url', 'local_path')} if media else None,
                      'segment_start': s.get('segment_start'), 'continuation_of': s.get('continuation_of'),
                      'planned_query': s.get('search_query'), 'fallback_queries': s.get('fallback_queries'),
                      'director': s.get('director'), 'older_search_diagnostics': s.get('search_diagnostics', [])[-12:],
                      'missing_reasons': s.get('missing_reason_messages', [])})
    with closing(service.projects._connection()) as c:
        jobs = [{'id': r['id'], 'action': r['action'], 'status': r['status'], 'error': r['error_message'], 'created_at': r['created_at'],
                 'progress': {k: v for k, v in json.loads(r['progress_json']).items() if k in ('message', 'percent', 'category', 'ai_error', 'ai_failure', 'review_skipped', 'unavailable_providers', 'review', 'media_summary')}}
                for r in c.execute('SELECT * FROM stock_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 10', (project_id,))]
    return {'generated_at': now(), 'project_id': project_id, 'plan_id': state['plan_id'], 'summary': state.get('media_summary'),
            'providers_configured': state['providers'], 'warnings': state['warnings'], 'jobs': jobs, 'slots': slots}
