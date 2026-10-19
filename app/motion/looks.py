"""Variety for infographic cards, no AI and no new fields.

Every card used the same rise-from-below entrance (the channel's accent colour stays: it is the brand), so a long
video felt memorised.  The look is chosen from the content of the spec (the same spec always
gives the same clip, so cached clips stay valid) and only changes values both engines already
draw: the direction/size of the entrance and a small stagger.
"""
import hashlib
import json
from copy import deepcopy

SKIP = ('map', 'route', 'empire', 'zoom', 'mark', 'beforeafter', 'intro', 'outro', 'endscreen', 'html', 'documentary')
RISE = (1., -1., 2., -2., .45, 0., 1.4)  # entrance: from below / above / far / short / pure fade
STAGGER = (0., .04, .08, 0., .06, .1)


def seed_of(spec):
    text = json.dumps({k: v for k, v in spec.items() if k != 'layout'}, sort_keys=True, default=str)
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def look_of(spec):
    s = seed_of(spec)
    return (s >> 4) % len(RISE), (s >> 8) % len(STAGGER)


def restyle(scene, spec, kit):
    if spec.get('template') in SKIP or any(e['type'] in ('relief', 'map') for e in scene['elements']):
        return scene
    rise_i, stagger_i = look_of(spec)
    if not (rise_i or stagger_i):
        return scene
    scene = deepcopy(scene)
    limit = scene['duration']
    for index, element in enumerate(scene['elements']):
        tracks = element.get('tracks') or {}
        delay = min(STAGGER[stagger_i] * min(index, 5), .3)
        if 'dy' in tracks:
            tracks['dy'] = [[t, v * RISE[rise_i]] for t, v in tracks['dy']]
        if delay:
            for name in ('opacity', 'dy'):
                if name in tracks and len(tracks[name]) >= 2 and tracks[name][-1][0] + delay <= limit - 2.05:
                    tracks[name] = [[round(t + delay, 3), v] for t, v in tracks[name]]
    scene['look'] = [rise_i, stagger_i]
    return scene
