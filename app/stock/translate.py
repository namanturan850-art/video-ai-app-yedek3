"""Turkish help for the media screen: the sentence spoken in each slot and the
owner's [GÖRSEL] note, translated with ONE AI request per video (saved in the
project folder, so a second run asks nothing). No AI, no answer, or a Turkish
video: the translation stays empty (or is the text itself) — the job never waits
on it longer than TRANSLATE_SECONDS."""
import hashlib
import json
import logging
import threading

from app.projects import linked
from app.stock.download import directory

LOG = logging.getLogger('uvicorn.error.stock')
TRANSLATE_SECONDS = 60
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['items'],
          'properties': {'items': {'type': 'array', 'items': {
              'type': 'object', 'additionalProperties': False, 'required': ['id', 'tr'],
              'properties': {'id': {'type': 'integer'}, 'tr': {'type': 'string'}}}}}}


def _key(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def _cache_path(service, pid):
    folder = directory(service.projects, pid)
    if linked(folder): return None
    folder.mkdir(parents=True, exist_ok=True)
    return folder / 'translations_tr.json'


def turkish(service, pid, language, texts):
    """{text: Turkish text} for the given texts; missing ones are left out."""
    texts = [t for t in dict.fromkeys(' '.join(str(x or '').split()) for x in texts) if t]
    if not texts: return {}
    if (language or '').casefold() == 'tr': return {t: t for t in texts}
    path = _cache_path(service, pid)
    try: saved = json.loads(path.read_text(encoding='utf-8')) if path and path.is_file() else {}
    except (OSError, ValueError): saved = {}
    if not isinstance(saved, dict): saved = {}
    missing = [t for t in texts if not isinstance(saved.get(_key(t)), str)]
    if missing:
        fresh = _ask(service, language, missing[:150])
        if fresh:
            saved.update({_key(t): v for t, v in fresh.items()})
            try:
                if path:
                    temporary = path.with_name('.translations-' + _key(str(path)))
                    temporary.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8'); temporary.replace(path)
            except OSError:
                pass
    return {t: saved[_key(t)] for t in texts if isinstance(saved.get(_key(t)), str)}


def _ask(service, language, texts):
    """One request for all texts; {} when no engine, an error or no answer in time."""
    settings = service.settings
    engine = settings.ai_engine() if hasattr(settings, 'ai_engine') else None
    if not engine: return {}
    try:
        factory = getattr(service, 'ai_factory', None)
        if factory is None:
            from app.providers.factory import make_script_provider
            factory = lambda: make_script_provider(engine, settings)
        ai = factory()
    except Exception:
        return {}
    lines = '\n'.join(f'{n}: {t[:400]}' for n, t in enumerate(texts))
    prompt = (f'Translate each numbered line (spoken language: {language}) into natural Turkish for the video owner. '
              'Keep names and numbers. Return one item per line with its number as id.\n\n' + lines)
    box = {}

    def work():
        try: box['answer'] = ai.complete_json('media_translate', prompt, SCHEMA, images=[], effort='low', max_tokens=min(8000, 200 + 120 * len(texts)))
        except Exception as error:  # any engine problem: the screen simply shows no translation
            box['error'] = type(error).__name__
    thread = threading.Thread(target=work, daemon=True)
    thread.start(); thread.join(TRANSLATE_SECONDS)
    if thread.is_alive() or not isinstance(box.get('answer'), dict):
        LOG.warning('stock operation=translate category=%s', 'timeout' if thread.is_alive() else box.get('error', 'no_answer'))
        return {}
    out = {}
    for item in box['answer'].get('items', []):
        if isinstance(item, dict) and isinstance(item.get('id'), int) and 0 <= item['id'] < len(texts) and isinstance(item.get('tr'), str):
            value = ' '.join(item['tr'].split())[:600]
            if value: out[texts[item['id']]] = value
    return out
