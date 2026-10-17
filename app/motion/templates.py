"""Parameterised motion-graphic templates. No free-form code: the AI only
fills fields (text, numbers, places, emphasis word) that are validated here.

A template becomes a renderer-neutral *scene*: elements with static props
and keyframe tracks. app/motion/raster.py (local, Pillow + FFmpeg) and
app/motion/motion.tsx (OpenMontage/Remotion) draw the same scene, so both
engines show the same animation. Timing is anchored to the emphasis moment
(the narration word), where the kit's sound effect plays.
"""
import gzip
import json
import math
import re
from functools import lru_cache
from pathlib import Path

W, H, FPS = 1920, 1080, 30
TEMPLATES = {'stat': 'Büyüyen sayı / istatistik', 'map': 'Harita + işaret', 'quote': 'Başlık / alıntı',
             'timeline': 'Zaman çizelgesi', 'compare': 'Karşılaştırma', 'list': 'Madde listesi'}
NUMBER = re.compile(r'(?<![\w])([+-]?)(\d{1,3}(?:[.,  ]\d{3})+|\d+(?:[.,]\d+)?)(\s?(?:%|‰|°C|°|km²|km|m|kg|t|Mio\.?|Mrd\.?|Millionen|Milliarden|million|billion|millions|milliards|millones|milyon|milyar)?)', re.I)
FONT_DIR = Path(__file__).resolve().parent.parent / 'static' / 'fonts'


class MotionError(ValueError):
    pass


def words(text):
    return re.findall(r"[\w’'-]+", text.casefold())


def clean(value, limit):
    value = ' '.join(str(value or '').split())
    return value[:limit]


def in_narration(value, narration):
    return clean(value, 300).casefold() in ' '.join(narration.split()).casefold()


def place_spoken(place, text, entities=()):
    """The place (or another name of it, or one of its words) is spoken."""
    from app.motion.places import lookup, spoken_places
    if not place: return False
    if in_narration(place, text) or place.casefold() in [str(e).casefold() for e in entities]: return True
    found = lookup(place)
    if found and any((lat, lon) == found[:2] for _, lat, lon in spoken_places(text)): return True
    return any(len(w) >= 4 and re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', text, re.I) for w in re.findall(r'[^\W\d_]+', place))


from app.motion.templates_extra import TEMPLATES_EXTRA  # noqa: E402  (the nine marker infographics)
TEMPLATES.update(TEMPLATES_EXTRA)
BASIC = ('stat', 'map', 'quote', 'timeline', 'compare', 'list')  # also drawn by OpenMontage (motion.tsx)


def validate(spec, narration, entities=(), *, trusted=False):
    """Clean spec (see _validate); the chosen layout (0-2, app/motion/layouts.py) is kept."""
    from app.motion.layouts import layout_of
    result = _validate(spec, narration, entities, trusted=trusted)
    if layout_of(spec):
        result = {**result, 'layout': layout_of(spec)}
    return result


def _validate(spec, narration, entities=(), *, trusted=False):
    """Return a clean spec or raise MotionError. Numbers, dates, places and
    quotes must be spoken in the narration (digits or words, e.g.
    “neunzehnhundertfünfundvierzig” = 1945) — a template never invents facts.
    trusted=True: the owner's own marker in the text ([SAYI: …], [HARİTA: …]);
    only the shape is checked."""
    from app.motion.numbers import is_spoken
    if not isinstance(spec, dict) or spec.get('template') not in TEMPLATES or not isinstance(spec.get('data'), dict):
        raise MotionError('template')
    t, d = spec['template'], spec['data']
    if t in TEMPLATES_EXTRA:
        from app.motion.templates_extra import validate_extra
        try: return validate_extra(spec)
        except (ValueError, TypeError, KeyError) as error: raise MotionError(str(error)) from None
    text = ' '.join(narration.split())
    spoken = lambda v: trusted or (bool(v) and in_narration(v, text))
    number = lambda v: bool(NUMBER.search(v)) and (trusted or is_spoken(NUMBER.search(v).group(2), text))
    if t == 'stat':
        value, label = clean(d.get('value'), 24), clean(d.get('label'), 70)
        if not number(value):
            raise MotionError('stat value must be a number from the narration')
        data = {'value': value, 'label': focus(label.rstrip(' …'))}  # at most 5 words under the number
    elif t == 'map':
        place, label = clean(d.get('place'), 60), clean(d.get('label'), 60)
        try:
            lat, lon = float(d.get('lat')), float(d.get('lon'))
        except (TypeError, ValueError):
            raise MotionError('map coordinates') from None
        if not (-85 <= lat <= 85 and -180 <= lon <= 180) or not place or not (trusted or place_spoken(place, text, entities)):
            raise MotionError('map place must be spoken')
        data = {'place': place, 'label': label, 'lat': round(lat, 3), 'lon': round(lon, 3)}
    elif t == 'quote':
        quote = clean(d.get('text'), 160).strip(' "“”„«»')
        if len(quote.split()) < 2 or not spoken(quote):
            raise MotionError('quote must be an exact narration phrase')
        data = {'text': focus(quote)}  # every text card: a 2-5 word accent, never the whole sentence
    elif t == 'timeline':
        events = d.get('events')
        if not isinstance(events, list) or not 2 <= len(events) <= 5:
            raise MotionError('timeline needs 2-5 events')
        data = {'events': []}
        for e in events:
            date, label = clean((e or {}).get('date'), 20), clean((e or {}).get('label'), 50)
            now = not re.search(r'\d', date) and len(date.split()) <= 2 and spoken(date)  # “aujourd'hui”, “heute”, “bugün” as the last point
            if not now and (not re.search(r'\d', date) or not (spoken(date) or all(is_spoken(n, text) for n in re.findall(r'\d+', date)))):
                raise MotionError('timeline dates must be spoken')
            data['events'].append({'date': date, 'label': label})
    elif t == 'compare':
        items = d.get('items')
        if not isinstance(items, list) or not 2 <= len(items) <= 5:
            raise MotionError('compare needs 2-5 items')
        data = {'title': clean(d.get('title'), 60), 'items': []}
        for item in items:
            label, value = clean((item or {}).get('label'), 40), clean((item or {}).get('value'), 24)
            if not label or (value and not number(value)):
                raise MotionError('compare values must be spoken numbers')
            data['items'].append({'label': label, 'value': value})
        if len(data['items']) > 2 and not all(i['value'] for i in data['items']):
            raise MotionError('more than two items need values (bar chart)')
    else:  # list
        items = d.get('items')
        if not isinstance(items, list) or not 2 <= len(items) <= 4:
            raise MotionError('list needs 2-4 items')
        data = {'title': clean(d.get('title'), 60), 'items': [clean(i, 60) for i in items]}
        if not all(data['items']):
            raise MotionError('empty list item')
    emphasis = clean(spec.get('emphasis'), 60)
    if emphasis and not in_narration(emphasis, text):
        emphasis = ''
    return {'template': t, 'data': data, 'emphasis': emphasis}


PERCENT = re.compile(r'(?i)\b(prozent|percent|per cent|por ciento|pour cent|pourcent)\b')


def focus(text, most=5):
    """2-5 word accent of a narration phrase (around a number/date, else its opening words)."""
    from app.rendering.smart_edit import highlight
    words = ' '.join(str(text or '').split()).rstrip('.!?…').split()
    return highlight(' '.join(words)) if len(words) > most else ' '.join(words).strip(',;:')


def short(sentence, limit=70):
    """At most `limit` characters, cut at a word."""
    if len(sentence) <= limit: return sentence
    return sentence[:limit].rsplit(' ', 1)[0].rstrip(' ,;:') + ' …'


def label_words(sentence, value=''):
    """The stat card's label: at most 5 words of the sentence, the number itself left out."""
    words = [w for w in ' '.join(sentence.split()).rstrip('.!?…').split() if w.strip(',.;:') != str(value).strip() and not re.fullmatch(r'[\d.,%]+', w)]
    return focus(' '.join(words))


def from_narration(sentence, entities=()):
    """Deterministic motion from one narration sentence: a number (digits or
    words) → counter, several years → timeline, a known place → map; a plain
    text card only when nothing else is spoken."""
    from app.motion.numbers import spoken_numbers
    from app.motion.places import spoken_places
    sentence = ' '.join(sentence.split()).rstrip('.!?…')
    years = list(dict.fromkeys(y for y in re.findall(r'(?<!\d)(1\d{3}|20\d{2})(?!\d)', sentence)))
    if len(years) < 2:
        years = list(dict.fromkeys(years + [str(n) for n in sorted(spoken_numbers(sentence)) if 1000 <= n <= 2100 and str(n) not in years]))
    if 2 <= len(years) <= 5:
        events = []
        for year in years:
            at = sentence.find(year)
            after = []
            for word in (sentence[at + len(year):].split() if at >= 0 else []):
                if re.search(r'\d', word) or word.casefold() in ('bis', 'to', 'until', 'hasta', "jusqu'en", 'und', 'and', 've', 'y', 'et') or len(after) == 3: break
                after.append(word)
            events.append({'date': year, 'label': clean(' '.join(after).strip(' ,;:'), 50)})
        return {'template': 'timeline', 'data': {'events': events}, 'emphasis': ''}
    match = NUMBER.search(sentence)
    if match:
        value = (match.group(1) + match.group(2) + match.group(3)).strip()
        return {'template': 'stat', 'data': {'value': value, 'label': label_words(sentence, value)}, 'emphasis': match.group(2)}
    for word in sentence.split():
        found = [n for n in spoken_numbers(word.strip(',.;:')) if n >= 2]
        if found:
            n = max(found)
            percent = PERCENT.search(sentence[sentence.find(word):sentence.find(word) + len(word) + 14]) or 'yüzde ' + word.casefold() in sentence.casefold()
            value = (f'%{n}' if 'yüzde' in sentence.casefold() else f'{n} %') if percent else str(n)
            return {'template': 'stat', 'data': {'value': value, 'label': label_words(sentence, word)}, 'emphasis': word.strip(',.;:')}
    places = spoken_places(sentence) or [p for e in entities for p in spoken_places(str(e)) if in_narration(p[0], sentence)]
    if places:
        name, lat, lon = places[0]
        return {'template': 'map', 'data': {'place': name, 'label': '', 'lat': lat, 'lon': lon}, 'emphasis': name.split()[0]}
    tokens = focus(sentence).split()
    text = ' '.join(tokens)
    emphasis = max(tokens, key=len) if tokens else ''
    return {'template': 'quote', 'data': {'text': text}, 'emphasis': emphasis.strip(',.;:')}


def grouped(value, language='de'):
    """'1000000' → '1.000.000' (en: '1,000,000'); anything else unchanged."""
    m = re.fullmatch(r'(\D*?)(\d{5,})(\D*)', value.strip())
    if not m: return value
    return m.group(1) + f'{int(m.group(2)):,}'.replace(',', ',' if language == 'en' else '.') + m.group(3)


def number_value(text):
    m = NUMBER.search(text)
    if not m: return 1.
    digits = m.group(2)
    if re.fullmatch(r'\d{1,3}(?:[.,\u202f ]\d{3})+', digits):
        return float(re.sub(r'\D', '', digits))
    try: return float(digits.replace(',', '.'))
    except ValueError: return 1.


# ---- geometry helpers -------------------------------------------------------
def mix(a, b, t):
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02X}' for x, y in zip(pa, pb))


@lru_cache(maxsize=32)
def _font(file, size, bold):
    from PIL import ImageFont
    path = FONT_DIR / file if file else None
    try:
        font = ImageFont.truetype(str(path), size) if path and path.is_file() else ImageFont.truetype('DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default(size=size)
    try:
        axes = font.get_variation_axes()
        font.set_variation_by_axes([700 if bold and str(a.get('name')) in ("b'Weight'", 'Weight') else a.get('default', 400) for a in axes])
    except Exception:
        pass
    return font


def measure(text, file, size, bold=True):
    try:
        return _font(file, size, bold).getlength(text)
    except Exception:
        return len(text) * size * .55


def wrap(text, file, size, width, lines=3):
    from app.text_layout import wrap_text
    return wrap_text(text, lambda value: measure(value, file, size), width)


def fit(text, file, start, width, lines=2, smallest=40):
    from app.text_layout import fit_text
    return fit_text(text, lambda value, size: measure(value, file, size), width, lines, start)


# ---- scene builder ------------------------------------------------------------
class Scene:
    def __init__(self, kit, duration, emphasis):
        from app.channels import FONTS
        self.kit, self.D = kit, round(float(duration), 3)
        # The emphasis leaves room for entry (<= .6 s) and a label that stays readable >= 2 s.
        self.E = round(min(max(emphasis, .6), max(.6, self.D - (2.8 if self.D >= 5 else .35))), 3)  # (clips under 5 s are too short for it)
        self.md = min(.6, float(kit.get('motion_duration', .6)))
        p = kit['palette']
        self.bg, self.primary, self.accent, self.fg = p['background'], p['primary'], p['accent'], p['text']
        self.head = FONTS[kit.get('heading_font', 'montserrat')][1]
        self.body = FONTS[kit.get('body_font', 'inter')][1]
        self.ease = kit.get('easing', 'smooth')
        self.elements, self.sfx = [], []

    def add(self, kind, tracks=None, **props):
        self.elements.append({'type': kind, 'props': props, 'tracks': tracks or {}})
        return self.elements[-1]

    def appear(self, start, dy=40, end_opacity=1.0):
        s = max(0., start)
        return {'opacity': [[s, 0], [s + self.md, end_opacity]], 'dy': [[s, dy], [s + self.md, 0]]}

    def text(self, text, x, y, size, *, font=None, fill=None, anchor='mm', start=0., dy=40, bold=True):
        return self.add('text', self.appear(start, dy), text=text, x=x, y=y, size=size, font=font or self.head,
                        fill=fill or self.fg, anchor=anchor, bold=bold, opacity=0)

    def sound(self, name, at):
        # A riser may start just before the clip (it leads into the emphasis);
        # sounds are mixed at absolute times, so that is safe.
        if -1.0 <= at <= self.D:
            self.sfx.append({'sound': name, 't': round(at, 3)})

    def result(self):
        return {'version': 1, 'width': W, 'height': H, 'fps': FPS, 'duration': self.D, 'emphasis_time': self.E,
                'ease': self.ease, 'background': self.bg, 'elements': self.elements, 'sfx': self.sfx}


def build(spec, kit, duration, emphasis_offset, language='de'):
    from app.motion.layouts import arrange
    return keep_text_safe(arrange(_build(spec, kit, duration, emphasis_offset, language), spec, kit))


def keep_text_safe(scene, margin_x=80, margin_y=64):
    """Final renderer-neutral guard for every animated text element.

    Templates measure their own rows, but counters grow during their hit
    animation and alternative layouts transform the completed scene.  Apply
    the same final bounds before either Pillow or Remotion sees it so the
    largest animated state remains inside the 16:9 safe area.
    """
    for element in scene.get('elements', []):
        if element.get('type') not in ('text', 'counter', 'years'):
            continue
        p = element.get('props', {})
        text = str(p.get('text') or p.get('target') or '')
        if not text and element.get('type') != 'years':
            continue
        tracks = element.get('tracks') or {}
        scales = [float(p.get('scale', 1) or 1)] + [float(v) for _, v in tracks.get('scale', [])]
        scale = max(scales)
        size = float(p.get('size', 40))
        available = W - 2 * margin_x
        while text and size > 18 and measure(text, p.get('font'), round(size * scale), p.get('bold', True)) > available:
            size -= 1
        p['size'] = size
        width = measure(text, p.get('font'), round(size * scale), p.get('bold', True)) if text else size * 6
        anchor = p.get('anchor', 'mm')
        x = float(p.get('x', W / 2))
        if anchor == 'lm':
            p['x'] = min(max(x, margin_x), W - margin_x - width)
        elif anchor == 'rm':
            p['x'] = min(max(x, margin_x + width), W - margin_x)
        else:
            p['x'] = min(max(x, margin_x + width / 2), W - margin_x - width / 2)
        dys = [float(p.get('dy', 0) or 0)] + [float(v) for _, v in tracks.get('dy', [])]
        half = size * scale * .72
        low, high = margin_y + half - min(dys), H - margin_y - half - max(dys)
        p['y'] = min(max(float(p.get('y', H / 2)), low), high) if low <= high else H / 2
    return scene


def _build(spec, kit, duration, emphasis_offset, language='de'):
    s = Scene(kit, duration, emphasis_offset)
    E, D, md = s.E, s.D, s.md
    s.add('rect', x=0, y=0, w=W, h=H, fill=s.bg, opacity=1)
    t, d = spec['template'], spec['data']
    # Saved older specs may still carry a whole sentence: drawn as a 2-5 word accent.
    if t == 'quote' and d.get('text'): d = {**d, 'text': focus(d['text'])}
    if t == 'stat' and d.get('label'): d = {**d, 'label': focus(str(d['label']).rstrip(' …'))}
    if t == 'map' and kit:  # [HARİTA] on the satellite style: the place on satellite tiles (relief renderer)
        from app.channels import map_style
        if not spec.get('local_only') and map_style(kit) == 'satellite':
            from app.motion.templates_extra import build_extra
            point = {'template': 'relief', 'data': {'mode': 'zoom', 'target': d['place'], 'lat': d['lat'], 'lon': d['lon'], 'title': d['place'], 'source': d['place']}, 'emphasis': ''}
            return build_extra(s, point, language).result()
    if t in TEMPLATES_EXTRA:
        from app.motion.templates_extra import build_extra
        return build_extra(s, spec, language).result()
    if t == 'stat':
        d = {**d, 'value': grouped(d['value'], language)}
        match = NUMBER.search(d['value'])
        # Fit the final formatted value at the animation's 1.08x peak.
        size, _ = fit(d['value'], s.head, 300, (W - 160) / 1.08, 1, 64)
        start = max(.15, E - max(1.2, md * 2))
        s.add('counter', {'value': [[start, 0], [E, 1]], 'opacity': [[start - .1, 0], [start + .2, 1]],
                          'scale': [[E, 1], [E + .15, 1.08], [E + .35, 1]]},
              target=d['value'], x=W / 2, y=440, size=size, font=s.head, fill=s.accent, anchor='mm', bold=True, opacity=0, language=language,
              from_year=bool(re.fullmatch(r'1\d{3}|20\d{2}', match.group(2))) and not match.group(3).strip())
        s.add('rect', {'w': [[E - .05, 0], [E + md, 520]], 'x': [[E - .05, W / 2], [E + md, W / 2 - 260]]}, x=W / 2, y=620, w=0, h=10, fill=s.accent, opacity=1)
        if d['label']:
            fs, rows = fit(d['label'], s.body, 66, 1500, 2, 40)
            for i, row in enumerate(rows):
                s.text(row, W / 2, 720 + i * fs * 1.25, fs, font=s.body, start=.15 + i * .1, bold=False)
        s.sound('rise', E - .9); s.sound('hit', E)
    elif t == 'map':
        span_from, span_to = 140., 46.
        # The pin lands early enough that the place label is readable >= 2 s
        # (it used to drop at the emphasis word and short clips ended first).
        at = min(E, max(.6, D - 2.6))
        s.add('map', {'zoom': [[0, 0], [at, 1]]}, lon=d['lon'], lat=d['lat'], span_from=span_from, span_to=span_to,
              land=mix(s.bg, s.primary, .28), coast=mix(s.bg, s.primary, .5), ocean=mix(s.bg, s.primary, .06))
        # The pin sits on the place itself (near the poles the view stops at ±85°, so it is not always the centre).
        left, top, span, height = map_view({'lon': d['lon'], 'lat': d['lat'], 'span_from': span_from, 'span_to': span_to}, 1)
        cx, cy = W / 2, (top - d['lat']) / height * H
        cy = min(max(cy, 120), H - 260)
        s.add('circle', {'r': [[at, 0], [at + 1.2, 140]], 'opacity': [[at, .55], [at + 1.2, 0]]}, cx=cx, cy=cy, r=0, fill='', stroke=s.accent, width=6, opacity=0)
        s.add('pin', {'dy': [[at - .45, -160], [at, 0]], 'opacity': [[at - .45, 0], [at - .3, 1]]}, x=cx, y=cy, size=46, fill=s.accent, hole=s.bg, opacity=0, dy=-160)
        label = d['place'] + (' · ' + d['label'] if d['label'] else '')
        fs, rows = fit(label, s.head, 64, W - 240, 2, 34)
        width = min(W - 160, max(measure(row, s.head, fs) for row in rows) + 80)
        box_y = min(cy + 90, H - 100 - fs * (1.7 + 1.25 * (len(rows) - 1)))
        s.add('rect', s.appear(at + .1, 30), x=cx - width / 2, y=box_y, w=width, h=fs * (1.7 + 1.25 * (len(rows) - 1)), fill=s.bg, radius=16, opacity=0)
        for i, row in enumerate(rows):
            s.text(row, cx, box_y + fs * .8 + i * fs * 1.25, fs, start=at + .1 + i * .05, dy=30)
        s.sound('rise', at - .9); s.sound('hit', at)
    elif t == 'quote':
        tokens = d['text'].split()
        fs, rows = fit(d['text'], s.head, 96, 1500, 4, 52)
        target = spec.get('emphasis', '').casefold()
        flat = [w for r in rows for w in r.split()]
        hit = next((i for i, w in enumerate(flat) if target and w.casefold().strip(',.;:!?') == target.strip(',.;:!?')), len(flat) - 1)
        step = max(.06, min(.35, (E - .3) / max(1, hit)))
        top = H / 2 - (len(rows) - 1) * fs * .65
        s.add('text', s.appear(.0, 20), text='“', x=150, y=top - fs * .5, size=fs * 2.4, font=s.head, fill=s.accent, anchor='mm', bold=True, opacity=0)
        index = 0
        for r, row in enumerate(rows):
            x = W / 2 - measure(row, s.head, fs) / 2
            for word in row.split():
                at = E if index == hit else .3 + index * step if index < hit else E + (index - hit) * min(step, .15)
                at = min(at, max(.3, D - 2.6))  # every word stays readable >= 2 s
                s.text(word, x, top + r * fs * 1.3, fs, anchor='lm', start=at, dy=24,
                       fill=s.accent if index == hit else s.fg)
                x += measure(word + ' ', s.head, fs); index += 1
        s.sound('click', E)
    elif t == 'timeline':
        events = d['events']
        left, right, y = 200, W - 200, H / 2
        s.add('line', {'x2': [[.2, left], [E, right]]}, x1=left, y1=y, x2=left, y2=y, stroke=mix(s.bg, s.primary, .5), width=6, opacity=1)
        target = spec.get('emphasis', '')
        key = next((i for i, e in enumerate(events) if target and target in (e['date'] + ' ' + e['label'])), len(events) - 1)
        for i, e in enumerate(events):
            x = left + (right - left) * (i + .5) / len(events)
            at = .2 + (E - .2) * (x - left) / (right - left)
            at = E if i == key else at
            s.add('circle', {'r': [[at, 0], [at + md * .6, 18], [at + md, 14 if i != key else 22]]}, cx=x, cy=y, r=0, fill=s.accent if i == key else s.primary, opacity=1)
            date_size, date_rows = fit(e['date'], s.head, 70 if i == key else 56, (right - left) / len(events) - 24, 1, 24)
            s.text(date_rows[0], x, y - 90, date_size, fill=s.accent if i == key else s.primary, start=at, dy=30)
            fs, rows = fit(e['label'], s.body, 40, 1500 / len(events), 2, 28)
            for j, row in enumerate(rows):
                s.text(row, x, y + 80 + j * fs * 1.25, fs, font=s.body, start=at + .1, dy=20, bold=False)
            s.sound('click', at)
    elif t == 'compare':
        items = d['items']
        if d.get('title'):
            title_size, title_rows = fit(d['title'], s.head, 64, W - 240, 2, 34)
            for i, row in enumerate(title_rows):
                s.text(row, W / 2, 120 + i * title_size * 1.2, title_size, start=.1 + i * .05)
        target = spec.get('emphasis', '')
        key = next((i for i, it in enumerate(items) if target and target in (it['label'] + ' ' + it['value'])), len(items) - 1)
        if all(it['value'] for it in items):  # bar chart
            values = []
            for it in items:
                values.append(number_value(it['value']))
            gap = min(150, 640 / len(items))
            top = max(260, (H - len(items) * gap) / 2)
            biggest = max(values) or 1
            room = min(1000, W - 640 - 24 - 100 - max(measure(grouped(it['value'], language), s.head, 46) for it in items))  # value never leaves the frame
            for i, (it, v) in enumerate(zip(items, values)):
                y = top + i * gap
                at = .3 + i * .15 if i != key else E - md
                s.text(it['label'], 180, y + 30, 46, font=s.body, anchor='lm', start=.15 + i * .1, bold=False)
                length = room * v / biggest
                s.add('rect', {'w': [[at, 0], [at + md if i != key else E, length]]}, x=640, y=y, w=0, h=60, fill=s.accent if i == key else s.primary, radius=10, opacity=1)
                s.text(grouped(it['value'], language), 640 + length + 24, y + 30, 46, anchor='lm', start=(at + md) if i != key else E, fill=s.accent if i == key else s.fg)
            s.sound('hit', E)
        else:  # versus
            a, b = items[0], items[1]
            for i, (it, x) in enumerate(((a, W * .27), (b, W * .73))):
                hl = i == key
                s.add('rect', {'opacity': [[.1 + i * .15, 0], [.1 + i * .15 + md, .95]], 'dy': [[.1 + i * .15, 60], [.1 + i * .15 + md, 0]]},
                      x=x - 380, y=300, w=760, h=480, fill=mix(s.bg, s.primary, .12), radius=24, opacity=0, dy=60)
                fs, rows = fit(it['label'], s.head, 76, 660, 3, 44)
                for j, row in enumerate(rows):
                    s.text(row, x, 540 - (len(rows) - 1) * fs * .6 + j * fs * 1.2, fs, fill=s.accent if hl else s.fg, start=.25 + i * .15)
                if hl:
                    s.add('rect', {'opacity': [[E, 0], [E + .2, 1]]}, x=x - 380, y=770, w=760, h=10, fill=s.accent, opacity=0)
            s.add('circle', {'r': [[.4, 0], [.4 + md, 70]]}, cx=W / 2, cy=540, r=0, fill=s.accent, opacity=1)
            s.text('VS', W / 2, 540, 60, fill=s.bg, start=.4 + md * .5, dy=0)
            s.sound('hit', E)
    else:  # list
        items, title = d['items'], d.get('title')
        top = 200 if title else 260
        if title:
            title_size, title_rows = fit(title, s.head, 84, W - 400, 2, 38)
            for i, row in enumerate(title_rows):
                s.text(row, 200, top + i * title_size * 1.15, title_size, anchor='lm', start=.1 + i * .05, fill=s.primary)
            top += (len(title_rows) - 1) * title_size * 1.15
        target = spec.get('emphasis', '')
        key = next((i for i, it in enumerate(items) if target and target in it), len(items) - 1)
        gap = 175
        for i, it in enumerate(items):
            y = top + 160 + i * gap
            at = E if i == key else .3 + (E - .3) * i / max(1, key) if i < key else E + (i - key) * .35
            s.add('rect', s.appear(at, 0), x=200, y=y - 22, w=44, h=44, fill=s.accent if i == key else s.primary, radius=8, opacity=0)
            fs, rows = fit(it, s.body, 72, 1400, 1, 40)
            s.text(rows[0], 290, y, fs, font=s.body, anchor='lm', start=at, dy=30, fill=s.accent if i == key else s.fg, bold=i == key)
            s.sound('click', at)
    return s.result()


# ---- shared evaluation (mirrored in motion.tsx) ---------------------------------
def ease(name, t):
    t = min(1., max(0., t))
    if name == 'snappy': return 1 - (1 - t) ** 3
    if name == 'linear': return t
    if name == 'bounce':
        n, d = 7.5625, 2.75
        if t < 1 / d: return n * t * t
        if t < 2 / d: t -= 1.5 / d; return n * t * t + .75
        if t < 2.5 / d: t -= 2.25 / d; return n * t * t + .9375
        t -= 2.625 / d; return n * t * t + .984375
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def value_at(track, t, name):
    if t <= track[0][0]: return track[0][1]
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ease(name, (t - t0) / max(1e-6, t1 - t0))
    return track[-1][1]


def props_at(element, t, name):
    props = dict(element['props'])
    for key, track in element['tracks'].items():
        props[key] = value_at(track, t, name)
    return props


def counter_text(target, progress, language, from_year=False):
    """Count towards the spoken number, keeping its own format (grouping, %)."""
    m = NUMBER.search(target)
    if not m: return target
    digits = m.group(2)
    sep = next((c for c in digits if not c.isdigit() and digits.count(c) and re.search(r'\d' + re.escape(c) + r'\d{3}(?!\d)', digits)), '')
    dec = '' if sep else next((c for c in digits if c in ',.'), '')
    raw = digits.replace(sep, '') if sep else digits
    value = float(raw.replace(dec, '.')) if dec else float(raw)
    places = len(raw.split(dec)[1]) if dec else 0
    start = value - 30 if from_year else 0
    current = start + (value - start) * progress
    text = f'{current:.{places}f}'
    if dec: text = text.replace('.', dec)
    if sep:
        whole, _, frac = text.partition(dec or '\0')
        whole = f'{int(whole):,}'.replace(',', sep)
        text = whole + ((dec + frac) if frac else '')
    return target[:m.start(2)] + text + target[m.end(2):]


@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def _land():
    with gzip.open(Path(__file__).with_name('world_land_50m.json.gz'), 'rt', encoding='utf-8') as f:
        return json.load(f)['polygons']


def land(box=None):
    """Natural Earth 1:50m coastlines (~2 km). box=(west, south, east, north) keeps the polygons near the view."""
    polygons = _land()
    if not box:
        return [list(p) for p in polygons]
    west, south, east, north = box
    result = []
    for p in polygons:
        xs, ys = [x for x, _ in p], [y for _, y in p]
        if max(ys) < south or min(ys) > north: continue
        if any(max(xs) + shift >= west and min(xs) + shift <= east for shift in (-360, 0, 360)):
            result.append(p)
    return result


def map_view(props, zoom):
    """Equirectangular view box (lon/lat) for the map element at zoom 0..1."""
    span = props['span_from'] + (props['span_to'] - props['span_from']) * zoom
    height = span * H / W
    lat = max(-85 + height / 2, min(85 - height / 2, props['lat']))
    return props['lon'] - span / 2, lat + height / 2, span, height  # left lon, top lat, width, height


def map_box(props):
    """(west, south, east, north) covering every view the map element can show (zoom 0..1)."""
    boxes = [map_view(props, z) for z in (0, 1)]
    return (min(b[0] for b in boxes), min(b[1] - b[3] for b in boxes), max(b[0] + b[2] for b in boxes), max(b[1] for b in boxes))
