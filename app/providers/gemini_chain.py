"""Gemini model backup chain.

When a model cannot answer, the next model of the owner's chain answers
instead, inside the same call, so scene planning, Medyayı Tamamla and every
other Gemini job simply continue:
- daily quota used up → that model is skipped until US Pacific midnight;
- one failure with “server busy” (5xx/503), a time-out or an unexplained
  429 → that model is skipped for 15 minutes (one attempt per model);
- an explicit per-minute limit is not a reason to switch: the caller waits
  briefly and asks the same model again.
At most MAX_MODELS models are tried per call; then the error reaches the job
(which continues locally) instead of waiting minutes for every model.
Every attempt (model, result, time) is kept for the diagnostics file.

Default chain (from the model list the API returned): stable Flash models,
then Flash-Lite, then — last — preview and Pro models (each group newest
first; the selected model leads its group). Never in the chain: experimental
builds, TTS, image, embedding, live/audio models, anything older than 2.5.
"""
from collections import deque
from datetime import datetime, timedelta, timezone
import re
import threading

from app.providers.base import ScriptProviderError

MIN_VERSION = 2.5
EXCLUDED = ('exp', 'tts', 'image', 'embedding', 'embed', 'live', 'audio', 'native', 'thinking', 'aqa', 'learnlm',
            'gemma', 'imagen', 'veo', 'vision', 'computer-use', 'robotics')
# Daily quota used up: switch to the next model and skip this one until the reset.
SWITCH = {'free_quota_exhausted'}
# The model itself cannot be used (removed/renamed): next model, no day-long mark.
SKIP = {'model_unavailable', 'model_unsupported'}
# Busy server, time-out or a 429 Google does not explain: one attempt → 15 minutes off.
SHAKY = {'upstream_error', 'gemini_timeout', 'generation_timeout', 'timeout', 'quota_limit', 'network_error'}
SHAKY_LIMIT, SHAKY_MINUTES, SHAKY_WAIT = 1, 15, 3
MAX_MODELS = 3  # models actually asked per call (one attempt each); skipped models do not count


def PAUSE(seconds):  # replaced in tests
    import time
    time.sleep(seconds)
ATTEMPTS = deque(maxlen=400)   # every model attempt of this app run (diagnostics)
_strikes, _lock = {}, threading.Lock()


def now_utc():
    return datetime.now(timezone.utc)


def pacific_midnight(moment=None):
    """Next US Pacific midnight (when Gemini daily quotas reset), as UTC."""
    moment = moment or now_utc()
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo('America/Los_Angeles')
    except Exception:  # no time-zone data (some Windows installs): standard offset
        zone = timezone(timedelta(hours=-8))
    here = moment.astimezone(zone)
    return (here + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def version(model):
    match = re.match(r'gemini-(\d+(?:\.\d+)?)', model or '')
    return float(match.group(1)) if match else None


def kind(model):
    """'flash', 'flash-lite', 'extra' (preview or Pro: last resort) or None."""
    name = (model or '').casefold()
    if not name.startswith('gemini-') or any(word in name for word in EXCLUDED):
        return None
    number = version(name)
    if number is None or number < MIN_VERSION:
        return None
    if 'preview' in name or 'pro' in name.split('-'):
        return 'extra'
    if 'flash-lite' in name or 'flash-8b' in name:
        return 'flash-lite'
    if 'flash' in name:
        return 'flash'
    return None


def eligible(model):
    return kind(model) is not None


def default_chain(selected, available):
    """Stable Flash → Flash-Lite → preview/Pro (newest first; the selected model leads its group).
    A selected model outside these groups (e.g. a custom name) still comes first."""
    newest = lambda m: (m != selected, -(version(m) or 0), len(m), m)
    pool = set(available) | ({selected} if selected else set())
    groups = [sorted((m for m in pool if kind(m) == k), key=newest) for k in ('flash', 'flash-lite', 'extra')]
    chain = [m for group in groups for m in group]
    return chain if selected in chain or not selected else [selected, *chain]


def chain_models(config):
    """The chain to use: the owner's saved order (models no longer available
    or below the floor dropped), or the automatic default. The selected
    model is always in it (first, unless the owner moved it)."""
    selected, available = config.get('model', ''), list(config.get('available_models') or [])
    saved = config.get('fallback_models')
    if not isinstance(saved, list):
        return default_chain(selected, available)
    order = [m for m in dict.fromkeys(saved) if isinstance(m, str) and (m == selected or (eligible(m) and m in available))]
    return order if selected in order or not selected else [selected, *order]


def short(model):
    """'gemini-2.5-flash' → '2.5-flash' for small notes on the screen."""
    return (model or '').removeprefix('gemini-')


class GeminiChain:
    """Looks like one Gemini provider; quietly moves down the chain."""
    name = 'Gemini'

    def __init__(self, api_key, models, settings, make):
        if not models:
            raise ScriptProviderError('Geçerli bir Gemini modeli seçip kaydedin.', 422, category='invalid_settings', stage='configuration')
        self._key, self.models, self.settings, self._make = api_key, list(models), settings, make
        self._providers = {}
        self.provider(self.models[0])  # key/model problems surface right away, as before
        self.last_model, self.switches, self.attempts = None, [], []
        self.on_try = None  # callback(model, number) — the screen shows which model is being asked

    @property
    def model(self):
        return self.last_model or next((m for m in self.models if m not in self.exhausted()), self.models[0])

    def provider(self, model):
        if model not in self._providers:
            self._providers[model] = self._make(self._key, model)
        return self._providers[model]

    def exhausted(self):
        marks = getattr(self.settings, 'gemini_exhausted', None)
        return marks() if marks else {}

    def _mark(self, model, until=None):
        mark = getattr(self.settings, 'mark_gemini_exhausted', None)
        if mark: mark(model, until or pacific_midnight().isoformat())

    def _note(self, model, result):
        entry = {'model': model, 'result': result, 'at': now_utc().isoformat()}
        self.attempts.append(entry); ATTEMPTS.append(entry)

    def _call(self, method, *args, **kwargs):
        skipped, last_error, asked = [], None, 0
        for model in self.models:
            if model in self.exhausted():
                skipped.append(model); continue
            if asked >= MAX_MODELS:
                break
            asked += 1
            if self.on_try: self.on_try(model, asked)
            for attempt in range(SHAKY_LIMIT):
                try:
                    result = getattr(self.provider(model), method)(*args, **kwargs)
                except ScriptProviderError as error:
                    self._note(model, error.category)
                    if error.category in SWITCH:
                        self._mark(model); skipped.append(model); last_error = error
                        self.switches.append({'from': model, 'reason': error.category, 'at': now_utc().isoformat()})
                        break
                    pictures = sum(1 for block in kwargs.get('images') or () if isinstance(block, dict) and block.get('type') == 'image')
                    if error.category == 'upstream_error' and pictures > 1:
                        # “Server busy” for a picture batch: maybe the batch, not the model. The caller
                        # checks with a small text request and sends pictures one by one; no mark here.
                        error.batch_rejected = True
                        raise
                    if error.category in SHAKY and len(self.models) > 1:
                        with _lock:
                            _strikes[model] = _strikes.get(model, 0) + 1
                            strikes = _strikes[model]
                        if strikes >= SHAKY_LIMIT:  # 15 minutes off, next model
                            with _lock: _strikes[model] = 0
                            self._mark(model, (now_utc() + timedelta(minutes=SHAKY_MINUTES)).isoformat())
                            skipped.append(model); last_error = error
                            self.switches.append({'from': model, 'reason': error.category, 'at': now_utc().isoformat()})
                            break
                        PAUSE(SHAKY_WAIT)  # a short breath, then the same model once more
                        continue
                    if error.category in SKIP and len(self.models) > 1:
                        skipped.append(model); last_error = error
                        break
                    raise  # per-minute limit, key problem, one-model chain…: the caller decides (waits / goes local)
                self._note(model, 'ok')
                with _lock: _strikes.pop(model, None)
                if self.last_model and self.last_model != model:
                    self.switches.append({'to': model, 'at': now_utc().isoformat()})
                self.last_model = model
                return result
        daily = getattr(last_error, 'category', 'free_quota_exhausted') == 'free_quota_exhausted' or last_error is None
        error = ScriptProviderError(
            f'Gemini yedek zincirindeki modellerin ({", ".join(short(m) for m in self.models)}) '
            + ('günlük ücretsiz kotası doldu.' if daily else 'şu anda yanıt vermiyor (sunucu meşgul / zaman aşımı); biraz sonra yeniden denenir.'),
            429 if daily else 503, category='free_quota_exhausted' if daily else 'upstream_error', retry_after=getattr(last_error, 'retry_after', 0) or 0,
            upstream_status=getattr(last_error, 'upstream_status', None))
        error.chain_exhausted = True
        error.chain_models = list(self.models)
        raise error

    def complete_json(self, *args, **kwargs):
        return self._call('complete_json', *args, **kwargs)

    def generate_script(self, *args, **kwargs):
        return self._call('generate_script', *args, **kwargs)

    def test_connection(self, *args, **kwargs):
        return self.provider(self.models[0]).test_connection(*args, **kwargs)

    def __getattr__(self, attribute):  # anything else (rarely used helpers) from the current model's provider
        if attribute.startswith('__') or attribute in ('_providers', '_make', '_key', 'models', 'settings'):
            raise AttributeError(attribute)
        return getattr(self.provider(self.model), attribute)
