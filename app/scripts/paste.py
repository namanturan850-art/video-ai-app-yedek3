"""“Metni yapıştır”: the owner's own narration text.

clean() removes Markdown and heading/number leftovers and reads the optional
square-bracket markers. Markers never reach narration or subtitles:
    [GÖRSEL: airplane cockpit at night]  → media search priority for that sentence
    [HARİTA: Bermuda Triangle]           → map infographic of that place
    [SAYI: %40]                          → number infographic
    [ÇİZELGE: 1945, 1962, 1991]          → timeline infographic
    [KARŞILAŞTIR: Rom | Karthago]        → comparison infographic
    [LİSTE: Stürme; Strömungen; Fehler]  → list infographic
A marker written right after a sentence belongs to that sentence; a marker at
the start of a paragraph (or inside a sentence) belongs to the sentence that
follows (or contains) it.
Any other [...] is removed from the narration with a warning.
"""
import re

# Marker names are compared without Turkish letters, so [çizelge: …] and [CIZELGE: …] work too.
KINDS = {'GORSEL': 'visual', 'HARITA': 'map', 'SAYI': 'number', 'CIZELGE': 'timeline', 'KARSILASTIR': 'compare', 'LISTE': 'list'}
LABELS = {'visual': 'GÖRSEL', 'map': 'HARİTA', 'number': 'SAYI', 'timeline': 'ÇİZELGE', 'compare': 'KARŞILAŞTIR', 'list': 'LİSTE'}
ASCII = str.maketrans({'İ': 'I', 'Ş': 'S', 'Ç': 'C', 'Ö': 'O', 'Ü': 'U', 'Ğ': 'G', '\u0307': None})
AVAILABLE = '[GÖRSEL: …], [HARİTA: …], [SAYI: …], [ÇİZELGE: 1945, 1962], [KARŞILAŞTIR: A | B], [LİSTE: bir; iki; üç]'
MARKER = re.compile(r'\[([^\[\]\n]{0,300})\]')
HEADING_WORDS = r'(?:bölüm|kısım|sahne|kapitel|teil|abschnitt|szene|chapter|section|part|scene|capítulo|sección|parte|escena|chapitre|partie|scène)'
SENTENCE_END = re.compile(r'(?<=[.!?…])["“”»’)]*\s+')


def _plain(line):
    """One line without Markdown decoration; None when the whole line is a
    heading, a numbered/section title or a rule (not spoken)."""
    stripped = line.strip()
    if not stripped:
        return ''
    if re.fullmatch(r'[-*_=~]{3,}', stripped) or stripped.startswith('#') or stripped.startswith('|'):
        return None
    if re.fullmatch(rf'{HEADING_WORDS}\s*\d+\s*[.:)\-–—]?\s*[^.!?]{{0,80}}', stripped, re.I):
        return None
    if re.fullmatch(r'\d+\s*[.)]\s*[^.!?]{1,80}', stripped) and len(stripped.split()) <= 8:
        return None  # “1. Einleitung” style title line
    if re.fullmatch(r'\*\*[^*]{1,80}\*\*:?|__[^_]{1,80}__:?', stripped):
        return None  # a bold-only line is a heading
    text = re.sub(r'^\s*(?:>+\s*)+', '', stripped)
    text = re.sub(r'^\s*(?:[-*•–]\s+|\d+\s*[.)]\s+)', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'(?<!\[)\[([^\[\]]+)\]\((?:https?://|www\.)[^)]*\)', r'\1', text)  # links → text
    text = re.sub(r'(\*\*|__)(.+?)\1', r'\2', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])', r'\1', text)
    text = re.sub(r'(?<![\w_])_(?!\s)([^_]+?)(?<!\s)_(?![\w_])', r'\1', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    return text


def sentences(paragraph):
    """(start, end) offsets of the sentences of one paragraph."""
    spans, start = [], 0
    for match in SENTENCE_END.finditer(paragraph):
        spans.append((start, match.start()))
        start = match.end()
    if start < len(paragraph):
        spans.append((start, len(paragraph)))
    return [(a, b) for a, b in spans if paragraph[a:b].strip()]


def clean(raw):
    """→ {'text': narration, 'markers': [...], 'warnings': [...]}"""
    raw = (raw or '').replace('\r\n', '\n').replace('\r', '\n').replace(' ', ' ')
    raw = ''.join(c for c in raw if c in '\n\t' or ord(c) >= 32)
    lines = [_plain(line) for line in raw.split('\n')]
    blocks, current = [], []
    for line in lines:
        if line is None or not line.strip():  # headings and rules also end a paragraph
            if current: blocks.append(' '.join(current)); current = []
            continue
        current.append(line.strip())
    if current: blocks.append(' '.join(current))
    paragraphs, markers, warnings = [], [], []
    for block in blocks:
        text, found = '', []
        position = 0
        for match in MARKER.finditer(block):
            text += block[position:match.start()]
            position = match.end()
            inner = match.group(1).strip()
            kind_raw, _, value = inner.partition(':')
            kind = KINDS.get(kind_raw.strip().upper().translate(ASCII))
            if kind and value.strip():
                before = ' '.join(text.split())
                found.append((len(before), bool(re.search(r'[.!?…]["“”»’)]*$', before)), kind, ' '.join(value.split())[:200]))
            else:
                warnings.append(f'Tanınmayan işaret: [{inner[:60]}] — seslendirmeye ve altyazıya gitmez. Kullanılabilenler: {AVAILABLE}.')
            text += ' '
        text += block[position:]
        paragraph = re.sub(r'\s+([,.;:!?…])', r'\1', ' '.join(text.split()))
        if not paragraph:
            for _, _, kind, value in found:
                warnings.append(f'[{LABELS[kind]}: {value}] işaretinin bağlanacağı bir cümle yok.')
            continue
        spans = sentences(paragraph)
        for offset, ends_sentence, kind, value in found:
            if ends_sentence:  # right after a sentence: that sentence
                span = next((s for s in reversed(spans) if s[0] < offset), spans[0])
            else:  # paragraph start or inside a sentence: the following / containing one
                span = next((s for s in spans if s[1] >= offset), spans[-1])
            markers.append({'type': kind, 'label': LABELS[kind], 'value': value, 'sentence': paragraph[span[0]:span[1]].strip()})
        paragraphs.append(paragraph)
    return {'text': '\n\n'.join(paragraphs), 'markers': markers, 'warnings': list(dict.fromkeys(warnings))}


def apply_markers(blocks, markers, language='de'):
    """Owner hints on the scene plan: [GÖRSEL] becomes the first search query
    and what must be shown; the infographic markers ([HARİTA], [SAYI],
    [ÇİZELGE], [KARŞILAŞTIR], [LİSTE]) are kept with their sentence and become a
    motion graphic in Medyayı Tamamla. The narration is never changed."""
    for marker in markers or []:
        sentence = ' '.join(marker.get('sentence', '').split())
        block = next((b for b in blocks if sentence and sentence in ' '.join(b['narration'].split())), None)
        if block is None:
            continue
        hints = block.setdefault('owner_hints', [])
        if any(h['type'] == marker['type'] and h['value'] == marker['value'] for h in hints):
            continue
        hints.append({'type': marker['type'], 'value': marker['value'], 'sentence': sentence[:600]})
        old = [q for q in [block.get('stock_query', ''), *block.get('alternative_stock_queries', [])] if q]
        if marker['type'] == 'visual':
            from app.scripts.query_clean import english_query
            query = english_query(marker['value'], language, limit=6) or marker['value']  # the note in English search words
            block['stock_query'] = query[:300]
            block['alternative_stock_queries'] = [q for q in old if q.casefold() != query.casefold()][:5] or [query]
            block['must_show'] = marker['value'][:300]
            block['visual_intent'] = (marker['value'] + ' — ' + block.get('visual_intent', ''))[:1500]
        elif marker['type'] == 'map':
            from app.scripts.query_clean import english_query
            extra = f'{english_query(marker["value"], language, strict=True, limit=3) or "old"} map'
            if extra.casefold() not in (q.casefold() for q in old):
                block['alternative_stock_queries'] = (block.get('alternative_stock_queries', []) + [extra[:300]])[-5:]
    return blocks
