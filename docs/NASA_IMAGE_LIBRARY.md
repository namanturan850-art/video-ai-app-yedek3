# NASA Image and Video Library (stok kaynağı)

Anahtar gerekmez. Medyayı Tamamla, Pixabay ve Wikimedia Commons'ın yanında bu kaynakta da görsel arar.
Yalnız **görsel** eklendi; video desteklenmiyor (bkz. "Neden video yok" altta).

## Kullanılan resmî API

Uç nokta: `https://images-api.nasa.gov/search` (GET, anahtarsız). Resmî belge: https://images.nasa.gov/docs

Canlı uçtan 2026-10-20'de doğrulanan örnek yanıt şekli (`q=earth&media_type=image&page_size=1`):

```json
{"collection": {"items": [
  {"data": [{"nasa_id": "PIA00342", "title": "The Earth & Moon", "media_type": "image",
             "center": "JPL", "date_created": "1998-06-04T00:00:00Z",
             "description": "…", "keywords": ["Earth", "Galileo"], "secondary_creator": "NASA/JPL/USGS"}],
   "links": [{"href": "https://images-assets.nasa.gov/image/PIA00342/PIA00342~orig.jpg", "rel": "preview", "render": "image", "width": 1700, "height": 2164, "size": 267383},
             {"href": "…~medium.jpg", "width": 1005, "height": 1280, …},
             {"href": "…~small.jpg", "width": 502, "height": 640, …},
             {"href": "…~thumb.jpg", "width": 502, "height": 640, …}]}
]}}
```

Kullanılan alanlar: `collection.items[].data[0]` içinde `nasa_id`, `title`, `description`, `media_type`,
`center`, `date_created`, `keywords`, `secondary_creator`, (varsa) `copyright`; `collection.items[].links[]`
içinde `href`, `render`, `width`, `height` (yalnız `render=="image"` ve genişlik/yükseklik tam sayı olan
bağlantılar kullanılır — her görsel adayı için en az 1080 sınıfı bir sürüm bulunur, yoksa en büyüğü).

## Neden video yok

Arama yanıtı video klipler için **süre veya boyut vermiyor** (yalnız önizleme JPG'lerinin boyutu var).
Gerçek süre/boyut için her aday için ayrı bir `/asset/<nasa_id>` isteği ve video dosyasının kendisinin
incelenmesi gerekir — bu da aramayı önemli ölçüde yavaşlatır (Medyayı Tamamla hızını düşürmemek az önce
öncelikliydi). Şimdilik yalnız görsel eklendi; video ihtiyacı olursa ayrı bir iş olarak eklenir.

## Lisans / telif

NASA'nın kendi ürettiği içerik (NASA Media Usage Guidelines: https://www.nasa.gov/multimedia/guidelines/)
genel olarak telif hakkıyla korunmaz, izinsiz kullanılabilir. Nadir istisnalar için arama sonucunda
`copyright` alanı doluysa o öğe **atlanır** (`FilteredResult`), hiçbir zaman indirilmez.

## İndirme
Yalnız `images-assets.nasa.gov` adresinden indirilir. Kaynak sayfası `images.nasa.gov/details/<nasa_id>`.

## Doğrulama durumu
Yukarıdaki yanıt şekli 2026-10-20'de canlı uçtan (`images-api.nasa.gov`) doğrulandı. Bu ortamdan kalıcı ağ
erişimi yok; testler bu belgelenmiş yanıt biçimini taklit eder. Canlı bağlantıyı kendi bilgisayarınızda
**Ayarlar → NASA Görsel Kütüphanesi → Bağlantıyı Test Et** ile bir kez doğrulayın.
