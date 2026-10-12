"""Gemini model backup chain.

When one model's quota is used up (daily free quota), the next model of the
owner's chain answers instead, inside the same call, so scene planning,
Medyayı Tamamla and every other Gemini job simply continue. A used-up model
is skipped until its quota resets (US Pacific midnight) instead of being
tried on every request. A per-minute limit is not a reason to switch: the
error goes back to the caller, which waits briefly and asks the same model
again. Only when every model of the chain is used up does the error reach
the job (which then stops with a plain message).

Default chain (from the model list the API returned): the selected model,
then the other Flash models (newest first), then the Flash-Lite models
(newest first). Never in the chain: preview/experimental builds, TTS, image,
embedding, live/audio models, and anything older than Gemini 2.5.
"""
from datetime import datetime, timedelta, timezone
import re

from app.providers.base import ScriptProviderError

MIN_VERSION = 2.5
EXCLUDED = ('preview', 'exp', 'tts', 'image', 'embedding', 'embed', 'live', 'audio', 'native', 'thinking', 'aqa', 'learnlm',
            'gemma', 'imagen', 'veo', 'vision', 'computer-use', 'robotics')
# Daily quota used up: switch to the next model and skip this one until the reset.
SWITCH = {'free_quota_exhausted'}
# The model itself cannot be used (removed/renamed): next model, no day-long mark.
SKIP = {'model_unavailable', 'model_unsupported'}


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
    """'flash', 'flash-lite' or None (not a chain model)."""
    name = (model or '').casefold()
    if not name.startswith('gemini-') or any(word in name for word in EXCLUDED):
        return None
    number = version(name)
    if number is None or number < MIN_VERSION:
        return None
    if 'flash-lite' in name or 'flash-8b' in name:
        return 'flash-lite'
    if 'flash' in name:
        return 'flash'
    return None


def eligible(model):
    return kind(model) is not None


def default_chain(selected, available):
    """Selected model, other Flash (newest first), then Flash-Lite (newest first)."""
    newest = lambda m: (-(version(m) or 0), len(m), m)
    flash = sorted({m for m in available if kind(m) == 'flash' and m != selected}, key=newest)
    lite = sorted({m for m in available if kind(m) == 'flash-lite' and m != selected}, key=newest)
    return [m for m in [selected, *flash, *lite] if m]


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
        self.last_model, self.switches = None, []

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

    def _mark(self, model):
        mark = getattr(self.settings, 'mark_gemini_exhausted', None)
        if mark: mark(model, pacific_midnight().isoformat())

    def _call(self, method, *args, **kwargs):
        skipped, last_error = [], None
        for model in self.models:
            if model in self.exhausted():
                skipped.append(model); continue
            try:
                result = getattr(self.provider(model), method)(*args, **kwargs)
            except ScriptProviderError as error:
                if error.category in SWITCH:
                    self._mark(model); skipped.append(model); last_error = error
                    self.switches.append({'from': model, 'reason': error.category, 'at': now_utc().isoformat()})
                    continue
                if error.category in SKIP and len(self.models) > 1:
                    skipped.append(model); last_error = error
                    continue
                raise  # per-minute limit, time-out, key problem…: the caller decides (waits / stops)
            if self.last_model and self.last_model != model:
                self.switches.append({'to': model, 'at': now_utc().isoformat()})
            self.last_model = model
            return result
        error = ScriptProviderError(
            f'Gemini yedek zincirindeki tüm modellerin ({", ".join(short(m) for m in self.models)}) günlük ücretsiz kotası doldu.',
            429, category='free_quota_exhausted', retry_after=getattr(last_error, 'retry_after', 0) or 0,
            upstream_status=getattr(last_error, 'upstream_status', None))
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
