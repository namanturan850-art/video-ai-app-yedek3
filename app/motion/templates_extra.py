"""Nine more animated infographics, made from the owner's markers (no AI):

    [ROTA: A > B > C]                 route drawn on the map
    [İMPARATORLUK: ad yıl-yıl]        border growing over time (approximate)
    [YAKINLAŞ: yer]                   zoom world → region → place
    [İŞARETLE: açıklama]              slow zoom on the scene's picture + circle/arrow + label
    [ÖNCESONRA: A | B]                sliding curtain between two pictures
    [İKON: sayı nesne]                icons multiplying + counter
    [ORAN: %değer etiket]             animated pie + percentage
    [HANEDAN: A > B, C > D]           family/dynasty tree (“>” new generation, “,” siblings)
    [BİLGİ: kısa metin]               “Biliyor muydunuz?” card

parse() turns a marker into a spec (places from the offline place list,
never invented); build_extra() draws it with the channel's Tarzım colours
and fonts on the shared Scene (same timing rules as the other templates).
Only the local renderer (app/motion/raster.py) draws these."""
import math
import re

TEMPLATES_EXTRA = {'route': 'Rota', 'empire': 'İmparatorluk sınırı', 'zoom': 'Yakınlaşma (dünya → yer)', 'mark': 'Görselde işaretle',
                   'beforeafter': 'Önce / sonra', 'icons': 'İkonlarla sayı', 'ratio': 'Oran (pasta)', 'dynasty': 'Hanedan ağacı', 'fact': 'Biliyor muydunuz?',
                   'relief': 'Kabartma harita (bölge / ok / yakınlaşma)', 'archive': 'Arşiv fotoğrafı (çerçeveli)', 'intro': 'Açılış (başlık + kanal)', 'outro': 'Kapanış (abone ol + zil)', 'endscreen': 'YouTube bitiş ekranı'}
MARKER_TEMPLATE = {'route': 'route', 'empire': 'empire', 'zoom': 'zoom', 'mark': 'mark', 'beforeafter': 'beforeafter', 'icons': 'icons',
                   'ratio': 'ratio', 'dynasty': 'dynasty', 'fact': 'fact', 'region': 'relief', 'arrow': 'relief', 'archive': 'archive'}
FACT_TITLE = {'de': 'Wussten Sie schon?', 'tr': 'Biliyor muydunuz?', 'en': 'Did you know?', 'es': '¿Sabías que…?', 'fr': 'Le saviez-vous ?'}
APPROX = {'de': 'ungefähre Ausdehnung', 'tr': 'yaklaşık sınırlar', 'en': 'approximate extent', 'es': 'extensión aproximada', 'fr': 'étendue approximative'}
WORLD = {'de': 'Welt', 'tr': 'Dünya', 'en': 'World', 'es': 'Mundo', 'fr': 'Monde'}
BEFORE_AFTER = {'de': ('VORHER', 'NACHHER'), 'tr': ('ÖNCE', 'SONRA'), 'en': ('BEFORE', 'AFTER'), 'es': ('ANTES', 'DESPUÉS'), 'fr': ('AVANT', 'APRÈS')}
ICON_WORDS = {
    'soldier': ('soldat', 'krieger', 'legionär', 'asker', 'savaşçı', 'soldier', 'warrior', 'legion', 'troop', 'ordu', 'armee'),
    'person': ('mensch', 'menschen', 'einwohner', 'person', 'leute', 'bewohner', 'kişi', 'insan', 'nüfus', 'people', 'person', 'sklave',
               'köle', 'arbeiter', 'işçi', 'pilger', 'hacı', 'zuschauer', 'seyirci', 'gefangene', 'esir', 'tote', 'ölü', 'kinder', 'çocuk'),
    'ship': ('schiff', 'boot', 'gemi', 'tekne', 'ship', 'boat', 'galeere', 'kadırga'),
    'house': ('haus', 'häuser', 'ev', 'house', 'home', 'hütte'),
    'building': ('gebäude', 'tempel', 'stadt', 'städte', 'bina', 'tapınak', 'şehir', 'building', 'temple', 'city', 'kirche', 'kilise'),
    'coin': ('münze', 'gold', 'silber', 'taler', 'denar', 'para', 'altın', 'sikke', 'coin', 'dollar', 'euro', 'lira', 'mark'),
    'tree': ('baum', 'bäume', 'ağaç', 'tree', 'wald', 'orman'),
    'animal': ('pferd', 'kamel', 'tier', 'schaf', 'rind', 'at', 'deve', 'hayvan', 'koyun', 'horse', 'camel', 'animal', 'elefant', 'fil'),
    'book': ('buch', 'bücher', 'schrift', 'rolle', 'kitap', 'book', 'scroll', 'tafel', 'tablet'),
    'planet': ('planet', 'gezegen', 'stern', 'yıldız', 'star', 'sonne', 'güneş', 'sun', 'mond', 'ay', 'moon', 'galaxie', 'galaksi', 'galaxy'),
}
# Approximate largest extent of well-known empires: names of places at the edge (resolved offline).
EMPIRES = {
    'roma': ('Rom', ['Lissabon', 'London', 'Köln', 'Wien', 'Konstanza', 'Trabzon', 'Bagdad', 'Petra', 'Assuan', 'Leptis Magna|Tripolis', 'Tanger']),
    'römisches reich': ('Rom', ['Lissabon', 'London', 'Köln', 'Wien', 'Konstanza', 'Trabzon', 'Bagdad', 'Petra', 'Assuan', 'Tripolis', 'Tanger']),
    'roman empire': ('Rom', ['Lissabon', 'London', 'Köln', 'Wien', 'Konstanza', 'Trabzon', 'Bagdad', 'Petra', 'Assuan', 'Tripolis', 'Tanger']),
    'osmanlı': ('Istanbul', ['Wien', 'Budapest', 'Krim|Simferopol', 'Baku', 'Bagdad', 'Basra', 'Mekka', 'Aden', 'Kairo', 'Tripolis', 'Algier', 'Belgrad']),
    'osmanisches reich': ('Istanbul', ['Wien', 'Budapest', 'Simferopol', 'Baku', 'Bagdad', 'Basra', 'Mekka', 'Aden', 'Kairo', 'Tripolis', 'Algier']),
    'ottoman empire': ('Istanbul', ['Wien', 'Budapest', 'Simferopol', 'Baku', 'Bagdad', 'Basra', 'Mekka', 'Aden', 'Kairo', 'Tripolis', 'Algier']),
    'assyrien': ('Ninive', ['Memphis', 'Theben', 'Tyrus', 'Antakya', 'Malatya', 'Van', 'Ekbatana', 'Susa', 'Babylon', 'Ur']),
    'assur': ('Ninive', ['Memphis', 'Theben', 'Tyrus', 'Antakya', 'Malatya', 'Van', 'Ekbatana', 'Susa', 'Babylon', 'Ur']),
    'asur': ('Ninive', ['Memphis', 'Theben', 'Tyrus', 'Antakya', 'Malatya', 'Van', 'Ekbatana', 'Susa', 'Babylon', 'Ur']),
    'babylonien': ('Babylon', ['Gaza', 'Jerusalem', 'Damaskus', 'Aleppo', 'Harran', 'Ninive', 'Susa', 'Ur', 'Teima|Tayma']),
    'babil': ('Babylon', ['Gaza', 'Jerusalem', 'Damaskus', 'Aleppo', 'Harran', 'Ninive', 'Susa', 'Ur']),
    'persien': ('Persepolis', ['Sardes', 'Byzanz', 'Memphis', 'Assuan', 'Samarkand', 'Kabul', 'Multan', 'Babylon', 'Jerusalem']),
    'pers': ('Persepolis', ['Sardes', 'Byzanz', 'Memphis', 'Assuan', 'Samarkand', 'Kabul', 'Multan', 'Babylon', 'Jerusalem']),
    'perserreich': ('Persepolis', ['Sardes', 'Byzanz', 'Memphis', 'Assuan', 'Samarkand', 'Kabul', 'Multan', 'Babylon', 'Jerusalem']),
    'alexander': ('Pella|Thessaloniki', ['Athen', 'Byzanz', 'Sardes', 'Memphis', 'Siwa', 'Babylon', 'Persepolis', 'Samarkand', 'Kabul', 'Multan']),
    'makedonien': ('Pella|Thessaloniki', ['Athen', 'Byzanz', 'Sardes', 'Memphis', 'Siwa', 'Babylon', 'Persepolis', 'Samarkand', 'Kabul', 'Multan']),
    'byzanz': ('Istanbul', ['Venedig', 'Rom', 'Karthago', 'Alexandria', 'Jerusalem', 'Antakya', 'Trabzon', 'Belgrad', 'Ravenna']),
    'bizans': ('Istanbul', ['Venedig', 'Rom', 'Karthago', 'Alexandria', 'Jerusalem', 'Antakya', 'Trabzon', 'Belgrad', 'Ravenna']),
    'mongolen': ('Karakorum|Ulaanbaatar', ['Kiew', 'Moskau', 'Bagdad', 'Damaskus', 'Delhi', 'Peking', 'Seoul', 'Wladiwostok']),
    'moğol': ('Karakorum|Ulaanbaatar', ['Kiew', 'Moskau', 'Bagdad', 'Damaskus', 'Delhi', 'Peking', 'Seoul', 'Wladiwostok']),
    'hethiter': ('Hattuscha', ['Troja', 'Milet', 'Tarsus', 'Kadesch', 'Ugarit', 'Malatya', 'Samsun']),
    'hitit': ('Hattuscha', ['Troja', 'Milet', 'Tarsus', 'Kadesch', 'Ugarit', 'Malatya', 'Samsun']),
    'ägypten': ('Theben', ['Alexandria', 'Gaza', 'Kadesch', 'Assuan', 'Meroe']),
    'mısır': ('Theben', ['Alexandria', 'Gaza', 'Kadesch', 'Assuan', 'Meroe']),
}


class MarkerError(ValueError):
    """The marker cannot be drawn; .message is plain Turkish for the owner."""
    def __init__(self, message):
        super().__init__(message); self.message = message


def where(name):
    """(display name, lat, lon, info) from the offline place list, or None."""
    from app.motion.places import find
    for option in str(name).split('|'):
        place = find(option.strip())
        if place: return option.strip(), place['lat'], place['lon'], place
    return None


def satellite_props(language):
    """Scene props of the satellite map style (+ Ayarlar → Mapbox → Eğik görünüm)."""
    from app.providers.satellite import oblique
    # camera 2: north up, pitch 60, haze — older tilted clips (camera turned along the route) are drawn again
    return {'theme': 'satellite', 'lang': language, **({'view': 'oblique', 'camera': 2} if oblique() else {})}


def near_each_other(stops):
    """Same-name places: each stop becomes the namesake closest to the other stops (in place)."""
    from app.motion.places import nearest
    for i, stop in enumerate(stops):
        others = [p for j, p in enumerate(stops) if j != i]
        lat, lon = sum(p['lat'] for p in others) / len(others), sum(p['lon'] for p in others) / len(others)
        found = nearest(stop['name'], lat, lon)
        far = lambda p: math.hypot(p['lat'] - lat, (p['lon'] - lon) * math.cos(math.radians(lat)))
        if found and far(stop) - far(found) > 3: stop.update(lat=found['lat'], lon=found['lon'])  # only a clearly closer namesake
    return stops


def modern_of(name):
    """Today's country/place of an ancient place from the hand-made list ('' when unknown)."""
    from app.motion.places import plain, places
    key = plain(name)
    return next((p['modern'] for p in places() if p['rank'] == 1 and p['modern'] and key in (plain(a) for a in p['aliases'])), '')


def nearby(lat, lon, radius, limit=4):
    """Well-known places around a point (context on a zoomed map)."""
    from app.motion.places import places
    found = []
    for p in places():
        if not (p['rank'] <= 2 or p.get('population', 0) >= 500_000): continue
        d = math.hypot(p['lat'] - lat, (p['lon'] - lon) * math.cos(math.radians(lat)))
        if .6 < d <= radius and p['kind'] not in ('region', 'sea', 'river', 'mountain', 'country'):
            found.append((d, p))
    out, seen = [], []
    for d, p in sorted(found, key=lambda x: (x[1]['rank'] > 1, x[0])):
        if any(math.hypot(p['lat'] - a, p['lon'] - b) < 1.2 for a, b in seen): continue
        seen.append((p['lat'], p['lon'])); out.append({'name': p['name'][:30], 'lat': p['lat'], 'lon': p['lon']})
        if len(out) >= limit: break
    return out


def year_value(text):
    """'27 v. Chr.' / 'MÖ 27' / '27 BC' → -27; '117' → 117; None when no year."""
    match = re.search(r'\d{1,4}', text or '')
    if not match: return None
    value = int(match.group())
    return -value if re.search(r'(?i)v\.\s*chr|vor\s+christus|\bbc\b|\bbce\b|\bmö\b|m\.\s*ö', text) else value


def year_text(value, language='de'):
    if value >= 0: return str(value)
    return {'de': f'{-value} v. Chr.', 'tr': f'MÖ {-value}', 'en': f'{-value} BC', 'es': f'{-value} a. C.', 'fr': f'{-value} av. J.-C.'}.get(language, f'{-value} BC')


def icon_for(word):
    low = (word or '').casefold()
    for icon, words in ICON_WORDS.items():
        if any(low.startswith(w) or w in low.split() for w in words): return icon
    return 'dot'


def hull(points):
    """Convex hull (lat, lon) in order, then pushed outwards a little so the border is not on the cities."""
    pts = sorted(set((round(a, 3), round(b, 3)) for a, b in points))
    if len(pts) < 3: return pts
    cross = lambda o, a, b: (a[1] - o[1]) * (b[0] - o[0]) - (a[0] - o[0]) * (b[1] - o[1])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0: lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0: upper.pop()
        upper.append(p)
    ring = lower[:-1] + upper[:-1]
    clat, clon = sum(a for a, _ in ring) / len(ring), sum(b for _, b in ring) / len(ring)
    out = []
    for lat, lon in ring:
        d = math.hypot(lat - clat, lon - clon) or 1
        out.append((round(lat + (lat - clat) / d * 1.6, 3), round(lon + (lon - clon) / d * 1.6, 3)))
    # Rounder border: a point between neighbours, pulled out a bit.
    smooth = []
    for i, a in enumerate(out):
        b = out[(i + 1) % len(out)]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        d = math.hypot(mid[0] - clat, mid[1] - clon) or 1
        smooth += [a, (round(mid[0] + (mid[0] - clat) / d * .8, 3), round(mid[1] + (mid[1] - clon) / d * .8, 3))]
    return smooth


def parse(kind, value, sentence='', language='de'):
    """Owner marker → spec (raises MarkerError with a Turkish reason)."""
    value = ' '.join(str(value or '').split())
    template = MARKER_TEMPLATE[kind]
    if template == 'relief' or kind == 'zoom':
        try:
            relief_spec = relief_marker(kind, value)
        except MarkerError:
            raise
        except Exception:  # e.g. a missing component (numpy) or unreadable map data: a plain reason, never a crash
            raise MarkerError('Kabartma harita çizilemedi: harita bileşenleri eksik veya okunamadı. START_AI_VIDEO_STUDIO.bat ile uygulamayı yeniden başlatın (eksik bileşen otomatik kurulur).') from None
        if relief_spec: return relief_spec
        if template == 'relief':
            raise MarkerError(f'“{value}” kabartma haritada bulunamadı. Ülke, bölge/il ya da “Vallée du Rhône” gibi bir nehir vadisi yazın; ok için: [OK: Lyon > Marseille].')
    if template == 'route':
        names = [v.strip() for v in re.split(r'>|→|->|–>', value) if v.strip()]
        if len(names) < 2: raise MarkerError('[ROTA] için en az iki yer yazın: [ROTA: Ninive > Babil > Kudüs].')
        stops, missing = [], []
        for name in names[:6]:
            found = where(name)
            if found: stops.append({'name': found[0][:40], 'lat': found[1], 'lon': found[2]})
            else: missing.append(name)
        if len(stops) < 2: raise MarkerError(f'Rota çizilemedi: şu yerler yer listesinde bulunamadı: {", ".join(missing)}.')
        near_each_other(stops)
        return {'template': 'route', 'data': {'stops': stops, 'missing': missing, 'source': value}, 'emphasis': ''}
    if template == 'empire':
        main, _, edge = value.partition('|')
        years = re.search(r'((?:MÖ|M\.Ö\.|BC|v\.\s*Chr\.)?\s*\d{1,4}\s*(?:v\.\s*Chr\.|BC|BCE|MÖ)?)\s*[-–—]\s*((?:MÖ|M\.Ö\.|BC|v\.\s*Chr\.|MS|AD|n\.\s*Chr\.)?\s*\d{1,4}\s*(?:v\.\s*Chr\.|n\.\s*Chr\.|BC|BCE|AD|MÖ|MS)?)', main)
        name = (main[:years.start()] if years else main).strip(' ,;:') or main.strip()
        start, end = (year_value(years.group(1)), year_value(years.group(2))) if years else (None, None)
        if years and start is not None and end is not None and start > 0 and re.search(r'(?i)v\.\s*chr|bc|mö', years.group(2)) and not re.search(r'(?i)v\.\s*chr|bc|mö', years.group(1)):
            start = -start  # “700-612 v. Chr.”: both years are before Christ
        key = name.casefold().replace('ı', 'i') if name.casefold().replace('ı', 'i') in EMPIRES else name.casefold()
        known = next((v for k, v in EMPIRES.items() if k == key or k in key.split() or key.startswith(k)), None)
        capital_name, edge_names = (edge.split(',')[0].strip(), [e.strip() for e in edge.split(',') if e.strip()]) if edge.strip() else (known or (None, []))
        if not capital_name: raise MarkerError(f'“{name}” için sınır bilgisi yok. Yerleri ekleyin: [İMPARATORLUK: {name} 700-612 | Başkent, Yer 2, Yer 3].')
        capital = where(capital_name)
        edges = [found for found in (where(e) for e in edge_names) if found]
        if not capital or len(edges) < 2: raise MarkerError(f'“{name}” sınırları için yeterli yer bulunamadı; işarete yerleri ekleyin: [İMPARATORLUK: {name} | Başkent, Yer 2, Yer 3].')
        area = hull([(capital[1], capital[2])] + [(e[1], e[2]) for e in edges])
        return {'template': 'empire', 'data': {'name': name[:40], 'start_year': start, 'end_year': end, 'capital': {'name': capital_name.split('|')[0][:40], 'lat': capital[1], 'lon': capital[2]},
                                               'area': area, 'source': value}, 'emphasis': ''}
    if template == 'zoom':
        found = where(value)
        if not found: raise MarkerError(f'“{value}” yer listesinde bulunamadı; yakınlaşma çizilemedi. Yerin bilinen bir adını yazın (örn. Babil, Kudüs, Roma).')
        from app.motion.places import country_name
        info = found[3]
        if not info.get('modern') and not info.get('country'): info = {**info, 'modern': modern_of(found[0])}
        region = country_name(info, language) if info['kind'] != 'country' else ''
        return {'template': 'zoom', 'data': {'place': found[0][:40], 'lat': found[1], 'lon': found[2], 'region': region[:40],
                                             'extent_km': info.get('extent_km') or 10, 'nearby': nearby(found[1], found[2], 9.), 'source': value},
                'emphasis': value.split()[0]}
    if template == 'archive':
        if len(value.split()) < 1: raise MarkerError('[ARŞİV] için fotoğrafı tarif edin: [ARŞİV: 1910 Paris sokakları].')
        search, _, caption = value.partition('|')  # [ARŞİV: old harbor photo | Brest, 1910]: the part after | is written under the photo
        return {'template': 'archive', 'data': {'label': search.strip()[:70], 'caption': caption.strip()[:50], 'image': '', 'source': value}, 'emphasis': ''}
    if template == 'mark':
        return {'template': 'mark', 'data': {'label': value[:70], 'image': '', 'fx': .5, 'fy': .5, 'source': value}, 'emphasis': ''}
    if template == 'beforeafter':
        parts = [p.strip() for p in re.split(r'\||/| vs\.? ', value) if p.strip()]
        if len(parts) != 2: raise MarkerError('[ÖNCESONRA] için iki şey yazın: [ÖNCESONRA: Antik liman | Bugünkü kıyı].')
        return {'template': 'beforeafter', 'data': {'before': parts[0][:40], 'after': parts[1][:40], 'images': [], 'source': value}, 'emphasis': ''}
    if template == 'icons':
        match = re.match(r'\s*([\d.,  ]+\d|\d+)\s*(.*)', value)
        if not match: raise MarkerError('[İKON] için sayı ve nesne yazın: [İKON: 10000 asker].')
        digits = re.sub(r'[^\d]', '', match.group(1))
        number = int(digits) if digits else 0
        if number <= 0: raise MarkerError('[İKON] sayısı sıfırdan büyük olmalı.')
        thing = match.group(2).strip()[:40]
        return {'template': 'icons', 'data': {'value': match.group(1).strip(), 'number': number, 'object': thing, 'icon': icon_for(thing), 'source': value}, 'emphasis': ''}
    if template == 'ratio':
        match = re.search(r'%\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%', value)
        if not match: raise MarkerError('[ORAN] için yüzde yazın: [ORAN: %40 nüfus kıyıda yaşıyor].')
        number = float((match.group(1) or match.group(2)).replace(',', '.'))
        if not 0 < number <= 100: raise MarkerError('[ORAN] değeri 0 ile 100 arasında olmalı.')
        label = (value[:match.start()] + value[match.end():]).strip(' ,;:-')
        shown = f'%{match.group(1) or match.group(2)}' if language == 'tr' else f'{match.group(1) or match.group(2)} %'
        return {'template': 'ratio', 'data': {'value': shown, 'percent': number, 'label': label[:70], 'source': value}, 'emphasis': ''}
    if template == 'dynasty':
        generations = [[n.strip()[:28] for n in g.split(',') if n.strip()][:4] for g in re.split(r'>|→', value) if g.strip()]
        generations = [g for g in generations if g][:5]
        if sum(len(g) for g in generations) < 2: raise MarkerError('[HANEDAN] için en az iki kişi yazın: [HANEDAN: Davud > Süleyman > Rehavam].')
        return {'template': 'dynasty', 'data': {'generations': generations, 'source': value}, 'emphasis': ''}
    text = value[:220]
    if len(text.split()) < 3: raise MarkerError('[BİLGİ] için kısa bir cümle yazın: [BİLGİ: Babil’in surları iki kat genişlikteydi].')
    return {'template': 'fact', 'data': {'text': text, 'source': value}, 'emphasis': ''}


def relief_marker(kind, value):
    """[BÖLGE: Bretagne] / [OK: A > B] / [YAKINLAŞ: yer] → relief map spec, or None."""
    from app.motion import relief
    original = value
    value, _, figure = value.partition('|')  # [BÖLGE: Bretagne | 27.208 km²] / [OK: Paris > New York | 6.640 mil]: a number box
    value, figure = value.strip(), figure.strip()[:24]
    extra = {'figure': figure} if figure else {}
    if kind == 'compare':
        parts = [v.strip() for v in re.split(r'\||\bvs\.?\b|\bgegen\b|\bkarşı\b', value + ('|' + figure if figure else '')) if v.strip()]
        if len(parts) != 2 or any(re.search(r'\d', p) for p in parts): return None
        a, b = relief.find(parts[0]), relief.find(parts[1])
        if not a or not b or not a['polygons'] or not b['polygons']: return None
        return {'template': 'relief', 'data': {'mode': 'compare', 'target': parts[0][:80], 'other': parts[1][:80], 'source': original}, 'emphasis': ''}
    if kind == 'arrow':
        parts = [v.strip() for v in re.split(r'>|→|->', value) if v.strip()]
        if len(parts) != 2: raise MarkerError('[OK] için iki yer yazın: [OK: Lyon > Marseille].')
        a, b = relief.place(parts[0]), relief.place(parts[1])
        if not a or not b: return None
        return {'template': 'relief', 'data': {'mode': 'arrow', 'from': parts[0][:60], 'to': parts[1][:60], 'source': value, **extra}, 'emphasis': ''}
    if relief.find(value) or (kind == 'zoom' and relief.place(value)):
        return {'template': 'relief', 'data': {'mode': 'region' if kind == 'region' else 'zoom', 'target': value[:80], 'source': value, **extra}, 'emphasis': ''}
    return None


def validate_extra(spec):
    """Shape check for a stored/edited spec (values come from the owner's marker)."""
    t, d = spec.get('template'), spec.get('data')
    if t not in TEMPLATES_EXTRA or not isinstance(d, dict): raise ValueError('template')
    if t == 'intro' and not d.get('title'): raise ValueError('title')
    if t == 'route' and len(d.get('stops') or []) < 2: raise ValueError('route stops')
    if t == 'empire' and (len(d.get('area') or []) < 3 or not d.get('capital')): raise ValueError('empire area')
    if t == 'zoom' and not (-85 <= float(d.get('lat', 99)) <= 85 and -180 <= float(d.get('lon', 999)) <= 180): raise ValueError('zoom place')
    if t == 'beforeafter' and len(d.get('images') or []) != 2: raise ValueError('two pictures')
    if t in ('mark', 'archive') and not d.get('image'): raise ValueError('picture')
    if t == 'icons' and not int(d.get('number') or 0) > 0: raise ValueError('number')
    if t == 'ratio' and not 0 < float(d.get('percent') or 0) <= 100: raise ValueError('percent')
    if t == 'dynasty' and sum(len(g) for g in d.get('generations') or []) < 2: raise ValueError('people')
    if t == 'fact' and not d.get('text'): raise ValueError('text')
    if t == 'relief':
        from app.motion import relief
        relief.plan({'data': d})  # the area / places must exist in the offline data
    return {'template': t, 'data': d, 'emphasis': str(spec.get('emphasis') or '')[:60]}


def summary(spec):
    d = spec['data']
    return {'intro': lambda: d['title'], 'outro': lambda: d.get('mode', 'subscribe'), 'endscreen': lambda: d.get('channel', ''),
            'route': lambda: ' → '.join(s['name'] for s in d['stops']), 'empire': lambda: d['name'], 'zoom': lambda: d['place'],
            'mark': lambda: d['label'], 'beforeafter': lambda: f'{d["before"]} / {d["after"]}', 'icons': lambda: f'{d["value"]} {d["object"]}',
            'ratio': lambda: f'{d["value"]} {d["label"]}', 'dynasty': lambda: ' > '.join(', '.join(g) for g in d['generations']),
            'fact': lambda: d['text'], 'relief': lambda: d.get('target') or f'{d.get("from")} → {d.get("to")}', 'archive': lambda: d['label']}[spec['template']]()


# ---- drawing --------------------------------------------------------------------
def fit_view(points, pad=1.5, minimum=8.):
    """(lat, lon, span) of a map view that shows all points."""
    from app.motion.templates import H, W
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    clat, clon = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    span = max((max(lons) - min(lons)) * pad, (max(lats) - min(lats)) * pad * W / H, minimum)
    return clat, clon, min(span, 330.)


def map_colours(s):
    from app.motion.templates import mix
    return dict(land=mix(s.bg, s.primary, .28), coast=mix(s.bg, s.primary, .5), ocean=mix(s.bg, s.primary, .06))


def title(s, text, y=96, size=58):
    from app.motion.templates import W, fit, mix
    if not text: return
    fs, rows = fit(text, s.head, size, 1500, 1, 34)
    width = min(1700, max(400, len(rows[0]) * fs * .6 + 120))
    s.add('rect', s.appear(.05, 0, .88), x=W / 2 - width / 2, y=y - fs * .85, w=width, h=fs * 1.7, fill=mix(s.bg, '#000000', .25), radius=18, opacity=0)
    s.text(rows[0], W / 2, y, fs, start=.1, dy=20)


def build_extra(s, spec, language='de'):
    from app.motion.templates import H, W, fit, measure, mix, grouped
    E, D, md = s.E, s.D, s.md
    t, d = spec['template'], spec['data']
    lang = language if language in FACT_TITLE else 'en'
    if t == 'relief':  # drawn whole by app/motion/relief.py (terrain, highlight, arrow, camera)
        from app.channels import map_style
        style = map_style(s.kit)
        extra = {'theme': 'dark'} if style == 'dark' else satellite_props(language) if style == 'satellite' else {}
        s.add('relief', spec=spec, **extra)  # the relief look keeps its old scene key
        return s
    if t == 'archive':  # drawn whole by app/motion/archive.py (white frame, tilt, slow zoom)
        s.add('archive', image_path=d.get('image_path', ''), caption=d.get('caption', ''))
        return s
    if t in ('intro', 'outro', 'endscreen'):
        from app.moments import draw
        return {'intro': lambda: draw.draw_intro(s, d), 'outro': lambda: draw.draw_outro(s, d, language), 'endscreen': lambda: draw.draw_endscreen(s, d)}[t]()
    if t == 'route':
        from app.channels import map_style
        if map_style(s.kit) == 'satellite':  # Harita stili → Uydu görüntüsü: the route on satellite tiles (yellow line, dots, names)
            s.add('relief', spec={'template': 'relief', 'data': {'mode': 'arrow', 'stops': d['stops'], 'source': d.get('source', '')}, 'emphasis': ''},
                  **satellite_props(language))
            return s
        stops = d['stops']
        clat, clon, span = fit_view([(p['lat'], p['lon']) for p in stops])
        s.add('map', {'zoom': [[0, 0], [max(.8, E * .4), 1]]}, lon=clon, lat=clat, span_from=min(330, span * 1.8), span_to=span, **map_colours(s))
        lengths = [math.hypot(b['lat'] - a['lat'], b['lon'] - a['lon']) for a, b in zip(stops, stops[1:])]
        total = sum(lengths) or 1
        start, end = max(.6, E * .3), max(E, min(D - .8, E + 1.5))
        s.add('geoline', {'progress': [[start, 0], [end, 1]]}, points=[[p['lat'], p['lon']] for p in stops], stroke=s.accent, width=10, opacity=1)
        reached = 0.
        for i, stop in enumerate(stops):
            at = start + (end - start) * reached / total
            if i < len(lengths): reached += lengths[i]
            s.add('geopin', {'opacity': [[at - .05, 0], [at + .15, 1]], 'size': [[at, 0], [at + .25, 22]]}, lat=stop['lat'], lon=stop['lon'], size=0,
                  fill=s.accent if i in (0, len(stops) - 1) else s.primary, hole=s.bg, opacity=0)
            s.add('geotext', {'opacity': [[at, 0], [at + .3, 1]]}, lat=stop['lat'], lon=stop['lon'], text=stop['name'], size=44 if len(stops) <= 4 else 36,
                  font=s.head, fill=s.fg, box=mix(s.bg, '#000000', .3), offset=62 if i % 2 == 0 else -62, opacity=0)
            s.sound('click', at)
        s.sound('rise', start - .2)
    elif t == 'empire':
        area = [tuple(p) for p in d['area']]
        cap = d['capital']
        clat, clon, span = fit_view(area + [(cap['lat'], cap['lon'])], 1.25, 10)
        s.add('map', {'zoom': [[0, 0], [.8, 1]]}, lon=clon, lat=clat, span_from=min(330, span * 1.5), span_to=span, **map_colours(s))
        grow_end = max(E, D * .78)
        s.add('geoarea', {'grow': [[.7, .05], [grow_end, 1]], 'opacity': [[.5, 0], [.8, 1]]}, points=[list(p) for p in area],
              center=[cap['lat'], cap['lon']], fill=s.accent, stroke=s.accent, fill_opacity=.42, width=5, opacity=0)
        s.add('geopin', {'opacity': [[.4, 0], [.6, 1]]}, lat=cap['lat'], lon=cap['lon'], size=16, fill=s.fg, hole=s.bg, opacity=0)
        s.add('geotext', {'opacity': [[.5, 0], [.8, 1]]}, lat=cap['lat'], lon=cap['lon'], text=cap['name'], size=38, font=s.body, fill=s.fg,
              box=mix(s.bg, '#000000', .3), offset=50, opacity=0)
        title(s, d['name'])
        if d.get('start_year') is not None and d.get('end_year') is not None:
            s.add('years', {'value': [[.7, 0], [grow_end, 1]], 'opacity': [[.3, 0], [.6, 1]]}, start_year=d['start_year'], end_year=d['end_year'],
                  language=lang, x=W - 120, y=H - 110, size=86, font=s.head, fill=s.accent, anchor='rm', bold=True, opacity=0, shadow=True)
        s.text(APPROX[lang], 120, H - 90, 34, font=s.body, anchor='lm', start=.6, bold=False, fill=mix(s.fg, s.bg, .3))
        s.sound('rise', .5); s.sound('hit', grow_end)
    elif t == 'zoom':
        city_span = max(5., min(14., float(d.get('extent_km') or 10) / 111 * 14))  # still shows coasts/neighbours around the place
        region_span = max(city_span * 3, 26.)
        world = 330.
        z_region = (world - region_span) / (world - city_span)
        s.add('map', {'zoom': [[0, 0], [.3, 0], [max(1., E * .55), z_region], [max(1.3, E * .7), z_region], [max(1.8, E), 1]]},
              lon=d['lon'], lat=d['lat'], span_from=world, span_to=city_span, **map_colours(s))
        crumbs = [WORLD[lang]] + ([d['region']] if d.get('region') else []) + [d['place']]
        times = [.2, max(1., E * .55), max(1.8, E)] if len(crumbs) == 3 else [.2, max(1.8, E)]
        x = 110
        for i, (crumb, at) in enumerate(zip(crumbs, times)):
            label = crumb + ('  ›' if i < len(crumbs) - 1 else '')
            s.text(label, x, 100, 44, anchor='lm', start=at, dy=16, fill=s.accent if i == len(crumbs) - 1 else s.fg)
            x += measure(label + '  ', s.head, 44)
        at = max(1.8, E)
        def clear(other):  # on the final (closest) view: not under the breadcrumb, the main label or the frame edge
            height = city_span * H / W
            x = W / 2 + (other['lon'] - d['lon']) * W / city_span
            y = H / 2 - (other['lat'] - d['lat']) * H / height
            return 120 < x < W - 120 and 200 < y < H - 70 and not (abs(x - W / 2) < 360 and H / 2 - 120 < y < H / 2 + 230)
        for other in [o for o in d.get('nearby') or [] if clear(o)]:
            s.add('geopin', {'opacity': [[times[1] if len(times) == 3 else .8, 0], [(times[1] if len(times) == 3 else .8) + .4, .9]]}, lat=other['lat'], lon=other['lon'],
                  size=10, fill=mix(s.fg, s.bg, .3), hole=s.bg, opacity=0)
            s.add('geotext', {'opacity': [[times[1] if len(times) == 3 else .8, 0], [(times[1] if len(times) == 3 else .8) + .4, .85]]}, lat=other['lat'], lon=other['lon'],
                  text=other['name'], size=32, font=s.body, fill=mix(s.fg, s.bg, .2), offset=36, bold=False, opacity=0)
        s.add('circle', {'r': [[at, 0], [at + 1.2, 150]], 'opacity': [[at, .55], [at + 1.2, 0]]}, cx=W / 2, cy=H / 2, r=0, fill='', stroke=s.accent, width=6, opacity=0)
        s.add('pin', {'dy': [[at - .4, -160], [at, 0]], 'opacity': [[at - .4, 0], [at - .25, 1]]}, x=W / 2, y=H / 2, size=46, fill=s.accent, hole=s.bg, opacity=0, dy=-160)
        fs = 60 if len(d['place']) < 24 else 48
        width = measure(d['place'], s.head, fs) + 80
        s.add('rect', s.appear(at + .1, 30), x=W / 2 - width / 2, y=H / 2 + 90, w=width, h=fs * 1.6, fill=s.bg, radius=16, opacity=0)
        s.text(d['place'], W / 2, H / 2 + 90 + fs * .8, fs, start=at + .1, dy=30)
        s.sound('whoosh', .3); s.sound('hit', at)
    elif t == 'mark':
        fx, fy = float(d.get('fx', .5)), float(d.get('fy', .5))
        zoom_to = 1.35
        s.add('image', {'zoom': [[0, 1.], [D, zoom_to]]}, path=d['image_path'], x=0, y=0, w=W, h=H, fx=fx, fy=fy, opacity=1)
        cx, cy = focus_on_screen(d['image_path'], fx, fy, (1 + zoom_to) / 2)
        r = 150
        s.add('ring', {'progress': [[E - .4, 0], [E + .5, 1]]}, cx=cx, cy=cy, r=r, squash=.8, stroke=s.accent, width=9, opacity=1)
        below = cy < H * .55
        ly = min(H - 110, cy + r + 150) if below else max(110, cy - r - 150)
        fs, rows = fit(d['label'], s.head, 54, 1200, 1, 34)
        width = measure(rows[0], s.head, fs) + 90
        lx = min(max(cx, width / 2 + 40), W - width / 2 - 40)
        s.add('arrow', {'progress': [[E + .3, 0], [E + .7, 1]], 'opacity': [[E + .3, 0], [E + .35, 1]]}, x1=lx, y1=ly + (-fs if below else fs),
              x2=cx, y2=cy + (r * .8 + 14 if below else -r * .8 - 14), stroke=s.accent, width=8, opacity=0)
        s.add('rect', s.appear(E + .2, 20), x=lx - width / 2, y=ly - fs * .8, w=width, h=fs * 1.6, fill=mix(s.bg, '#000000', .3), radius=16, opacity=0)
        s.text(rows[0], lx, ly, fs, start=E + .2, dy=20)
        s.sound('click', E)
    elif t == 'beforeafter':
        a, b = d['image_paths']
        words = BEFORE_AFTER[lang]
        s.add('image', {}, path=b, x=0, y=0, w=W, h=H, opacity=1)
        s.add('image', {'reveal': [[.4, 1.], [max(1.2, E), .5]]}, path=a, x=0, y=0, w=W, h=H, opacity=1, reveal=1.)
        s.add('line', {'x1': [[.4, W], [max(1.2, E), W / 2]], 'x2': [[.4, W], [max(1.2, E), W / 2]]}, x1=W, y1=0, x2=W, y2=H, stroke=s.fg, width=8, opacity=1)
        for i, (word, label, x, anchor) in enumerate(((words[0], d['before'], 70, 'lm'), (words[1], d['after'], W - 70, 'rm'))):
            at = .3 if i == 0 else max(1.2, E)
            fs, rows = fit(label, s.head, 54, 800, 1, 32)
            width = max(measure(word, s.head, 40), measure(rows[0], s.head, fs)) + 60
            s.add('rect', s.appear(at, 20, .72), x=x - 30 if anchor == 'lm' else x - width + 30, y=40, w=width, h=150, fill=mix(s.bg, '#000000', .35), radius=16, opacity=0)
            s.add('text', s.appear(at, 20), text=word, x=x, y=90, size=40, font=s.head, fill=s.accent, anchor=anchor, bold=True, opacity=0, shadow=True)
            s.add('text', s.appear(at + .1, 20), text=rows[0], x=x, y=150, size=fs, font=s.head, fill=s.fg, anchor=anchor, bold=True, opacity=0, shadow=True)
        s.sound('whoosh', .4); s.sound('hit', max(1.2, E))
    elif t == 'icons':
        number = int(d['number'])
        unit = 1
        while number / unit > 40:
            unit = unit * 2 if str(unit)[0] == '1' else unit * 5 // 2 if str(unit)[0] == '2' else unit * 2
        count = max(1, min(40, math.ceil(number / unit)))
        columns = min(10, count)
        rows = math.ceil(count / columns)
        size = 120 if rows <= 2 else 96 if rows <= 3 else 78
        gap = size * 1.4
        left = W / 2 - (columns - 1) * gap / 2
        top = 640 - (rows - 1) * gap / 2
        start, end = .4, max(1.2, E)
        for i in range(count):
            at = start + (end - start) * i / max(1, count - 1)
            x, y = left + (i % columns) * gap, top + (i // columns) * gap
            s.add('icon', {'scale': [[at, 0], [at + .25, 1.12], [at + .4, 1]], 'opacity': [[at, 0], [at + .1, 1]]}, icon=d['icon'], x=x, y=y, size=size,
                  fill=s.accent if i == count - 1 else s.primary, opacity=0, scale=0)
        s.add('counter', {'value': [[start, 0], [end, 1]], 'opacity': [[start - .1, 0], [start + .2, 1]]}, target=grouped(str(number), language),
              x=W / 2, y=170, size=160, font=s.head, fill=s.accent, anchor='mm', bold=True, opacity=0, language=language, from_year=False)
        fs, label = fit(d['object'], s.body, 64, 1500, 1, 36)
        s.text(label[0], W / 2, 290, fs, font=s.body, start=.3, bold=False)
        if unit > 1:
            legend = f'1 = {grouped(str(unit), language)}'
            s.text(legend, W - 110, H - 70, 36, font=s.body, anchor='rm', start=end, bold=False, fill=mix(s.fg, s.bg, .3))
        s.sound('rise', end - .9); s.sound('hit', end)
    elif t == 'ratio':
        p = float(d['percent'])
        cx, cy, r = 600, H / 2 + 20, 300
        s.add('circle', s.appear(.1, 0), cx=cx, cy=cy, r=r, fill=mix(s.bg, s.primary, .22), opacity=0)
        s.add('arc', {'sweep': [[.4, 0], [max(1., E), 360 * p / 100]]}, cx=cx, cy=cy, r=r, start=-90, sweep=0, fill=s.accent, opacity=1)
        s.add('circle', s.appear(.1, 0), cx=cx, cy=cy, r=r * .55, fill=s.bg, opacity=0)
        s.add('counter', {'value': [[.4, 0], [max(1., E), 1]], 'opacity': [[.3, 0], [.5, 1]]}, target=d['value'], x=cx, y=cy, size=110, font=s.head,
              fill=s.fg, anchor='mm', bold=True, opacity=0, language=language, from_year=False)
        if d.get('label'):
            fs, rows = fit(d['label'], s.body, 64, 780, 4, 38)
            top = cy - (len(rows) - 1) * fs * .65
            for i, row in enumerate(rows):
                s.text(row, 1020, top + i * fs * 1.3, fs, font=s.body, anchor='lm', start=.3 + i * .1, bold=False)
        s.sound('rise', max(1., E) - .9); s.sound('hit', max(1., E))
    elif t == 'dynasty':
        generations = d['generations']
        rows = len(generations)
        gap_y = min(210, (H - 260) / max(1, rows))
        top = H / 2 - (rows - 1) * gap_y / 2
        previous = None
        for g, people in enumerate(generations):
            at = .3 + (max(1., E) - .3) * g / max(1, rows - 1)
            y = top + g * gap_y
            gap_x = min(420, 1600 / len(people))
            xs = [W / 2 + (i - (len(people) - 1) / 2) * gap_x for i in range(len(people))]
            for i, (name, x) in enumerate(zip(people, xs)):
                fs, line = fit(name, s.head, 46, gap_x - 50, 1, 28)
                width = min(gap_x - 30, measure(line[0], s.head, fs) + 70)
                if previous:
                    px, py = previous
                    mid = (py + y) / 2
                    s.add('line', {'y2': [[at - .35, py + 40], [at - .2, mid]]}, x1=px, y1=py + 40, x2=px, y2=py + 40, stroke=mix(s.bg, s.primary, .6), width=5, opacity=1)
                    s.add('line', {'x2': [[at - .2, px], [at - .05, x]]}, x1=px, y1=mid, x2=px, y2=mid, stroke=mix(s.bg, s.primary, .6), width=5, opacity=1)
                    s.add('line', {'y2': [[at - .05, mid], [at, y - 40]]}, x1=x, y1=mid, x2=x, y2=mid, stroke=mix(s.bg, s.primary, .6), width=5, opacity=1)
                s.add('rect', s.appear(at, 24, 1.), x=x - width / 2, y=y - 40, w=width, h=80, fill=s.accent if i == 0 else mix(s.bg, s.primary, .35), radius=18, opacity=0)
                s.text(line[0], x, y, fs, start=at, dy=24, fill=s.bg if i == 0 else s.fg)
            previous = (xs[0], y)
            s.sound('click', at)
    else:  # fact
        heading = FACT_TITLE[lang]
        panel_w, panel_h = 1500, 640
        x0, y0 = W / 2 - panel_w / 2, H / 2 - panel_h / 2
        s.add('rect', {'opacity': [[.1, 0], [.1 + md, 1]], 'dy': [[.1, 80], [.1 + md, 0]]}, x=x0, y=y0, w=panel_w, h=panel_h, fill=mix(s.bg, s.primary, .14), radius=36, opacity=0, dy=80)
        s.add('rect', {'w': [[.3, 0], [.3 + md, panel_w - 120]]}, x=x0 + 60, y=y0 + 150, w=0, h=8, fill=s.accent, opacity=1)
        s.add('circle', {'r': [[.25, 0], [.25 + md, 58]]}, cx=x0 + 120, cy=y0 + 80, r=0, fill=s.accent, opacity=1)
        s.text('?', x0 + 120, y0 + 80, 76, fill=s.bg, start=.3, dy=0)
        s.text(heading, x0 + 210, y0 + 80, 64, anchor='lm', start=.3, dy=20, fill=s.accent)
        fs, rows = fit(d['text'], s.body, 84, panel_w - 160, 5, 40)
        middle = y0 + 160 + (panel_h - 160) / 2
        for i, row in enumerate(rows):
            s.text(row, x0 + 80, middle - (len(rows) - 1) * fs * .65 + i * fs * 1.3, fs, font=s.body, anchor='lm', start=max(.5, E * .5) + i * .12, dy=24, bold=False)
        s.sound('click', .3)
    return s


def focus_on_screen(path, fx, fy, zoom):
    """Where the focus point of the picture lands on the 1920×1080 frame at this zoom."""
    from app.motion.templates import H, W
    try:
        from PIL import Image
        with Image.open(path) as picture: pw, ph = picture.size
    except Exception:
        return W * fx, H * fy
    scale = max(W / pw, H / ph) * zoom
    cw, ch = W / scale, H / scale
    left = min(max(fx * pw - cw / 2, 0), pw - cw)
    top = min(max(fy * ph - ch / 2, 0), ph - ch)
    return (fx * pw - left) * scale, (fy * ph - top) * scale
