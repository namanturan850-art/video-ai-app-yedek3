"""Mapbox style identities; outbound requests always use the fixed Mapbox API host."""
import re

STYLE_URI = re.compile(r'^mapbox://styles/([A-Za-z0-9_-]{1,64})/([A-Za-z0-9_-]{1,100})$')
BUILTINS = [
    ('satellite-streets-v12', 'Uydu + yollar'), ('satellite-v9', 'Uydu'),
    ('outdoors-v12', 'Arazi'), ('streets-v12', 'Sokak'),
    ('dark-v11', 'Koyu'), ('light-v11', 'Açık'),
    ('navigation-day-v1', 'Navigasyon gündüz'), ('navigation-night-v1', 'Navigasyon gece'),
]


def validate_uri(value):
    if not isinstance(value, str) or not STYLE_URI.fullmatch(value):
        raise ValueError('Mapbox Studio → Share → Style URL bağlantısını girin (mapbox://styles/kullanıcı/stil).')
    return value


def static_template(uri):
    match = STYLE_URI.fullmatch(validate_uri(uri))
    return ('https://api.mapbox.com/styles/v1/' + match[1] + '/' + match[2]
            + '/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x')


def styles(config):
    return ([{'uri': '', 'name': 'Mevcut uydu ayarı', 'custom': False}]
            + [{'uri': 'mapbox://styles/mapbox/' + identifier, 'name': label, 'custom': False}
               for identifier, label in BUILTINS]
            + [{**item, 'custom': True} for item in config.get('custom_styles', [])])


def selection_valid(config):
    return config.get('selected_style', '') in {s['uri'] for s in styles(config)}
