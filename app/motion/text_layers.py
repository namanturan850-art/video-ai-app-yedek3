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


def _exit(duration):
    delay = max(.8, duration - .5)
    return f'{delay:.2f}'


def design(section, text, duration):
    """(html, css) for one sentence. `vurgular`: large statement with a growing bar. `katmanlar`: top-left title."""
    safe = escape(text.strip(), quote=True)
    leave = _exit(duration)
    if section == 'vurgular':
        size = _size(text, 80)
        html = f"<div class='v'><span class='bar'></span><span class='t'>{safe}</span></div>"
        css = (f".v{{position:absolute;left:150px;top:300px;width:1180px;padding-left:40px;font-family:Arial,Helvetica,sans-serif;color:#fff;"
               f"animation:vleave .5s ease-in {leave}s forwards}}"
               f".bar{{position:absolute;left:0;top:8px;bottom:8px;width:9px;background:{ACCENT};box-shadow:0 0 24px rgba(242,140,40,.55);"
               f"transform-origin:0 0;animation:vbar .7s ease-out .05s both}}"
               f".t{{display:block;font-size:{size}px;font-weight:800;line-height:1.12;letter-spacing:-1px;text-shadow:0 4px 26px rgba(0,0,0,.7);"
               f"animation:vtext .75s ease-out .25s both}}"
               "@keyframes vbar{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
               "@keyframes vtext{from{opacity:0;transform:translateX(-36px)}to{opacity:1;transform:none}}"
               "@keyframes vleave{from{opacity:1}to{opacity:0}}")
    else:
        size = _size(text, 58)
        html = f"<div class='k'><span class='line'></span><span class='t'>{safe}</span></div>"
        css = (f".k{{position:absolute;left:0;top:0;width:1500px;padding:96px 0 170px 120px;font-family:Arial,Helvetica,sans-serif;color:#fff;"
               f"background:radial-gradient(ellipse 85% 100% at 0% 0%,rgba(8,10,14,.74),rgba(8,10,14,.42) 45%,rgba(8,10,14,0) 100%);"
               f"animation:kenter .6s ease-out both,kleave .5s ease-in {leave}s forwards}}"
               f".line{{display:block;width:0;height:5px;margin-bottom:22px;background:{ACCENT};animation:kline .8s ease-out .2s both}}"
               f".t{{display:block;width:1060px;font-size:{size}px;font-weight:700;line-height:1.16;text-shadow:0 3px 18px rgba(0,0,0,.65);"
               f"animation:ktext .7s ease-out .4s both}}"
               "@keyframes kenter{from{opacity:0}to{opacity:1}}"
               "@keyframes kline{from{width:0}to{width:150px}}"
               "@keyframes ktext{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}"
               "@keyframes kleave{from{opacity:1}to{opacity:0}}")
    return html, css


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
            html, css = design(section, text, end - start)
            record = {'scene_id': item['scene_id'], 'start': start, 'end': end, 'track': track, 'html': html, 'css': css}
            if 'object_id' in item:
                record['object_id'] = item['object_id']
            payload.setdefault('html_katmanlari', []).append(record)
            moved += 1
        payload[section] = keep
    return moved
