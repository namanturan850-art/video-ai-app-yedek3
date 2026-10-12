"""Local place list for map graphics: common places with their names in
German, English, Turkish, Spanish and French (lat, lon in degrees). Places
not listed here are asked from the AI (or the map is not drawn)."""
import re
import unicodedata

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
]


def plain(text):
    text = unicodedata.normalize('NFKD', str(text or '').replace('ß', 'ss').replace('ı', 'i')).casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


INDEX = sorted(((plain(name), lat, lon, names.split('|')[0]) for lat, lon, names in PLACES for name in names.split('|')),
               key=lambda item: -len(item[0]))


def lookup(name):
    """(lat, lon, display name) for a place name, or None."""
    wanted = plain(name)
    if not wanted: return None
    for alias, lat, lon, _ in INDEX:
        if alias == wanted: return lat, lon, name
    for alias, lat, lon, _ in INDEX:  # “die Bermuda-Inseln”, “Bermuda Triangle area”
        if len(alias) >= 3 and f' {alias} ' in f' {wanted} ': return lat, lon, name
    return None


def spoken_places(text):
    """Places from the list spoken in the text: [(name exactly as written, lat, lon)] in reading order."""
    text = str(text or '')
    spans = [(m.start(), m.end(), plain(m.group())) for m in re.finditer(r'[^\W_]+', text)]
    found, taken, used = [], set(), set()
    for alias, lat, lon, _ in INDEX:
        size = len(alias.split())
        if len(alias) < 3 or (lat, lon) in taken: continue
        for i in range(len(spans) - size + 1):
            if any(j in used for j in range(i, i + size)): continue
            if ' '.join(w for _, _, w in spans[i:i + size]) == alias:
                found.append((spans[i][0], text[spans[i][0]:spans[i + size - 1][1]], lat, lon))
                taken.add((lat, lon)); used.update(range(i, i + size))
                break
    return [item[1:] for item in sorted(found)]
