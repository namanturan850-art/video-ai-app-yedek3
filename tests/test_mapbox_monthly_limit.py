"""Ayarlar → Mapbox monthly safety limit: requests are counted per month (tiles and
tilted pictures apart), cached pictures are not requested again, and at the limit
no request is sent. Fake HTTP only; the real API was not called."""
import json

import httpx
import pytest

from app.providers import satellite as s


def provider(tmp_path, seen, status=200):
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(status, content=b'\xff\xd8fake', headers={'content-type': 'image/jpeg'})
    return s.MapboxSatelliteProvider('pk.test-key-123', 'https://api.mapbox.com/v4/x/{z}/{x}/{y}.jpg', cache=tmp_path / 'tiles',
                                     transport=httpx.MockTransport(handler))


def test_counter_limit_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'USAGE_FILE', tmp_path / 'usage.json')
    monkeypatch.setattr(s, 'LIMITS', lambda: {'tiles': 2, 'static': 1})
    seen = []
    p = provider(tmp_path, seen)
    p.tile(1, 0, 0); p.tile(1, 0, 0); p.tile(1, 1, 0)  # the same tile twice: one request (cache)
    assert len(seen) == 2 and s.usage()['tiles'] == 2
    with pytest.raises(s.SatelliteError) as error:
        p.tile(1, 1, 1)
    assert error.value.category == 'monthly_limit' and 'Bu ayki Mapbox güvenlik sınırına ulaşıldı' in str(error.value)
    assert len(seen) == 2  # no request at the limit
    p.static(2., 48., 5., 0, 45, 300, 200); p.static(2., 48., 5., 0, 45, 300, 200)  # same picture: reused
    assert s.usage()['static'] == 1 and 'Bu ay: 2 karo / 1 eğik görüntü' in s.usage_text()
    (tmp_path / 'usage.json').write_text(json.dumps({'month': '2000-01', 'tiles': 9, 'static': 9}))
    assert s.usage() == {'month': s.month(), 'tiles': 0, 'static': 0}  # a new month starts at zero


def test_rejected_key_mentions_account_limit_or_payment(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'USAGE_FILE', None)
    with pytest.raises(s.SatelliteError) as error:
        provider(tmp_path, [], 403).tile(1, 0, 0)
    assert 'Mapbox hesabında kullanım sınırı veya ödeme sorunu olabilir' in str(error.value)
