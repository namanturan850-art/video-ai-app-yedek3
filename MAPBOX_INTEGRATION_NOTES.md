# Mapbox (uydu haritası) entegrasyon notları

Kullanım: Video ekranı → **Harita stili → Uydu görüntüsü**. Anahtar Ayarlar → Mapbox bölümünde girilir; ayar dosyasında şifreli saklanır, `.env` veya kaynak dosyalarına yazılmaz.

## Kullanılan istek (yalnız bu)

- Mapbox **Raster Tiles API**, `mapbox.satellite` tileset'i (satellite-v9 stilinin uydu katmanı), 512 px (@2x) JPEG karo:
  `GET https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.jpg90?access_token=<anahtar>`
- Karo düzeni: Web Mercator (XYZ), z = yakınlık, x/y = karo numarası.
- Yanıt: resim (JPEG). 401/403 → anahtar kabul edilmedi, 404 → karo yok, 429 → hız sınırı, diğerleri → sunucu hatası. Hepsi Türkçe uyarıya çevrilir ve çizilmiş (koyu) harita kullanılır; iş durmaz.
- Görüntüde sağ altta “© Mapbox” yazar (Mapbox kullanım koşulları atıf ister).

## Eğik görünüm (Static Images API)

- Ayarlar → Mapbox → **“Eğik görünüm”** kutusu (varsayılan açık). Açıkken [OK], [ROTA], [HARİTA], [BÖLGE], [YAKINLAŞ] sahnelerinin her biri için **tek istek**:
  `GET https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x?access_token=<anahtar>`
  (adres deseni proje sahibinin verdiği biçimdir; Ayarlar → Mapbox → “Eğik görünüm adresi” alanından düzeltilebilir).
- Kullanılan değerler: 1280×720 (@2x = 2560×1440), eğim (pitch) 60 (rota/ok) veya 55 (bölge/yer), açı (bearing) 0 — kuzey yukarıda, yönler haritadaki gibi, yakınlık tüm noktalar resmin ~%60'ına sığacak şekilde. Kodda sınırlar: pitch 0–60, zoom 0–22, en/boy ≤ 1280 (doğrulanmadı; API de denetler).
- Çizgi ve isimler, Mapbox GL kamerasının yaklaşık modeliyle (36,87° görüş açısı, 512 px dünya karoları) resmin üstüne çizilir; gerçek görüntüde birkaç piksel kayma olabilir.
- Kamera: sahne tüm eğik resimle başlar, sonunda varış noktasına %45 yakınlaşır; uzak (üst) kenarda hafif sis.
- İstek başarısızsa (401/403, 404, 422, 429, ağ hatası, okunamayan resim): Türkçe uyarı “Eğik görünüm alınamadı (…); düz uydu görünümü kullanıldı.” ve eski düz karo görünümü; o da olmazsa koyu harita.
- Kutu kapalıyken yalnız düz karo görünümü (eski davranış) kullanılır.
- Tanılama: render uyarılarında her harita için “Harita (…): eğik görünüm (eğim …°, açı …°) — istek: <adres>?access_token=pk.***abcd” satırı; “Bağlantıyı Test Et” eğik isteği de dener ve adresi (anahtar gizli) gösterir.

## Doğrulama durumu

- Bu desen Mapbox'ın herkese açık API belgelerindeki Raster Tiles API biçimidir; **bu geliştirme ortamından docs.mapbox.com ve api.mapbox.com'a erişilemedi**, gerçek bir anahtarla **hiç denenmedi**.
- Adres şablonu Ayarlar → Mapbox → “Uydu karo adresi” alanındadır; Mapbox belgeleri farklıysa kod değiştirmeden düzeltilebilir (yalnız `https://api.mapbox.com/` ile başlayan ve `{z}`, `{x}`, `{y}` içeren adres kabul edilir; anahtar adrese yazılmaz).
- Karolar `data/tile_cache/` klasöründe önbelleğe alınır (dosya adında anahtar yoktur). Kullanım/kota Mapbox hesabınıza göre ücretlendirilebilir.
- Eğik görünüm (Static Images API) de bu ortamdan denenemedi: api.mapbox.com'a bağlantı vekil sunucu tarafından engellendi (403) ve gerçek anahtar yok. Testler sahte sağlayıcıyla, aynı kamera modeliyle çizilmiş yapay manzara resmiyle yapıldı.
