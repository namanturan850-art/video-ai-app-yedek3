"""Numbers written as words in the narration (German first, also English,
Spanish, French, Turkish), so a motion graphic showing “1945” or “%40” is
accepted when the narration says “neunzehnhundertfünfundvierzig” or
“vierzig Prozent”. Only reads numbers; never changes any text.
"""
import re

UNITS = {
    'de': {'null': 0, 'eins': 1, 'ein': 1, 'eine': 1, 'zwei': 2, 'zwo': 2, 'drei': 3, 'vier': 4, 'fünf': 5, 'sechs': 6, 'sieben': 7,
           'acht': 8, 'neun': 9, 'zehn': 10, 'elf': 11, 'zwölf': 12, 'dreizehn': 13, 'vierzehn': 14, 'fünfzehn': 15, 'sechzehn': 16,
           'siebzehn': 17, 'achtzehn': 18, 'neunzehn': 19, 'zwanzig': 20, 'dreißig': 30, 'dreissig': 30, 'vierzig': 40, 'fünfzig': 50,
           'sechzig': 60, 'siebzig': 70, 'achtzig': 80, 'neunzig': 90},
    'en': {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
           'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
           'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90},
    'es': {'cero': 0, 'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9,
           'diez': 10, 'once': 11, 'doce': 12, 'trece': 13, 'catorce': 14, 'quince': 15, 'dieciséis': 16, 'diecisiete': 17,
           'dieciocho': 18, 'diecinueve': 19, 'veinte': 20, 'veintiuno': 21, 'veintidós': 22, 'veintitrés': 23, 'veinticuatro': 24,
           'veinticinco': 25, 'veintiséis': 26, 'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29, 'treinta': 30, 'cuarenta': 40,
           'cincuenta': 50, 'sesenta': 60, 'setenta': 70, 'ochenta': 80, 'noventa': 90, 'cien': 100, 'ciento': 100,
           'doscientos': 200, 'trescientos': 300, 'cuatrocientos': 400, 'quinientos': 500, 'seiscientos': 600, 'setecientos': 700,
           'ochocientos': 800, 'novecientos': 900},
    'fr': {'zéro': 0, 'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5, 'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9,
           'dix': 10, 'onze': 11, 'douze': 12, 'treize': 13, 'quatorze': 14, 'quinze': 15, 'seize': 16, 'vingt': 20, 'vingts': 20,
           'trente': 30, 'quarante': 40, 'cinquante': 50, 'soixante': 60},
    'tr': {'sıfır': 0, 'bir': 1, 'iki': 2, 'üç': 3, 'dört': 4, 'beş': 5, 'altı': 6, 'yedi': 7, 'sekiz': 8, 'dokuz': 9, 'on': 10,
           'yirmi': 20, 'otuz': 30, 'kırk': 40, 'elli': 50, 'altmış': 60, 'yetmiş': 70, 'seksen': 80, 'doksan': 90},
}
MULTIPLIERS = {'hundert': 100, 'tausend': 1000, 'million': 10 ** 6, 'millionen': 10 ** 6, 'milliarde': 10 ** 9, 'milliarden': 10 ** 9,
               'hundred': 100, 'thousand': 1000, 'millions': 10 ** 6, 'billion': 10 ** 9, 'billions': 10 ** 9,
               'mil': 1000, 'millón': 10 ** 6, 'millones': 10 ** 6, 'cent': 100, 'cents': 100, 'mille': 1000, 'milliard': 10 ** 9,
               'milliards': 10 ** 9, 'yüz': 100, 'bin': 1000, 'milyon': 10 ** 6, 'milyar': 10 ** 9}
CONNECTORS = {'und', 'and', 'y', 'et'}
# Single words that are (almost) always an article/pronoun, not a number.
ARTICLES = {'ein', 'eine', 'un', 'une', 'uno', 'una', 'one', 'bir', 'on'}
VALUES = {w: v for table in UNITS.values() for w, v in table.items()}
# German writes numbers as one word: split “neunzehnhundertfünfundvierzig”.
GERMAN = sorted([*UNITS['de'], 'hundert', 'tausend', 'und'], key=len, reverse=True)


def _split_german(word):
    out, i = [], 0
    while i < len(word):
        part = next((p for p in GERMAN if word.startswith(p, i)), None)
        if not part: return None
        out.append(part); i += len(part)
    return out if len(out) > 1 or out[0] in UNITS['de'] or out[0] in ('hundert', 'tausend') else None


def tokens(text):
    out = []
    for raw in re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)*|\d+", (text or '').casefold()):
        for word in raw.split('-'):
            word = re.sub(r'(?<=.{3})(mal|fach|fache|fachen)$', '', word) if word not in VALUES else word  # “hundertmal”, “dreifach”
            german = _split_german(word) if word not in VALUES and word not in MULTIPLIERS and len(word) > 6 else None
            if german: out.append(('compound', german))
            else: out.append(('word', word))
    return out


def _runs(text):
    """Consecutive number words → lists of number groups (one list per run)."""
    runs, group, total, current, last, linked = [], [], 0, 0, None, False

    def flush():
        nonlocal total, current, last
        if last is not None: group.append(total + current)
        total, current, last = 0, 0, None

    def feed(word):
        nonlocal total, current, last, linked
        if word in CONNECTORS:
            if last is not None: linked = True
            return True
        if word in MULTIPLIERS:
            m = MULTIPLIERS[word]
            if m == 100: current = (current or 1) * 100
            else: total += (current or 1) * m; current = 0
            last, linked = 'mult', False
            return True
        if word in VALUES:
            v = VALUES[word]
            joins = last in (None, 'mult') or linked or current % 100 == 0 or (v < 10 and current % 10 == 0 and current % 100 >= 20) \
                or (current % 100 in (60, 80) and 10 <= v < 20) or (word in ('vingt', 'vingts') and current % 100 == 4)
            if not joins: flush()
            if word in ('vingt', 'vingts') and current % 100 == 4: current += 76  # quatre-vingt(s) = 80
            else: current += v
            last, linked = 'value', False
            return True
        return False

    for kind, item in tokens(text):
        parts = item if kind == 'compound' else [item]
        if kind == 'word' and item in ARTICLES and last is None:
            if group: runs.append(group); group = []
            continue
        if all(p in VALUES or p in MULTIPLIERS or p in CONNECTORS for p in parts):
            for p in parts: feed(p)
            if kind == 'compound': linked = False
            continue
        flush()
        if group: runs.append(group); group = []
        linked = False
    flush()
    if group: runs.append(group)
    return runs


def spoken_numbers(text):
    """Every number written as words in the text (plus “nineteen forty-five”
    year readings)."""
    found = set()
    for groups in _runs(text):
        found.update(groups)
        for a, b in zip(groups, groups[1:]):
            if 10 <= a <= 99 and 0 <= b <= 99: found.add(a * 100 + b)
    return found


def value_of(digits):
    """'1.945' / '1,945' / '40' / '3,5' → number, or None."""
    digits = digits.strip()
    if re.fullmatch(r'\d{1,3}(?:[.,   ]\d{3})+', digits):
        return float(re.sub(r'\D', '', digits))
    try: return float(digits.replace(',', '.'))
    except ValueError: return None


def is_spoken(digits, narration):
    """True when the number is in the narration as digits or as words."""
    text = ' '.join((narration or '').split()).casefold()
    if digits and digits.casefold() in text:
        return True
    value = value_of(digits)
    if value is None: return False
    if value in {value_of(d) for d in re.findall(r'\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?', text)}:
        return True
    return value.is_integer() and int(value) in spoken_numbers(text)
