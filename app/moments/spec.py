"""Giriş / kapanış / bitiş ekranı için şablon belirtimleri (spec)."""
from app.moments.plan import AUTO


def moment_spec(kind, value, title, channel):
    """[GİRİŞ] / [KAPANIŞ] işareti (veya otomatik tanınan cümle) → şablon spec'i."""
    value = ' '.join(str(value or '').split())
    channel = ' '.join(str(channel or '').split())[:60]
    if kind == 'intro':
        custom = '' if value in ('', AUTO) else value
        return {'template': 'intro', 'data': {'title': (custom or ' '.join(str(title or '').split()))[:90] or channel, 'channel': channel}, 'emphasis': ''}
    return {'template': 'outro', 'data': {'mode': 'farewell' if value == 'farewell' else 'subscribe', 'channel': channel}, 'emphasis': ''}


def endscreen_spec(channel):
    return {'template': 'endscreen', 'data': {'channel': ' '.join(str(channel or '').split())[:60]}, 'emphasis': ''}
