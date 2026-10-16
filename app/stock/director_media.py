"""“Medyayı Tamamla”: the AI (Gemini free tier by default, Claude if chosen)
chooses stock media and every slot gets filled.

Chain per slot (each stock step needs the AI's approval after it has looked
at the candidates' preview frames; irrelevant media is never used to fill):
  1. stock video with the planned queries
  2. stock video with queries the AI rewrites for this slot
  3. stock image (rendered with light camera motion)
  4. media for the broader topic (still approved by the AI)
  5. very short slots (<1.5 s): continue the neighbouring shot
  6. motion graphic from the narration (only when no stock fits); a scene
     with no number/place/date uses its own text, never generic scenery.
Every candidate is also checked against the video's period and place
(app/stock/setting.py): modern things in an ancient topic, cartoon/3D in a
history documentary, landmarks of places the video never names are dropped.
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
from app.providers.gemini_chain import MAX_MODELS
from app.stock import relevance
from app.stock.shot import bind as bind_shot, narration as shot_narration, memo_key
from app.stock.performance import timed
from app.stock.cards import render_card
from app.stock.download import USER_AGENT, asset_path, directory, safe_url
from app.stock.identities import identity_keys
from app.stock.models import StockError

LOG = logging.getLogger('uvicorn.error.stock')


def clock():  # replaced in tests
    import time
    return time.monotonic()
STAGES = {'locked': 'Kilitli (sizin seçiminiz)', 'kept': 'Mevcut seçim · yapay zekâ onayladı',
          'stock_video': '1 · Stok video (planlanan sorgu)', 'rewritten_video': '2 · Stok video (yapay zekânın yeni sorgusu)',
          'stock_image': '3 · Stok görsel + hafif kamera hareketi', 'broader': '4 · Daha geniş konu medyası',
          'merged': '6 · Komşu çekimin devamı (çok kısa yuva)', 'card': '5 · Üretilmiş kart',
          'neutral': '5 · Nötr görüntü (manzara / gökyüzü / doku)',
          'motion': '5 · Motion grafik (anlatımdan)', 'motion_planned': 'Motion grafik (yönetmen planı)',
          'motion_edit': 'Motion grafik (sizin düzenlemeniz)', 'motion_owner': 'İnfografik (metindeki işaretiniz)',
          'motion_balance': 'Motion grafik (dengeli kurgu)',  # older projects only
          'relaxed': '4b · Gevşetilmiş dönem/yer filtresiyle stok'}
MOTION_WARN = 25        # % of slots: above this the screen warns (too little stock footage)
MOTION_TARGET = MOTION_WARN / 100  # legacy relaxation helper; automatic calls disabled
QUOTE_SHARE = .30       # at most this share of motion slots may be a plain text (quote) card
CANDIDATES = 4          # at most this many candidates per slot go to the AI (after a metadata pre-filter)
IMAGES_PER_REQUEST = 4  # pictures per AI request (each ≤512 px JPEG); one after a batch got “server busy”
APPROVE_SCORE = 7       # 0-10: only 7+ stock media is ever used
CLIP_APPROVE = 7        # local picture model (CLIP) score that approves a candidate by itself
CLIP_MIN = 4            # below this CLIP score a candidate is dropped (dog / office / modern city …)
SIMILAR_FRAMING = 6     # dHash bits: closer than this to the previous shot of the scene = same framing
# Never-wanted signs in provider metadata (checked before the AI look).
RED_FLAGS = {'watermark', 'watermarked', 'logo', 'logos', 'subscribe', 'intro', 'outro', 'template', 'lower third', 'green screen', 'chroma key'}
MERGE_SECONDS = 1.5
REUSE_GAP = 6           # the same clip again (another part of it) only this many slots apart, in another scene
OPENING_CARD = 4        # first scene: a card's words show at most this long, over moving footage
WAIT_BUDGET = 60        # seconds of rate-limit pauses per job; then the job continues with local scoring
FIRST_ANSWER_SECONDS = 60  # no AI answer at all within this time → the whole job continues locally
REQUEST_SECONDS = 60    # later: one request may take this long, then that look is skipped
PROGRESS_TICK = 2       # seconds between “model X, N s left” screen updates
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
PROBE_SCHEMA = {'type': 'object', 'required': ['ok'], 'properties': {'ok': {'type': 'boolean'}}}
PLACE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['found', 'lat', 'lon'],
                'properties': {'found': {'type': 'boolean'}, 'lat': {'type': 'number'}, 'lon': {'type': 'number'}}}
INFOGRAPHIC = ('map', 'number', 'timeline', 'compare', 'list', 'route', 'empire', 'zoom', 'mark', 'beforeafter', 'icons', 'ratio', 'dynasty', 'fact', 'intro', 'outro', 'region', 'arrow', 'archive')
MAP_MARKERS = ('map', 'route', 'empire', 'zoom', 'region', 'arrow', 'compare')  # never stock footage, even when the place is unknown
NEW_MARKERS = ('route', 'empire', 'zoom', 'mark', 'beforeafter', 'icons', 'ratio', 'dynasty', 'fact', 'region', 'arrow', 'archive')
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


def key_text(media):
    return f'{media["provider"]}:{media["media_type"]}:{media["media_id"]}'


def clip_descriptor(slot, scene, language='de', setting=None):
    """English description for the picture model: the owner's [GÖRSEL] note,
    the slot's planned query and the sentence's filmable words (+ the video's
    period and place, e.g. “ancient Mesopotamia”)."""
    scene = bind_shot(scene, slot, language) if not scene.get('_shot_bound') and 'estimated_start' in slot else scene
    from app.scripts.query_clean import english_query
    hints = [h.get('value', '') for h in scene.get('owner_hints') or [] if h.get('type') == 'visual']
    narration = scene.get('narration_text', '')
    parts = [english_query(h, language, limit=6) for h in hints]
    parts += [english_query(q, language, limit=5) for q in (slot.get('search_query'), scene.get('primary_stock_query')) if q]
    parts.append(english_query(narration, language, strict=True, limit=6))
    seen, words = set(), []
    for part in parts:
        for word in part.split():
            if word.casefold() not in seen: seen.add(word.casefold()); words.append(word)
    where = [w for w in str((setting or {}).get('label_en') or '').split() if w.casefold() not in seen and w.isascii()]
    if words: return 'a photo of ' + ' '.join(words[:16]) + (', ' + ' '.join(where) if where else '')
    return ('a photo of ' + ' '.join(where)) if where else 'a documentary photo'


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
    ratio = media['width'] / max(1, media['height'])
    if not (1.6 <= ratio <= 1.95 if media['media_type']=='video' else 1.3 <= ratio <= 2.):
        return 'orientation'
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
        self.local, self.requests = False, 0
        self.answered, self.ai_waited, self.skipped_looks, self.last_error, self.single = False, 0.0, 0, None, False
        self.clip, self.marker_error, self.marker_note = None, '', ''
        self.unavailable = dict(self.progress.get('unavailable_providers', {}))
        self.rejected, self.rejected_keys, self.rejected_hashes = [], set(), set()
        self.filtered_keys, self.ai_rejected_keys, self.looks, self.scene_last = set(), set(), {}, {}
        self.scene_order, self.scene_text, self.topic, self.owner, self.language = [], {}, '', {}, 'de'
        self.setting, self.scene_settings, self.setting_seen = None, {}, set()
        self.relax = 0  # 0: period/place rules in full; 1: period/look rules off; 2: place rules off too (see relaxed())

    # ---- AI engine---------------------------------------------------------
    def connect(self):
        """The AI look is optional: switched off in Settings, no engine, or the
        engine cannot be reached → local scoring (tags/words), never a stop."""
        settings = self.service.settings
        from app.stock.clip_check import MISSING, ClipCheck
        self.clip = ClipCheck(self.service)
        self.progress['clip_ready'] = self.clip.ready()
        if not self.progress['clip_ready']: self.progress['clip_warning'] = MISSING
        else: self.progress.pop('clip_warning', None)
        engine = settings.ai_engine()
        self.engine = engine or 'gemini'
        self.label = 'Claude' if engine == 'claude' else 'Gemini'
        if not getattr(settings, 'ai_visual_check', lambda: False)():
            return self._go_local(None, 'off')
        if not engine:
            return self._go_local(None, 'no_engine')
        try:
            factory = getattr(self.service, 'ai_factory', None)
            if factory is None:
                from app.providers.factory import make_script_provider
                factory = lambda: make_script_provider(self.engine, self.service.settings)
            self.ai = factory()
        except ScriptProviderError as error:
            self._go_local(error)

    def _go_local(self, error, why='down'):
        """From now on this job judges candidates locally (provider tags and
        words, as before the AI look existed). Those slots are marked “yapay
        zekâ onayı yok” and the AI looks at them again on a later press."""
        if self.ai is not None: self.chain = self.ai  # keep its attempt log for the diagnostics file
        self.ai, self.local = None, True
        if error is not None:
            category = getattr(error, 'category', '') or 'provider_error'
            self.ai_error = str(error)
            self.progress['ai_failure'] = {'category': category, 'message': str(error)[:300], 'upstream_status': getattr(error, 'upstream_status', None),
                                           'stage': getattr(error, 'stage', ''), 'waited_seconds': round(self.waited + self.ai_waited), 'at': now(),
                                           'slot_id': self.progress.get('slot_id')}
            why = 'down'
            self.progress['local_reason'] = local_message(self.label, category, int(getattr(error, 'retry_after', 0) or 0), getattr(error, 'chain_models', None))
        else:
            self.progress['local_reason'] = {'off': ('Gemini görsel kontrolü kapalı (varsayılan); adaylar yerel görüntü modeli (CLIP) ve etiket/kelime eşleşmesiyle seçildi.'
                                                     if self.clip and self.clip.ready() else
                                                     'Gemini görsel kontrolü kapalı (varsayılan); adaylar etiket/kelime eşleşmesiyle seçildi.'),
                                             'no_engine': 'Yapay zekâ ayarlı değil; medya yerel kelime eşleşmesiyle seçildi.'}[why]
        self.progress['local_mode'] = why
        return None

    def _ask(self, purpose, prompt, schema, images=(), max_tokens=2000):
        """One AI request with a hard deadline. Until the engine has answered
        once, all waiting together may take FIRST_ANSWER_SECONDS (then the
        whole job continues locally); later, one request may take
        REQUEST_SECONDS (then that look is skipped; twice in a row → local)."""
        if self.local or not self.ai: return None
        self.last_error = None
        for attempt in range(3):
            limit = REQUEST_SECONDS if self.answered else FIRST_ANSWER_SECONDS - self.ai_waited
            if limit <= 0:
                return self._timed_out(limit)
            self.requests += 1
            self.progress['ai_requests'] = self.requests
            started = clock()
            done, answer, error = self._call_ai(purpose, prompt, schema, images, max_tokens, limit)
            spent = clock() - started
            if not done:  # no answer before the deadline: never wait longer
                self.ai_waited += spent
                return self._timed_out(limit)
            if error is None:
                self.unusable, self.skipped_looks, self.answered = 0, 0, True
                self.progress.pop('ai_trying', None)
                return answer
            if not self.answered: self.ai_waited += spent
            category = getattr(error, 'category', '')
            self.last_error = category
            if getattr(error, 'batch_rejected', False) and not self.single:
                self.last_error = 'batch_rejected'  # the caller checks whether pictures one by one still work
                return None
            if category in UNUSABLE:
                # This one answer is unusable; the engine itself still works.
                self.unusable += 1
                if self.unusable >= UNUSABLE_LIMIT: self._go_local(error)
                return None
            exhausted = getattr(error, 'chain_exhausted', False)
            if category not in ('rate_limit', 'quota_limit') or exhausted:
                if self.answered and category in TRANSIENT and not exhausted:
                    return self._skip_look(error)
                self._go_local(error)  # quota/key/model problem, the chain could not answer, or a time-out: continue locally
                return None
            # An explicit per-minute limit: a short wait inside the budget, then the same model again.
            pause = min(30, max(5, int(getattr(error, 'retry_after', 0) or 10)))
            if attempt >= 2 or self.waited + pause > WAIT_BUDGET or (not self.answered and self.ai_waited + pause >= FIRST_ANSWER_SECONDS):
                self._go_local(error)
                return None
            self.progress['message'] = f'{self.label} kısa bir hız sınırına takıldı: {pause} sn bekleniyor, sonra devam edilecek'
            self.service._checkpoint(self.job, self.progress, light=True)
            getattr(self.service, 'ai_sleep', _sleep)(pause, self.service)
            if self.service.closed: raise StockError('interrupted', 'İşlem durdu; tamamlanan yuvalar korundu. Medyayı Tamamla ile sürdürün.')
            self.waited += pause
            if not self.answered: self.ai_waited += pause
        return None

    def _call_ai(self, purpose, prompt, schema, images, max_tokens, limit):
        """(finished, answer, error). The request runs in a helper thread so the
        screen can show which model is being asked and how many seconds are
        left; after `limit` seconds the job stops waiting for it."""
        import contextvars
        import threading
        box = {'model': getattr(self.ai, 'model', ''), 'number': 1}
        models = len(getattr(self.ai, 'models', []) or [1])
        if hasattr(self.ai, 'on_try'):
            self.ai.on_try = lambda model, number: box.update(model=model, number=number)
        kwargs = {'images': list(images), 'effort': 'low', 'max_tokens': max_tokens}

        def work():
            try: box['answer'] = self.ai.complete_json(purpose, prompt, schema, **kwargs)
            except ScriptProviderError as error: box['error'] = error
            except Exception as error:  # never let a helper-thread crash stall the job
                box['error'] = ScriptProviderError(f'{self.label} isteği tamamlanamadı.', category='network_error', exception_class=type(error).__name__)
        thread = threading.Thread(target=contextvars.copy_context().run, args=(work,), daemon=True)
        started = clock()
        thread.start()
        while True:
            thread.join(min(PROGRESS_TICK, max(0.0, limit - (clock() - started))))
            if not thread.is_alive(): break
            left = limit - (clock() - started)
            if left <= 0: break
            model = str(box.get('model') or '').removeprefix('gemini-')
            self.progress['ai_trying'] = {'model': box.get('model'), 'number': box.get('number'), 'seconds_left': int(left + .999)}
            self.progress['message'] = (f'{self.label} {model} deneniyor ({min(box.get("number") or 1, MAX_MODELS)}/{min(models, MAX_MODELS)}) · '
                                        f'en fazla {int(left + .999)} sn kaldı; cevap gelmezse yerel seçime geçilecek')
            self.service._checkpoint(self.job, self.progress, light=True)
            if self.service.closed: break
        if thread.is_alive():
            return False, None, None
        return True, box.get('answer'), box.get('error')

    def _timed_out(self, limit):
        error = ScriptProviderError(f'{self.label} {int(REQUEST_SECONDS if self.answered else FIRST_ANSWER_SECONDS)} sn içinde yanıt vermedi.',
                                    504, category='gemini_timeout' if self.engine == 'gemini' else 'timeout')
        self.last_error = error.category
        if self.answered:
            return self._skip_look(error)
        self._go_local(error)  # no answer at all in the first minute: the WHOLE job continues locally
        return None

    def _skip_look(self, error):
        """The engine answered before; this one look is skipped (local scoring for it). Twice in a row → local."""
        self.skipped_looks += 1
        self.progress['ai_skipped_looks'] = self.progress.get('ai_skipped_looks', 0) + 1
        if self.skipped_looks >= 2: self._go_local(error)
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
        where = self.where(scene)
        return (f'Video topic: {self.topic}\n'
                + (f'Period and place of this video: {where["label_en"]}. Footage that contradicts it is wrong '
                   '(modern people, cars, shops or cities in an older period; cartoons or 3D renders in a history documentary; '
                   'landmarks of other places such as Easter Island or the pyramids of Giza).\n' if where and where.get('label_en') else '') +
                f'Previous sentence: "{sentence_at(before, 1.0)}"\nNext sentence: "{sentence_at(after, 0.0)}"\n'
                + (f'Proper names (priority): {", ".join(scene.get("entities") or [])}\n' if scene.get('entities') else '')
                + (f'Owner’s own visual note (top priority): {hints}\n' if hints else '')
                + (f'The owner REJECTED these earlier picks (avoid similar footage): {owner}\n' if owner else '') +
                f'Narration of this shot (spoken language {scene.get("stock_query_language", "")}): '
                f'"{sentence_at(scene.get("narration_text", ""), .5) if used_seconds(slot) < 6 else scene.get("narration_text", "")[:600]}"\n'
                f'Scene narration: "{scene.get("narration_text", "")[:900]}"\n'
                f'Visual goal: {scene.get("visual_intent") or slot.get("visual_goal", "")}\n'
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

    @timed('judging')
    def judge(self, slot, scene, pool, *, batch=None, review_selected=False):
        """Verdicts by key for up to CANDIDATES candidates per slot. Known
        verdicts (any project, same kind of shot) are reused; the rest go to
        the AI in ONE request, each candidate as one picture (a video's start/
        middle/end frames side by side). Without the AI: local scoring."""
        if 'estimated_start' in slot:
            scene = bind_shot(scene, slot, getattr(self, 'language', 'en'))
        from app.stock.verdict_cache import VerdictCache, cache_key, context
        cache = self.verdict_cache()
        if getattr(self, 'clip', None):
            self.clip.ready()  # initialize the model identity before cache lookup
        model = getattr(getattr(self,'clip',None),'model_version','')
        evaluator = {'clip': model, 'cloud': getattr(self, 'engine', '') if not self.local else '',
                     'model': getattr(getattr(self, 'ai', None), 'model', '')}
        fingerprint = context(scene, {**slot, 'quality_setting': self.where(scene), 'quality_evaluator': evaluator})
        budget_key = (fingerprint, scene.get('scene_id'))
        verdicts, ask = {}, []
        for media in pool:
            known = cache.get(cache_key(media, fingerprint)) if cache else None
            if known and isinstance(known.get('score'), int):
                verdicts[key(media)] = {**known, 'cached': True}
                self.progress['ai_cached'] = self.progress.get('ai_cached', 0) + 1
                self.look_budget = getattr(self, 'look_budget', {})
                self.look_budget[budget_key] = 1
            else:
                ask.append(media)
        if not ask: return verdicts
        decided = self.clip_judge(slot, scene, ask)  # the local picture model first: clear matches / clear misses
        if cache and decided:
            cache.put({cache_key(m, fingerprint): {**decided[key(m)], 'at': now()}
                       for m in ask if key(m) in decided})
        verdicts.update(decided)
        ask = [m for m in ask if key(m) not in decided]
        if not ask: return verdicts
        if self.local:
            verdicts.update(self.local_judge(slot, scene, ask)); return verdicts
        profile = slot.get('relevance_profile') or relevance.profile(scene, slot)
        supported = []
        for media in ask:
            if relevance.acceptable(relevance.evaluate(media, profile), profile):
                supported.append(media)
            else:
                verdicts[key(media)] = {'score': 0, 'approved': False, 'local': True,
                                       'reason': 'Kaynak etiketleri cümlenin konusunu desteklemiyor; elendi.'}
        ask = supported
        if not ask: return verdicts
        if not review_selected and getattr(self, 'look_budget', {}).get(budget_key, 0) >= 1:
            # Do not fetch/composite previews for a cloud request we will skip.
            self.progress['visual_budget_skipped'] = self.progress.get('visual_budget_skipped', 0) + len(ask)
            return verdicts
        entries = []
        for index, media in enumerate(ask, 1):
            frames = self.frames(media)
            if not frames:
                director = slot.setdefault('director', {}) or {}
                director['skipped_no_preview'] = director.get('skipped_no_preview', 0) + 1; slot['director'] = director
                continue
            entries.append((index, media, collage(frames)))
        if not entries: return verdicts
        model_before = None
        start = 0
        while start < len(entries):
            # At most IMAGES_PER_REQUEST pictures per request (one after a picture batch was refused).
            group = entries[start:start + (1 if self.single else IMAGES_PER_REQUEST)]
            start += len(group)
            if self.local:
                verdicts.update(self.local_judge(slot, scene, [m for _, m, _ in group])); continue
            self.look_budget = getattr(self,'look_budget',{})
            if not review_selected and self.look_budget.get(budget_key,0)>=1:
                # One bounded visual batch per exact sentence/scene/constraints.
                # Extra searches use confirmed CLIP verdicts or relevant motion;
                # they never create an unbounded cascade of paid requests.
                # An exhausted paid budget is not visual approval. Only the
                # already resolved CLIP/cache verdicts may select stock here.
                self.progress['visual_budget_skipped']=self.progress.get('visual_budget_skipped',0)+len(group)
                continue
            self.look_budget[budget_key]=self.look_budget.get(budget_key,0)+1
            answer = self._rate(slot, scene, group, batch)
            if answer is None and self.last_error == 'batch_rejected' and not self.local:
                if self.diagnose_batch():  # small text requests work: the picture batch was the problem
                    self.look_budget[budget_key]=0  # retry the rejected batch once as individual pictures
                    start -= len(group); continue  # the same candidates again, one per request
            if answer is None:  # skipped look or the AI went away: score these locally
                verdicts.update(self.local_judge(slot, scene, [m for _, m, _ in group])); continue
            model = getattr(self.ai, 'last_model', None) or getattr(self.ai, 'model', None) or model_before  # which model of the chain decided
            model_before = model
            listed = {index: media for index, media, _ in group}
            fresh = {}
            for item in answer.get('verdicts', []):
                index = item.get('candidate')
                if isinstance(index, int) and index in listed:
                    try: score = max(0, min(10, round(float(item.get('score', 0)))))
                    except (TypeError, ValueError): score = 0
                    verdict = {'score': score, 'approved': item.get('approved') is not False and score >= APPROVE_SCORE,
                               'reason': ' '.join(str(item.get('reason', '')).split())[:300],
                               **({'model': model} if isinstance(model, str) and model else {})}
                    profile = slot.get('relevance_profile') or relevance.profile(scene, slot)
                    if verdict['approved'] and not relevance.acceptable(relevance.evaluate(listed[index], profile), profile):
                        verdict.update(score=min(score,4), approved=False,
                                       reason='Görsel yanıt olumlu olsa da kaynak etiketleri cümlenin konusunu desteklemiyor; elendi.')
                    verdicts[key(listed[index])] = verdict
                    fresh[cache_key(listed[index], fingerprint)] = {**verdict, 'at': now()}
            if cache: cache.put(fresh)
        return verdicts

    def _rate(self, slot, scene, group, batch):
        blocks, listed = [], []
        for index, media, picture in group:
            orientation = 'landscape' if media['width'] > media['height'] else 'portrait/square (will be shown on a blurred background)'
            blocks.append({'type': 'text', 'text': f'Candidate {index}: {media["media_type"]}, {media["width"]}x{media["height"]}, {orientation}'
                                                   + (f', {media["duration"]:.0f} s' if media.get('duration') else '')
                                                   + f'. Provider tags: {media.get("description", "")[:200]}'
                                                   + (f'. Local image model (CLIP): {media["clip"]["verdict"]}' if media.get('clip') else '')})
            blocks.append(picture)
            listed.append(index)
        shots = (f'\nThis scene has {batch} shots; the candidates are pooled for all of them — rate each candidate for the scene.' if batch and batch > 1 else '')
        prompt = (self.brief(slot, scene) + shots + '\n\nYou are choosing documentary B-roll for this shot. For EVERY candidate above '
                  '(a video candidate is ONE picture with its start, middle and end frames side by side), give score 0-10 using these criteria: '
                  '(1) does it show what the narration says right now (the visual goal / MUST show)? '
                  '(2) do the period, place and setting fit (no modern things in historical scenes, right environment, day/night)? '
                  '(3) is anything from the MUST-NOT list visible? (4) any text, watermark or logo on screen? (5) image quality. '
                  'A score of 7 or more means a viewer would see exactly what is being said; unrelated, generic-but-wrong, '
                  'anachronistic, watermarked or low-quality footage scores at most 4. approved=true only for 7+ with nothing from '
                  'the MUST-NOT list. reason: ONE short sentence in Turkish for the channel owner. '
                  f'Candidates to rate: {listed}.')
        return self._ask('media_select', prompt, JUDGE_SCHEMA, blocks)

    def diagnose_batch(self):
        """A picture batch got “server busy” (503): is it the server or the
        batch? One tiny text request decides. Text works → pictures go one per
        request from now on; text fails too → the job continues locally."""
        self.progress['message'] = f'{self.label} görsel toplu isteğe “sunucu meşgul” dedi; küçük bir metin isteğiyle nedeni kontrol ediliyor'
        self.service._checkpoint(self.job, self.progress, light=True)
        answer = self._ask('media_probe', 'Connectivity check. Answer with {"ok": true}.', PROBE_SCHEMA, max_tokens=50)
        works = isinstance(answer, dict) or self.last_error in UNUSABLE  # any reply (even an odd one) means text requests get through
        self.progress['gemini_503_diagnosis'] = (
            'Küçük metin isteği çalıştı, görsel toplu istek 503 verdi: neden toplu görsel isteği. Bundan sonra her istekte tek aday gönderildi.' if works else
            'Küçük metin isteği de yanıt vermedi: neden Gemini sunucusunun genel yoğunluğu. Seçim yerel olarak sürdü.')
        if works: self.single = True
        elif not self.local: self._go_local(ScriptProviderError(f'{self.label} metin isteğine de yanıt vermedi.', 503, category='upstream_error'))
        return works

    @timed('clip')
    def clip_judge(self, slot, scene, pool, descriptor=None):
        """CLIP scores (0-10) of the candidates' preview frames against the
        sentence + [GÖRSEL] note. Clear match → approved, clear miss or below
        CLIP_MIN → rejected; the rest stay undecided (marked on the media) for
        Gemini (when switched on) or the local word check."""
        if not self.clip or not self.clip.ready(): return {}
        items = []
        for media in pool:
            frames = []
            for block in self.frames(media):
                try: frames.append(base64.b64decode(block['source']['data']))
                except (KeyError, ValueError, TypeError): pass
            if frames: items.append((key_text(media), frames))
        if not items: return {}
        descriptor = descriptor or clip_descriptor(slot, scene, self.language, self.where(scene))
        from app.stock.setting import penalties
        self.progress['message'] = f'Yuva {slot["order"]} · yerel görüntü modeli (CLIP) {len(items)} adayı karşılaştırıyor'
        self.service._checkpoint(self.job, self.progress, light=True)
        scores = self.clip.score(descriptor, items, directory(self.service.projects, self.pid), penalties(self.where(scene), descriptor))
        if not scores and self.clip.broken:
            self.progress['clip_warning'] = 'Yerel görüntü modeli (CLIP) çalışmadı; bu işte medya etiket/kelime eşleşmesiyle seçildi.'
        decided = {}
        for media in pool:
            result = scores.get(key_text(media))
            if not result: continue
            clip = {**result, 'descriptor': descriptor[:160]}
            media['clip'] = clip
            self.progress['clip_checked'] = self.progress.get('clip_checked', 0) + 1
            if isinstance(result.get('conflict'), dict):  # looks like something the period/place rules out
                from app.stock.setting import reason
                self.setting_rejected(media, result['conflict'])
                decided[key(media)] = {'score': min(result['score'], 2), 'approved': False, 'local': True, 'clip': clip, 'setting_conflict': result['conflict'],
                                       'reason': f'Yerel görüntü modeli (CLIP): {reason(result["conflict"])} — videonun dönemi/yeri: {self.where(scene).get("label", "")}; elendi.'}
            elif result['verdict'] == 'match' and result['score'] >= CLIP_APPROVE:
                decided[key(media)] = {'score': result['score'], 'approved': True, 'local': True, 'clip': clip, 'clip_approved': True,
                                       'reason': f'Yerel görüntü modeli (CLIP) kareleri cümleyle eşleştirdi: {result["score"]}/10.'}
            elif result['verdict'] == 'mismatch' or result['score'] < CLIP_MIN:
                decided[key(media)] = {'score': min(result['score'], 4), 'approved': False, 'local': True, 'clip': clip,
                                       'reason': f'Yerel görüntü modeli (CLIP): kareler cümleyle ilgisiz ({result["score"]}/10), elendi.'}
        return decided

    def verdict_cache(self):
        if not hasattr(self, '_verdicts'):
            from app.stock.verdict_cache import VerdictCache
            storage = getattr(self.service.projects, 'storage', None)
            self._verdicts = VerdictCache(storage) if storage else None
        return self._verdicts

    def local_judge(self, slot, scene, pool):
        """Without the AI: provider tags/words against the scene (the older,
        local relevance scoring). Approved ones carry no AI approval."""
        profile = slot.get('relevance_profile') or relevance.profile(scene, slot)
        wanted = local_words(' '.join(str(x or '') for x in (scene.get('must_show'), scene.get('visual_intent'), scene.get('primary_stock_query'),
                                                             slot.get('search_query'), slot.get('visual_goal'), *(scene.get('alternative_stock_queries') or []),
                                                             *(scene.get('entities') or []), *(h.get('value', '') for h in scene.get('owner_hints') or []))))
        verdicts = {}
        for media in pool:
            scored = {**media, **relevance.evaluate(media, profile)}
            value = scored.get('relevance_score') or 0
            # The English query that found it was made from this scene (plan, rewrite or topic): its words count too.
            shared = (wanted | local_words(media.get('query_used', ''))) & local_words(media.get('description', ''))
            ok = relevance.acceptable(scored, profile) and (len(shared) >= 2 or value >= relevance.STRONG)
            verdicts[key(media)] = {'score': min(9, APPROVE_SCORE + max(0, len(shared) - 1) + (value >= 40)) if ok else min(4, len(shared) * 2),
                                    'approved': ok, 'local': True, 'relevance_label': scored.get('relevance_label'),
                                    **({'clip': media['clip']} if media.get('clip') else {}),
                                    'reason': (f'Etiketler sahneyle eşleşiyor ({", ".join(sorted(shared)[:4])})' if ok and shared else
                                               'Etiketler sahneyle eşleşiyor' if ok else 'Etiketler sahneyle eşleşmiyor') + ' — yerel kontrol, yapay zekâ onayı yok.'}
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
        local = self.local_queries(scene, broader)
        seen = {frozenset(t.casefold().split()) for t in tried}
        fresh_local = [q for q in local if frozenset(q.casefold().split()) not in seen]
        if fresh_local:return list(dict.fromkeys(fresh_local))[:3]
        # Rare unknown vocabulary may need a rewrite; never one paid rewrite
        # for every slot and tier of a long film.
        self.query_requests=getattr(self,'query_requests',0)
        if self.query_requests>=3:return []
        self.query_requests+=1
        answer = self._ask('media_queries', self.brief(slot, scene) + f'\nAlready tried: {", ".join(tried)[:600]}\n' + ask, QUERY_SCHEMA, max_tokens=600)
        queries = [' '.join(str(q).split())[:80] for q in (answer or {}).get('queries', []) if isinstance(q, str) and q.strip()]
        if not queries:  # no AI (off, down or no answer): English queries made locally, never an empty step
            queries = self.local_queries(scene, broader)
        seen = {frozenset(t.casefold().split()) for t in tried}
        return [q for q in dict.fromkeys(queries) if frozenset(q.casefold().split()) not in seen][:3]

    def local_queries(self, scene, broader=False):
        """Without the AI: the filmable English words of each sentence of the
        scene (other angles), or — broader — the topic's English fallback queries."""
        from app.scripts.query_clean import english_query, generic_queries
        if broader: return generic_queries(self.topic, self.language)
        out = []
        for sentence in re.split(r'(?<=[.!?…])\s+', scene.get('narration_text', '')):
            words = english_query(sentence, self.language, strict=True, limit=6).split()
            for start in range(0, max(1, len(words) - 1), 2):
                part = ' '.join(words[start:start + 2])
                if len(part.split()) == 2: out.append(part)
        return out

    # ---- searching -----------------------------------------------------------
    def providers(self, scene=None):
        """Pixabay (with a key) and Wikimedia Commons (no key; Pexels is switched
        off). History/archaeology/museum/map scenes ask Wikimedia first."""
        from app.stock.providers import ACTIVE
        names = [n for n in ACTIVE if n == 'wikimedia' or self.service.settings.stock_config(n).get('api_key')]
        if scene is not None and historic(scene): names.sort(key=lambda n: n != 'wikimedia')
        return [n for n in names if n not in self.unavailable]

    @timed('search')
    def search(self, slot, kinds, query, log, scene=None, page=1, provider_names=None):
        from app.scripts.query_clean import english_query, generic_queries
        language = self.language  # the narration language (German/Turkish words are translated)
        english = english_query(query, language, limit=6)
        if not english:  # nothing English left (an older plan's German words): a topic query instead
            english = generic_queries(self.topic, language)[0]
        if english != query: log.setdefault('translated', {})[query] = english
        query = english
        found = []
        executor = getattr(self.service, 'search_executor', None)
        pending = {(kind, name): executor.submit(self.service._cache_search, self.pid, name, kind, query, page=page)
                   for kind in kinds for name in (provider_names or self.providers(scene))} if executor else {}
        for kind in kinds:
            for name in (provider_names or self.providers(scene)):
                entry = {'provider': name, 'media_type': kind, 'query': query, 'page': page}
                self.progress['message'] = f'Yuva {slot["order"]} · {name.title()} {"video" if kind == "video" else "görsel"} aranıyor: “{query}”'
                self.service._checkpoint(self.job, self.progress, light=True)
                try:
                    future = pending.get((kind, name))
                    results, _, cached = future.result() if future else self.service._cache_search(self.pid, name, kind, query, page=page)
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
                if page == 1 and len(results) < 15 and name != 'magnific':  # legacy thin page fallback
                    try:
                        more, _, _ = self.service._cache_search(self.pid, name, kind, query, page=2)
                        results = list(results) + [m for m in more if key(m) not in {key(r) for r in results}]
                    except Exception:
                        pass
                entry.update(results=len(results), cached=cached)
                log['searches'].append(entry)
                found.extend(results)
        return found

    def segment(self, media, need, slot=None):
        """Same footage again only rarely: at most a second use, a different part of a long
        video, never in the same scene and never within REUSE_GAP slots of its first use
        (no repeats in a row). Pictures are used once."""
        taken = self.usage.get(key(media), [])
        if taken:
            if len(taken) >= 2 or media['media_type'] != 'video': return None
            if slot is not None:
                order = {s['slot_id']: i for i, s in enumerate(sorted(getattr(self, 'slots', []), key=lambda s: s['estimated_start']))}
                scene_of = {s['slot_id']: s['scene_id'] for s in getattr(self, 'slots', [])}
                here = order.get(slot['slot_id'])
                for other, _ in taken:
                    if scene_of.get(other) == slot.get('scene_id') or (here is not None and other in order and abs(order[other] - here) < REUSE_GAP):
                        return None
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
        past = self.where(scene).get('era') != 'contemporary'  # only a historical video (or scene) gets the strict “no modern stock” rule
        if media.get('provider') != 'wikimedia' and historic(scene) and past and not getattr(self, 'relax', False) and any(f' {w} ' in tags or f' {w}s ' in tags for w in MODERN):
            return 'modern_in_history'  # a history/museum scene never gets modern stock (cars, phones, offices …)
        from app.stock.setting import tag_conflict
        conflict = tag_conflict(self.where(scene), tags, media.get('provider', ''))
        if conflict:  # the provider's own tags contradict the video's period/place (works without CLIP)
            self.setting_rejected(media, {'kind': conflict[0], 'label': conflict[1], 'source': 'tags'})
            return 'setting_conflict'
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
            if reason is None and self.segment(media, need, slot) is None: reason = 'used_elsewhere'
            if reason is None and k in log['judged'] and not log['judged'][k]['approved']: reason = 'ai_rejected_before'
            if reason is None: reason = self.prefilter(media, scene or {})
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                if reason in ('owner_rejected', 'watermark_or_logo', 'must_not_show', 'modern_in_history', 'setting_conflict') and k not in self.filtered_keys:
                    self.filtered_keys.add(k); self.progress['irrelevant_filtered'] = len(self.filtered_keys) + self.progress.get('ai_rejected', 0)
                continue
            pool.append(relevance.annotate(media, slot['relevance_profile'], 1, media.get('query_used', '')))
        archive = bool(scene) and historic(scene)  # history/museum/map scenes: Commons archive material first
        pool.sort(key=lambda m: (m['width'] > m['height'], archive and m['provider'] == 'wikimedia', key(m) not in self.usage, relevance.rank(m, slot)), reverse=True)
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

    def prejudge(self, scene, slots):
        """Fewer requests: the first planned query of every slot of the scene
        is searched (cached), at most CANDIDATES fresh candidates per slot are
        pooled (max 16) and judged in one request. Slots then reuse these
        verdicts; only a slot whose candidates all failed asks again."""
        clip = bool(self.clip and self.clip.ready())
        if (self.local and not clip) or not slots: return
        # Only pool shots which describe the same narration, never different sentences.
        groups = {}
        for slot in slots:
            bound = bind_shot(scene, slot, self.language)
            groups.setdefault(memo_key(bound), []).append(slot)
        if len(groups) > 1:
            for group in groups.values():
                self.prejudge(bind_shot(scene, group[0], self.language), group)
            return
        scene = bind_shot(scene, slots[0], self.language)
        memo = self.memo.setdefault(memo_key(scene), {'judged': {}})
        pooled, seen = [], set()
        for slot in slots:
            slot['relevance_profile'] = relevance.profile(scene, slot)
            query = next((q for q in [scene.get('primary_stock_query'), slot.get('search_query'), *slot.get('fallback_queries', [])] if q), None)
            if not query: continue
            kinds = ['video'] if slot.get('preferred_type') != 'stock_image' else ['image', 'video']
            log = {'steps': [], 'searches': [], 'judged': memo['judged'], 'rejected': {}}
            fresh = [m for m in self.pool(slot, self.search(slot, kinds, query, log, scene), log, set(), scene)
                     if key(m) not in memo['judged'] and key(m) not in seen][:CANDIDATES]
            for media in fresh:
                seen.add(key(media)); pooled.append(media)
        pooled = pooled[:24 if clip else 16]
        if not pooled: return
        self.progress['message'] = (f'Sahne {scene.get("order", "")} · {"yerel görüntü modeli (CLIP)" if clip else self.label} '
                                    f'{len(pooled)} adaya tek seferde bakıyor ({len(slots)} yuva)')
        self.service._checkpoint(self.job, self.progress, light=True)
        for k, verdict in self.judge(slots[0], scene, pooled, batch=len(slots)).items():
            memo['judged'][k] = verdict

    def try_step(self, slot, scene, stage, kinds, queries, log, exclude):
        """Queries are tiers (very specific → medium → general): each tier is
        searched, pre-filtered and judged on its own; only when no candidate
        reaches 7/10 does the next tier start."""
        step = {'stage': stage, 'label': STAGES[stage], 'queries': list(queries), 'judged': []}
        log['steps'].append(step)
        for query in queries:
            pool = self.pool(slot, self.search(slot, kinds, query, log, scene), log, exclude, scene)
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

    def extended_search(self, slot, scene, queries, log, exclude):
        """Extra pages, then optional Premium source; stop as soon as a candidate passes checks."""
        from app.stock import relevance
        from app.stock.magnific import MagnificStockProvider
        config = self.service.settings.stock_config('magnific')
        sources = self.providers(scene)
        free = [name for name in sources if name in ('pixabay', 'wikimedia')]
        for query in list(dict.fromkeys(queries))[:2]:
            for page in (2, 3):
                for provider in free:
                    results = self.search(slot, ['video'], query, log, scene, page=page, provider_names=[provider])
                    pool = self.pool(slot, results, log, exclude, scene)
                    for media in pool[:CANDIDATES]:
                        verdict = self.judge(slot, scene, [media]).get(key(media))
                        if verdict and verdict.get('approved') and verdict.get('score', 0) >= APPROVE_SCORE:
                            if self.take(slot, media, verdict, 'stock_video', log):
                                return True
        if not (config.get('enabled') and config.get('api_key')):
            return False
        for query in list(dict.fromkeys(queries))[:2]:
            for page in (1, 2):
                results = self.search(slot, ['video'], query, log, scene, page=page, provider_names=['magnific'])
                pool = self.pool(slot, results, log, exclude, scene)
                for media in pool[:CANDIDATES]:
                    verdict = self.judge(slot, scene, [media]).get(key(media))
                    if (verdict and verdict.get('approved') and verdict.get('score', 0) >= APPROVE_SCORE
                            and (verdict.get('clip_approved') or not verdict.get('local'))):
                        if self.take(slot, media, verdict, 'stock_video', log):
                            return True
        return False

    @timed('download_validation')
    def take(self, slot, media, verdict, stage, log):
        need = used_seconds(slot)
        start = self.segment(media, need, slot)
        if start is None: return None
        try:
            saved = self.service.downloader.download(self.pid, media)
            from app.stock.quality import inspect_media
            from app.rendering.tools import discover
            inspector = getattr(self.service, 'quality_inspector', inspect_media)
            if not hasattr(self, 'quality_tools'): self.quality_tools = discover()
            self.quality_cache = getattr(self, 'quality_cache', {})
            quality_key = (saved.get('sha256'), round(start,3))
            if quality_key not in self.quality_cache:
                self.quality_cache[quality_key] = inspector(self.service.projects, self.pid, saved, self.quality_tools, start)
            quality = self.quality_cache[quality_key]
            if not quality.get('accepted'):
                log['steps'][-1].setdefault('quality_rejections', []).append(quality.get('reason','quality_unverified'))
                return None
            if media['media_type']=='video' and (quality.get('duration') or 0) + .05 < start + need:
                return None
        except StockError as error:
            log['steps'][-1].setdefault('download_errors', []).append(error.category)
            return None
        if any(identity_keys(saved) & identity_keys(other) for k, other in self.media_by_key.items() if k != key(media)):
            return None  # same bytes under another id: still a duplicate
        segment = start if key(media) in self.usage else None
        self.register(slot['slot_id'], saved, segment or 0., need)
        slot.update(selected_media=saved, status='complete', missing_reasons=[], warnings=[], local_validation=quality,
                    segment_start=segment, continuation_of=None,
                    ai_review=None if verdict.get('local') else {'approved': True, 'score': verdict['score'], 'reason': verdict['reason'], 'reviewed_at': now(),
                                                                 **({'model': verdict['model']} if verdict.get('model') else {})},
                    local_review={'approved': True, 'score': verdict['score'], 'label': verdict.get('relevance_label'), 'reviewed_at': now(),
                                  **({'clip': verdict['clip']} if verdict.get('clip') else {}),
                                  'method': 'clip' if verdict.get('clip_approved') else 'words'} if verdict.get('local') else None,
                    needs_ai_review=bool(verdict.get('local')) and not verdict.get('clip_approved'),
                    message=verdict['reason'])
        if saved['width'] <= saved['height']:
            slot['warnings'].append('Dikey/kare kaynak: yatay videoda bulanık arka planla gösterilir.')
        if segment is not None:
            slot['warnings'].append('Aynı uzun klibin başka bir bölümü kullanılıyor (çakışma yok).')
        log['steps'][-1]['result'] = 'chosen'
        from app.stock.verdict_cache import context
        original = getattr(self, 'scene_by_id', {}).get(slot['scene_id'])
        if original:
            slot['selection_context'] = context(bind_shot(original, slot, self.language), slot)
        where = self.where(self.scene_by_id.get(slot['scene_id'], {}) if hasattr(self, 'scene_by_id') else {})
        if where.get('label'):
            from app.stock.setting import rules_version
            slot['setting_check'] = {'label': where['label'], 'clip': bool(verdict.get('clip')), 'rules': rules_version()}
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
            scene = getattr(self, 'scene_by_id', {}).get(slot['scene_id'])
            if scene and (neighbour['scene_id'] != slot['scene_id'] or shot_narration(scene, neighbour) != shot_narration(scene, slot)):
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
            switches = self.service.settings.moments() if hasattr(self.service.settings, 'moments') else {}
            for hint in scene.get('owner_hints') or []:
                if hint.get('type') not in INFOGRAPHIC or not hint.get('value'): continue
                if (hint['type'] == 'intro' and not switches.get('intro_card')) or (hint['type'] == 'outro' and not switches.get('outro_card')):
                    continue  # switched off in Ayarlar (default): an older plan's moment becomes a normal scene
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
        """(lat, lon) from the local place lists / Mapbox Geocoding, else from the AI, else None."""
        from app.motion.places import locate
        found = locate(name)
        if found: return found['lat'], found['lon']
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

    def nearest_map(self, hint, scene):
        """(spec, Turkish note) for a map marker whose place could not be found: the
        map of the nearest known place — another place in the same marker, a place
        spoken in this scene, then in the neighbouring scenes, then anywhere in the
        script; the whole world as the very last resort."""
        from app.motion.places import locate, spoken_places
        value = ' '.join(str(hint['value']).split())
        reason = getattr(self, 'marker_error', '') or 'yer listesinde ve Mapbox yer aramasında bulunamadı'
        found = None
        for part in re.split(r'>|→|->|\||;|,|\bvs\.?\b|\bkarşı\b|\bgegen\b', value):
            part = part.strip()
            if part and not re.search(r'\d', part) and (place := locate(part)):
                found = (part, place['lat'], place['lon']); break
        if not found:
            order = getattr(self, 'scene_order', []) or [scene.get('scene_id')]
            here = order.index(scene['scene_id']) if scene.get('scene_id') in order else 0
            texts = [str(hint.get('sentence') or ''), scene.get('narration_text', '')] + [
                getattr(self, 'scene_text', {}).get(order[i], '') for i in sorted(range(len(order)), key=lambda i: abs(i - here)) if i != here]
            found = next((spot for text in texts for spot in spoken_places(text)[:1]), None)
        name, lat, lon = found or ('', 20., 0.)
        spec = {'template': 'relief', 'data': {'mode': 'zoom', 'target': (name or value)[:60], 'lat': float(lat), 'lon': float(lon),
                                               'title': (name or value)[:60], 'source': value, **({} if name else {'span': 50.})}, 'emphasis': ''}
        where = f'en yakın bilinen yer ({name})' if name else 'dünya haritası'
        return spec, f'[{value[:60]}] {reason.rstrip(".")}; {where} ile harita çizildi. Yer adını kontrol edin (yazım veya daha bilinen bir ad).'

    def owner_spec(self, hint, scene):
        """The marker's own values become the infographic (only the shape is checked)."""
        from app.motion.numbers import spoken_numbers
        from app.motion.templates import MotionError, short, validate
        kind, value = hint['type'], ' '.join(str(hint['value']).split())
        sentence = ' '.join(str(hint.get('sentence') or sentence_at(scene.get('narration_text', ''), 0)).split()).rstrip('.!?…')
        narration = scene.get('narration_text', '')
        split = lambda text, signs: [x.strip() for x in re.split(signs, text) if x.strip()]
        spec = None
        self.marker_error = ''
        if kind in ('intro', 'outro'):  # kanal anları: stok aranmaz, başlık ve kanal adı projeden gelir
            from app.moments.spec import moment_spec
            channels = getattr(self.service, 'channels', None)
            return moment_spec(kind, value, self.service.projects.get(self.pid).get('name', ''), channels.for_project(self.pid)['name'] if channels else '')
        if kind in NEW_MARKERS:
            from app.motion.templates_extra import MarkerError, parse
            try:
                spec = parse(kind, value, sentence, self.language)
            except MarkerError as error:
                self.marker_error = error.message
                return None
            if spec['data'].get('missing'):
                self.marker_note = f'Yer listesinde bulunamadı, rotaya eklenmedi: {", ".join(spec["data"]["missing"])}.'
            return spec
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
                if not match and 1 <= len(item.split()) <= 2:  # “aujourd'hui” / “heute” / “bugün”: a point without a year
                    events.append({'date': item.strip()[:20], 'label': ''}); continue
                if not match: continue
                date, label = match.group(1)[:20], match.group(2)
                if not label:
                    at = narration.find(date)
                    label = ' '.join(w for w in narration[at + len(date):].split()[:3] if not re.search(r'\d', w)) if at >= 0 else ''
                events.append({'date': date, 'label': label.strip(' ,;:.')[:50]})
            if len(events) >= 2: spec = {'template': 'timeline', 'data': {'events': events[:5]}, 'emphasis': ''}
            elif events: spec = {'template': 'stat', 'data': {'value': events[0]['date'], 'label': short(sentence)}, 'emphasis': events[0]['date']}
        elif kind == 'compare':
            from app.motion.templates_extra import relief_marker
            try:
                compared = relief_marker('compare', value)  # two areas, no numbers: blue/orange overlay on the map, area ratio
            except Exception:
                compared = None
            if compared:
                return compared
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

    def pictures(self, spec, slot, scene):
        """İŞARETLE / ÖNCESONRA need photos: stock pictures for the note (English
        search, checked like any candidate) are downloaded into the project."""
        from app.scripts.query_clean import english_query
        data = spec['data']
        old = spec['template'] == 'archive' and self.archive_period(data, scene)
        if spec['template'] in ('mark', 'archive'):
            if data.get('image'): return True
            base = english_query(data['label'], self.language, limit=5) or scene.get('primary_stock_query') or self.topic
            wanted = [f'{base} black and white', base] if old else [base]
        else:
            if len(data.get('images') or []) == 2: return True
            wanted = [english_query(data['before'], self.language, limit=5), english_query(data['after'], self.language, limit=5)]
        names = []
        slot['relevance_profile'] = slot.get('relevance_profile') or relevance.profile(scene, slot)
        if old:
            self.marker_error = f'{old} dönemine uygun siyah-beyaz / eski arşiv fotoğrafı bulunamadı'
            from app.stock.setting import _era_of_year
            base_setting = self.where(scene) or {}
            era = {**base_setting, 'era': _era_of_year(int(old)) if old.isdigit() else (base_setting.get('era') or '20th'),
                   'decade': (int(old) // 10 * 10) if old.isdigit() and int(old) >= 1900 else None}
            era['label'] = era.get('label') or old
            chosen = None
            for query in wanted:  # one archive photo: the first query that finds an old-looking one wins
                log = {'steps': [{'stage': 'motion_owner', 'label': STAGES['motion_owner'], 'judged': []}], 'searches': [], 'judged': {}, 'rejected': {}}
                pool = [m for m in self.pool(slot, self.search(slot, ['image'], query, log, scene), log, set(), scene)
                        if m['media_type'] == 'image' and not self.archive_conflict(m, era) and self.looks_old(m)][:CANDIDATES]
                sid = scene.get('scene_id'); before = self.scene_settings.get(sid) if hasattr(self, 'scene_settings') else None
                if hasattr(self, 'scene_settings') and self.setting: self.scene_settings[sid] = era  # CLIP: penalties of that period (CG, 3D, modern ships…)
                try: verdicts = self.judge(slot, scene, pool) if pool else {}
                finally:
                    if hasattr(self, 'scene_settings') and self.setting:
                        if before is None: self.scene_settings.pop(sid, None)
                        else: self.scene_settings[sid] = before
                for media in sorted((m for m in pool if verdicts.get(key(m), {}).get('approved')), key=lambda m: -verdicts[key(m)]['score']):
                    try: chosen = self.service.downloader.download(self.pid, media); break
                    except StockError: continue
                if chosen: break
            if not chosen: return False
            self.marker_error = ''
            data['image'] = chosen['local_path'].rsplit('/', 1)[-1]
            return True
        for query in wanted:
            log = {'steps': [{'stage': 'motion_owner', 'label': STAGES['motion_owner'], 'judged': []}], 'searches': [], 'judged': {}, 'rejected': {}}
            pool = [m for m in self.pool(slot, self.search(slot, ['image'], query or self.topic, log, scene), log, set(), scene)
                    if m['media_type'] == 'image'][:CANDIDATES]
            verdicts = self.judge(slot, scene, pool) if pool else {}
            ranked = sorted((m for m in pool if verdicts.get(key(m), {}).get('approved')), key=lambda m: -verdicts[key(m)]['score'])
            saved = None
            for media in ranked:
                try: saved = self.service.downloader.download(self.pid, media); break
                except StockError: continue
            if not saved: return False
            names.append(saved['local_path'].rsplit('/', 1)[-1])
        if spec['template'] in ('mark', 'archive'): data['image'] = names[0]
        else: data['images'] = names
        return True

    def archive_period(self, data, scene):
        """'1910' / 'antik' …: the period an [ARŞİV] photo must look like ('' = present day, any photo)."""
        text = ' '.join(str(x or '') for x in (data.get('label'), data.get('caption'), data.get('source'), scene.get('narration_text')))
        years = [int(y) for y in re.findall(r'(?<!\d)(1[0-9]\d\d)(?!\d)', text) if int(y) < 1975]
        if years: return str(min(years))
        era = (self.where(scene) or {}).get('era')
        return {'ancient': 'antik', 'medieval': 'Orta Çağ', 'early_modern': 'eski', '19th': '19. yüzyıl', '20th': '20. yüzyıl'}.get(era, '')

    def archive_conflict(self, media, era):
        """An archive candidate's tags show CG / 3D / a modern scene (whatever the video's own period)."""
        from app.stock.setting import tag_conflict
        tags = ' ' + relevance.normalized(f'{media.get("description", "")} {media.get("query_used", "")}') + ' '
        cg = any(f' {w} ' in tags for w in ('3d', 'render', 'rendering', 'cgi', 'illustration', 'digital art', 'ai generated', 'modern', 'cruise', 'container'))
        return cg or bool(tag_conflict({**era, 'era': era.get('era') or '20th'}, tags, media.get('provider', '')))

    def looks_old(self, media):
        """Black-and-white / sepia preview (low colour saturation), or archive tags when there is no preview."""
        tags = ' ' + relevance.normalized(media.get('description', '')) + ' '
        block = next((b for b in (self.thumbnail(u, media['provider']) for u in self.frame_urls(media)[:1]) if b), None)
        if block:
            try:
                from io import BytesIO
                from PIL import Image
                picture = Image.open(BytesIO(base64.b64decode(block['source']['data']))).convert('HSV').resize((64, 64))
                return sum(picture.getchannel('S').getdata()) / (64 * 64 * 255) < .14
            except Exception:
                pass
        return any(f' {w} ' in tags for w in ('black and white', 'monochrome', 'sepia', 'vintage', 'historic', 'archive', 'old photo', 'bw'))

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
        previous = self.neighbour_motion(slot)[0]
        same = lambda o: bool(previous) and o['template'] == previous[0]  # two infographics in a row: a different type where possible
        # A plain text card is the last choice; repeat=True: a graphic already shown beats a text card.
        ranked = sorted(options, key=lambda o: (o['template'] == 'quote', o not in fresh, same(o))) if repeat else sorted(fresh or options, key=lambda o: (o['template'] == 'quote', same(o)))
        return (ranked or [{'template': 'quote', 'data': {'text': narration.split('.')[0][:120] or scene.get('visual_intent', '')}, 'emphasis': ''}])[0]

    def quote_full(self):
        """At most ~30% of the motion graphics may be plain text cards."""
        motion = [s for s in self.slots if is_generated(s.get('selected_media')) and s['selected_media']['media_type'] == 'video' and not s.get('continuation_of')]
        quotes = sum(((s['selected_media'].get('source_metadata') or {}).get('motion') or {}).get('template') == 'quote' for s in motion)
        return quotes + 1 > max(1, QUOTE_SHARE * (len(motion) + 1))

    def neighbour_motion(self, slot):
        """(template, layout) of the infographics just before and after this slot (any distance), or None."""
        from app.motion.layouts import layout_of
        ordered = sorted(self.slots, key=lambda s: s.get('estimated_start', 0))
        index = next((i for i, s in enumerate(ordered) if 'slot_id' in slot and s.get('slot_id') == slot['slot_id']), None)
        if index is None: return None, None

        def first(candidates):
            for other in candidates:
                media = other.get('selected_media')
                spec = is_generated(media) and (media.get('source_metadata') or {}).get('motion')
                if spec and not other.get('continuation_of'):
                    return spec['template'], layout_of(spec)
            return None
        return first(reversed(ordered[:index])), first(ordered[index + 1:])

    @timed('motion')
    def motion(self, slot, scene, log, spec=None, stage='motion'):
        from app.motion.clips import render_clip, media_record
        from app.motion.layouts import pick
        spec = spec or self.motion_spec(slot, scene)
        if stage in ('motion', 'motion_planned') and self.opening_overlay(slot, scene, log, spec):
            return True
        marker = json.dumps({k: v for k, v in spec.items() if k != 'layout'}, sort_keys=True)
        if stage == 'motion' and marker in self.card_texts and self.continue_card(slot, marker, log):
            return True
        self.card_texts.add(marker)
        # Two infographics in a row never share template and layout.
        keep = stage == 'motion_edit' and 'layout' in spec  # the owner chose it on the media screen
        spec = {**spec, 'layout': spec['layout'] if keep else pick(*self.neighbour_motion(slot), spec['template'])}
        slot['motion_layout_owner'] = keep
        need = used_seconds(slot)
        self.progress['message'] = f'Yuva {slot["order"]} · motion grafik çiziliyor'
        self.service._checkpoint(self.job, self.progress, light=True)
        folder = directory(self.service.projects, self.pid)
        language = self.service._handoff(self.pid).get('language', 'de')
        try:
            path, scene_data, engine = render_clip(folder, spec, self.kit(), need, self.emphasis_offset(slot, scene, spec), language=language,
                                                   bridge=getattr(self.service, 'openmontage', None), cancelled=lambda:self.service.closed)
        except Exception:
            if self.service.closed:raise StockError('interrupted','İşlem durdu; tamamlanan grafikler korundu.')
            LOG.warning('stock operation=motion category=render_failed')
            return self.card(slot, scene, log)  # extreme fallback (e.g. FFmpeg missing): still a picture
        media = media_record(path, spec, scene_data, engine)
        counter = 'motion_cache_hits' if engine == 'cache' else 'motion_renders'
        self.progress[counter] = self.progress.get(counter, 0) + 1
        engines = self.progress.setdefault('motion_engines', {})
        engines[engine] = engines.get(engine, 0) + 1
        from app.motion import relief as relief_module
        if relief_module.LAST_WARNING:  # satellite tiles failed: drawn map used, the reason in Turkish
            self.progress.setdefault('marker_warnings', []).append(relief_module.LAST_WARNING)
            slot_note = relief_module.LAST_WARNING; relief_module.LAST_WARNING = ''
        else:
            slot_note = ''
        from app.motion.templates import TEMPLATES
        why = {'motion_planned': 'yönetmen bu sahneyi motion grafik olarak planladı', 'motion_edit': 'sizin düzenlediğiniz motion grafik',
               'motion_owner': 'metindeki işaretinize göre'}.get(
            stage, 'onaylanan stok medya bulunamadı')
        slot.update(selected_media=media, status='complete', continuation_of=None, segment_start=None, missing_reasons=[], warnings=[slot_note] if slot_note else [],
                    ai_review=None, message=(f'⚠ {slot_note} ' if slot_note else '') + f'{TEMPLATES[spec["template"]]}: “{media["description"][:80]}” ({why}).')
        log['steps'].append({'stage': stage, 'label': STAGES[stage], 'result': 'chosen', 'template': spec['template'], 'engine': engine,
                             'because': 'no_approved_stock' if stage == 'motion' else stage})
        return True

    def moment_off(self, media):
        template = (((media or {}).get('source_metadata') or {}).get('motion') or {}).get('template')
        if template not in ('intro', 'outro'): return False
        switches = self.service.settings.moments() if hasattr(self.service.settings, 'moments') else {}
        return not switches.get('intro_card' if template == 'intro' else 'outro_card')

    def opening_card(self, slot, media):
        """A drawn card (not the owner's marker, intro/outro or own edit) filling
        more than OPENING_CARD seconds of the first scene."""
        meta = (media or {}).get('source_metadata') or {}
        spec = meta.get('motion') or {}
        return (bool(self.scene_order) and slot['scene_id'] == self.scene_order[0] and used_seconds(slot) > OPENING_CARD
                and not slot.get('locked') and not slot.get('motion_edited') and not meta.get('owner_hint') and slot['slot_id'] not in self.owner
                and spec.get('template') not in ('intro', 'outro') and (spec.get('template') in ('stat', 'quote', 'timeline', 'map') or meta.get('card_kind')))

    def opening_overlay(self, slot, scene, log, spec):
        """Opening scene: no full-screen card longer than OPENING_CARD seconds.
        The slot gets moving footage (stock, the neighbouring take or neutral
        footage of the setting) and the card's 2-5 words as a band over it for
        at most OPENING_CARD seconds. False: nothing moving found (normal card)."""
        if not self.scene_order or scene.get('scene_id') != self.scene_order[0] or used_seconds(slot) <= OPENING_CARD:
            return False
        from app.motion.templates import focus
        data = spec.get('data') or {}
        text = focus(' '.join(x for x in (str(data.get('value') or ''), str(data.get('label') or data.get('text') or data.get('place') or '')) if x))
        if not text: return False
        planned = list(dict.fromkeys(q for q in [slot.get('search_query'), *slot.get('fallback_queries', []), scene.get('primary_stock_query'),
                                                 *scene.get('alternative_stock_queries', [])] if q))[:4]
        slot.setdefault('relevance_profile', relevance.profile(scene, slot))
        tried = any(step.get('stage') == 'stock_video' for step in log['steps'])  # a planned graphic: stock was not searched yet
        chosen = bool(planned) and not tried and self.try_step(slot, scene, 'stock_video', ['video'], planned, log, set())
        chosen = chosen or self.merge(slot, log, limit=60.0)
        if not chosen: return False
        slot['lower_third'], slot['lower_third_seconds'] = text, OPENING_CARD
        slot['message'] = f'Açılış: hareketli görüntü üstünde “{text}” ({OPENING_CARD:g} sn; tam ekran kart yerine).'
        return True

    def card(self, slot, scene, log, framed=False):
        kind, text = card_spec(slot, scene, self.card_texts)
        if text in self.card_texts and self.continue_card(slot, text, log):
            return True
        self.card_texts.add(text)
        folder = directory(self.service.projects, self.pid)
        name = uuid4().hex + '.png'
        drawn = render_card(folder / name, kind, text, framed=framed)
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
        scene = bind_shot(scene, slot, self.language)
        slot.pop('lower_third', None)  # belongs to the media chosen below
        slot.pop('lower_third_seconds', None)
        slot['relevance_profile'] = relevance.profile(scene, slot)
        # Slots of one scene share the AI's verdicts and rewritten queries.
        memo = self.memo.setdefault(memo_key(scene), {'judged': {}})
        log = {'started_at': now(), 'steps': [], 'searches': [], 'judged': memo['judged'], 'rejected': {}}
        planned = list(dict.fromkeys(q for q in [scene.get('primary_stock_query'), slot.get('search_query'), *slot.get('fallback_queries', []),
                                                 *scene.get('alternative_stock_queries', [])] if q))[:4]
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
        if not chosen:
            chosen = self.extended_search(slot, scene, planned + rewritten, log, exclude)
        if not chosen and keep_if_only_card:
            log['steps'].append({'stage': 'kept', 'label': STAGES['kept'], 'result': 'kept_no_better_option'})
            return log
        if not chosen and used_seconds(slot) < MERGE_SECONDS and self.merge(slot, log):
            chosen = True
        if not chosen:
            spec = self.motion_spec(slot, scene)
            if spec['template'] == 'quote':
                # A band over the neighbouring shot beats a full-screen text card.
                if self.merge(slot, log, limit=6.0):
                    from app.rendering.smart_edit import highlight
                    slot['lower_third'] = highlight(' '.join(spec['data']['text'].split()))
                    slot['message'] = 'Komşu çekim devam ediyor; yazı video üstünde alt bant olarak gösterilir.'
                    return log
                # A relevant graphic is preferable to generic scenery or another sentence's facts.
            self.motion(slot, scene, log, spec)
        return log

    # ---- motion share: looser period/place rules before (or instead of) a graphic ----
    def motion_count(self):
        return sum(1 for s in self.slots if s.get('status') == 'complete' and is_generated(s.get('selected_media')))

    def setting_blocked(self, log, memo):
        """Did the period/place rules (not the lack of footage) empty this slot?"""
        return bool(log.get('rejected', {}).get('setting_conflict') or log.get('rejected', {}).get('modern_in_history')
                    or any(v.get('setting_conflict') for v in memo['judged'].values()))

    def relaxed(self, slot, scene, memo, log, exclude, queries):
        """Searches again with looser rules: level 1 drops the period/look rules (anachronism, cartoon/3D, “modern in a
        history scene”), level 2 the wrong-place rules too. Candidates dropped before come back through the same
        search; each still has to reach 7/10 (CLIP / AI / words). Verdicts made here never leak into the strict ones."""
        if not queries: return None
        for level in (1, 2):
            self.relax = level
            local = {**log, 'judged': {k: v for k, v in memo['judged'].items() if not v.get('setting_conflict')}, 'rejected': {}}
            try: chosen = self.try_step(slot, scene, 'relaxed', ['video', 'image'], queries, local, exclude)
            finally: self.relax = 0
            if chosen:
                note = 'dönem/görünüm kuralları gevşetildi' if level == 1 else 'dönem ve coğrafya kuralları gevşetildi'
                slot['setting_relaxed'] = level
                slot['message'] = f'⚠ Motion oranı yüksek olduğu için {note}. ' + slot.get('message', '')
                self.progress['relaxed_slots'] = self.progress.get('relaxed_slots', 0) + 1
                return chosen
        return None

    def relax_pass(self):
        """After the main pass: still above the motion target → the graphics that only filled an empty slot get
        another try with looser rules, best-fitting first (the order of the slots), until the target is met."""
        total = len(self.slots)
        if total < 4: return
        def candidate(slot):
            media, meta = slot.get('selected_media'), (slot.get('selected_media') or {}).get('source_metadata') or {}
            return (slot.get('status') == 'complete' and is_generated(media) and not slot.get('locked') and not slot.get('manual_stock')
                    and not slot.get('motion_edited') and not meta.get('owner_hint') and not meta.get('planned') and not slot.get('continuation_of')
                    and (meta.get('motion') or {}).get('template') not in ('intro', 'outro', 'endscreen'))
        for slot in sorted((s for s in self.slots if candidate(s)), key=lambda s: s['estimated_start']):
            if self.motion_count() <= MOTION_TARGET * total or self.service.closed: break
            scene = self.scene_by_id[slot['scene_id']]
            memo = self.memo.setdefault(slot['scene_id'], {'judged': {}})
            slot['relevance_profile'] = relevance.profile(scene, slot)
            planned = list(dict.fromkeys(q for q in [slot.get('search_query'), *slot.get('fallback_queries', []), scene.get('primary_stock_query'),
                                                     *scene.get('alternative_stock_queries', []), *memo.get('rewritten', []), *memo.get('broader', [])] if q))[:8]
            backup, old = deepcopy(slot), slot.get('selected_media')
            self._release(slot)
            log = {'started_at': now(), 'steps': [], 'searches': [], 'judged': {}, 'rejected': {}}
            self.progress.update(message=f'Yuva {slot["order"]} · motion oranı yüksek, gevşetilmiş kurallarla stok aranıyor')
            self.service._checkpoint(self.job, self.progress, light=True)
            if self.relaxed(slot, scene, memo, log, set(), planned):
                self.finish_slot(slot, log)
            else:
                slot.clear(); slot.update(backup)
                if old: self.register(slot['slot_id'], old, float(slot.get('segment_start') or 0), used_seconds(slot))

    def where(self, scene):
        """The period/place this scene is checked against (the video's, or the
        scene's own when it names other years, e.g. a flashback)."""
        if not getattr(self, 'setting', None): return {}  # (unit tests build the director without run())
        sid = (scene.get('scene_id'), scene.get('narration_text', ''))
        if not hasattr(self, 'scene_settings'): self.scene_settings = {}
        if sid not in self.scene_settings:
            from app.stock.setting import for_scene
            self.scene_settings[sid] = for_scene(self.setting, scene.get('narration_text', ''))
        setting = self.scene_settings[sid] or {}
        return {**setting, 'relax': self.relax} if self.relax and setting else setting

    def setting_rejected(self, media, conflict):
        counts = self.progress.setdefault('setting_rejected', {})
        kind = conflict.get('kind', 'other')
        if not hasattr(self, 'setting_seen'): self.setting_seen = set()
        if key_text(media) not in self.setting_seen:
            self.setting_seen.add(key_text(media))
            counts[kind] = counts.get(kind, 0) + 1

    def neutral(self, slot, scene, log, exclude):
        """No candidate fits the sentence: neutral footage of the setting
        (landscape, sky, texture). Judged like any shot (CLIP, the AI when it
        is on, else the tags) — but against the neutral picture itself, with
        the scene's period/place rules and MUST-NOT list still in force."""
        from app.stock.setting import neutral_queries
        where = self.where(scene)
        queries = neutral_queries(where)
        step = {'stage': 'neutral', 'label': STAGES['neutral'], 'queries': queries, 'judged': []}
        log['steps'].append(step)
        label = where.get('label') or 'videonun konusu'
        for query in queries:
            # Earlier verdicts were about the sentence, not this neutral picture: only a period/place conflict still counts.
            conflicts = {k for k, v in log['judged'].items() if v.get('setting_conflict')}
            pool = self.pool(slot, self.search(slot, ['video', 'image'], query, log, scene), {**log, 'judged': {}}, exclude | conflicts, scene)[:CANDIDATES]
            if not pool: continue
            goal = f'Neutral filler shot: {query} ({where.get("label_en") or "fitting the video"}). It does not need to show what is said.'
            shot = {**scene, 'narration_text': query, 'visual_intent': goal, 'must_show': query, 'primary_stock_query': query,
                    'alternative_stock_queries': [], 'owner_hints': [], 'entities': []}
            probe = {**slot, 'search_query': query, 'fallback_queries': [], 'visual_goal': goal}
            probe['relevance_profile'] = relevance.profile(shot, probe)
            verdicts = self.judge(probe, shot, pool)
            for media in self.order(slot, [m for m in pool if verdicts.get(key(m), {}).get('approved') and verdicts[key(m)]['score'] >= APPROVE_SCORE], verdicts):
                verdict = {**verdicts[key(media)], 'reason': f'Nötr görüntü (“{query}”): cümleye birebir uyan, döneme/yere uygun aday bulunamadı ({label}).'}
                step['judged'].append({'provider': media['provider'], 'media_type': media['media_type'], 'media_id': media['media_id'], 'query': query,
                                       **{k: v for k, v in verdict.items() if k != 'clip'}})
                if self.take(slot, media, verdict, 'neutral', log):
                    return True
        step['result'] = 'no_approved_candidate'
        return False

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
            is_generated(media) and json.dumps({k: v for k, v in ((media.get('source_metadata') or {}).get('motion') or {}).items() if k != 'layout'}, sort_keys=True) == text)
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
        self.scene_by_id = scenes
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
        self.language = project.get('language') or 'de'
        from app.stock.setting import infer
        mode = getattr(service.settings, 'era_mode', lambda: 'auto')()  # Ayarlar → Video dönemi
        self.setting = infer([sc.get('narration_text', '') for sc in ordered_scenes], self.topic, mode)
        self.scene_settings, self.setting_seen = {}, set()
        if self.setting.get('label'):
            self.progress['setting'] = {k: self.setting.get(k) for k in ('label', 'label_en', 'era', 'decade', 'regions', 'mode')}
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
            if not single and not slot['locked'] and planned and first[slot['scene_id']] == slot['slot_id'] and not slot.get('manual_stock') and not (
                    slot.get('lower_third_seconds') and self.valid(slot)) and (
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
                elif self.moment_off(media): targets.append((slot, 'reselect'))  # an intro/outro card that is now switched off
                elif self.opening_card(slot, media): targets.append((slot, 'opening'))  # an older long full-screen card in the first scene
            elif self.local and (slot.get('local_review') or {}).get('approved') and slot.get('selection_context') == self.selection_context(slot, scenes[slot['scene_id']]):
                pass  # a completed, unchanged sentence was already checked; resume skips it
            elif not (slot.get('ai_review') or {}).get('approved') or (slot['ai_review'].get('score') or 0) < APPROVE_SCORE:
                targets.append((slot, 'unreviewed'))  # below 7/10 is never kept
        if not single: targets += self.recheck_setting(scenes, {t['slot_id'] for t, _ in targets})
        # Infographics need no AI look: they are drawn first, so even if the AI
        # quota runs out later every marked/planned scene already has its graphic.
        targets.sort(key=lambda t: t[1] not in ('motion_owner', 'motion_planned'))
        total = max(1, len(targets))
        prejudged = set()
        for done, (slot, why) in enumerate(targets):
            if service.closed: raise StockError('interrupted', 'İşlem durdu; tamamlanan yuvalar korundu. Medyayı Tamamla ile sürdürün.')
            scene = scenes[slot['scene_id']]
            if not single and slot['scene_id'] not in prejudged and why in ('missing', 'retry_card'):
                prejudged.add(slot['scene_id'])  # all of this scene's slots: ONE AI look at their pooled candidates
                self.prejudge(scene, [t for t, w in targets if t['scene_id'] == slot['scene_id'] and w in ('missing', 'retry_card')])
            self.progress.update(percent=max(1, int(done / total * 85)), slot_id=slot['slot_id'],
                                 message=f'Yuva {slot["order"]} ({done + 1}/{total}) hazırlanıyor')
            service._checkpoint(self.job, self.progress)
            try:
                log = self.handle(slot, scene, why)
            except StockError as error:
                if error.category in ('stale_plan', 'interrupted', 'locked', 'ai_paused') or (single and error.category == 'invalid_input'): raise
                log = {'steps': [], 'searches': [], 'judged': {}, 'error': error.category}
                self.motion(slot, scene, log)
            except Exception as error:  # one slot's unexpected problem never stops the whole job
                LOG.warning('stock operation=slot category=unexpected exception_class=%s slot=%s', type(error).__name__, slot.get('order'))
                log = {'steps': [], 'searches': [], 'judged': {}, 'error': 'unexpected'}
                self.progress.setdefault('slot_errors', []).append(f'Yuva {slot.get("order")}: beklenmeyen hata ({type(error).__name__}); yazı kartı kullanıldı.')
                self.card(slot, scene, log)
            self.finish_slot(slot, log)
        # Period/place constraints never weaken just to reduce the motion share.
        if targets and not single and not self.local:  # nothing new chosen: nothing to re-review
            try:
                self.review(scenes)
            except StockError as error:
                if error.category != 'ai_paused': raise
                self.progress['review_skipped'] = str(error)  # every slot is already filled; only the extra look is skipped
        self.finalize()

    def selection_context(self, slot, scene):
        from app.stock.verdict_cache import context
        return context(bind_shot(scene, slot, self.language), slot)

    def handle(self, slot, scene, why):
        scene = bind_shot(scene, slot, self.language)
        empty = lambda: {'steps': [], 'searches': [], 'judged': {}}
        if why == 'motion_owner':
            hint = self.owner[slot['slot_id']]
            spec = self.owner_spec(hint, scene)
            self._release(slot); log = empty()
            archive = spec is not None and spec['template'] == 'archive'
            if spec is not None and spec['template'] in ('mark', 'beforeafter', 'archive') and not self.pictures(spec, slot, scene):
                self.marker_error = self.marker_error or 'bu sahne için uygun görsel bulunamadı'
                spec = None
            if spec is None and archive:  # no fitting archive photo: a framed text card (never a modern colour photo or CG)
                why = self.marker_error
                self.card(slot, scene, log, framed=True)
                slot['message'] = f'⚠ [ARŞİV: {hint["value"]}] {why.rstrip(".")}; yerine yazı kartı kondu. ' + slot.get('message', '')
                self.progress.setdefault('marker_warnings', []).append(f'[{hint["value"][:60]}]: {why}; yazı kartı kondu')
                return log
            if spec is None and hint['type'] in MAP_MARKERS:  # a place nobody could locate: still a map (nearest known place), never stock footage
                spec, note = self.nearest_map(hint, scene)
                self.marker_note = note
            if spec is None:  # e.g. an unreadable [SAYI] marker: the narration decides
                log = self.fill(slot, scene)
                why = getattr(self, 'marker_error', '') or ('yer haritada bulunamadı' if hint['type'] == 'map' else 'işaret biçimi okunamadı')
                slot['message'] = f'⚠ [{hint["type"]}: {hint["value"]}] işareti çizilemedi ({why.rstrip(".")}). ' + slot.get('message', '')
                self.progress.setdefault('marker_warnings', []).append(f'[{hint["value"][:60]}]: {why}')
                return log
            self.motion(slot, scene, log, spec, 'motion_owner')
            slot['selected_media'].setdefault('source_metadata', {})['owner_hint'] = hint
            if getattr(self, 'marker_note', ''):
                slot['message'] = f'⚠ {self.marker_note} ' + slot.get('message', '')
                self.progress.setdefault('marker_warnings', []).append(self.marker_note); self.marker_note = ''
            return log
        if why == 'motion_planned':
            planned, spec = scene['motion_spec'], scene['motion_spec']
            self._release(slot); log = empty()
            if planned['template'] == 'quote':  # a text card is the last choice
                other = self.motion_spec(slot, scene)
                if other['template'] != 'quote': spec = other
                elif self.quote_full(): return self.fill(slot, scene)  # enough text cards: stock footage instead
            self.motion(slot, scene, log, spec, 'motion_planned')
            if is_generated(slot.get('selected_media')):
                slot['selected_media'].setdefault('source_metadata', {})['planned'] = planned
                if scene.get('motion_suggested'): slot['selected_media']['source_metadata']['suggested'] = True  # the owner approves or changes it
            return log
        if why == 'to_motion':
            self._release(slot); slot.pop('manual_stock', None); log = empty()
            self.motion(slot, scene, log, scene.get('motion_spec') or None, 'motion_planned' if scene.get('motion_spec') else 'motion'); return log
        if why == 'motion_edit':
            spec = self.progress['motion']
            if spec['template'] in ('mark', 'beforeafter', 'archive') and not self.pictures(spec, slot, scene):
                raise StockError('invalid_input', 'Bu işaret için uygun görsel bulunamadı; metni değiştirip yeniden deneyin. Mevcut medya korundu.')
            self._release(slot); log = empty(); self.motion(slot, scene, log, spec, 'motion_edit'); slot['motion_edited'] = True; return log
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
            verdict = self.judge(slot, scene, [media],review_selected=True).get(key(media))
            if verdict and verdict.get('clip_approved'):  # the local picture model confirms it
                slot.update(local_review={'approved': True, 'score': verdict['score'], 'clip': verdict['clip'], 'method': 'clip', 'reviewed_at': now()},
                            needs_ai_review=False, message=verdict['reason'])
                slot['selection_context'] = self.selection_context(slot, scene)
                log['steps'][0]['result'] = 'kept'
                return log
            if verdict and verdict.get('local') and not (verdict.get('clip') and not verdict['approved']):
                # No AI right now: a pick that still matches the scene's words stays (marked for a later AI look).
                if verdict['approved']:
                    if not slot.get('local_review'):
                        slot.update(local_review={'approved': True, 'score': verdict['score'], 'label': verdict.get('relevance_label'), 'reviewed_at': now()},
                                    message=verdict['reason'])
                    slot['needs_ai_review'] = True
                    slot['selection_context'] = self.selection_context(slot, scene)
                    log['steps'][0]['result'] = 'kept_no_better_option'
                    return log
            elif verdict and verdict['approved'] and verdict['score'] >= APPROVE_SCORE:
                slot.update(ai_review={'approved': True, **verdict, 'reviewed_at': now()}, local_review=None, needs_ai_review=False, message=verdict['reason'])
                log['steps'][0]['result'] = 'kept'
                return log
            self._release(slot)
            log2 = self.fill(slot, scene, exclude={key(media)})
            log2['previous_rejected'] = verdict
            return log2
        if why == 'opening':
            backup, old = deepcopy(slot), slot.get('selected_media')
            log = {'steps': [], 'searches': [], 'judged': {}, 'rejected': {}}
            self._release(slot)
            slot['relevance_profile'] = relevance.profile(scene, slot)
            if not self.opening_overlay(slot, scene, log, (old.get('source_metadata') or {}).get('motion') or {}):
                slot.clear(); slot.update(backup)  # nothing moving found: the card stays
                self.register(slot['slot_id'], old, 0., used_seconds(slot))
            return log
        if why in ('reselect', 'setting'):
            old = slot.get('selected_media')
            exclude = {key(old)} if old and not is_generated(old) else set()
            self._release(slot)
            return self.fill(slot, scene, exclude=exclude)
        if why == 'retry_card':
            self._release(slot)
        return self.fill(slot, scene)

    def recheck_setting(self, scenes, already):
        """Stock picks kept from earlier runs are checked once against the
        video's period/place (tags, and CLIP when installed); a clear conflict
        (modern shop in an ancient topic, Easter Island in a Babylon video,
        cartoon/3D in a history documentary) is chosen again."""
        from app.stock.setting import penalties, rules_version, tag_conflict
        out, groups, rules = [], {}, rules_version()
        clip = bool(self.clip and self.clip.ready())
        for slot in self.slots:
            media = slot.get('selected_media')
            if (slot['slot_id'] in already or slot.get('locked') or slot.get('manual_stock') or slot.get('continuation_of')
                    or not media or is_generated(media) or not self.valid(slot)):
                continue
            where = self.where(self.scene_by_id.get(slot['scene_id'], {}))
            done = slot.get('setting_check') or {}
            if not where.get('label') or (isinstance(done, dict) and done.get('label') == where['label'] and done.get('rules') == rules
                                          and (done.get('clip') or not clip)): continue
            tags = ' ' + relevance.normalized(f'{media.get("description", "")} {media.get("query_used", "")}') + ' '
            conflict = tag_conflict(where, tags, media.get('provider', ''))
            if conflict:
                self.setting_rejected(media, {'kind': conflict[0], 'label': conflict[1]})
                out.append((slot, 'setting')); continue
            groups.setdefault(slot['scene_id'], (where, []))[1].append(slot)
        if clip:
            for scene_id, (where, slots) in groups.items():
                label = where['label']
                # The scene's own description (the whole narration), as when the pick was made.
                descriptor = clip_descriptor({'duration': 99}, self.scene_by_id.get(scene_id, {}), self.language, where)
                items, by_key = [], {}
                for slot in slots:
                    frames = []
                    for block in self.frames(slot['selected_media']):
                        try: frames.append(base64.b64decode(block['source']['data']))
                        except (KeyError, ValueError, TypeError): pass
                    if frames:
                        name = key_text(slot['selected_media'])
                        if name not in by_key: items.append((name, frames))
                        by_key.setdefault(name, []).append(slot)
                if not items: continue
                self.progress['message'] = f'Önceki seçimler videonun dönemi/yeriyle karşılaştırılıyor ({label}, sahne {self.scene_by_id.get(scene_id, {}).get("order", "")}, {len(items)} yuva)'
                self.service._checkpoint(self.job, self.progress, light=True)
                scores = self.clip.score(descriptor, items, directory(self.service.projects, self.pid), penalties(where, descriptor))
                for name, result in scores.items():
                    for slot in by_key.get(name, []):
                        if isinstance(result.get('conflict'), dict):
                            self.setting_rejected(slot['selected_media'], result['conflict'])
                            out.append((slot, 'setting'))
                        else:
                            slot['setting_check'] = {'label': label, 'clip': True, 'rules': rules}
        else:
            for where, slots in groups.values():
                for slot in slots: slot['setting_check'] = {'label': where['label'], 'clip': False, 'rules': rules}
        if out: self.progress['setting_reselected'] = len(out)
        return out

    def _release(self, slot):
        media = slot.get('selected_media')
        if media and key(media) in self.usage:
            self.usage[key(media)] = [u for u in self.usage[key(media)] if u[0] != slot['slot_id']]
            if not self.usage[key(media)]: del self.usage[key(media)]
        slot.update(selected_media=None, status='pending', ai_review=None, segment_start=None, continuation_of=None)

    def review(self, scenes):
        """Whole-video look: repeated or too similar shots, tone breaks.
        Skipped when the server refused picture batches (one picture per request)."""
        if self.local or self.single: return
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

    def count_requests(self):
        """AI requests of this job and of the project so far (shown on the screen)."""
        try:
            path = directory(self.service.projects, self.pid) / 'ai_requests.json'
            data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
            data = {'total': int(data.get('total', 0)) + self.requests, 'cached': int(data.get('cached', 0)) + self.progress.get('ai_cached', 0),
                    'last_job': self.requests, 'updated_at': now()}
            path.write_text(json.dumps(data), encoding='utf-8')
            self.progress['ai_requests_total'] = data['total']
        except (OSError, ValueError, StockError):
            pass

    def owner_help(self, slots):
        """Per slot: the sentence spoken there, its Turkish translation and the
        [GÖRSEL] note in Turkish (one AI request per video, saved; none → empty)."""
        from app.stock.translate import turkish
        scenes = getattr(self, 'scene_by_id', {})
        spoken, notes = {}, {}
        for slot in slots:
            scene = scenes.get(slot['scene_id'])
            if not scene: continue
            span = max(.001, scene['end_estimate'] - scene['start_estimate'])
            middle = (slot['estimated_start'] + slot['estimated_end']) / 2
            spoken[slot['slot_id']] = shot_narration(scene, slot)
            notes[slot['slot_id']] = '; '.join(str(h.get('value', '')) for h in scene.get('owner_hints') or [] if h.get('type') == 'visual' and h.get('value'))
        self.progress['message'] = 'Cümlelerin Türkçesi hazırlanıyor (video başına tek istek; yapay zekâ yoksa boş kalır)'
        self.service._checkpoint(self.job, self.progress, light=True)
        report = {}
        try:
            tr = turkish(self.service, self.pid, self.language, [*spoken.values(), *notes.values()], report)
        except Exception:  # translation is only a help: never stops the job
            LOG.warning('stock operation=translate category=unexpected')
            tr, report = {}, {'reason': 'Çeviri beklenmeyen bir hata nedeniyle yapılamadı.'}
        self.translation_note = report.get('reason', '') if any(s and not tr.get(' '.join(s.split())) for s in spoken.values()) else ''
        clean = lambda text: ' '.join(str(text or '').split())
        return {sid: {'sentence': spoken[sid], 'sentence_tr': tr.get(clean(spoken[sid]), ''),
                      'visual_note': notes.get(sid, ''), 'visual_note_tr': tr.get(clean(notes.get(sid, '')), '')} for sid in spoken}

    def bands(self, slots):
        """[ŞERİT: üst satır | alt satır] → {slot_id: {'top', 'bottom'}}: the slot (real footage first)
        playing while that sentence is spoken."""
        out = {}
        for scene in getattr(self, 'scene_by_id', {}).values():
            words = ' '.join(scene.get('narration_text', '').split())
            span = max(.001, scene['end_estimate'] - scene['start_estimate'])
            for hint in scene.get('owner_hints') or []:
                if hint.get('type') != 'band' or not hint.get('value'): continue
                top, _, bottom = str(hint['value']).partition('|')
                top, bottom = (top.strip(), bottom.strip()) if bottom.strip() else ('', top.strip())
                where = words.find(' '.join(str(hint.get('sentence', '')).split())) if hint.get('sentence') else -1
                at = scene['start_estimate'] + span * (len(words[:where].split()) / max(1, len(words.split())) if where >= 0 else 0)
                own = sorted((s for s in slots if s['scene_id'] == scene['scene_id'] and s.get('selected_media')), key=lambda s: abs((s['estimated_start'] + s['estimated_end']) / 2 - at))
                real = [s for s in own if not is_generated(s['selected_media'])] or own
                if real: out[real[0]['slot_id']] = {'top': top, 'bottom': bottom}
        return out

    def finalize(self):
        service, job = self.service, self.job
        help_text = self.owner_help(self.slots) if getattr(self, 'slots', None) else {}
        with service.projects.lock, closing(service.projects._connection()) as c, c:
            state = service._load(c, self.pid, job['plan_id'])
            bands = self.bands(state['slots'])
            for slot in state['slots']:
                if slot['slot_id'] in help_text: slot.update(help_text[slot['slot_id']])
                if slot['slot_id'] in bands: slot['band'] = bands[slot['slot_id']]
                elif 'band' in slot and not bands.get(slot['slot_id']): slot.pop('band')
                slot['review_flags'] = review_flags(slot)
            # Every raw slot is now filled: the old render-only reflow plan
            # (built for gaps) is obsolete and must not hide new selections.
            state.pop('recovery_plan', None)
            # Kept picks checked against the period/place this run: remembered, so the next run skips them.
            checked = {s['slot_id']: s for s in self.slots if s.get('setting_check') and s.get('selected_media')}
            for slot in state['slots']:
                mine = checked.get(slot['slot_id'])
                if mine and slot.get('selected_media') and key(slot['selected_media']) == key(mine['selected_media']):
                    slot['setting_check'] = mine['setting_check']
            state['media_summary'] = summary(state['slots'])
            state['translation_note'] = getattr(self, 'translation_note', '')
            service._save(c, state)
            service._mirror(state)
        result = state['media_summary']
        self.count_requests()
        engine = self.ai or getattr(self, 'chain', None)
        if getattr(engine, 'attempts', None): self.progress['ai_attempts'] = engine.attempts[-150:]  # model + result of every try
        self.progress.update(percent=100, category='none', media_summary=result,
                             message=result['text'] + (' · Bütün video incelemesi atlandı: ' + self.progress['review_skipped'].split('.')[0] if self.progress.get('review_skipped') else '')
                             + (' · Görüntü yeri kalmadığı için gösterilemeyen işaretler: ' + ', '.join(self.progress['owner_unplaced']) if self.progress.get('owner_unplaced') else '')
                             + (' · ' + self.progress['local_reason'] if self.progress.get('local_reason') else ''))
        service._checkpoint(job, self.progress, status='completed')


def review_flags(slot):
    """Why the owner should look at this pick (Turkish), [] when nothing stands out:
    a low CLIP score, chosen by tags/words only, or close to a period/place problem."""
    media = slot.get('selected_media')
    if not media or is_generated(media) or slot.get('continuation_of') or slot.get('locked') or slot.get('status') != 'complete':
        return []
    review, ai = slot.get('local_review') or {}, slot.get('ai_review') or {}
    clip = review.get('clip') or {}
    flags = []
    if not ai.get('approved'):
        if isinstance(clip.get('score'), int) and clip['score'] < CLIP_APPROVE:
            flags.append(f'CLIP puanı düşük ({clip["score"]}/10)')
        elif not clip and review.get('method') != 'clip':
            flags.append('Yalnız etiket/kelime eşleşmesiyle seçildi (görüntü modeli bakmadı)')
    margin = clip.get('setting_margin')
    if isinstance(margin, (int, float)) and margin > SETTING_NEAR:
        flags.append(f'Dönem/yer kontrolünde sınıra yakın ({clip.get("setting_closest") or "uygunsuz öğe"} benzerliği)')
    return flags


SETTING_NEAR = -.01  # CLIP: the nearest period/place problem is within this of the shot's own description


TEMPLATE_WORDS = {'stat': 'sayı', 'map': 'harita', 'timeline': 'çizelge', 'compare': 'karşılaştırma', 'list': 'liste', 'quote': 'yazı',
                  'route': 'rota', 'empire': 'imparatorluk', 'zoom': 'yakınlaşma', 'mark': 'işaretleme', 'beforeafter': 'önce/sonra',
                  'icons': 'ikon', 'ratio': 'oran', 'dynasty': 'hanedan', 'fact': 'bilgi kartı'}


MODERN = {'car', 'traffic', 'highway', 'smartphone', 'phone', 'laptop', 'computer', 'office', 'skyscraper', 'skyline', 'business', 'businessman',
          'airplane', 'airport', 'neon', 'shopping', 'mall', 'selfie', 'drone', 'keyboard', 'screen', 'tablet', 'headphones', 'subway', 'tram',
          'motorcycle', 'truck', 'bus', 'taxi', 'concert', 'nightclub', 'gym', 'startup', 'meeting', 'apartment', 'supermarket'}
HISTORIC = re.compile(r'(?i)\b(ancient|antique|roman|greek|egypt\w*|pharaoh|medieval|middle ages|histor\w*|archaeolog\w*|excavat\w*|museum|artifact|artefact|'
                      r'relief|engraving|etching|lithograph|woodcut|manuscript|codex|fresco|mosaic|sculpture|statue|bust|ruins?|'
                      r'map|maps|atlas|chart|painting|portrait|empire|dynasty|century|vintage|archive|antik\w*|römisch\w*|'
                      r'mittelalter\w*|geschicht\w*|archäolog\w*|karte|gemälde|stich|kupferstich|ruine\w*|tarih\w*|arkeoloji\w*|'
                      r'müze\w*|harita\w*|kabartma\w*|gravür\w*|minyatür\w*)\b')


def historic(scene):
    """History, archaeology, museum, map, engraving… (or a year before 1900) in the scene notes."""
    text = ' '.join(str(scene.get(k) or '') for k in ('visual_intent', 'primary_stock_query', 'must_show', 'narration_text'))
    text += ' ' + ' '.join(scene.get('alternative_stock_queries') or [])
    text += ' ' + ' '.join(str(h.get('type')) for h in scene.get('owner_hints') or [])
    return bool(HISTORIC.search(text) or re.search(r'(?<!\d)1[0-8]\d\d(?!\d)', text))


LOCAL_GENERIC = {'closeup', 'close', 'shot', 'view', 'scene', 'background', 'footage', 'video', 'image', 'photo', 'cinematic', 'aerial', 'slow',
                 'motion', 'old', 'ancient', 'modern', 'beautiful', 'people', 'person', 'man', 'woman', 'light', 'dark', 'night', 'day', 'time',
                 'nature', 'documentary', 'stock', 'with', 'from', 'into', 'over', 'under', 'the', 'and'}


def local_words(text):
    """Meaningful lower-case words (no stop/generic words, simple plural folded)."""
    out = set()
    for word in re.findall(r'[a-zäöüßçğış]+', relevance.normalized(text)):
        if len(word) < 3 or word in relevance.STOP or word in LOCAL_GENERIC: continue
        out.add(word[:-1] if len(word) > 4 and word.endswith('s') else word)
    return out


def collage(blocks, width=512):
    """Up to three preview frames side by side as ONE JPEG image block, at
    most `width` px wide (fewer and smaller pictures per request: busy
    servers refuse big picture batches less often). A single frame is
    returned as it is (already ≤512 px)."""
    if len(blocks) <= 1: return blocks[0]
    try:
        from io import BytesIO
        from PIL import Image
        images = [Image.open(BytesIO(base64.b64decode(b['source']['data']))).convert('RGB') for b in blocks[:3]]
        height = 240
        images = [i.resize((max(1, round(i.width * height / i.height)), height)) for i in images]
        sheet = Image.new('RGB', (sum(i.width for i in images) + 8 * (len(images) - 1), height), (0, 0, 0))
        x = 0
        for image in images:
            sheet.paste(image, (x, 0)); x += image.width + 8
        if sheet.width > width:
            sheet = sheet.resize((width, max(1, round(sheet.height * width / sheet.width))))
        out = BytesIO(); sheet.save(out, 'JPEG', quality=80)
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64.b64encode(out.getvalue()).decode()}}
    except Exception:
        return blocks[0]


def local_message(label, category, retry, models=None):
    """Plain Turkish: why the AI look stopped, that the job went on, and when to re-check."""
    kept = (' Medya seçimi durmadı: kalan yuvalar yerel kelime/etiket eşleşmesiyle seçildi ve “yapay zekâ onayı yok” olarak işaretlendi.'
            f' {label} geri gelince “Yapay zekâyla yeniden kontrol et” düğmesine basın.')
    if category == 'free_quota_exhausted':
        minutes = minutes_to_pacific_midnight()
        when = f'yaklaşık {minutes // 60} saat {minutes % 60} dk sonra' if minutes >= 60 else f'yaklaşık {minutes} dk sonra'
        which = (f'{label} yedek zincirindeki tüm modellerin ({", ".join(m.removeprefix("gemini-") for m in models)}) günlük ücretsiz kotası doldu'
                 if models and len(models) > 1 else f'{label} günlük ücretsiz kotası doldu')
        return f'{which}; kota {when} (ABD Pasifik gece yarısı) yenilenir.' + kept
    if category in ('rate_limit', 'quota_limit'):
        minutes = max(1, -(-max(retry, 60) // 60))
        return f'{label} kota/hız sınırına takıldı ({minutes} dk sonra açılır).' + kept
    if category in TRANSIENT:
        which = f'{label} yedek zincirindeki modeller' if models and len(models) > 1 else label
        return f'{which} şu anda yanıt vermiyor ({ERROR_TEXT.get(category, "geçici hata")}); kısa beklemelerle yeniden denendi.' + kept
    if category in UNUSABLE:
        return f'{label} art arda okunamayan yanıt verdi.' + kept
    if category in ('key_rejected', 'missing_key', 'invalid_settings'):
        return f'{label} API anahtarı kabul edilmedi veya kayıtlı değil (Ayarlar → {label}).' + kept
    if category in ('model_unavailable', 'model_unsupported', 'invalid_request'):
        return f'Seçili {label} modeli isteği kabul etmedi (Ayarlar → {label} → Modelleri Getir).' + kept
    if category == 'billing_quota':
        return f'{label} hesabında bakiye/kota yok.' + kept
    return f'{label} yanıt vermedi ({category}).' + kept


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
    models = {}
    for s in filled:
        model = (s.get('ai_review') or {}).get('model')
        if model and not is_generated(s['selected_media']) and not s.get('continuation_of'): models[model] = models.get(model, 0) + 1
    if models:
        text += ' · seçen model' + ('ler' if len(models) > 1 else '') + ': ' + ', '.join(f'{m.removeprefix("gemini-")} ({n})' for m, n in sorted(models.items(), key=lambda kv: -kv[1]))
    clip = [s for s in filled if (s.get('local_review') or {}).get('method') == 'clip' and not (s.get('ai_review') or {}).get('approved')]
    if clip: text += f' · {len(clip)} yuva yerel görüntü modeliyle (CLIP) onaylandı'
    unchecked = [s['slot_id'] for s in filled if not is_generated(s['selected_media']) and not s.get('continuation_of')
                 and not (s.get('ai_review') or {}).get('approved') and (s.get('local_review') or {}).get('method') != 'clip']
    if unchecked: text += f' · {len(unchecked)} yuva yalnız etiket/kelimeyle seçildi'
    return {'unchecked': len(unchecked), 'unchecked_slots': unchecked,'total': len(slots), 'filled': len(filled), 'videos': videos, 'images': images, 'cards': cards, 'motion': motion, 'merged': merged,
            'motion_templates': templates, 'models': models, 'motion_slot_percent': round(100 * (motion + cards) / len(slots)) if slots else 0,
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
            with httpx.Client(timeout=30, follow_redirects=False, headers={'User-Agent': USER_AGENT}) as client, client.stream('GET', url) as response:
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


def shrink(data, width=512):
    """Every picture sent to the AI is a JPEG at most 512 px wide (small
    requests: cheaper, and busy servers refuse them less). Unchanged on error."""
    try:
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(data))
        if image.width <= width and data.startswith(b'\xff\xd8'): return data
        if image.width > width:
            image = image.resize((width, max(1, round(image.height * width / image.width))))
        out = BytesIO(); image.convert('RGB').save(out, 'JPEG', quality=82)
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
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=False, headers={'User-Agent': USER_AGENT}) as client:
            with client.stream('GET',url) as response:
                if response.status_code!=200:return None
                data=bytearray()
                for chunk in response.iter_bytes(65536):
                    data.extend(chunk)
                    if len(data)>3_000_000:return None
                return bytes(data)
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
                'progress': {k: v for k, v in json.loads(r['progress_json']).items() if k in ('message', 'percent', 'category', 'timings', 'ai_error', 'ai_failure', 'review_skipped', 'unavailable_providers', 'review', 'media_summary',
                                                                                    'ai_attempts', 'ai_requests', 'ai_cached', 'ai_requests_total', 'local_mode', 'local_reason')}}
                for r in c.execute('SELECT * FROM stock_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 10', (project_id,))]
    from app.providers.gemini_chain import ATTEMPTS
    tried = {}
    for attempt in ATTEMPTS:
        row = tried.setdefault(attempt['model'], {'ok': 0, 'errors': {}})
        if attempt['result'] == 'ok': row['ok'] += 1
        else: row['errors'][attempt['result']] = row['errors'].get(attempt['result'], 0) + 1
    return {'generated_at': now(), 'project_id': project_id, 'plan_id': state['plan_id'], 'summary': state.get('media_summary'),
            'gemini_models_tried': tried, 'gemini_attempts': list(ATTEMPTS)[-200:], 'gemini_skipped_until': getattr(service.settings, 'gemini_exhausted', dict)(),
            'providers_configured': state['providers'], 'warnings': state['warnings'], 'jobs': jobs, 'slots': slots}
