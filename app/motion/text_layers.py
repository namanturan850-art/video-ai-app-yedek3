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


def design(section, text, duration, variant=0):
    """(html, css). vurgular: statement with a bar (variant 0) or a centred card with rules (1).
    katmanlar: top-left title (0) or top-right title (1). Words enter one by one; the key word is underlined."""
    words, delays, settle = _words(text.strip())
    leave = _leave(duration)
    underline = f'{settle + .1:.2f}'
    font = 'font-family:Arial,Helvetica,sans-serif;color:#fff'
    word = ('.w{display:inline-block;opacity:0;animation:wordin .65s cubic-bezier(.2,.8,.2,1) both}'
            f'.hl{{background:linear-gradient({ACCENT},{ACCENT}) no-repeat 0 94%/0% .09em;color:#FFD9A8;animation:wordin .65s cubic-bezier(.2,.8,.2,1) both,sweep .7s ease-out {underline}s forwards}}'
            + delays)
    frames = ('@keyframes wordin{from{opacity:0;transform:translateY(34px);filter:blur(10px)}to{opacity:1;transform:none;filter:blur(0)}}'
              '@keyframes sweep{from{background-size:0% .09em}to{background-size:100% .09em}}'
              '@keyframes fade{from{opacity:1}to{opacity:0}}')
    if section == 'vurgular' and variant % 2 == 0:
        size = _size(text, 80)
        html = f"<div class='v'><span class='bar'></span><span class='t'>{words}</span></div>"
        css = (f".v{{position:absolute;left:150px;top:300px;width:1180px;padding-left:40px;{font};animation:fade .5s ease-in {leave}s forwards}}"
               f".bar{{position:absolute;left:0;top:8px;bottom:8px;width:9px;background:{ACCENT};box-shadow:0 0 24px rgba(242,140,40,.55);transform-origin:0 0;animation:bar .7s ease-out .05s both}}"
               f".t{{display:block;font-size:{size}px;font-weight:800;line-height:1.14;letter-spacing:-1px;text-shadow:0 4px 26px rgba(0,0,0,.7)}}"
               '@keyframes bar{from{transform:scaleY(0)}to{transform:scaleY(1)}}')
    elif section == 'vurgular':
        size = _size(text, 84)
        html = f"<div class='c'><span class='top'></span><span class='t'>{words}</span><span class='bottom'></span></div>"
        css = (f".c{{position:absolute;left:260px;top:330px;width:1400px;text-align:center;{font};animation:fade .5s ease-in {leave}s forwards}}"
               f".top,.bottom{{display:block;height:4px;margin:0 auto;width:0;background:{ACCENT};animation:rule .8s ease-out .1s both}}"
               ".top{margin-bottom:34px}.bottom{margin-top:34px;animation-delay:.3s}"
               f".t{{display:block;font-size:{size}px;font-weight:800;line-height:1.14;letter-spacing:-1px;text-shadow:0 4px 28px rgba(0,0,0,.75)}}"
               '@keyframes rule{from{width:0}to{width:260px}}')
    else:
        size = _size(text, 58)
        right = variant % 2 == 1
        html = f"<div class='k{' r' if right else ''}'><span class='line'></span><span class='t'>{words}</span></div>"
        place = 'right:0;text-align:right;padding:96px 120px 170px 0' if right else 'left:0;padding:96px 0 170px 120px'
        origin = '100% 0' if right else '0% 0'
        css = (f".k{{position:absolute;top:0;width:1500px;{place};{font};"
               f"background:radial-gradient(ellipse 85% 100% at {origin},rgba(8,10,14,.74),rgba(8,10,14,.42) 45%,rgba(8,10,14,0) 100%);"
               f"animation:kenter .6s ease-out both,fade .5s ease-in {leave}s forwards}}"
               f".line{{display:block;width:0;height:5px;margin-bottom:22px;background:{ACCENT};{'margin-left:auto;' if right else ''}animation:kline .8s ease-out .2s both}}"
               f".t{{display:block;width:1060px;{'margin-left:auto;' if right else ''}font-size:{size}px;font-weight:700;line-height:1.18;text-shadow:0 3px 18px rgba(0,0,0,.65)}}"
               '@keyframes kenter{from{opacity:0}to{opacity:1}}@keyframes kline{from{width:0}to{width:150px}}')
    return html, css + word + frames


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
