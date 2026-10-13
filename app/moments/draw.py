"""Giriş, kapanış (abone ol + zil) ve YouTube bitiş ekranı çizimleri.

Kanalın Tarzım renkleri ve fontlarıyla, ortak Scene üzerine çizilir; tüm
yazılar videonun dilindedir (phrases.labels). Yalnız yerel çizici
(app/motion/raster.py) çizer; Remotion gerekmez.
"""
from app.moments.phrases import labels

INTRO_SECONDS = (3.0, 5.0)
END_SCREEN_SECONDS = 20.0


def intro_length(duration):
    """Açılış animasyonu 3–5 sn; klip daha uzunsa son kare düzeni kalır."""
    return min(max(duration, INTRO_SECONDS[0]), INTRO_SECONDS[1]) if duration >= INTRO_SECONDS[0] else duration


def draw_intro(s, d):
    from app.motion.templates import H, W, fit
    D = s.D
    live = intro_length(D)
    title, channel = d['title'], d['channel']
    s.add('rect', {'w': [[0, 0], [min(1.0, live * .3), W]]}, x=0, y=H / 2 + 118, w=0, h=10, fill=s.accent, opacity=1)
    fs, rows = fit(title, s.head, 110, 1560, 2, 54)
    top = H / 2 - 60 - (len(rows) - 1) * fs * .6
    for i, row in enumerate(rows):
        s.text(row, W / 2, top + i * fs * 1.2, fs, start=.25 + i * .15, dy=50)
    if channel:
        s.text(channel.upper() if len(channel) <= 28 else channel, W / 2, H / 2 + 200, 56, font=s.body, fill=s.accent, start=.9, dy=30)
    s.sound('rise', -.1)
    s.sound('hit', .3)
    return s


def _bell(s, cx, cy, size, start, colour, ring_colour):
    """Zil: kubbe + gövde + çan dili; sallanma x anahtar karelerindeki salınımla, halkalar büyüyen çemberlerle."""
    swing = [[start, 0]]
    t = start
    for i, amplitude in enumerate((16, -14, 11, -8, 5, -3, 0)):
        t += .11
        swing.append([t, amplitude])
    def shake(base):
        return {'cx': [[a, base + v] for a, v in swing]}
    def shake_x(base):
        return {'x': [[a, base + v] for a, v in swing]}
    appear = {'opacity': [[start - .4, 0], [start - .1, 1]]}
    r = size * .5
    s.add('arc', {**shake(cx), **appear}, cx=cx, cy=cy - r * .1, r=r, start=180, sweep=180, fill=colour, opacity=0)
    s.add('rect', {**shake_x(cx - r), **appear}, x=cx - r, y=cy - r * .1, w=r * 2, h=r * .78, fill=colour, radius=6, opacity=0)
    s.add('rect', {**shake_x(cx - r * 1.25), **appear}, x=cx - r * 1.25, y=cy + r * .62, w=r * 2.5, h=r * .22, fill=colour, radius=r * .11, opacity=0)
    s.add('circle', {**shake(cx), **appear}, cx=cx, cy=cy + r * 1.02, r=r * .2, fill=colour, opacity=0)
    s.add('circle', {**shake(cx), **appear}, cx=cx, cy=cy - r * .78, r=r * .12, fill=colour, opacity=0)
    for k in range(3):
        at = start + .05 + k * .22
        s.add('circle', {'r': [[at, r * 1.2], [at + .7, r * 2.1]], 'opacity': [[at - .01, 0], [at, .7], [at + .7, 0]]}, cx=cx, cy=cy, r=0, fill='', stroke=ring_colour, width=7, opacity=0)


def draw_outro(s, d, language):
    """Abone ol düğmesi basılır → "Abonelik alındı" → zil çalar. farewell: teşekkür yazısı + kanal adı."""
    from app.motion.templates import H, W, fit, mix
    D, md = s.D, s.md
    text = labels(language)
    if d.get('mode') == 'farewell':
        fs, rows = fit(text['thanks'], s.head, 100, 1500, 2, 52)
        for i, row in enumerate(rows):
            s.text(row, W / 2, H / 2 - 40 + (i - (len(rows) - 1) / 2) * fs * 1.2, fs, start=.2 + i * .15)
        s.add('rect', {'w': [[.4, 0], [.4 + md * 1.5, 640]], 'x': [[.4, W / 2], [.4 + md * 1.5, W / 2 - 320]]}, x=W / 2, y=H / 2 + 110, w=0, h=8, fill=s.accent, opacity=1)
        if d.get('channel'):
            s.text(d['channel'], W / 2, H / 2 + 190, 60, font=s.body, fill=s.accent, start=.8, dy=24)
        s.sound('rise', -.1)
        return s
    # --- subscribe button + bell -------------------------------------------------
    bw, bh = 620, 150
    x0, y0 = W / 2 - bw / 2 - 90, H / 2 - bh / 2
    press = min(max(1.4, D * .38), max(1.4, D - 2.2))  # moment of the tap
    done = press + .25
    button = '#E62117'  # YouTube kırmızısı; gri hali "abone olundu"
    grey = mix(s.bg, s.primary, .28)
    s.add('rect', {'opacity': [[.1, 0], [.1 + md, 1]], 'dy': [[.1, 70], [.1 + md, 0]]}, x=x0, y=y0, w=bw, h=bh, fill=button, radius=bh / 2, opacity=0, dy=70)
    s.add('rect', {'opacity': [[done, 0], [done + .2, 1]]}, x=x0, y=y0, w=bw, h=bh, fill=grey, radius=bh / 2, opacity=0)
    s.add('text', {'opacity': [[.3, 0], [.3 + md, 1], [done, 1], [done + .15, 0]]}, text=text['subscribe'].upper(), x=x0 + bw / 2, y=y0 + bh / 2, size=62, font=s.head, fill='#FFFFFF', anchor='mm', bold=True, opacity=0)
    s.add('text', {'opacity': [[done + .05, 0], [done + .25, 1]]}, text=text['subscribed'].upper(), x=x0 + bw / 2, y=y0 + bh / 2, size=58, font=s.head, fill=s.fg, anchor='mm', bold=True, opacity=0)
    # tap ripple
    s.add('circle', {'r': [[press, 0], [press + .5, 96]], 'opacity': [[press, .7], [press + .5, 0]]}, cx=x0 + bw * .72, cy=y0 + bh * .6, r=0, fill='', stroke='#FFFFFF', width=8, opacity=0)
    s.add('circle', {'r': [[press - .25, 0], [press, 26]], 'opacity': [[press - .25, 0], [press - .15, .9], [press + .35, .9], [press + .5, 0]]}, cx=x0 + bw * .72, cy=y0 + bh * .6, r=0, fill='#FFFFFF', opacity=0)
    s.add('rect', {'w': [[.5, 0], [.5 + md, bw]]}, x=x0, y=y0 + bh + 40, w=0, h=6, fill=s.accent, opacity=1)
    _bell(s, x0 + bw + 150, H / 2, 150, done + .35, s.accent, s.accent)
    if d.get('channel'):
        s.text(d['channel'], W / 2, y0 + bh + 120, 54, font=s.body, fill=s.fg, start=.9, dy=24)
    s.sound('rise', -.1)
    s.sound('click', press)
    s.sound('hit', done + .35)
    return s


def draw_endscreen(s, d):
    """Son 20 sn: sade arka plan; YouTube'un bitiş ekranı öğeleri için ortada ve sağda alan boş bırakılır."""
    from app.motion.templates import H, W, mix
    # Slow, very quiet gradient bands only at the edges; the middle stays empty.
    s.add('rect', {'opacity': [[0, 0], [.8, 1]]}, x=0, y=0, w=W, h=18, fill=s.accent, opacity=0)
    s.add('rect', {'opacity': [[0, 0], [.8, 1]]}, x=0, y=H - 18, w=W, h=18, fill=s.accent, opacity=0)
    s.add('rect', {'opacity': [[0, 0], [1.2, 1]]}, x=0, y=18, w=W, h=H - 36, fill=mix(s.bg, s.primary, .04), opacity=0)
    return s
