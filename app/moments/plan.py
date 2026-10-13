"""Giriş / kapanış anlarını sahne planına işler (işaretle veya otomatik tanıma).

İşaretler ([GİRİŞ], [KAPANIŞ]) seslendirmeye ve altyazıya gitmez (paste.clean
metinden çıkarır). İşaret yoksa videonun dilindeki karşılama / abone ol / veda
cümleleri phrases.py kalıplarıyla tanınır; tanınan cümle için stok arama
yapılmaz, ilgili şablon (intro / outro) kullanılır.

Kurallar: giriş yalnız videonun ilk cümlelerinde, kapanış yalnız son
cümlelerinde olur. Videonun ortasındaki bir abone ol çağrısı animasyon
almaz (normal stok akışı sürer).
"""
import math

from app.moments.phrases import classify
from app.scripts.paste import sentences

AUTO = '*'  # işaretin değeri yoksa: başlık ve kanal adı projeden alınır
INTRO_WINDOW = 3  # ilk kaç cümlede "hoş geldiniz" aranır
TYPES = ('intro', 'outro')


def closing_window(count):
    return max(6, math.ceil(count * .15))


def _flat(blocks):
    """[(block index, sentence text)] in spoken order."""
    out = []
    for index, block in enumerate(blocks):
        text = ' '.join(str(block.get('narration', '')).split())
        for a, b in sentences(text):
            out.append((index, text[a:b].strip()))
    return out


def _find(flat, sentence):
    sentence = ' '.join(str(sentence or '').split())
    return next((i for i, (_, text) in enumerate(flat) if sentence and (sentence in text or text in sentence)), None)


def apply_moments(blocks, language):
    """Adds owner_hints of type 'intro' / 'outro'; drops those in the wrong part of the video."""
    flat = _flat(blocks)
    count = len(flat)
    if not count:
        return blocks
    first_closing = count - closing_window(count)
    # 1) explicit markers: keep only the first intro at the start and the last outro at the end
    for block in blocks:
        for hint in list(block.get('owner_hints') or []):
            if hint.get('type') not in TYPES:
                continue
            at = _find(flat, hint.get('sentence'))
            wrong = at is None or (at >= INTRO_WINDOW * 2 if hint['type'] == 'intro' else at < first_closing)
            if wrong:
                block['owner_hints'].remove(hint)
    have = lambda kind: any(h.get('type') == kind for b in blocks for h in b.get('owner_hints') or [])
    # 2) automatic recognition in the video's language
    found_intro = next(((i, flat[i]) for i in range(min(INTRO_WINDOW, count)) if classify(flat[i][1], language) == 'intro'), None)
    if found_intro and not have('intro'):
        _add(blocks, found_intro[1], 'intro', AUTO)
    if not have('outro'):
        subscribe = farewell = None
        for i in range(max(first_closing, 0), count):
            kind = classify(flat[i][1], language)
            if kind == 'subscribe':
                subscribe = flat[i]
            elif kind == 'farewell':
                farewell = flat[i]
        if subscribe:
            _add(blocks, subscribe, 'outro', 'subscribe')
        if farewell and farewell != subscribe:
            _add(blocks, farewell, 'outro', 'farewell')
    return blocks


def _add(blocks, entry, kind, value):
    index, sentence = entry
    hints = blocks[index].setdefault('owner_hints', [])
    if not any(h.get('type') == kind and h.get('value') == value for h in hints):
        hints.append({'type': kind, 'value': value, 'sentence': sentence[:600]})


def closing_present(blocks):
    return any(h.get('type') == 'outro' for b in blocks for h in b.get('owner_hints') or [])
