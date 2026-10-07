"""One extensible language registry shared by projects, scripts and future output."""
LANGUAGES = {'de': 'Almanca', 'es': 'İspanyolca', 'en': 'İngilizce', 'fr': 'Fransızca', 'tr': 'Türkçe'}


def validate_language(value):
    if value not in LANGUAGES:
        raise ValueError('Dil için geçerli bir değer seçin.')
    return value
