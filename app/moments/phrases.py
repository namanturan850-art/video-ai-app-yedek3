"""Dil başına giriş / abone ol / veda kalıpları ve ekran yazıları — TEK DOSYA.

Yeni dil eklemek için: aşağıdaki LANGUAGE_DATA sözlüğüne dil koduyla bir blok
ekleyin (örn. 'it': {...}). Başka hiçbir dosyayı değiştirmeniz gerekmez.

  intro      videonun BAŞINDA söylenen karşılama kalıpları
  subscribe  "abone olun / zili açın" çağrısı kalıpları
  farewell   videonun SONUNDA söylenen veda kalıpları
  labels     ekranda görünen yazılar (videonun dilinde)

Kalıplar küçük harfle, aksansız karşılaştırılır (ä=a, é=e, ı=i …). Bir kalıp
tam kelime olarak aranır; sonuna * koyarsanız kelime başı olarak aranır
("bienvenid*" → bienvenidos, bienvenida). Dil tanımlı değilse otomatik tanıma
yapılmaz (işaretler yine çalışır) ve yazılar İngilizce gösterilir.
"""
import re
import unicodedata

LANGUAGE_DATA = {
    'de': {
        'intro': ['willkommen*', 'herzlich willkommen', 'hallo und willkommen', 'schon dass du', 'schon dass ihr', 'schon dass sie'],
        'subscribe': ['abonniert', 'abonnieren', 'abonnier*', 'abo da lassen', 'glocke', 'kanal abonn*'],
        'farewell': ['bis zum nachsten mal', 'bis zum nachsten video', 'bis bald', 'auf wiedersehen', 'tschuss', 'danke furs zuschauen',
                     'danke furs zusehen', 'bis nachstes mal', 'bis zur nachsten folge'],
        'labels': {'subscribe': 'Abonnieren', 'subscribed': 'Abonniert', 'thanks': 'Danke fürs Zuschauen!'},
    },
    'es': {
        'intro': ['bienvenid*', 'hola y bienvenid*', 'te doy la bienvenida', 'les damos la bienvenida'],
        'subscribe': ['suscribete', 'suscribanse', 'suscribirse', 'suscribirte', 'suscribete al canal', 'campanita', 'activa la campana', 'activen la campana'],
        'farewell': ['hasta la proxima', 'hasta pronto', 'hasta luego', 'nos vemos', 'gracias por ver', 'gracias por verlo', 'hasta el proximo video'],
        'labels': {'subscribe': 'Suscribirse', 'subscribed': 'Suscrito', 'thanks': '¡Gracias por ver!'},
    },
    'fr': {
        'intro': ['bienvenue', 'bonjour et bienvenue', 'salut et bienvenue'],
        'subscribe': ['abonnez vous', 'abonne toi', 'abonnez-vous', 'abonne-toi', 'abonner', 'abonnement', 'cloche', 'activez la cloche'],
        'farewell': ['a bientot', 'a la prochaine', 'au revoir', 'merci d avoir regarde', 'merci de votre attention', 'a tres vite', 'a la prochaine video'],
        'labels': {'subscribe': "S'abonner", 'subscribed': 'Abonné', 'thanks': 'Merci d’avoir regardé !'},
    },
    'en': {
        'intro': ['welcome', 'hello and welcome', 'hi and welcome'],
        'subscribe': ['subscribe', 'subscribing', 'hit the bell', 'notification bell', 'ring the bell'],
        'farewell': ['see you next time', 'until next time', 'see you in the next', 'thanks for watching', 'thank you for watching', 'goodbye', 'see you soon'],
        'labels': {'subscribe': 'Subscribe', 'subscribed': 'Subscribed', 'thanks': 'Thanks for watching!'},
    },
    'tr': {
        'intro': ['hos geldin*', 'hosgeldin*', 'merhaba ve hos geldin*', 'kanalima hos geldin*'],
        'subscribe': ['abone ol*', 'abone olmayi', 'abone olmayin', 'abone olun', 'abonelik', 'zil', 'bildirimleri ac*', 'zili calin', 'zile basin'],
        'farewell': ['bir sonraki videoda', 'gorusmek uzere', 'hosca kal*', 'izlediginiz icin tesekkur*', 'bir sonraki bolumde', 'sonraki videoda gorusuruz'],
        'labels': {'subscribe': 'Abone ol', 'subscribed': 'Abone olundu', 'thanks': 'İzlediğiniz için teşekkürler!'},
    },
}
FALLBACK = 'en'


def fold(text):
    """Küçük harf, aksansız, noktalamasız; tek boşluklu kelimeler."""
    text = str(text or '').replace('ı', 'i').replace('İ', 'i').replace('ß', 'ss')
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r"[^\w\s]|_", ' ', text.replace('’', ' ').replace("'", ' ')).split())


_COMPILED = {}


def _patterns(language, kind):
    key = (language, kind)
    if key not in _COMPILED:
        found = []
        for raw in LANGUAGE_DATA.get(language, {}).get(kind, []):
            word = fold(raw.rstrip('*'))
            if word:
                found.append(re.compile(r'(?<!\w)' + re.escape(word) + (r'' if raw.endswith('*') else r'(?!\w)')))
        _COMPILED[key] = found
    return _COMPILED[key]


def classify(sentence, language):
    """'subscribe' | 'farewell' | 'intro' | None — what the sentence is, in the video's language."""
    text = fold(sentence)
    if not text:
        return None
    for kind in ('subscribe', 'farewell', 'intro'):
        if any(p.search(text) for p in _patterns(language, kind)):
            return kind
    return None


def labels(language):
    """Ekran yazıları videonun dilinde; dil tanımlı değilse İngilizce."""
    return LANGUAGE_DATA.get(language, LANGUAGE_DATA[FALLBACK])['labels']
