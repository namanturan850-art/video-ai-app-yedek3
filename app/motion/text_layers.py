"""Give AI-proposed plain text a designed, animated look.

`vurgular` and `katmanlar` records that only carry a sentence would otherwise be drawn as flat
subtitle-like text. When Remotion is ready they become `html_katmanlari` records built from the two
fixed designs below, so no model-written HTML is involved. Text is escaped; the result still goes
through the same sanitizer, preview, draft and approval path as any other HTML layer.
"""
from html import escape

ACCENT = '#F28C28'
TEXT_KEYS = {'scene_id', 'start', 'end', 'object_id', 'text', 'effect'}
SECTION_TRACK = {'vurgular': 'emphasis', 'katmanlar': 'layers'}


def _size(text, base):
    n = len(text)
    return base if n <= 28 else round(base * .85) if n <= 50 else round(base * .72) if n <= 80 else round(base * .6) if n <= 120 else round(base * .5)


def _leave(duration):
    return f'{max(1.0, duration - .5):.2f}'


def _key_index(words):
    """The word to underline: a number if there is one, otherwise the longest word."""
    for i, w in enumerate(words):
        if any(c.isdigit() for c in w):
            return i
    return max(range(len(words)), key=lambda i: (len(words[i].strip('.,;:!?¿¡"\'')), -i))


def _words(text):
    words = text.split()
    key = _key_index(words)
    step = min(.09, 1.0 / max(1, len(words)))
    html = ' '.join(f"<span class='w w{i}{' hl' if i == key else ''}'>{escape(w, quote=True)}</span>" for i, w in enumerate(words))
    delays = ''.join(f'.w{i}{{animation-delay:{.3 + i * step:.2f}s}}' for i in range(len(words)))
    return html, delays, .3 + len(words) * step


# Gilroy is a commercial font, so it is not bundled. If the user installs Gilroy Bold in Windows the
# layers use it; otherwise Montserrat (similar geometric look) or Arial is used.
FAMILY = "Gilroy,'Gilroy Bold','Gilroy-Bold',Montserrat,Arial,Helvetica,sans-serif"
FONT = f'font-family:{FAMILY};color:#fff'
FRAMES = ('@keyframes wordin{from{opacity:0;transform:translateY(34px);filter:blur(10px)}to{opacity:1;transform:none;filter:blur(0)}}'
          '@keyframes sweep{from{background-size:0% .09em}to{background-size:100% .09em}}'
          '@keyframes fade{from{opacity:1}to{opacity:0}}')


def _word_css(delays, underline):
    return ('.w{display:inline-block;opacity:0;animation:wordin .65s cubic-bezier(.2,.8,.2,1) both}'
            f'.hl{{background:linear-gradient({ACCENT},{ACCENT}) no-repeat 0 94%/0% .09em;color:#FFD9A8;'
            f'animation:wordin .65s cubic-bezier(.2,.8,.2,1) both,sweep .7s ease-out {underline}s forwards}}' + delays)


def _statement(text, words, leave):
    size = _size(text, 80)
    return (f"<div class='v'><span class='bar'></span><span class='t'>{words}</span></div>",
            f".v{{position:absolute;left:150px;top:300px;width:1180px;padding-left:40px;{FONT};animation:fade .5s ease-in {leave}s forwards}}"
            f".bar{{position:absolute;left:0;top:8px;bottom:8px;width:9px;background:{ACCENT};box-shadow:0 0 24px rgba(242,140,40,.55);transform-origin:0 0;animation:bar .7s ease-out .05s both}}"
            f".t{{display:block;font-size:{size}px;font-weight:700;line-height:1.14;letter-spacing:-1px;text-shadow:0 4px 26px rgba(0,0,0,.7)}}"
            '@keyframes bar{from{transform:scaleY(0)}to{transform:scaleY(1)}}')


def _card(text, words, leave):
    size = _size(text, 84)
    return (f"<div class='c'><span class='top'></span><span class='t'>{words}</span><span class='bottom'></span></div>",
            f".c{{position:absolute;left:260px;top:330px;width:1400px;text-align:center;{FONT};animation:fade .5s ease-in {leave}s forwards}}"
            f".top,.bottom{{display:block;height:4px;margin:0 auto;width:0;background:{ACCENT};animation:rule .8s ease-out .1s both}}"
            ".top{margin-bottom:34px}.bottom{margin-top:34px;animation-delay:.3s}"
            f".t{{display:block;font-size:{size}px;font-weight:700;line-height:1.14;letter-spacing:-1px;text-shadow:0 4px 28px rgba(0,0,0,.75)}}"
            '@keyframes rule{from{width:0}to{width:260px}}')


def _title(text, words, leave, right=False):
    size = _size(text, 58)
    place = 'right:0;text-align:right;padding:96px 120px 170px 0' if right else 'left:0;padding:96px 0 170px 120px'
    origin = '100% 0' if right else '0% 0'
    push = 'margin-left:auto;' if right else ''
    return (f"<div class='k'><span class='line'></span><span class='t'>{words}</span></div>",
            f".k{{position:absolute;top:0;width:1500px;{place};{FONT};"
            f"background:radial-gradient(ellipse 85% 100% at {origin},rgba(8,10,14,.74),rgba(8,10,14,.42) 45%,rgba(8,10,14,0) 100%);"
            f"animation:kenter .6s ease-out both,fade .5s ease-in {leave}s forwards}}"
            f".line{{display:block;width:0;height:5px;margin-bottom:22px;background:{ACCENT};{push}animation:kline .8s ease-out .2s both}}"
            f".t{{display:block;width:1060px;{push}font-size:{size}px;font-weight:700;line-height:1.18;text-shadow:0 3px 18px rgba(0,0,0,.65)}}"
            '@keyframes kenter{from{opacity:0}to{opacity:1}}@keyframes kline{from{width:0}to{width:150px}}')


def _marker(text, words, leave, settle):
    """Highlighter pen: the key word is painted over with a marker stroke."""
    size = _size(text, 76)
    paint = f'{settle + .05:.2f}'
    return (f"<div class='m'><span class='t'>{words}</span></div>",
            f".m{{position:absolute;left:150px;top:310px;width:1250px;{FONT};animation:fade .5s ease-in {leave}s forwards}}"
            f".t{{display:block;font-size:{size}px;font-weight:700;line-height:1.2;text-shadow:0 4px 24px rgba(0,0,0,.65)}}"
            f".hl{{background:linear-gradient(#FFD23F,#FFD23F) no-repeat 0 60%/0% 82%;color:#fff;"
            f"animation:wordin .65s cubic-bezier(.2,.8,.2,1) both,paint .6s cubic-bezier(.4,0,.2,1) {paint}s forwards}}"
            '@keyframes paint{0%{background-size:0% 82%;color:#fff}45%{color:#fff}100%{background-size:100% 82%;color:#15171C}}')


def _block(text, leave):
    """Colour block wipes across, uncovering the sentence behind it."""
    size = _size(text, 74)
    safe = escape(text.strip(), quote=True)
    return (f"<div class='b'><span class='rv'><span class='rt'>{safe}</span><span class='rb'></span></span></div>",
            f".b{{position:absolute;left:150px;top:320px;width:1300px;{FONT};animation:fade .5s ease-in {leave}s forwards}}"
            ".rv{display:inline-block;position:relative;overflow:hidden;max-width:1300px;padding:6px 6px 10px 0}"
            f".rt{{display:block;font-size:{size}px;font-weight:700;line-height:1.16;text-shadow:0 4px 24px rgba(0,0,0,.65);opacity:0;animation:show .01s linear .5s forwards}}"
            f".rb{{position:absolute;left:0;top:0;right:0;bottom:0;background:{ACCENT};transform:translateX(-101%);animation:pass 1.1s cubic-bezier(.7,0,.2,1) .1s forwards}}"
            '@keyframes pass{0%{transform:translateX(-101%)}45%{transform:translateX(0)}100%{transform:translateX(101%)}}'
            '@keyframes show{from{opacity:0}to{opacity:1}}')


def _focus(text, leave):
    """Cinematic title: soft and wide at first, then pulls into focus."""
    size = _size(text, 86)
    safe = escape(text.strip(), quote=True)
    return (f"<div class='f'><span class='t'>{safe}</span><span class='u'></span></div>",
            f".f{{position:absolute;left:210px;top:380px;width:1500px;text-align:center;{FONT};animation:fade .6s ease-in {leave}s forwards}}"
            f".t{{display:block;font-size:{size}px;font-weight:700;line-height:1.15;text-shadow:0 6px 34px rgba(0,0,0,.75);animation:pull 1.5s cubic-bezier(.2,.7,.2,1) both}}"
            f".u{{display:block;height:4px;width:0;margin:30px auto 0;background:{ACCENT};animation:rule2 .9s ease-out 1.1s both}}"
            '@keyframes pull{from{opacity:0;letter-spacing:.35em;filter:blur(22px);transform:scale(1.12)}to{opacity:1;letter-spacing:0;filter:blur(0);transform:none}}'
            '@keyframes rule2{from{width:0}to{width:220px}}')


def _teletype(text, leave):
    """Typed out letter by letter with a caret; one line, fixed-width letters."""
    n = len(text.strip())
    size = max(30, min(58, int(1500 / (n * .62))))
    safe = escape(text.strip(), quote=True)
    seconds = max(.9, min(2.6, n * .045))
    return (f"<div class='ty'><span class='line'></span><span class='tp'>{safe}</span></div>",
            f".ty{{position:absolute;left:0;top:0;width:1700px;padding:96px 0 170px 120px;{FONT};"
            "background:radial-gradient(ellipse 85% 100% at 0% 0%,rgba(8,10,14,.74),rgba(8,10,14,.42) 45%,rgba(8,10,14,0) 100%);"
            f"animation:kenter .5s ease-out both,fade .5s ease-in {leave}s forwards}}"
            f".line{{display:block;width:0;height:5px;margin-bottom:22px;background:{ACCENT};animation:kline .8s ease-out .1s both}}"
            f".tp{{display:block;overflow:hidden;white-space:nowrap;width:0;border-right:6px solid {ACCENT};font-family:Consolas,'Courier New',monospace;"
            f"font-size:{size}px;font-weight:700;line-height:1.3;text-shadow:0 3px 18px rgba(0,0,0,.65);"
            f"animation:type {seconds:.2f}s steps({n},end) .5s forwards,caret .5s steps(2,start) infinite}}"
            f"@keyframes type{{from{{width:0}}to{{width:{n}ch}}}}"
            f"@keyframes caret{{from{{border-right-color:{ACCENT}}}to{{border-right-color:transparent}}}}"
            '@keyframes kenter{from{opacity:0}to{opacity:1}}@keyframes kline{from{width:0}to{width:150px}}')


VARIANTS = {'vurgular': ('statement', 'card', 'marker', 'block', 'focus'),
            'katmanlar': ('title', 'title_right', 'teletype')}


def design(section, text, duration, variant=0):
    """(html, css) for one sentence. Variants rotate so consecutive proposals do not look identical.
    vurgular: statement with bar, centred card, highlighter, colour-block wipe, focus pull.
    katmanlar: top-left title, top-right title, teletype."""
    text = text.strip()
    names = VARIANTS[section]
    name = names[variant % len(names)]
    if name == 'teletype' and len(text) > 56:
        name = 'title'
    leave = _leave(duration)
    words, delays, settle = _words(text)
    if name == 'block':
        html, css = _block(text, leave)
        return html, css + FRAMES
    if name == 'focus':
        html, css = _focus(text, leave)
        return html, css + FRAMES
    if name == 'teletype':
        html, css = _teletype(text, leave)
        return html, css + FRAMES
    builders = {'statement': lambda: _statement(text, words, leave), 'card': lambda: _card(text, words, leave),
                'marker': lambda: _marker(text, words, leave, settle), 'title': lambda: _title(text, words, leave),
                'title_right': lambda: _title(text, words, leave, True)}
    html, css = builders[name]()
    return html, _word_css(delays, f'{settle + .1:.2f}') + css + FRAMES


def convert(payload, scenes, max_seconds):
    """Move eligible plain-text records of `payload` into html_katmanlari. Returns how many moved."""
    moved = 0
    for section, track in SECTION_TRACK.items():
        items = payload.get(section)
        if not isinstance(items, list):
            continue
        keep = []
        for item in items:
            scene = scenes.get(item.get('scene_id')) if isinstance(item, dict) else None
            text = item.get('text') if isinstance(item, dict) else None
            if (scene is None or not isinstance(text, str) or not text.strip() or len(text) > 160 or set(item) - TEXT_KEYS
                    or item.get('effect') not in (None, 'none') or scene.get('locked') or scene.get('start') is None):
                keep.append(item)
                continue
            start, end = item.get('start', scene['start']), item.get('end', scene['end'])
            if (type(start) not in (int, float) or type(end) not in (int, float) or not scene['start'] <= start < end <= scene['end']
                    or end - start > max_seconds or end - start < 1.2):
                keep.append(item)
                continue
            html, css = design(section, text, end - start, moved)
            record = {'scene_id': item['scene_id'], 'start': start, 'end': end, 'track': track, 'html': html, 'css': css}
            if 'object_id' in item:
                record['object_id'] = item['object_id']
            payload.setdefault('html_katmanlari', []).append(record)
            moved += 1
        payload[section] = keep
    return moved
