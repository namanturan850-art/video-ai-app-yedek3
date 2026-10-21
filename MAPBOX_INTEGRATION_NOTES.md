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
- İstek başarısızsa (401/403, 404, 422, 429, ağ hatası, okunamayan resim): Türkçe uyarı “Eğik görünüm alınamadı (…); düz uydu görünümü kullanıldı.” ve eski düz karo görünümü; o da olmazsa renkli kabartma harita (uydu stilinde koyu neon harita hiç kullanılmaz).
- Kutu kapalıyken yalnız düz karo görünümü (eski davranış) kullanılır.
- Tanılama: render uyarılarında her harita için “Harita (…): eğik görünüm (eğim …°, açı …°) — istek: <adres>?access_token=pk.***abcd” satırı; “Bağlantıyı Test Et” eğik isteği de dener ve adresi (anahtar gizli) gösterir.

## Aylık güvenlik sınırı

- Uygulama Mapbox'a gönderilen istekleri her ay sayar: karo ve eğik görüntü ayrı (`data/mapbox_usage.json`). Yeni ayda sayaç sıfırdan başlar. Ayarlar → Mapbox durum satırında “Bu ay: X karo / Y eğik görüntü” yazar.
- Varsayılan sınırlar: 600.000 karo, 40.000 eğik görüntü (Ayarlar → Mapbox'tan değiştirilebilir). Sınıra gelince istek gönderilmez; çizilmiş harita kullanılır ve “Bu ayki Mapbox güvenlik sınırına ulaşıldı.” uyarısı çıkar.
- Önceden indirilen karo/eğik görüntü `data/tile_cache/` klasöründen kullanılır; yeniden istek atılmaz ve sayılmaz.
- 401/403 uyarısı: “Mapbox hesabında kullanım sınırı veya ödeme sorunu olabilir.” Bu sınır yalnız uygulamanın kendi sayacıdır; Mapbox hesabındaki gerçek ücret/kota Mapbox panelinden kontrol edilmelidir.

## Yer arama (Geocoding) — yalnız harita işaretleri için

- Bir harita işaretindeki yer (örn. “Genêts”) çevrimdışı listelerde (elle derlenen liste + anıtlar, GeoNames 15 000+ şehirler, GeoNames 1 000+ kasabalar ve Natural Earth yerleşimleri) yoksa **tek istek**:
  `GET https://api.mapbox.com/search/geocode/v6/forward?q=<yer adı>&access_token=<anahtar>`
  (adres Ayarlar dosyasında `geocode_url`; kod değiştirmeden düzeltilebilir).
- Yanıttan **yalnız** standart GeoJSON alanı okunur: `features[0].geometry.coordinates` = `[boylam, enlem]` (RFC 7946). Başka alan kullanılmaz/varsayılmaz.
- Yanıtlar (bulunamadı dahil) `data/geocode_cache.json` dosyasında saklanır; aynı ad bir daha sorulmaz. Ağ/anahtar hatası saklanmaz.
- Hiçbir yerde bulunamazsa video stok videoya düşmez: aynı işaretteki başka yer, sahnede/komşu sahnelerde/metinde geçen en yakın bilinen yer ile harita çizilir ve Türkçe uyarı gösterilir.
- Bu istek de bu ortamdan gerçek anahtarla **denenmedi** (api.mapbox.com engelli); testler sahte HTTP yanıtıyla yapıldı.

## Doğrulama durumu

- Bu desen Mapbox'ın herkese açık API belgelerindeki Raster Tiles API biçimidir; **bu geliştirme ortamından docs.mapbox.com ve api.mapbox.com'a erişilemedi**, gerçek bir anahtarla **hiç denenmedi**.
- Adres şablonu Ayarlar → Mapbox → “Uydu karo adresi” alanındadır; Mapbox belgeleri farklıysa kod değiştirmeden düzeltilebilir (yalnız `https://api.mapbox.com/` ile başlayan ve `{z}`, `{x}`, `{y}` içeren adres kabul edilir; anahtar adrese yazılmaz).
- Karolar `data/tile_cache/` klasöründe önbelleğe alınır (dosya adında anahtar yoktur). Kullanım/kota Mapbox hesabınıza göre ücretlendirilebilir.
- Eğik görünüm (Static Images API) de bu ortamdan denenemedi: api.mapbox.com'a bağlantı vekil sunucu tarafından engellendi (403) ve gerçek anahtar yok. Testler sahte sağlayıcıyla, aynı kamera modeliyle çizilmiş yapay manzara resmiyle yapıldı.


## 2026-10-21 — NAMAN stil kartları

Stiller Ayarlar ve Render ekranlarında aynı seçiciyle kaydedilir. Sabit hazır
stil kimlikleri ve `mapbox://styles/{owner}/{style}` bağlantısıyla eklenen en
çok 20 özel stil desteklenir. Bağlantıda sorgu, anahtar, farklı sunucu veya
fazladan yol kabul edilmez. Önizleme yalnız kayıtlı kart için, aynı köken ve
ayar başlığı korumalı POST isteğiyle alınır. API anahtarı yalnız sunucudaki
Mapbox isteğinde kullanılır; HTTP istemci günlüklerinde gizlenir.

Seçili stil için mevcut Static Images şablonunun owner/style kısmı kullanılır.
Düz görünüm de aynı stilin Static Images yanıtlarından birleştirilir: z/x/y
karosunun merkezi hesaplanır, 256×256 @2x resim zoom=z-1 ile istenir. Böylece
512 px karo ve Web Mercator ayak izi korunur; ek bir belgelenmeyen karo uç
noktası eklenmez. Bu istekler **static** sayacına yazılır. Eğik görünüm aynı
stilin doğrudan statik görüntüsünü kullanır. Stil URI’si oluşturulan sahne
kimliğine katılır; farklı stil için eski motion önbelleği yeniden kullanılmaz.

Önizleme örnek konumu Paris’tir; tüm harita konumunu değiştirmez. Önizlemeler
Mapbox isteğine sayılır, yerel URL tabanlı önbellek tekrar istekleri azaltır.
Aynı Studio stilini Mapbox’ta yeniden yayımlamak için mevcut dosya önbelleğini
zorla tazeleme bu sürümde eklenmedi.

Kaynak: Mapbox resmî JavaScript SDK Static Images isteği ve owner/style
parametreleri: https://github.com/mapbox/mapbox-sdk-js/blob/9680651c01a6ca0f52bd113ce306e016f4fb6d99/services/static.js
Bu kaynak GitHub üzerinden incelendi. Konsol, docs ve gerçek API bu ortamda
403 ile engellendi; canlı hesap doğrulaması yapılmadı. Testlerdeki harita
resimleri açıkça sentetiktir; hazır stillerin hesaptaki erişimi önizleme veya
Bağlantıyı Test Et ile ayrıca görülür.
