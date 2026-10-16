"""Stock searches are English only (stock sites are tagged in English).

english_query() turns any planned query — the AI's, the local plan's or the
owner's [GÖRSEL] note — into English search words:
- German/Turkish words from the built-in word list are translated
  (“Stadttor” → “city gate”, “surları” → “city walls”), German compounds are
  split (“Stadtmauer” → “city stone wall”);
- place names become their English name (“Kudüs” → “Jerusalem”, “Rom” → “Rome”);
- numbers, numbers written as words (“Siebenhundertfünf”), era marks
  (“v. Chr.”, “MÖ”) and filler words are removed;
- any other word that is clearly not English (umlauts, Turkish letters,
  German endings, German/Turkish function words) is dropped.
strict=True (the local plan): only translated words and English place names
are kept — the narration's own words never reach a search.
generic_queries() gives English fallback queries for a topic."""
import re
import unicodedata
from functools import lru_cache

ERA = re.compile(r'(?i)\b(?:v|n)\.\s*chr\.?|\b(?:vor|nach)\s+christus\b|\b(?:vor|nach)\s+chr\b|\bm\.\s*[öo]\.?|\bm\.\s*s\.?|'
                 r'\b(?:mö|ms|bce|ce|bc|ad)\b(?=\s|$)|\bmilattan\s+(?:önce|sonra)\b|\bjh\.?|\bjahrhunderts?\b|\byüzyıl\w*')
# Endings English words practically never have (“black”, “kitchen”, “young” must stay English).
GERMAN_SHAPE = re.compile(r'(?:ß|ungen$|heit$|keit$|lich$|isch$|schaft$|chen$(?<!itchen)(?<!tchen))')
TURKISH_SHAPE = re.compile(r'(?:ı|ş|ğ|ç|lar$|ler$|ları$|leri$|nın$|nin$|sı$|si$|daki$|deki$)')
EN_FILLER = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'its', 'his', 'her', 'their', 'into',
             'over', 'under', 'as', 'is', 'are', 'was', 'were', 'be', 'that', 'this', 'these', 'those', 'very', 'some', 'about', 'they', 'have',
             'has', 'had', 'been', 'but', 'who', 'which', 'it'}
ENGLISH_KEEP = {'old', 'ancient', 'medieval', 'historic', 'roman', 'greek', 'egyptian', 'biblical', 'holy', 'stone', 'wooden', 'golden', 'dark',
                'aerial', 'closeup', 'close', 'view', 'night', 'sunset', 'sunrise', 'desert', 'city', 'ruins', 'temple', 'map', 'old', 'people',
                'landscape', 'documentary', 'cinematic', 'slow', 'motion', 'interior', 'exterior', 'street', 'market', 'army', 'soldiers'}
ADJECTIVES = {
    'de': {'antik': 'ancient', 'alt': 'old', 'groß': 'large', 'gross': 'large', 'klein': 'small', 'dunkel': 'dark', 'hell': 'bright',
           'römisch': 'roman', 'griechisch': 'greek', 'ägyptisch': 'egyptian', 'biblisch': 'biblical', 'mittelalterlich': 'medieval',
           'heilig': 'holy', 'golden': 'golden', 'steinern': 'stone', 'hölzern': 'wooden', 'zerstört': 'destroyed', 'brennend': 'burning',
           'verlassen': 'abandoned', 'leer': 'empty', 'jüdisch': 'jewish', 'assyrisch': 'assyrian', 'babylonisch': 'babylonian',
           'persisch': 'persian', 'osmanisch': 'ottoman', 'byzantinisch': 'byzantine', 'christlich': 'christian', 'königlich': 'royal'},
    'tr': {'antik': 'ancient', 'eski': 'old', 'büyük': 'large', 'küçük': 'small', 'karanlık': 'dark', 'kutsal': 'holy', 'altın': 'golden',
           'taş': 'stone', 'ahşap': 'wooden', 'yıkık': 'destroyed', 'yanan': 'burning', 'terk': 'abandoned', 'roma': 'roman',
           'mısır': 'egyptian', 'osmanlı': 'ottoman', 'bizans': 'byzantine'},
}
EXTRA_NOUNS = {
    'de': {'christus': 'jesus christ', 'jesus': 'jesus christ', 'leichnam': 'burial', 'begräbnis': 'burial', 'grabmal': 'tomb',
           'handvoll': '', 'stadttor': 'city gate', 'stadtmauer': 'city walls', 'mauern': 'city walls', 'ruinen': 'ruins', 'tal': 'valley',
           'hügel': 'hill', 'feld': 'field', 'ernte': 'harvest', 'weizen': 'wheat', 'schafe': 'sheep', 'schaf': 'sheep', 'ziege': 'goat',
           'hirte': 'shepherd', 'zelt': 'tent', 'karawane': 'caravan', 'wagen': 'chariot', 'streitwagen': 'chariot', 'bogen': 'bow arrow',
           'speer': 'spear', 'pfeil': 'arrows', 'tafel': 'clay tablet', 'tontafel': 'clay tablet', 'keilschrift': 'cuneiform',
           'altar': 'altar', 'rauch': 'smoke', 'staub': 'dust', 'blut': 'blood', 'tränen': 'tears', 'hand': 'hands', 'hände': 'hands',
           'gesicht': 'face', 'augen': 'eyes', 'thronsaal': 'throne room', 'garten': 'garden', 'brunnen': 'water well', 'sonnenuntergang': 'sunset',
           'sonnenaufgang': 'sunrise', 'sterne': 'stars', 'raumschiff': 'spaceship', 'astronaut': 'astronaut', 'mondlandung': 'moon landing',
           'schwarzes': '', 'loch': 'black hole', 'erdbeben': 'earthquake', 'flut': 'flood', 'dürre': 'drought', 'hunger': 'famine',
           'pest': 'plague', 'seuche': 'epidemic', 'gericht': 'court', 'gesetz': 'law', 'schreiber': 'scribe', 'rolle': 'scroll'},
    'tr': {'isa': 'jesus christ', 'mesih': 'jesus christ', 'ceset': 'burial', 'cenaze': 'funeral', 'kapı': 'gate', 'kapısı': 'city gate',
           'surları': 'city walls', 'duvar': 'stone wall', 'vadi': 'valley', 'tepe': 'hill', 'tarla': 'field', 'hasat': 'harvest',
           'buğday': 'wheat', 'koyun': 'sheep', 'keçi': 'goat', 'çoban': 'shepherd', 'çadır': 'tent', 'kervan': 'caravan', 'araba': 'chariot',
           'yay': 'bow arrow', 'mızrak': 'spear', 'ok': 'arrows', 'tablet': 'clay tablet', 'sunak': 'altar', 'duman': 'smoke', 'toz': 'dust',
           'kan': 'blood', 'el': 'hands', 'yüz': 'face', 'göz': 'eyes', 'bahçe': 'garden', 'kuyu': 'water well', 'günbatımı': 'sunset',
           'uzay': 'outer space', 'astronot': 'astronaut', 'deprem': 'earthquake', 'sel': 'flood', 'kıtlık': 'famine', 'veba': 'plague',
           'mahkeme': 'court', 'kâtip': 'scribe', 'tomar': 'scroll'},
}
TOPICS = [  # (words in a topic, English fallback queries)
    (('rom', 'roma', 'römer', 'roman', 'griech', 'yunan', 'antik', 'ancient', 'assyr', 'asur', 'babylon', 'babil', 'ägypt', 'mısır', 'egypt',
      'pharao', 'firavun', 'bibel', 'bible', 'kutsal', 'king', 'könig', 'kral', 'reich', 'empire', 'imparator', 'tarih', 'history', 'geschichte',
      'jerusalem', 'kudüs', 'israel', 'juda', 'krieg', 'savaş', 'war'),
     ['ancient ruins', 'old stone city', 'historic manuscript', 'desert landscape', 'old map']),
    (('weltall', 'space', 'uzay', 'planet', 'gezegen', 'stern', 'star', 'yıldız', 'galax', 'mond', 'moon', 'ay ', 'nasa', 'rakete', 'roket', 'rocket'),
     ['outer space stars', 'galaxy nebula', 'planet earth from space', 'night sky stars', 'rocket launch']),
    (('meer', 'ocean', 'okyanus', 'deniz', 'sea', 'schiff', 'ship', 'gemi', 'bermuda', 'insel', 'island', 'ada'),
     ['ocean waves', 'ship at sea', 'stormy sea', 'island coast', 'underwater ocean']),
    (('wald', 'forest', 'orman', 'tier', 'animal', 'hayvan', 'natur', 'nature', 'doğa', 'dschungel', 'jungle'),
     ['forest landscape', 'wild animals', 'jungle river', 'mountain landscape', 'nature aerial']),
    (('stadt', 'city', 'şehir', 'land', 'country', 'ülke', 'geograf', 'coğrafya', 'karte', 'harita', 'map'),
     ['aerial city view', 'world map', 'mountain landscape', 'river valley', 'country road']),
]
SPANISH_FUNCTION = set('pero aunque porque mientras entonces tambien también solo sólo para desde hasta hacia entre sobre durante donde cuando como cómo sino sus su es son fue fueron hay muy más mas cada este esta estos estas ese esa eso se lo nos les ya sin con por una uno unos unas el la los las del al que y o en de'.split())

GENERIC = ['documentary landscape', 'cinematic landscape', 'clouds sky timelapse']


def plain_text(text):
    from app.motion.places import plain
    return plain(text)


def fold(word):
    return unicodedata.normalize('NFC', word.casefold().strip("’'-.,;:!?()\"“”„«»"))


def _table(language):
    from app.scripts.local_words import DE, ES, FR, TR
    base = {'tr': TR, 'fr': FR, 'es': ES}.get(language, DE)
    return {**base, **ADJECTIVES.get(language, {}), **EXTRA_NOUNS.get(language, {})}


def translate(word, language):
    """English words for one German/Turkish word, '' when unknown (no guessing)."""
    from app.scripts.local_words import ENDINGS
    low = fold(word)
    for lang in (language, 'tr' if language == 'de' else 'de'):
        table = _table(lang)
        if low in table: return table[low]
        for ending in sorted(ENDINGS.get(lang, ()) + (('e', 'en', 'er', 'es', 'em') if lang == 'de' else ()), key=len, reverse=True):
            stem = low[:-len(ending)]
            if low.endswith(ending) and len(stem) >= 3 and stem in table: return table[stem]
        if lang == 'tr':  # tapınağı → tapınak, kitabı → kitap
            for ending in ('ları', 'leri', 'ı', 'i', 'u', 'ü', 'sı', 'si', 'su', 'sü'):
                stem = low[:-len(ending)] if low.endswith(ending) else ''
                for soft, hard in (('ğ', 'k'), ('b', 'p'), ('c', 'ç'), ('d', 't')):
                    if stem.endswith(soft) and stem[:-1] + hard in table: return table[stem[:-1] + hard]
        if lang == 'de' and len(low) >= 8:  # compounds: Stadtmauer → stadt + mauer
            for cut in range(3, len(low) - 2):
                head, tail = low[:cut], low[cut:]
                head = head[:-1] if head.endswith('s') and head[:-1] in table else head
                if head in table and tail in table: return f'{table[head]} {table[tail]}'
            for cut in range(3, len(low) - 3):  # at least the head noun (…mauer → stone wall)
                if low[cut:] in table and len(low[cut:]) >= 4: return table[low[cut:]]
    from app.scripts.local_words import english
    return english(word, language)


def place_english(word, exact=False):
    """English name of a place written in any language, or ''."""
    from app.motion.places import find, index, notable, plain
    key = plain(word)
    place = index().get(key) if exact else find(word)
    if not place or not notable(place, key): return ''  # never a small town that happens to share a common word
    return place.get('en') or ''


def _stop_words():
    from app.scripts.local_plan import STOP
    from app.motion.numbers import VALUES, MULTIPLIERS
    return STOP | set(VALUES) | set(MULTIPLIERS) | GERMAN_TURKISH_SMALL | {'jahr', 'jahre', 'jahrhundert', 'yıl', 'yılı', 'yılında', 'yüzyıl', 'chr', 'christi'}


# (words that are also English — in, an, am, so, war, man… — are not listed)
GERMAN_TURKISH_SMALL = {'von', 'vom', 'im', 'zu', 'zum', 'zur', 'auf', 'mit', 'bei', 'aus', 'ins', 'ist', 'sind', 'wurde', 'wurden', 'hatte',
                        'sein', 'seine', 'ihre', 'ihr', 'sich', 'nicht', 'kein', 'keine', 'sie', 'wir', 'ich', 'dort', 'ganz', 'durch', 'gegen',
                        'ohne', 'zwischen', 'neben', 'hinter', 'olan', 'olarak', 'kadar', 'sonra', 'önce', 'içinde', 'üzerinde', 'altında',
                        'yanında', 'hiç', 'tüm', 'bütün'}
# Words that are both a German/Turkish word of the list and a common English search word: kept in English queries.
SAME_IN_ENGLISH = {'see', 'kind', 'hand', 'boot', 'tag', 'rat', 'rock', 'wand', 'arm', 'gift', 'bad', 'hut', 'fest', 'tier', 'mut', 'arena',
                   'museum', 'forum', 'planet', 'pilot', 'radar', 'computer', 'auto', 'relief', 'statue', 'altar', 'tablet', 'gold', 'ok', 'el', 'kale',
                   'sur', 'tor', 'stern', 'bogen', 'rolle', 'mosaik', 'golden', 'alt', 'see', 'hell', 'yay', 'ada', 'su', 'mum', 'para', 'sel', 'toz', 'kan'}


def is_number_word(low):
    from app.motion.numbers import tokens, VALUES, MULTIPLIERS
    if low in VALUES or low in MULTIPLIERS: return True
    return any(kind == 'compound' for kind, _ in tokens(low))


def foreign(word):
    """Clearly not an English search word."""
    low = fold(word)
    if not low.isascii(): return True
    if low in _stop_words() and low not in EN_FILLER and low not in ENGLISH_KEEP: return True
    return bool(GERMAN_SHAPE.search(low)) and low not in ENGLISH_KEEP and len(low) > 4 and not low.endswith(('tch', 'ish'))


@lru_cache(maxsize=1)
def english_vocabulary():
    """English words the app itself uses (translations, topic queries): safe in a strict query."""
    from app.scripts.local_words import DE, ES, FR, TR
    words = set(ENGLISH_KEEP)
    for table in (DE, TR, FR, ES, *ADJECTIVES.values(), *EXTRA_NOUNS.values()):
        for value in table.values(): words.update(value.split())
    for _, queries in TOPICS:
        for query in queries: words.update(query.split())
    for query in GENERIC: words.update(query.split())
    return frozenset(w for w in words if w not in EN_FILLER)


def german_like(word, language):
    low = fold(word)
    if not low: return False
    if not low.isascii() and not place_english(word): return True
    if low in GERMAN_TURKISH_SMALL or (low in _stop_words() and low not in EN_FILLER): return True
    if low in SAME_IN_ENGLISH: return False
    name = place_english(word) if len(low) >= 4 else ''
    if name and plain_text(name) != plain_text(word): return True  # a place written in German/Turkish (“Bermudadreieck”, “Kudüs”)
    value = translate(word, language)
    if low in value.split() or low.rstrip('s') in value.split(): return False  # “cockpit” → “cockpit”: the same word in English
    return bool(value) and (word[:1].isupper() or low in _table(language) or bool(GERMAN_SHAPE.search(low)))


def english_query(query, language='de', *, strict=False, limit=5):
    """English search words for a query ('' when nothing English is left)."""
    text = ERA.sub(' ', str(query or ''))
    text = re.sub(r'\d+[\w.,]*', ' ', text)
    out = []
    words = re.findall(r"[^\W\d_][\w’'-]*", text)
    if not strict and any(german_like(w, language) for w in words):
        strict = True  # a German/Turkish query: only translated words and place names, never the rest
    i = 0
    while i < len(words):
        word = words[i]
        low = fold(word)
        if language == 'es' and low in SPANISH_FUNCTION:
            i += 1; continue
        two = f'{word} {words[i + 1]}' if i + 1 < len(words) else ''
        if two and word[:1].isupper() and place_english(two, exact=True):
            out.append(place_english(two, exact=True)); i += 2; continue
        i += 1
        if not low or (strict and low in EN_FILLER) or is_number_word(low): continue
        if strict:
            if low in english_vocabulary() and low.isascii():  # already an English word of the lists (“ship”, “ruins”)
                out.append(low); continue
            value = place_english(word, exact=True) or translate(word, language)
            if value: out.append(value)
            continue
        if not foreign(word) and len(low) >= 2: out.append(word.strip("’'-.,;:!?()\"“”„«»"))  # English words stay as written
    seen, result = set(), []
    for part in ' '.join(out).split():
        key = part.casefold()
        if (key in seen and key not in EN_FILLER) or (strict and key in EN_FILLER): continue
        seen.add(key); result.append(part)
    return ' '.join(result[:limit])


def generic_queries(topic, language='de'):
    """English fallback queries that fit the video topic (never empty)."""
    low = f' {fold(topic or "")} '
    own = english_query(topic, language, strict=True, limit=3)
    for keys, queries in TOPICS:
        if any(k in low for k in keys):
            return ([own] if len(own.split()) >= 2 else []) + queries
    return ([own] if len(own.split()) >= 2 else []) + GENERIC


def clean_block(block, language='de', *, strict=False, topic=''):
    """English-only stock_query / alternatives for one plan block (in place)."""
    queries = [block.get('stock_query', ''), *(block.get('alternative_stock_queries') or [])]
    cleaned = []
    for query in queries:
        english = english_query(query, language, strict=strict)
        if len(english.split()) == 1:  # one word is too vague (and fails the plan check): add a different English word of the topic
            extra = next((w for q in generic_queries(topic, language) + GENERIC for w in q.split() if w.casefold() != english.casefold()), 'landscape')
            english = f'{english} {extra}'
        if english and english.casefold() not in (c.casefold() for c in cleaned): cleaned.append(english)
    if not cleaned: cleaned = generic_queries(topic, language)[:3]
    block['stock_query'] = cleaned[0][:300]
    block['alternative_stock_queries'] = [c[:300] for c in cleaned[1:6]] or [q for q in generic_queries(topic, language) if q != cleaned[0]][:2]
    return block


def scope_query(query, narration):
    """Remove foreign places from a query when this shot names its own place.

    Country labels come only from the bundled GeoNames data. No guessed
    country is appended, and a sentence explicitly comparing places keeps both.
    """
    from app.motion.places import spoken_places, find, country_name, plain
    spoken = spoken_places(narration)
    if not spoken: return query
    allowed = set()
    for name, _, _ in spoken:
        place = find(name)
        allowed.add(plain(name))
        if place:
            allowed.update(plain(a) for a in place.get('aliases', []))
            allowed.update(plain(country_name(place, lang)) for lang in ('en', 'de', 'es', 'tr', 'fr'))
    result = query
    for name, _, _ in spoken_places(query):
        if plain(name) not in allowed:
            result = re.sub(r'(?<!\w)' + re.escape(name) + r'(?!\w)', ' ', result, flags=re.I)
    return ' '.join(result.split())
