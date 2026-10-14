"""Three layouts per infographic template (no AI, both engines).

A layout re-arranges the renderer-neutral scene built by templates.py, so the
local renderer (raster.py) and OpenMontage (motion.tsx) draw the same frame:

    card templates     0 centre · 1 framed panel · 2 side band + content
    map templates      0 subject in the centre · 1 subject left · 2 subject right
    picture templates  0 labels as designed · 1 labels low · 2 labels elsewhere

spec['layout'] (0, 1, 2) picks one; missing = 0 (the original look, so old
clips keep their cache key). The media director varies it so two infographics
in a row never share template *and* layout.
"""
from copy import deepcopy

W, H = 1920, 1080
COUNT = 3
MAP_TEMPLATES = ('map', 'route', 'empire', 'zoom')
PICTURE_TEMPLATES = ('mark', 'beforeafter')
MOMENTS = ('intro', 'outro', 'endscreen')  # fixed designs: no alternative arrangements
NAMES = {'card': ('Orta', 'Panel', 'Yan şerit'), 'map': ('Konu ortada', 'Konu solda', 'Konu sağda'),
         'picture': ('Etiket üstte', 'Etiket altta', 'Etiket yanda')}
GLYPH = {'stat': '#', 'ratio': '%', 'icons': '#', 'quote': '“', 'fact': '?'}
POS_X, POS_Y = ('x', 'cx', 'x1', 'x2'), ('y', 'cy', 'y1', 'y2')
LENGTH = ('w', 'h', 'r', 'size', 'radius', 'width', 'dy')


def family(template):
    return 'map' if template in MAP_TEMPLATES else 'picture' if template in PICTURE_TEMPLATES else 'card'


def layout_of(spec):
    value = spec.get('layout', 0) if isinstance(spec, dict) else 0
    return value if type(value) is int and 0 <= value < COUNT else 0


def label(spec):
    return NAMES[family(spec['template'])][layout_of(spec)]


def _map(element, fn):
    """Apply fn(key, value) to every static prop and every keyframe value."""
    p = element['props']
    for key in list(p):
        if isinstance(p[key], (int, float)) and not isinstance(p[key], bool):
            p[key] = fn(key, p[key])
    for key, track in element.get('tracks', {}).items():
        element['tracks'][key] = [[t, fn(key, v)] for t, v in track]


def _affine(element, k, ox, oy):
    def fn(key, v):
        if key in POS_X: return v * k + ox
        if key in POS_Y: return v * k + oy
        if key in LENGTH: return v * k
        return v
    _map(element, fn)


def _shift(element, dx=0., dy=0.):
    _map(element, lambda key, v: v + dx if key in POS_X else v + dy if key in POS_Y else v)


def _text_width(element):
    from app.motion.templates import measure
    p = element['props']
    try: return measure(str(p.get('text', '')), p.get('font'), p.get('size', 40), p.get('bold', True))
    except Exception: return len(str(p.get('text', ''))) * p.get('size', 40) * .55


def _keep_inside(element):
    """After a sideways move, a label never leaves the frame (rects 40 px, texts 80 px margin: a label box is text + 80)."""
    p = element['props']
    if element['type'] == 'rect' and 'w' in p and p['w'] < W - 80:
        dx = min(max(p['x'], 40), W - 40 - p['w']) - p['x']
    elif element['type'] == 'text' and p.get('anchor', 'mm') == 'mm':
        half = _text_width(element) / 2
        dx = min(max(p['x'], 80 + half), W - 80 - half) - p['x']
    else:
        return
    if dx: _shift(element, dx)


def _appear(at, end=1.):
    return {'opacity': [[at, 0], [at + .4, end]]}


def _card(scene, spec, kit, layout):
    from app.motion.templates import mix
    pal = kit['palette']
    base, content = scene['elements'][:1], scene['elements'][1:]
    if layout == 1:  # framed panel with an accent bar
        k = .84
        ox, oy = (W - k * W) / 2, (H - k * H) / 2
        deco = [{'type': 'rect', 'props': {'x': ox - 24, 'y': oy - 24, 'w': k * W + 48, 'h': k * H + 48, 'fill': mix(pal['background'], pal['primary'], .1),
                                           'radius': 40, 'opacity': 0}, 'tracks': _appear(0.)},
                {'type': 'rect', 'props': {'x': ox - 24, 'y': oy - 24, 'w': 0, 'h': 12, 'fill': pal['accent'], 'opacity': 1},
                 'tracks': {'w': [[.1, 0], [.6, k * W + 48]]}}]
    else:  # side band (accent stripe + template glyph) and the content beside it
        band, k = W * .24, .74
        ox, oy = band + (W - band - k * W) / 2, (H - k * H) / 2
        deco = [{'type': 'rect', 'props': {'x': -band, 'y': 0, 'w': band, 'h': H, 'fill': mix(pal['background'], pal['primary'], .16), 'opacity': 1},
                 'tracks': {'x': [[0, -band], [.45, 0]]}},
                {'type': 'rect', 'props': {'x': band - 12, 'y': 0, 'w': 12, 'h': 0, 'fill': pal['accent'], 'opacity': 1},
                 'tracks': {'h': [[.15, 0], [.6, H]]}}]
        glyph = GLYPH.get(spec['template'])
        if glyph:
            from app.channels import FONTS
            deco.append({'type': 'text', 'props': {'text': glyph, 'x': band / 2, 'y': H / 2, 'size': 260, 'font': FONTS[kit.get('heading_font', 'montserrat')][1],
                                                   'fill': pal['accent'], 'anchor': 'mm', 'bold': True, 'opacity': 0, 'dy': 0}, 'tracks': _appear(.15)})
        else:  # three accent dots
            deco += [{'type': 'circle', 'props': {'cx': band / 2, 'cy': H / 2 + (i - 1) * 90, 'r': 0, 'fill': pal['accent'], 'opacity': 1},
                      'tracks': {'r': [[.2 + i * .1, 0], [.5 + i * .1, 22]]}} for i in range(3)]
    for element in content:
        _affine(element, k, ox, oy)
    scene['elements'] = base + deco + content


def _maps(scene, spec, layout):
    side = 1 if layout == 1 else -1  # 1: subject on the left third, -1: on the right third
    wide = spec['template'] in ('route', 'empire')  # a whole route/area: zoom out a little so it still fits
    for element in scene['elements']:
        if element['type'] == 'map':
            p = element['props']
            if wide:
                p['span_to'] = min(330., p['span_to'] * 1.4)
            p['lon'] = p['lon'] + side * (.15 if wide else .2) * p['span_to']
    if wide: return  # everything sits on the map (geo elements follow it); titles stay put
    dx = -side * .2 * W
    for element in scene['elements'][1:]:
        if element['type'] in ('map', 'image') or element['type'].startswith('geo'): continue
        _shift(element, dx)
        _keep_inside(element)


def _pictures(scene, spec, layout):
    elements = scene['elements']
    if spec['template'] == 'mark':
        arrow = next((e for e in elements if e['type'] == 'arrow'), None)
        box = next((e for e in elements if e['type'] == 'rect' and e is not elements[0]), None)
        text = next((e for e in elements if e['type'] == 'text'), None)
        ring = next((e for e in elements if e['type'] == 'ring'), None)
        if not (arrow and box and text and ring): return
        b = box['props']
        x0, y0 = (80, H - 60 - b['h']) if layout == 1 else (W - 80 - b['w'], 60) if ring['props']['cx'] < W / 2 else (80, 60)
        dx, dy = x0 - b['x'], y0 - b['y']
        _shift(box, dx, dy); _shift(text, dx, dy)
        a, r = arrow['props'], ring['props']
        below = r['cy'] < y0  # the label is below the ring: the arrow starts at its top edge
        a['x1'], a['y1'] = x0 + b['w'] / 2, (y0 if below else y0 + b['h'])
        a['x2'], a['y2'] = r['cx'], r['cy'] + (r['r'] * .8 + 14 if below else -r['r'] * .8 - 14)
    else:  # before/after: the two label groups (box + two texts each) move together
        dy = (H - 230) if layout == 1 else (H / 2 - 115)
        for element in elements[1:]:
            if element['type'] in ('rect', 'text'):
                _shift(element, 0, dy)


def arrange(scene, spec, kit):
    layout = layout_of(spec)
    if not layout or spec['template'] in MOMENTS or any(e['type'] == 'relief' for e in scene['elements']):
        return scene  # a relief/satellite map frames itself
    scene = deepcopy(scene)
    kind = family(spec['template'])
    if kind == 'card': _card(scene, spec, kit, layout)
    elif kind == 'map': _maps(scene, spec, layout)
    else: _pictures(scene, spec, layout)
    scene['layout'] = layout
    return scene


def pick(previous, following, template):
    """Layout for a new infographic between its neighbours ((template, layout) or None):
    never the same template + layout as the infographic before or after it."""
    taken = {n[1] for n in (previous, following) if n and n[0] == template}
    if previous and previous[0] != template:
        taken.add(previous[1])  # a different template still gets a different arrangement where possible
    start = (previous[1] + 1) % COUNT if previous else 0
    for step in range(COUNT):
        layout = (start + step) % COUNT
        if layout not in taken: return layout
    return start  # unreachable: at most two of the three layouts are taken
