"""“Medyayı Tamamla”: the AI (Gemini free tier by default, Claude if chosen)
chooses stock media and every slot gets filled.

Chain per slot (each stock step needs the AI's approval after it has looked
at the candidates' preview frames; irrelevant media is never used to fill):
  1. stock video with the planned queries
  2. stock video with queries the AI rewrites for this slot
  3. stock image (rendered with light camera motion)
  4. media for the broader topic (still approved by the AI)
  6. very short slots (<1.5 s): continue the neighbouring shot
  5. code-generated card (title/quote, number, simple location map) — local,
     cannot fail, text always taken from the narration
Provider errors and timeouts only skip that provider; the chain continues.
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
          'motion_edit': 'Motion grafik (sizin düzenlemeniz)', 'motion_balance': 'Motion grafik (dengeli kurgu: %40 motion)'}
MOTION_SHARE = .40      # owner's target: ~40% motion graphics, ~60% stock footage
CANDIDATES = 5          # per AI look
APPROVE_SCORE = 6       # 0-10
MERGE_SECONDS = 1.5
WAIT_BUDGET = 900       # seconds of rate-limit waiting per job (free tier)
UNREACHABLE = 'Yapay zekâya ulaşılamadı'
REVIEW_MAX = 8
PROVIDER_DOWN = {'rate_limit', 'key_rejected', 'missing_key', 'timeout', 'connection_error', 'upstream_error', 'invalid_request', 'invalid_response'}
ERROR_TEXT = {'rate_limit': 'kullanım sınırı', 'key_rejected': 'anahtar kabul edilmedi', 'missing_key': 'anahtar yok',
              'timeout': 'zaman aşımı', 'connection_error': 'bağlantı kurulamadı', 'upstream_error': 'sunucu hatası',
              'invalid_response': 'okunamayan yanıt', 'invalid_request': 'istek reddedildi'}
JUDGE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['verdicts'],
                'properties': {'verdicts': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['candidate', 'score', 'approved', 'reason'],
                    'properties': {'candidate': {'type': 'integer'}, 'score': {'type': 'integer'},
                                   'approved': {'type': 'boolean'}, 'reason': {'type': 'string'}}}}}}
QUERY_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['queries'],
                'properties': {'queries': {'type': 'array', 'items': {'type': 'string'}}}}
REVIEW_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['replace'],
                 'properties': {'replace': {'type': 'array', 'items': {
                     'type': 'object', 'additionalProperties': False, 'required': ['slot', 'reason'],
                     'properties': {'slot': {'type': 'integer'}, 'reason': {'type': 'string'}}}}}}


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
        self.ai, self.ai_error, self.waited = None, '', 0
        self.unavailable = dict(self.progress.get('unavailable_providers', {}))

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
            self._ai_failed(error)

    def _ai_failed(self, error):
        self.ai = None
        self.ai_error = str(error)
        self.progress['ai_error'] = self.ai_error

    def _ask(self, purpose, prompt, schema, images=(), max_tokens=2000):
        if not self.ai: return None
        for attempt in range(5):
            try:
                return self.ai.complete_json(purpose, prompt, schema, images=list(images), effort='low', max_tokens=max_tokens)
            except ScriptProviderError as error:
                category = getattr(error, 'category', '')
                if category in ('invalid_response', 'incomplete_response', 'response_schema_mismatch', 'empty_response',
                                'thought_only_response', 'output_limit', 'unexpected_finish_reason', 'blocked_response'):
                    return None  # this one answer is unusable; the engine itself still works
                # Free-tier per-minute limit: wait and retry (bounded per job).
                if category in ('rate_limit', 'quota_limit', 'upstream_error', 'gemini_timeout') and attempt < 4 and self.waited < WAIT_BUDGET:
                    pause = min(60, max(5, int(getattr(error, 'retry_after', 0) or 20)))
                    self.progress['message'] = f'{self.label} hız sınırı: {pause} sn bekleniyor, sonra devam edilecek'
                    self.service._checkpoint(self.job, self.progress, light=True)
                    getattr(self.service, 'ai_sleep', _sleep)(pause, self.service)
                    self.waited += pause
                    continue
                self._ai_failed(error)
                return None
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
        return (f'Narration of this shot (spoken language {scene.get("stock_query_language", "")}): '
                f'"{sentence_at(scene.get("narration_text", ""), .5) if used_seconds(slot) < 6 else scene.get("narration_text", "")[:600]}"\n'
                f'Scene narration: "{scene.get("narration_text", "")[:900]}"\n'
                f'Visual goal: {slot.get("visual_goal") or scene.get("visual_intent", "")}\n'
                f'MUST show: {scene.get("must_show") or "(not specified)"}\n'
                f'MUST NOT show: {scene.get("must_not_show") or "(not specified)"}\n'
                f'Shot length: {used_seconds(slot):.1f} s. Mood: {scene.get("mood", "")}.')

    def judge(self, slot, scene, pool):
        """The AI looks at up to five candidates; returns verdicts by key."""
        blocks, listed = [], []
        for index, media in enumerate(pool, 1):
            frames = [b for b in (self.thumbnail(u, media['provider']) for u in self.frame_urls(media)) if b]
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
        prompt = (self.brief(slot, scene) + '\n\nYou are choosing documentary B-roll for this shot. For EVERY candidate above, '
                  'look at the frames and give score 0-10 for how well it shows what the narration says right now. '
                  'approved=true only if it clearly fits the MUST-show note (if any), shows nothing from the MUST-NOT list, '
                  'contains no visible logos/watermarks/readable on-screen text in another language, and would not mislead the viewer. '
                  'Contextual footage (e.g. ocean for a ship disappearance) is fine when no literal footage exists; unrelated or '
                  'generic-but-wrong footage is not. reason: ONE short sentence in Turkish for the channel owner. '
                  f'Candidates to rate: {listed}.')
        answer = self._ask('media_select', prompt, JUDGE_SCHEMA, blocks)
        verdicts = {}
        for item in (answer or {}).get('verdicts', []):
            index = item.get('candidate')
            if isinstance(index, int) and index in listed:
                verdicts[key(pool[index - 1])] = {'score': max(0, min(10, int(item.get('score', 0)))),
                                                  'approved': item.get('approved') is True,
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

    def pool(self, slot, results, log, exclude):
        need, seen, pool = used_seconds(slot), set(), []
        rejected = log.setdefault('rejected', {})
        for media in results:
            k = key(media)
            if k in seen or k in exclude: continue
            seen.add(k)
            reason = technical(media, need)
            if reason is None and self.segment(media, need) is None: reason = 'used_elsewhere'
            if reason is None and k in log['judged'] and not log['judged'][k]['approved']: reason = 'ai_rejected_before'
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            pool.append(relevance.annotate(media, slot['relevance_profile'], 1, media.get('query_used', '')))
        pool.sort(key=lambda m: (m['width'] > m['height'], key(m) not in self.usage, relevance.rank(m, slot)), reverse=True)
        return pool

    def try_step(self, slot, scene, stage, kinds, queries, log, exclude):
        step = {'stage': stage, 'label': STAGES[stage], 'queries': list(queries), 'judged': []}
        log['steps'].append(step)
        if not self.ai:
            step['result'] = 'ai_unavailable'
            return None
        waiting = []
        for index, query in enumerate(queries):
            waiting.extend(self.search(slot, kinds, query, log))
            pool = self.pool(slot, waiting, log, exclude)
            # The AI already approved these for this scene (another slot):
            # reuse the verdict instead of paying for the same look again.
            known = sorted((m for m in pool if log['judged'].get(key(m), {}).get('approved') and log['judged'][key(m)]['score'] >= APPROVE_SCORE),
                           key=lambda m: (log['judged'][key(m)]['score'], m['width'] > m['height'], key(m) not in self.usage), reverse=True)
            for media in known:
                chosen = self.take(slot, media, log['judged'][key(media)], stage, log)
                if chosen:
                    step['judged'].append({'provider': media['provider'], 'media_type': media['media_type'], 'media_id': media['media_id'],
                                           'query': media.get('query_used'), **log['judged'][key(media)], 'reused_verdict': True})
                    return chosen
            fresh = [m for m in pool if key(m) not in log['judged']]
            if len(fresh) < CANDIDATES and index < len(queries) - 1:
                continue
            pool = fresh[:CANDIDATES]
            if not pool:
                continue
            self.progress['message'] = f'Yuva {slot["order"]} · {self.label} {len(pool)} adaya bakıyor'
            self.service._checkpoint(self.job, self.progress, light=True)
            verdicts = self.judge(slot, scene, pool)
            for media in pool:
                verdict = verdicts.get(key(media))
                if verdict is None: continue
                log['judged'][key(media)] = verdict
                step['judged'].append({'provider': media['provider'], 'media_type': media['media_type'], 'media_id': media['media_id'],
                                       'query': media.get('query_used'), 'width': media['width'], 'height': media['height'],
                                       'duration': media.get('duration'), **verdict})
            approved = sorted((m for m in pool if verdicts.get(key(m), {}).get('approved') and verdicts[key(m)]['score'] >= APPROVE_SCORE),
                              key=lambda m: (verdicts[key(m)]['score'], m['width'] > m['height']), reverse=True)
            for media in approved:
                chosen = self.take(slot, media, verdicts[key(media)], stage, log)
                if chosen: return chosen
            waiting = [m for m in waiting if key(m) not in log['judged']]
            if not self.ai:
                break
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
        return saved

    def register(self, slot_id, media, start, need):
        self.usage.setdefault(key(media), []).append((slot_id, start + need))
        self.media_by_key[key(media)] = media

    # ---- other steps -------------------------------------------------------
    def merge(self, slot, log):
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
                        message='Çok kısa yuva: komşu çekim kesintisiz devam ediyor.')
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

    def motion_spec(self, slot, scene):
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
        return (fresh or options or [{'template': 'quote', 'data': {'text': narration.split('.')[0][:120] or scene.get('visual_intent', '')}, 'emphasis': ''}])[0]

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
               'motion_balance': 'videonun %40’ı motion grafik olsun diye seçildi'}.get(
            stage, UNREACHABLE if not self.ai else 'onaylanan stok medya bulunamadı')
        slot.update(selected_media=media, status='complete', continuation_of=None, segment_start=None, missing_reasons=[], warnings=[],
                    ai_review=None, message=f'{TEMPLATES[spec["template"]]}: “{media["description"][:80]}” ({why}).')
        log['steps'].append({'stage': stage, 'label': STAGES[stage], 'result': 'chosen', 'template': spec['template'], 'engine': engine,
                             'because': 'ai_unavailable' if not self.ai and stage == 'motion' else stage})
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
        why = UNREACHABLE if not self.ai else 'onaylanan stok medya bulunamadı'
        slot.update(selected_media=media, status='complete', continuation_of=None, segment_start=None, missing_reasons=[],
                    warnings=[] if drawn == 'drawn' else ['Yazı tipi bulunamadı; kart yazısız çizildi.'], ai_review=None,
                    message=f'{names[kind]}: “{text}” ({why}).')
        log['steps'].append({'stage': 'card', 'label': STAGES['card'], 'result': 'chosen', 'card_kind': kind, 'card_text': text,
                             'because': 'ai_unavailable' if not self.ai else 'no_approved_stock'})
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
        if not chosen and self.ai:
            if 'rewritten' not in memo: memo['rewritten'] = self.rewrite(slot, scene, planned)
            rewritten = memo['rewritten']
            log['rewritten_queries'] = rewritten
            if rewritten: chosen = self.try_step(slot, scene, 'rewritten_video', ['video'], rewritten, log, exclude)
        if not chosen:
            chosen = self.try_step(slot, scene, 'stock_image', ['image'], (rewritten + planned)[:5], log, exclude)
        if not chosen and self.ai:
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
            self.motion(slot, scene, log)
        return log

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
        self.connect()
        single = job.get('slot_id')
        action = {'reselect': 'reselect', 'to_motion': 'to_motion', 'to_stock': 'to_stock', 'motion_edit': 'motion_edit'}.get(job['action'], 'reselect')
        first = {}
        for slot in sorted(self.slots, key=lambda s: s['estimated_start']):
            first.setdefault(slot['scene_id'], slot['slot_id'])
        # Keep what is valid and already approved (or locked / generated).
        targets = []
        for slot in sorted(self.slots, key=lambda s: s['estimated_start']):
            media = slot.get('selected_media')
            if single and slot['slot_id'] == single:
                targets.append((slot, action))
                continue
            planned = scenes[slot['scene_id']].get('motion_spec')
            if not single and not slot['locked'] and planned and first[slot['scene_id']] == slot['slot_id'] and not slot.get('manual_stock') and (
                    not self.valid(slot) or not is_generated(media) and not (slot.get('ai_review') or {}).get('approved')
                    or is_generated(media) and (media.get('source_metadata') or {}).get('motion') != planned and not slot.get('motion_edited')):
                targets.append((slot, 'motion_planned'))
                continue
            if not self.valid(slot):
                if not slot['locked']: targets.append((slot, 'missing'))
                continue
            if slot.get('continuation_of'):
                continue
            self.register(slot['slot_id'], media, float(slot.get('segment_start') or 0), used_seconds(slot))
            if single or slot['locked']: continue
            if is_generated(media):
                if UNREACHABLE in slot.get('message', ''): targets.append((slot, 'retry_card'))
            elif not (slot.get('ai_review') or {}).get('approved'):
                targets.append((slot, 'unreviewed'))
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
                if error.category in ('stale_plan', 'interrupted', 'locked'): raise
                log = {'steps': [], 'searches': [], 'judged': {}, 'error': error.category}
                self.motion(slot, scene, log)
            self.finish_slot(slot, log)
        if not single:
            for slot in self.balance_motion([s for s, w in targets if w == 'missing'], scenes):
                self.progress.update(message=f'Yuva {slot["order"]} · dengeli kurgu için motion grafik')
                service._checkpoint(self.job, self.progress)
                self._release(slot); log = {'steps': [], 'searches': [], 'judged': {}}
                self.motion(slot, scenes[slot['scene_id']], log, None, 'motion_balance'); self.finish_slot(slot, log)
        if targets and not single and self.ai:  # nothing new chosen: nothing to re-review
            self.review(scenes)
        self.finalize()

    def balance_motion(self, filled, scenes):
        """Bring motion graphics to ~40% of the running time (owner's target).
        Runs after the stock search, so slots that had to become motion
        already count; only slots filled with stock in this run are converted,
        spread out (never three in a row), preferring a number, date or place."""
        span = lambda s: max(0., s['estimated_end'] - s['estimated_start'])
        ordered = sorted(self.slots, key=lambda s: s['estimated_start'])
        total = sum(span(s) for s in ordered)
        if not total: return []
        index = {s['slot_id']: i for i, s in enumerate(ordered)}
        def is_motion(s):
            m = s.get('selected_media')
            return is_generated(m) and (m.get('source_metadata') or {}).get('kind') == 'motion'
        motion = {index[s['slot_id']] for s in ordered if is_motion(s)}
        share = sum(span(ordered[i]) for i in motion) / total
        if share >= MOTION_SHARE - .02: return []
        planned = {ordered[i]['scene_id'] for i in motion}
        candidates = []
        for s in filled:
            if is_generated(s.get('selected_media')) or not self.valid(s) or s['locked'] or s.get('manual_stock') or s.get('continuation_of') \
                    or any(o.get('continuation_of') == s['slot_id'] for o in ordered) or span(s) > 12 or s['scene_id'] in planned: continue
            try: template = self.motion_spec(s, scenes[s['scene_id']])['template']
            except Exception: continue
            candidates.append((s, 2 if template != 'quote' else 1))
        chosen = []
        while share < MOTION_SHARE and candidates:
            def score(item):
                i = index[item[0]['slot_id']]
                return (min(min((abs(i - j) for j in motion), default=99), 4), item[1], -i)
            def crowded(i):
                return {i - 1, i - 2} <= motion or {i + 1, i + 2} <= motion or {i - 1, i + 1} <= motion
            allowed = [c for c in candidates if not crowded(index[c[0]['slot_id']])]
            if not allowed: break
            best = max(allowed, key=score)
            candidates.remove(best); motion.add(index[best[0]['slot_id']]); chosen.append(best[0]); share += span(best[0]) / total
        return sorted(chosen, key=lambda s: s['estimated_start'])

    def handle(self, slot, scene, why):
        empty = lambda: {'steps': [], 'searches': [], 'judged': {}}
        if why == 'motion_planned':
            self._release(slot); log = empty(); self.motion(slot, scene, log, scene['motion_spec'], 'motion_planned'); return log
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
            verdict = self.judge(slot, scene, [media]).get(key(media)) if self.ai else None
            if verdict and verdict['approved'] and verdict['score'] >= APPROVE_SCORE:
                slot.update(ai_review={'approved': True, **verdict, 'reviewed_at': now()}, message=verdict['reason'])
                log['steps'][0]['result'] = 'kept'
                return log
            if not self.ai:
                log['steps'][0]['result'] = 'kept_no_better_option'
                slot['message'] = UNREACHABLE + '; mevcut seçim henüz onaylanmadı.'
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
                             message=result['text'] + (f' · {UNREACHABLE} ({self.label}): ' + self.ai_error if self.ai_error else ''))
        service._checkpoint(job, self.progress, status='completed')


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
    text = f'{len(filled)}/{len(slots)} yuva dolu · {videos} video · {images} görsel · {motion} motion grafik' + (f' · {cards} kart' if cards else '')
    if merged: text += f' (bunların {merged} tanesi önceki çekimin devamı)'
    if missing: text += f' · {len(missing)} eksik ({seconds} sn)'
    return {'total': len(slots), 'filled': len(filled), 'videos': videos, 'images': images, 'cards': cards, 'motion': motion, 'merged': merged,
            'motion_seconds': motion_seconds, 'motion_percent': round(100 * motion_seconds / total_seconds, 1),
            'missing': len(missing), 'missing_seconds': seconds, 'text': text,
            'ai_approved': sum(bool((s.get('ai_review') or {}).get('approved')) for s in filled if not is_generated(s['selected_media']))}


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
                 'progress': {k: v for k, v in json.loads(r['progress_json']).items() if k in ('message', 'percent', 'category', 'ai_error', 'unavailable_providers', 'review', 'media_summary')}}
                for r in c.execute('SELECT * FROM stock_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 10', (project_id,))]
    return {'generated_at': now(), 'project_id': project_id, 'plan_id': state['plan_id'], 'summary': state.get('media_summary'),
            'providers_configured': state['providers'], 'warnings': state['warnings'], 'jobs': jobs, 'slots': slots}
