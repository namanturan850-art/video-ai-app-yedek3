"""Offline place data for the map infographics (no internet, no AI):
1. the small hand-made list below (names in German, English, Turkish,
   Spanish and French), checked first;
2. ancient places, regions and seas with ancient ↔ modern names
   (app/motion/places_extra.py);
3. every country and every city with 15 000+ inhabitants, with their other
   names (GeoNames CC BY 4.0 + Unicode CLDR names; app/motion/places_world.json.gz,
   built by tools/build_places.py).
Map markers only (locate()), when the lists above do not know the name:
4. towns and villages with 1 000+ inhabitants (GeoNames) and Natural Earth
   populated places (app/motion/places_local.json.gz, tools/build_places_local.py);
5. Mapbox Geocoding (app/providers/geocoding.py), when a Mapbox key is set.
A place found nowhere is reported to the owner (never guessed)."""
import math
import gzip
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'places_world.json.gz'
LOCAL = Path(__file__).resolve().parent / 'places_local.json.gz'

PLACES = [
    # (lat, lon, names)
    (25.0, -71.0, 'Bermuda-Dreieck|Bermudadreieck|Bermuda Triangle|Bermuda Üçgeni|Triángulo de las Bermudas|Triangle des Bermudes'),
    (32.3, -64.8, 'Bermuda|Bermudas|Bermudes'),
    (27.8, -81.7, 'Florida|Floride'),
    (25.76, -80.19, 'Miami'),
    (18.2, -66.5, 'Puerto Rico|Porto Rico|Porto Riko'),
    (24.25, -76.0, 'Bahamas|Bahama'),
    (21.5, -79.0, 'Kuba|Cuba|Küba'),
    (18.1, -77.3, 'Jamaika|Jamaica|Jamaïque'),
    (15.0, -75.0, 'Karibik|Caribbean|Karayipler|Caribe|Caraïbes'),
    (30.0, -40.0, 'Atlantik|Atlantischer Ozean|Atlantic|Atlantic Ocean|Atlas Okyanusu|Atlántico|Atlantique'),
    (0.0, -160.0, 'Pazifik|Pazifischer Ozean|Pacific|Pacific Ocean|Büyük Okyanus|Pasifik|Pacífico|Pacifique'),
    (-20.0, 80.0, 'Indischer Ozean|Indian Ocean|Hint Okyanusu|Océano Índico|Océan Indien'),
    (11.35, 142.2, 'Marianengraben|Mariana Trench|Mariana Çukuru|Fosa de las Marianas|Fosse des Mariannes'),
    (41.9, -50.0, 'Titanic'),
    (35.0, 18.0, 'Mittelmeer|Mediterranean|Akdeniz|Mediterráneo|Méditerranée'),
    (56.0, 3.0, 'Nordsee|North Sea|Kuzey Denizi|Mar del Norte|Mer du Nord'),
    (58.0, 20.0, 'Ostsee|Baltic Sea|Baltık Denizi|Mar Báltico|Mer Baltique'),
    (43.0, 34.0, 'Schwarzes Meer|Black Sea|Karadeniz|Mar Negro|Mer Noire'),
    (20.0, 38.5, 'Rotes Meer|Red Sea|Kızıldeniz|Mar Rojo|Mer Rouge'),
    (41.9, 12.5, 'Rom|Rome|Roma'),
    (36.85, 10.33, 'Karthago|Carthage|Kartaca|Cartago'),
    (40.75, 14.49, 'Pompeji|Pompeii|Pompei|Pompeya|Pompéi'),
    (45.44, 12.33, 'Venedig|Venice|Venedik|Venecia|Venise'),
    (37.6, 14.0, 'Sizilien|Sicily|Sicilya|Sicilia|Sicile'),
    (42.8, 12.6, 'Italien|Italy|İtalya|Italia|Italie'),
    (37.98, 23.73, 'Athen|Athens|Atina|Atenas|Athènes'),
    (39.0, 22.0, 'Griechenland|Greece|Yunanistan|Grecia|Grèce'),
    (35.24, 24.8, 'Kreta|Crete|Girit|Creta|Crète'),
    (39.96, 26.24, 'Troja|Troy|Truva|Troya|Troie'),
    (37.07, 22.43, 'Sparta|Esparta|Sparte'),
    (41.01, 28.98, 'Istanbul|İstanbul|Konstantinopel|Constantinople|Constantinopla|Byzanz'),
    (39.0, 35.0, 'Türkei|Turkey|Türkiye|Turquía|Turquie|Anatolien|Anatolia|Anadolu'),
    (26.8, 30.8, 'Ägypten|Egypt|Mısır|Egipto|Égypte'),
    (30.04, 31.24, 'Kairo|Cairo|Kahire|El Cairo|Le Caire'),
    (29.98, 31.13, 'Gizeh|Giza|Gize|Gizeh'),
    (30.0, 31.2, 'Nil|Nile|Nil Nehri|Nilo'),
    (31.78, 35.22, 'Jerusalem|Kudüs|Jerusalén|Jérusalem'),
    (21.42, 39.83, 'Mekka|Mecca|Mekke|La Meca|La Mecque'),
    (32.54, 44.42, 'Babylon|Babil|Babilonia|Babylone'),
    (33.0, 44.0, 'Mesopotamien|Mesopotamia|Mezopotamya|Mésopotamie'),
    (32.0, 53.0, 'Persien|Persia|Pers|Perse|Iran|İran|Irán'),
    (21.0, 78.0, 'Indien|India|Hindistan|Inde'),
    (35.0, 103.0, 'China|Çin|Chine'),
    (39.9, 116.4, 'Peking|Beijing|Pekin|Pékin'),
    (36.2, 138.25, 'Japan|Japonya|Japón|Japon'),
    (35.68, 139.69, 'Tokio|Tokyo|Tokyo'),
    (61.5, 105.0, 'Russland|Russia|Rusya|Rusia|Russie'),
    (55.75, 37.62, 'Moskau|Moscow|Moskova|Moscú|Moscou'),
    (60.0, 100.0, 'Sibirien|Siberia|Sibirya|Sibérie'),
    (28.0, 84.0, 'Himalaya|Himalayas|Himalaja'),
    (27.99, 86.93, 'Mount Everest|Everest'),
    (11.55, 92.24, 'North Sentinel|Nord-Sentinel|Nord Sentinel|Kuzey Sentinel|Sentinel del Norte|Sentinelle du Nord'),
    (12.0, 92.8, 'Andamanen|Andaman Islands|Andaman Adaları|Islas Andamán|Îles Andaman|Andamanen-Inseln'),
    (-6.0, 145.0, 'Papua-Neuguinea|Papua New Guinea|Papua Yeni Gine|Papúa Nueva Guinea|Papouasie-Nouvelle-Guinée|Neuguinea|New Guinea|Yeni Gine'),
    (-3.0, 115.0, 'Indonesien|Indonesia|Endonezya|Indonésie'),
    (-25.0, 134.0, 'Australien|Australia|Avustralya|Australie'),
    (-41.0, 174.0, 'Neuseeland|New Zealand|Yeni Zelanda|Nueva Zelanda|Nouvelle-Zélande'),
    (20.8, -156.3, 'Hawaii|Havai|Hawái|Hawaï'),
    (-17.65, -149.43, 'Tahiti|Tahití'),
    (-15.0, -150.0, 'Polynesien|Polynesia|Polinezya|Polinesia|Polynésie'),
    (-3.4, -62.0, 'Amazonas|Amazon|Amazon Nehri|Amazonia|Amazonie|Amazonasgebiet|Amazonas-Regenwald'),
    (-10.0, -53.0, 'Brasilien|Brazil|Brezilya|Brasil|Brésil'),
    (-9.2, -75.0, 'Peru|Perú|Pérou'),
    (-13.16, -72.55, 'Machu Picchu'),
    (-35.7, -71.5, 'Chile|Şili|Chili'),
    (-38.4, -63.6, 'Argentinien|Argentina|Arjantin|Argentine'),
    (-55.98, -67.27, 'Kap Hoorn|Cape Horn|Horn Burnu|Cabo de Hornos|Cap Horn'),
    (23.6, -102.5, 'Mexiko|Mexico|Meksika|México|Mexique'),
    (9.08, -79.68, 'Panamakanal|Panama Canal|Panama Kanalı|Canal de Panamá|Canal de Panama'),
    (39.8, -98.6, 'USA|Vereinigte Staaten|United States|Amerika|America|ABD|Estados Unidos|États-Unis'),
    (40.71, -74.0, 'New York|New York City|Nueva York'),
    (38.9, -77.04, 'Washington'),
    (36.8, -119.4, 'Kalifornien|California|Kaliforniya|Californie'),
    (31.0, -100.0, 'Texas|Teksas'),
    (64.2, -149.5, 'Alaska'),
    (56.1, -106.3, 'Kanada|Canada|Canadá'),
    (72.0, -40.0, 'Grönland|Greenland|Grönland|Groenlandia|Groenland'),
    (64.96, -19.0, 'Island|Iceland|İzlanda|Islandia|Islande'),
    (60.5, 8.5, 'Norwegen|Norway|Norveç|Noruega|Norvège'),
    (60.1, 18.6, 'Schweden|Sweden|İsveç|Suecia|Suède'),
    (51.2, 10.4, 'Deutschland|Germany|Almanya|Alemania|Allemagne'),
    (52.52, 13.4, 'Berlin|Berlín'),
    (46.2, 2.2, 'Frankreich|France|Fransa|Francia'),
    (48.86, 2.35, 'Paris|París'),
    (40.4, -3.7, 'Spanien|Spain|İspanya|España|Espagne'),
    (40.42, -3.7, 'Madrid'),
    (39.4, -8.2, 'Portugal|Portekiz'),
    (38.72, -9.14, 'Lissabon|Lisbon|Lizbon|Lisboa|Lisbonne'),
    (36.14, -5.35, 'Gibraltar|Cebelitarık'),
    (54.0, -2.0, 'England|Großbritannien|Britain|Great Britain|United Kingdom|İngiltere|Inglaterra|Angleterre|Royaume-Uni'),
    (51.51, -0.13, 'London|Londra|Londres'),
    (30.6, 32.3, 'Suezkanal|Suez Canal|Süveyş Kanalı|Canal de Suez'),
    (23.0, 13.0, 'Sahara|Sahra|Sáhara'),
    (2.0, 21.0, 'Afrika|Africa|Afrika Kıtası|África|Afrique'),
    (-4.0, 22.0, 'Kongo|Congo'),
    (-30.6, 22.9, 'Südafrika|South Africa|Güney Afrika|Sudáfrica|Afrique du Sud'),
    (-34.36, 18.47, 'Kap der Guten Hoffnung|Cape of Good Hope|Ümit Burnu|Cabo de Buena Esperanza|Cap de Bonne-Espérance'),
    (-18.8, 47.0, 'Madagaskar|Madagascar'),
    (7.9, 80.8, 'Sri Lanka|Ceylon|Seylan'),
    (-75.0, 0.0, 'Antarktis|Antarctica|Antarktika|Antártida|Antarctique'),
    (75.0, 0.0, 'Arktis|Arctic|Arktik|Ártico|Arctique'),
    (84.0, 0.0, 'Nordpol|North Pole|Kuzey Kutbu|Polo Norte|Pôle Nord'),
    (-84.0, 0.0, 'Südpol|South Pole|Güney Kutbu|Polo Sur|Pôle Sud'),
    (54.0, 15.0, 'Europa|Europe|Avrupa'),
    (34.0, 100.0, 'Asien|Asia|Asya|Asie'),
    # Landmarks and monuments (approximate centre point).
    (48.636, -1.5115, 'Mont-Saint-Michel|Mont Saint-Michel|Le Mont-Saint-Michel|Mont Saint Michel'),
    (48.66, -1.58, 'Bucht des Mont-Saint-Michel|Bay of Mont-Saint-Michel|Mont-Saint-Michel Körfezi|Bahía del Monte Saint-Michel|Baie du Mont-Saint-Michel'),
    (48.8584, 2.2945, 'Eiffelturm|Eiffel Tower|Eyfel Kulesi|Torre Eiffel|Tour Eiffel'),
    (48.853, 2.3499, 'Notre-Dame de Paris|Notre Dame de Paris|Kathedrale Notre-Dame'),
    (48.8049, 2.1204, 'Schloss Versailles|Palace of Versailles|Versay Sarayı|Palacio de Versalles|Château de Versailles'),
    (47.6162, 1.517, 'Schloss Chambord|Château de Chambord|Chambord'),
    (43.9475, 4.5353, 'Pont du Gard'),
    (45.0537, 1.1679, 'Höhle von Lascaux|Lascaux Cave|Lascaux Mağarası|Cueva de Lascaux|Grotte de Lascaux|Lascaux'),
    (45.8326, 6.8652, 'Mont Blanc|Montblanc|Monte Bianco'),
    (45.9763, 7.6586, 'Matterhorn|Cervin|Monte Cervino'),
    (41.8902, 12.4922, 'Kolosseum|Colosseum|Kolezyum|Coliseo|Colisée'),
    (37.9715, 23.7257, 'Akropolis|Acropolis|Akropol|Acrópolis|Acropole'),
    (41.0086, 28.9802, 'Hagia Sophia|Ayasofya|Santa Sofía|Sainte-Sophie'),
    (47.5576, 10.7498, 'Schloss Neuschwanstein|Neuschwanstein Castle|Neuschwanstein Şatosu|Castillo de Neuschwanstein|Château de Neuschwanstein|Neuschwanstein'),
    (52.5163, 13.3777, 'Brandenburger Tor|Brandenburg Gate|Brandenburg Kapısı|Puerta de Brandeburgo|Porte de Brandebourg'),
    (41.4036, 2.1744, 'Sagrada Família|Sagrada Familia'),
    (37.1761, -3.5881, 'Alhambra'),
    (51.5007, -0.1246, 'Big Ben'),
    (51.5081, -0.0759, 'Tower of London|Londoner Tower|Londra Kulesi|Torre de Londres|Tour de Londres'),
    (40.6892, -74.0445, 'Freiheitsstatue|Statue of Liberty|Özgürlük Heykeli|Estatua de la Libertad|Statue de la Liberté'),
    (37.8199, -122.4783, 'Golden Gate Bridge|Golden Gate Köprüsü|Puente Golden Gate|Pont du Golden Gate|Golden Gate'),
    (40.4319, 116.5704, 'Chinesische Mauer|Große Mauer|Great Wall of China|Great Wall|Çin Seddi|Gran Muralla China|Grande Muraille de Chine|Grande Muraille'),
    (27.1751, 78.0421, 'Taj Mahal|Tac Mahal'),
    (20.6843, -88.5678, 'Chichén Itzá|Chichen Itza'),
]


def plain(text):
    text = unicodedata.normalize('NFKD', str(text or '').replace('ß', 'ss').replace('ı', 'i')).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


# Common words that are also the name of some small town somewhere: never read as a place in narration.
COMMON = {'essen', 'halle', 'hof', 'mark', 'marken', 'kiel', 'bad', 'stadt', 'land', 'berg', 'tal', 'see', 'feld', 'weil', 'lage', 'bergen',
          'nur', 'ende', 'mission', 'victoria', 'union', 'liberty', 'independence', 'concord', 'progress', 'hope', 'paradise', 'eden', 'goshen',
          'bethlehem', 'nazareth', 'salem', 'ariel', 'kale', 'kent', 'derince', 'bulut', 'deniz', 'yalova', 'ordu', 'van', 'mus', 'bar', 'bat',
          'gaza', 'sur', 'dan', 'gat', 'ur', 'mari', 'saba', 'jordan', 'georgia', 'kongo', 'china', 'turkey', 'chad', 'niger', 'guinea'}


# Hand-made entries are written “German|English|Turkish|…”; these start with the English name already.
EN_FIRST = {'Babylon', 'Nimrud', 'Uruk', 'Nippur', 'Mari', 'Ebla', 'Persepolis', 'Pasargadae', 'Sumer', 'Akkad', 'Samaria', 'Sinai', 'Jericho',
            'Megiddo', 'Hazor', 'Bethel', 'Dan', 'Hebron', 'Ekron', 'Masada', 'Qumran', 'Sidon', 'Byblos', 'Ugarit', 'Palmyra', 'Petra', 'Jordan',
            'Tigris', 'Göbekli Tepe', 'Çatalhöyük', 'Tarsus', 'Edessa', 'Knossos', 'Olympia', 'Delphi', 'Memphis', 'Amarna', 'Tanis', 'Avaris',
            'Abu Simbel', 'Meroe', 'Aksum', 'Timbuktu', 'Great Zimbabwe', 'Herculaneum', 'Ostia', 'Stonehenge', 'Harappa', 'Angkor', 'Samarkand',
            'Cusco', 'Tenochtitlan', 'Mohenjo-Daro', 'Ur', 'Susa', 'Florida', 'Miami', 'Puerto Rico', 'Bahamas', 'Bermuda', 'Titanic', 'Sparta',
            'Istanbul', 'Jerusalem', 'China', 'Japan', 'Mount Everest', 'North Sentinel', 'Hawaii', 'Tahiti', 'Machu Picchu', 'Peru', 'Chile',
            'USA', 'New York', 'Washington', 'Texas', 'Alaska', 'Berlin', 'Paris', 'Madrid', 'Portugal', 'Gibraltar', 'England', 'London', 'Sahara',
            'Sri Lanka', 'Mont-Saint-Michel', 'Pont du Gard', 'Notre-Dame de Paris', 'Mont Blanc', 'Matterhorn', 'Hagia Sophia', 'Sagrada Família',
            'Alhambra', 'Big Ben', 'Tower of London', 'Golden Gate Bridge', 'Taj Mahal', 'Chichén Itzá'}


def ascii_name(name):
    return unicodedata.normalize('NFKD', name.replace('ß', 'ss').replace('ı', 'i')).encode('ascii', 'ignore').decode().strip()


EN_OVERRIDE = {'Bermuda-Dreieck': 'Bermuda Triangle', 'Atlantik': 'Atlantic Ocean', 'Pazifik': 'Pacific Ocean', 'Ägäis': 'Aegean Sea',
               'Adria': 'Adriatic Sea', 'Judäa': 'Judea', 'Indischer Ozean': 'Indian Ocean', 'Bermuda': 'Bermuda', 'Kreta': 'Crete'}


def english_name(names, hand_made=True):
    if hand_made and names[0] in EN_OVERRIDE: return EN_OVERRIDE[names[0]]
    if hand_made and names[0] not in EN_FIRST and len(names) > 1 and names[1].isascii(): return names[1]
    return names[0] if names[0].isascii() else ascii_name(names[0])


@lru_cache(maxsize=1)
def places():
    """All places: dicts with name, lat, lon, kind, modern/country, extent_km, rank (lower wins)."""
    out = []
    for lat, lon, names in PLACES:
        parts = names.split('|')
        out.append({'name': parts[0], 'en': english_name(parts), 'aliases': parts, 'lat': lat, 'lon': lon, 'kind': 'manual', 'modern': '', 'extent_km': 0, 'rank': 0})
    from app.motion.places_extra import EXTRA
    for lat, lon, names, kind, modern, extent in EXTRA:
        parts = names.split('|')
        out.append({'name': parts[0], 'en': english_name(parts), 'aliases': parts, 'lat': lat, 'lon': lon, 'kind': kind, 'modern': modern, 'extent_km': extent, 'rank': 1})
    for name, lat, lon, kind, code, extent, population, others in world_data().get('places', []):
        out.append({'name': name, 'en': english_name([name], False), 'aliases': [name, *others], 'lat': lat, 'lon': lon, 'kind': kind,
                    'modern': '', 'country': code, 'extent_km': extent, 'population': population,
                    'rank': 2 if kind == 'country' else 3 + 1 / max(1, population) ** .25})
    return out


@lru_cache(maxsize=1)
def world_data():
    try:
        with gzip.open(DATA, 'rt', encoding='utf-8') as source:
            return json.load(source)
    except (OSError, ValueError, KeyError):
        return {}


def country_name(place, language='de'):
    """Today's country of a place in the video language ('' when unknown)."""
    countries = world_data().get('countries', {})
    code = place.get('country') or ''
    if not code and place.get('modern'):  # hand-made list: “Hillah, Irak” (Turkish country name)
        last = plain(place['modern'].split(',')[-1])
        code = SHORT.get(last) or next((c for c, names in countries.items() if plain(names.get('tr', '')) == last or plain(names.get('en', '')) == last), '')
    names = countries.get(code) or {}
    return names.get(language) or names.get('en') or ''  # never a Turkish name in a German video


SHORT = {'abd': 'US', 'bati seria': 'PS', 'ingiltere': 'GB', 'britanya': 'GB', 'filistin': 'PS'}


@lru_cache(maxsize=1)
def index():
    best = {}
    for place in places():
        for alias in place['aliases']:
            key = plain(alias)
            if len(key) < 2: continue
            if key not in best or place['rank'] < best[key]['rank']: best[key] = place
    return best


@lru_cache(maxsize=1)
def namesakes():
    every = {}
    for place in places():
        for alias in dict.fromkeys(plain(a) for a in place['aliases']):
            if len(alias) >= 2: every.setdefault(alias, []).append(place)
    return every


def nearest(name, lat, lon):
    """Of the places sharing exactly this name, the one closest to (lat, lon):
    “Paris > Rennes > Brest” is Brest in France, not Brest in Belarus. None when unknown."""
    options = namesakes().get(plain(name), []) or local_index().get(plain(name), [])  # the owner typed this name: every namesake counts
    if not options: return None
    return min(options, key=lambda p: math.hypot(p['lat'] - lat, (p['lon'] - lon) * math.cos(math.radians(lat))))


def notable(place, key):
    """Can this place be recognised in narration by itself? (hand-made lists, countries, big cities)"""
    if place['rank'] <= 1: return True
    if key in COMMON or len(key) < 4: return False
    return place['kind'] == 'country' or place.get('population', 0) >= 300_000


def find(name):
    """The place for a name (any of its names, ancient or modern), or None:
    {'name', 'lat', 'lon', 'kind', 'modern', 'extent_km'}."""
    wanted = plain(name)
    if not wanted: return None
    table = index()
    if wanted in table: return table[wanted]
    tokens = wanted.split()
    for size in range(min(4, len(tokens)), 0, -1):  # “die Bermuda-Inseln”, “Bermuda Triangle area”
        for i in range(len(tokens) - size + 1):
            key = ' '.join(tokens[i:i + size])
            if len(key) < 3 or key not in table: continue
            place = table[key]
            # Part of a longer name: only the hand-made lists, or a notable place covering most of the name
            # (“Kennedy Space Center” is not the Bogotá district “Kennedy”).
            if place['rank'] <= 1 or (notable(place, key) and size * 2 >= len(tokens)):
                return place
    return None


def lookup(name):
    """(lat, lon, display name) for a place name, or None."""
    place = find(name)
    return (place['lat'], place['lon'], name) if place else None


def spoken_places(text):
    """Places spoken in the text: [(name exactly as written, lat, lon)] in reading order.
    Hand-made entries anywhere; other places only when written with a capital letter."""
    text = str(text or '')
    spans = [(m.start(), m.end(), plain(m.group()), m.group()[:1].isupper()) for m in re.finditer(r'[^\W_]+', text)]
    table, found, taken, i = index(), [], set(), 0
    while i < len(spans):
        for size in range(min(4, len(spans) - i), 0, -1):
            key = ' '.join(w for _, _, w, _ in spans[i:i + size])
            place = table.get(key)
            if not place or len(key) < 3 or not notable(place, key) or (place['rank'] > 1 and not spans[i][3]): continue
            if (place['lat'], place['lon']) not in taken:
                found.append((text[spans[i][0]:spans[i + size - 1][1]], place['lat'], place['lon']))
                taken.add((place['lat'], place['lon']))
            i += size - 1
            break
        i += 1
    return found


@lru_cache(maxsize=1)
def local_index():
    """{plain name: [place, …]} of the towns and villages (places_local.json.gz), most inhabitants first."""
    try:
        with gzip.open(LOCAL, 'rt', encoding='utf-8') as source:
            rows = json.load(source).get('places', [])
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for name, lat, lon, code, population, others in rows:
        place = {'name': name, 'lat': lat, 'lon': lon, 'kind': 'town', 'country': code, 'population': population, 'extent_km': 4, 'modern': ''}
        for alias in dict.fromkeys(plain(a) for a in [name, *others]):
            if len(alias) >= 3: out.setdefault(alias, []).append(place)
    return out


def distance(a, lat, lon):
    return math.hypot(a['lat'] - lat, (a['lon'] - lon) * math.cos(math.radians(lat)))


def locate(name, near=None):
    """The place for a map marker: the lists above, then the town list, then
    Mapbox Geocoding (cached). near=(lat, lon) picks the closest namesake.
    A dict like find() (+ 'source': 'list' | 'town' | 'mapbox'), or None."""
    place = find(name)
    if place: return {**place, 'source': 'list'}
    towns = local_index().get(plain(name)) or []
    if towns:
        best = min(towns, key=lambda p: distance(p, *near)) if near else towns[0]
        return {**best, 'source': 'town'}
    from app.providers.geocoding import geocode
    found = geocode(name)
    if found:
        return {'name': str(name).strip()[:60], 'lat': found[0], 'lon': found[1], 'kind': 'geocoded', 'modern': '', 'extent_km': 4, 'rank': 4, 'source': 'mapbox'}
    return None
