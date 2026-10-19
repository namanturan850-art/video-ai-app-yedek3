"""Give AI-proposed plain text a designed, animated look.

`vurgular` and `katmanlar` records that only carry a sentence would otherwise be drawn as flat
subtitle-like text. When Remotion is ready they become `html_katmanlari` records built from the fixed
designs below, so no model-written HTML is involved. Text is escaped; the result still goes through the
same sanitizer, preview, draft and approval path as any other HTML layer.

Content is derived locally from the sentence: it is split into a headline and a lighter second line, one
key word (a number, else the longest word) is highlighted, and a small category label is chosen from the
sentence's own vocabulary (nature, data, geography, history...) in the video's language. Nothing is added
that the sentence does not say, except that coarse label.
"""
from html import escape
import re

ACCENT = '#F5B84B'
BLUE = '#4DB3FF'
TEXT_KEYS = {'scene_id', 'start', 'end', 'object_id', 'text', 'effect'}
SECTION_TRACK = {'vurgular': 'emphasis', 'katmanlar': 'layers'}
# NamanBold/NamanLight are the user's own fonts when present (app/motion/fonts.py); Montserrat is bundled.
BOLD = "'NamanBold','Gilroy Bold','Gilroy',Montserrat,Arial,Helvetica,sans-serif"
LIGHT = "'NamanLight','Gilroy Light',Montserrat,Arial,Helvetica,sans-serif"
KICKERS = {
    'Bilimsel/doğa': {'tr': 'DOĞA', 'en': 'NATURE', 'de': 'NATUR', 'fr': 'NATURE', 'es': 'NATURALEZA'},
    'İnfografik': {'tr': 'VERİ', 'en': 'DATA', 'de': 'DATEN', 'fr': 'DONNÉES', 'es': 'DATOS'},
    'Coğrafya': {'tr': 'COĞRAFYA', 'en': 'GEOGRAPHY', 'de': 'GEOGRAFIE', 'fr': 'GÉOGRAPHIE', 'es': 'GEOGRAFÍA'},
    'Zaman çizelgesi': {'tr': 'TARİH', 'en': 'HISTORY', 'de': 'GESCHICHTE', 'fr': 'HISTOIRE', 'es': 'HISTORIA'},
    'Karşılaştırma': {'tr': 'KARŞILAŞTIRMA', 'en': 'COMPARISON', 'de': 'VERGLEICH', 'fr': 'COMPARAISON', 'es': 'COMPARACIÓN'},
    'Açıklayıcı': {'tr': 'SÜREÇ', 'en': 'PROCESS', 'de': 'PROZESS', 'fr': 'PROCESSUS', 'es': 'PROCESO'},
}
YEAR = re.compile(r'\b(1[0-9]{3}|20[0-9]{2})\b')
PIN = 'M12 2C8.1 2 5 5.1 5 9c0 5.3 7 13 7 13s7-7.7 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z'


def kicker_for(text, language):
    from app.animation.references import purposes
    found = purposes(text)
    for purpose in found:
        if purpose in KICKERS:
            return found, KICKERS[purpose].get(language) or KICKERS[purpose]['en']
    return found, ''


def _key_index(words):
    """The word to emphasise: a number if there is one, otherwise the longest word."""
    for i, w in enumerate(words):
        if any(c.isdigit() for c in w):
            return i
    return max(range(len(words)), key=lambda i: (len(words[i].strip('.,;:!?¿¡"\'')), -i))


def split_sentence(text):
    """(headline words, second-line words, key position) - key is ('h', i) or ('s', i)."""
    words = text.split()
    if len(words) <= 4:
        return words, [], ('h', _key_index(words))
    total = len(text)
    best, best_score = None, None
    for i in range(2, len(words) - 1):
        first = len(' '.join(words[:i]))
        score = abs(first - total / 2) - (total if words[i - 1][-1:] in ',;:.' else 0)
        if best_score is None or score < best_score:
            best, best_score = i, score
    head, sub = words[:best], words[best:]
    key = _key_index(words)
    return head, sub, (('h', key) if key < best else ('s', key - best))


def _span(word, index, key):
    return f"<span class='w w{index}{' hl' if key else ''}'>{escape(word, quote=True)}</span>"


def _leave(duration):
    return f'{max(1.0, duration - .5):.2f}'


def _hsize(text, base=76):
    n = len(text)
    return base if n <= 22 else round(base * .9) if n <= 34 else round(base * .8) if n <= 48 else round(base * .69) if n <= 64 else round(base * .58)


def _line_html(words, key, offset=0):
    return ' '.join(_span(w, offset + i, key == i) for i, w in enumerate(words))


def _delays(count, offset=0, start=.3, step=.1):
    step = min(step, 1.0 / max(1, count))
    return ''.join(f'.w{offset + i}{{animation-delay:{start + i * step:.2f}s}}' for i in range(count)), start + count * step


BASE_FRAMES = ('@keyframes wordin{from{opacity:0;transform:translateY(30px);filter:blur(9px)}to{opacity:1;transform:none;filter:blur(0)}}'
               '@keyframes fade{from{opacity:1}to{opacity:0}}'
               '@keyframes rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}'
               '@keyframes growy{from{transform:scaleY(0)}to{transform:scaleY(1)}}'
               '@keyframes show{from{opacity:0}to{opacity:1}}')
WORD = '.w{display:inline-block;opacity:0;animation:wordin .7s cubic-bezier(.2,.8,.2,1) both}'


def _kicker(label, color, line=460):
    if not label:
        return '', ''
    html = f"<span class='kick'>{escape(label, quote=True)}<span class='kl'></span></span>"
    css = (f".kick{{display:block;font-family:{LIGHT};font-weight:400;font-size:20px;letter-spacing:.38em;text-transform:uppercase;"
           f"color:rgba(255,255,255,.82);margin-bottom:18px;white-space:nowrap;opacity:0;animation:rise .6s ease-out .15s both}}"
           f".kl{{display:inline-block;vertical-align:middle;margin-left:26px;width:0;height:1px;background:{color};opacity:.9;"
           f"animation:klg .9s ease-out .4s forwards}}@keyframes klg{{from{{width:0}}to{{width:{line}px}}}}")
    return html, css


def _editorial(text, y, duration, label):
    head, sub, (where, k) = split_sentence(text)
    leave = _leave(duration)
    size = _hsize(' '.join(head))
    sub_size = max(30, round(size * .62))
    delays, settle = _delays(len(head), 0)
    kick_html, kick_css = _kicker(label, ACCENT)
    sub_html = f"<span class='sub'>{_line_html(sub, k if where == 's' else -1, 100)}</span>" if sub else ''
    sub_delays = _delays(len(sub), 100, settle + .05, .08)[0] if sub else ''
    html = (f"<div class='s'></div><div class='e'><span class='bar'></span>{kick_html}"
            f"<span class='hd'>{_line_html(head, k if where == 'h' else -1)}</span>{sub_html}</div>")
    css = (f".s{{position:absolute;left:0;top:0;width:1500px;height:1080px;"
           "background:radial-gradient(ellipse 80% 70% at 0% 40%,rgba(4,7,12,.78),rgba(4,7,12,.4) 50%,rgba(4,7,12,0) 100%);"
           f"animation:show .8s ease-out both,fade .5s ease-in {leave}s forwards}}"
           f".e{{position:absolute;left:150px;top:{y}px;width:1250px;padding-left:46px;color:#fff;animation:fade .5s ease-in {leave}s forwards}}"
           f".bar{{position:absolute;left:0;top:2px;bottom:6px;width:7px;background:{ACCENT};box-shadow:0 0 22px rgba(245,184,75,.45);transform-origin:0 0;animation:growy .8s ease-out .05s both}}"
           f".hd{{display:block;font-family:{LIGHT};font-weight:400;font-size:{size}px;line-height:1.12;text-shadow:0 3px 22px rgba(0,0,0,.7)}}"
           f".hl{{font-family:{BOLD};font-weight:700;color:{ACCENT}}}"
           f".sub{{display:block;margin-top:12px;font-family:{LIGHT};font-weight:300;font-size:{sub_size}px;line-height:1.2;color:rgba(255,255,255,.92);text-shadow:0 3px 20px rgba(0,0,0,.7)}}"
           + kick_css + WORD + delays + sub_delays)
    return html, css + BASE_FRAMES


def _glass(text, y, duration, label):
    head, sub, (where, k) = split_sentence(text)
    leave = _leave(duration)
    size = round(_hsize(' '.join(head), 70))
    sub_size = max(28, round(size * .6))
    delays, settle = _delays(len(head), 0)
    kick_html, kick_css = _kicker(label, BLUE, 380)
    sub_html = f"<span class='sub'>{_line_html(sub, k if where == 's' else -1, 100)}</span>" if sub else ''
    sub_delays = _delays(len(sub), 100, settle + .05, .08)[0] if sub else ''
    html = (f"<div class='g'><span class='c1'></span><span class='c2'></span>{kick_html}"
            f"<span class='hd'>{_line_html(head, k if where == 'h' else -1)}</span>{sub_html}<span class='ul'></span></div>")
    css = (f".g{{position:absolute;left:110px;top:{y}px;width:1090px;padding:54px 64px 56px 64px;color:#fff;"
           "background:linear-gradient(rgba(110,170,255,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(110,170,255,.06) 1px,transparent 1px),rgba(8,20,44,.68);"
           "background-size:48px 48px,48px 48px,auto;border:1px solid rgba(110,170,255,.34);"
           f"animation:gin .8s cubic-bezier(.2,.8,.2,1) both,fade .5s ease-in {leave}s forwards}}"
           f".c1,.c2{{position:absolute;width:46px;height:46px;transform:scale(0);animation:cin .6s ease-out .5s forwards}}"
           f".c1{{left:-26px;top:-26px;border-left:4px solid {BLUE};border-top:4px solid {BLUE};transform-origin:0 0}}"
           f".c2{{right:-26px;bottom:-26px;border-right:4px solid {BLUE};border-bottom:4px solid {BLUE};transform-origin:100% 100%}}"
           f".hd{{display:block;font-family:{BOLD};font-weight:700;font-size:{size}px;line-height:1.12;text-shadow:0 2px 14px rgba(0,0,0,.5)}}"
           f".hl{{color:{BLUE}}}"
           f".sub{{display:block;margin-top:10px;font-family:{LIGHT};font-weight:300;font-size:{sub_size}px;line-height:1.2;color:rgba(255,255,255,.92)}}"
           f".sub .w{{font-family:{LIGHT};font-weight:300}}"
           f".ul{{display:block;width:0;height:5px;margin-top:30px;background:{BLUE};box-shadow:0 0 18px rgba(77,179,255,.85);animation:ulg 1s ease-out {settle + .3:.2f}s forwards}}"
           "@keyframes gin{from{opacity:0;transform:translateX(-34px)}to{opacity:1;transform:none}}"
           "@keyframes cin{from{transform:scale(0)}to{transform:scale(1)}}"
           "@keyframes ulg{from{width:0}to{width:300px}}"
           + kick_css + WORD + delays + sub_delays)
    return html, css + BASE_FRAMES


def _place(title, sub, y, duration):
    leave = _leave(duration)
    size = 104 if len(title) <= 12 else 88 if len(title) <= 20 else 72
    sub_html = f"<span class='ps'>{escape(sub, quote=True)}</span><span class='pl'></span>" if sub else ''
    html = (f"<div class='s'></div><div class='p'><span class='pbar'></span><span class='row'>"
            f"<svg class='pin' width='68' height='68' viewBox='0 0 24 24'><path d='{PIN}' fill='{ACCENT}'/></svg>"
            f"<span class='pt'>{escape(title, quote=True)}</span></span>{sub_html}</div>")
    css = (".s{position:absolute;left:0;top:0;width:1500px;height:1080px;"
           "background:radial-gradient(ellipse 80% 70% at 0% 50%,rgba(4,7,12,.8),rgba(4,7,12,.42) 50%,rgba(4,7,12,0) 100%);"
           f"animation:show .8s ease-out both,fade .5s ease-in {leave}s forwards}}"
           f".p{{position:absolute;left:150px;top:{y}px;width:1100px;padding-left:38px;color:#fff;animation:fade .5s ease-in {leave}s forwards}}"
           f".pbar{{position:absolute;left:0;top:0;bottom:0;width:3px;background:{ACCENT};transform-origin:0 0;animation:growy .8s ease-out .05s both}}"
           ".row{display:block;white-space:nowrap}"
           ".pin{display:inline-block;vertical-align:middle;margin-right:26px;filter:drop-shadow(0 4px 12px rgba(0,0,0,.55));opacity:0;animation:drop .7s cubic-bezier(.3,1.5,.4,1) .2s both}"
           f".pt{{display:inline-block;vertical-align:middle;font-family:{BOLD};font-weight:700;font-size:{size}px;line-height:1.05;text-shadow:0 4px 26px rgba(0,0,0,.7);opacity:0;animation:wordin .8s cubic-bezier(.2,.8,.2,1) .35s both}}"
           f".ps{{display:block;margin:16px 0 0 94px;font-family:{LIGHT};font-weight:300;font-size:30px;letter-spacing:.42em;text-transform:uppercase;"
           "text-shadow:0 2px 14px rgba(0,0,0,.7);opacity:0;animation:rise .7s ease-out .8s both}"
           ".pl{display:block;margin:22px 0 0 94px;height:1px;width:0;background:rgba(255,255,255,.6);animation:plg 1s ease-out 1s forwards}"
           "@keyframes drop{from{opacity:0;transform:translateY(-34px) scale(.7)}to{opacity:1;transform:none}}"
           "@keyframes plg{from{width:0}to{width:440px}}")
    return html, css + BASE_FRAMES


def place_parts(text, found):
    """('Roma', 'año 1871') for 'Roma, año 1871'; ('Roma', '') for a short place name; else None."""
    parts = [p.strip() for p in re.split(r'[,–—]|\s-\s|:', text, maxsplit=1)]
    if len(parts) == 2 and parts[0] and parts[1] and len(parts[0].split()) <= 3 and len(parts[1].split()) <= 4 and (YEAR.search(parts[1]) or 'Coğrafya' in found):
        return parts[0], parts[1]
    if 'Coğrafya' in found and len(text.split()) <= 3 and text.strip()[:1].isupper():
        return text.strip(), ''
    return None


def _marker(text, y, duration):
    """Highlighter pen over the key word."""
    words = text.split()
    key = _key_index(words)
    delays, settle = _delays(len(words), 0)
    size = _hsize(text, 74)
    html = f"<div class='m'><span class='t'>{_line_html(words, key)}</span></div>"
    css = (f".m{{position:absolute;left:150px;top:{y}px;width:1250px;color:#fff;animation:fade .5s ease-in {_leave(duration)}s forwards}}"
           f".t{{display:block;font-family:{BOLD};font-weight:700;font-size:{size}px;line-height:1.2;text-shadow:0 4px 24px rgba(0,0,0,.65)}}"
           "@keyframes paint{0%{background-size:0% 82%;color:#fff}45%{color:#fff}100%{background-size:100% 82%;color:#15171C}}"
           f".hl{{background:linear-gradient(#FFD23F,#FFD23F) no-repeat 0 60%/0% 82%;animation:wordin .7s cubic-bezier(.2,.8,.2,1) both,paint .6s cubic-bezier(.4,0,.2,1) {settle + .05:.2f}s forwards}}"
           + WORD + delays)
    return html, css + BASE_FRAMES


def _focus(text, y, duration):
    """Cinematic title: soft and wide at first, then pulls into focus."""
    size = _hsize(text, 84)
    html = f"<div class='f'><span class='t'>{escape(text, quote=True)}</span><span class='u'></span></div>"
    css = (f".f{{position:absolute;left:210px;top:{y}px;width:1500px;text-align:center;color:#fff;animation:fade .6s ease-in {_leave(duration)}s forwards}}"
           f".t{{display:block;font-family:{BOLD};font-weight:700;font-size:{size}px;line-height:1.15;text-shadow:0 6px 34px rgba(0,0,0,.75);animation:pull 1.5s cubic-bezier(.2,.7,.2,1) both}}"
           f".u{{display:block;height:4px;width:0;margin:30px auto 0;background:{ACCENT};animation:rule2 .9s ease-out 1.1s both}}"
           "@keyframes pull{from{opacity:0;letter-spacing:.35em;filter:blur(22px);transform:scale(1.12)}to{opacity:1;letter-spacing:0;filter:blur(0);transform:none}}"
           "@keyframes rule2{from{width:0}to{width:220px}}")
    return html, css + BASE_FRAMES


def _teletype(text, y, duration, label):
    """Typed out letter by letter with a caret; one line, fixed-width letters."""
    n = len(text)
    size = max(30, min(58, int(1500 / (n * .62))))
    seconds = max(.9, min(2.6, n * .045))
    kick_html, kick_css = _kicker(label, ACCENT, 300)
    html = f"<div class='s'></div><div class='ty'>{kick_html}<span class='tp'>{escape(text, quote=True)}</span></div>"
    css = (".s{position:absolute;left:0;top:0;width:1500px;height:1080px;"
           "background:radial-gradient(ellipse 80% 70% at 0% 40%,rgba(4,7,12,.78),rgba(4,7,12,.4) 50%,rgba(4,7,12,0) 100%);"
           f"animation:show .6s ease-out both,fade .5s ease-in {_leave(duration)}s forwards}}"
           f".ty{{position:absolute;left:150px;top:{y}px;width:1500px;color:#fff;animation:fade .5s ease-in {_leave(duration)}s forwards}}"
           f".tp{{display:block;overflow:hidden;white-space:nowrap;width:0;border-right:6px solid {ACCENT};font-family:Consolas,'Courier New',monospace;"
           f"font-size:{size}px;font-weight:700;line-height:1.3;text-shadow:0 3px 18px rgba(0,0,0,.65);"
           f"animation:type {seconds:.2f}s steps({n},end) .6s forwards,caret .5s steps(2,start) infinite}}"
           f"@keyframes type{{from{{width:0}}to{{width:{n}ch}}}}"
           f"@keyframes caret{{from{{border-right-color:{ACCENT}}}to{{border-right-color:transparent}}}}"
           + kick_css)
    return html, css + BASE_FRAMES


VARIANTS = {'vurgular': ('editorial', 'glass', 'marker', 'focus'),
            'katmanlar': ('editorial', 'glass', 'teletype')}
POSITION = {'vurgular': 300, 'katmanlar': 150}


def design(section, text, duration, variant=0, language='en'):
    """(html, css) for one sentence. Variants rotate so consecutive proposals do not look identical;
    a place/date sentence ('Roma, año 1871') always gets the pin card."""
    text = ' '.join(text.split())
    found, label = kicker_for(text, language)
    y = POSITION[section]
    place = place_parts(text, found)
    if place:
        return _place(place[0], place[1], y, duration)
    names = VARIANTS[section]
    name = names[variant % len(names)]
    if name == 'teletype' and len(text) > 56:
        name = 'editorial'
    if name == 'editorial':
        return _editorial(text, y, duration, label)
    if name == 'glass':
        return _glass(text, y + (30 if section == 'vurgular' else 0), duration, label)
    if name == 'marker':
        return _marker(text, y, duration)
    if name == 'focus':
        return _focus(text, y + 80, duration)
    return _teletype(text, y, duration, label)


def convert(payload, scenes, max_seconds, language='en', budget=None):
    """Move eligible plain-text records of `payload` into html_katmanlari. Returns how many moved.
    `budget` caps how many may be added (a plan holds at most MAX_LAYERS HTML layers); the rest stay plain text."""
    moved = 0
    if budget is None:
        from app.motion.html_layer import MAX_LAYERS
        budget = MAX_LAYERS - len([x for x in payload.get('html_katmanlari', []) if isinstance(x, dict)])
    for section, track in SECTION_TRACK.items():
        items = payload.get(section)
        if not isinstance(items, list):
            continue
        keep = []
        for item in items:
            scene = scenes.get(item.get('scene_id')) if isinstance(item, dict) else None
            text = item.get('text') if isinstance(item, dict) else None
            if moved >= budget:
                keep.append(item)
                continue
            if (scene is None or not isinstance(text, str) or not text.strip() or len(text) > 160 or set(item) - TEXT_KEYS
                    or item.get('effect') not in (None, 'none') or scene.get('locked') or scene.get('start') is None):
                keep.append(item)
                continue
            start, end = item.get('start', scene['start']), item.get('end', scene['end'])
            if (type(start) not in (int, float) or type(end) not in (int, float) or not scene['start'] <= start < end <= scene['end']
                    or end - start > max_seconds or end - start < 1.2):
                keep.append(item)
                continue
            html, css = design(section, text, end - start, moved, language)
            record = {'scene_id': item['scene_id'], 'start': start, 'end': end, 'track': track, 'html': html, 'css': css}
            if 'object_id' in item:
                record['object_id'] = item['object_id']
            payload.setdefault('html_katmanlari', []).append(record)
            moved += 1
        payload[section] = keep
    return moved
