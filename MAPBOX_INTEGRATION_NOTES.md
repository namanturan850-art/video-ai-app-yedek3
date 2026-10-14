# Mapbox (uydu haritası) entegrasyon notları

Kullanım: Video ekranı → **Harita stili → Uydu görüntüsü**. Anahtar Ayarlar → Mapbox bölümünde girilir; ayar dosyasında şifreli saklanır, `.env` veya kaynak dosyalarına yazılmaz.

## Kullanılan istek (yalnız bu)

- Mapbox **Raster Tiles API**, `mapbox.satellite` tileset'i (satellite-v9 stilinin uydu katmanı), 512 px (@2x) JPEG karo:
  `GET https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90?access_token=<anahtar>`
- Karo düzeni: Web Mercator (XYZ), z = yakınlık, x/y = karo numarası.
- Yanıt: resim (JPEG). 401/403 → anahtar kabul edilmedi, 404 → karo yok, 429 → hız sınırı, diğerleri → sunucu hatası. Hepsi Türkçe uyarıya çevrilir ve çizilmiş (koyu) harita kullanılır; iş durmaz.
- Görüntüde sağ altta “© Mapbox” yazar (Mapbox kullanım koşulları atıf ister).

## Doğrulama durumu

- Bu desen Mapbox'ın herkese açık API belgelerindeki Raster Tiles API biçimidir; **bu geliştirme ortamından docs.mapbox.com ve api.mapbox.com'a erişilemedi**, gerçek bir anahtarla **hiç denenmedi**.
- Adres şablonu Ayarlar → Mapbox → “Uydu karo adresi” alanındadır; Mapbox belgeleri farklıysa kod değiştirmeden düzeltilebilir (yalnız `https://api.mapbox.com/` ile başlayan ve `{z}`, `{x}`, `{y}` içeren adres kabul edilir; anahtar adrese yazılmaz).
- Karolar `data/tile_cache/` klasöründe önbelleğe alınır (dosya adında anahtar yoktur). Kullanım/kota Mapbox hesabınıza göre ücretlendirilebilir.
