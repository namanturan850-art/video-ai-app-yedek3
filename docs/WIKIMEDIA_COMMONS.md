# Wikimedia Commons (stok kaynağı)

Anahtar gerekmez. Medyayı Tamamla, Pixabay'in yanında Wikimedia Commons'ta da arar. Tarih, arkeoloji, müze ve harita sahnelerinde Commons'a önce bakılır.

**Pexels şu an kapalı.** Pexels yeni anahtar vermiyor. Kod ve anahtar alanı duruyor; açmak için `app/stock/providers.py` içinde `PEXELS_ENABLED = True` yapın.

## Kullanılan resmî API (MediaWiki Action API)

Uç nokta: `https://commons.wikimedia.org/w/api.php` (GET, anahtarsız).

| Parametre | Değer | Belge |
|---|---|---|
| `action=query`, `format=json`, `formatversion=2` | standart sorgu, JSON, sayfa listesi | https://www.mediawiki.org/wiki/API:Query , https://www.mediawiki.org/wiki/API:JSON_version_2 |
| `generator=search`, `gsrsearch`, `gsrnamespace=6`, `gsrlimit=30`, `gsroffset` | Dosya ad alanında tam metin arama, sayfalama | https://www.mediawiki.org/wiki/API:Search |
| `filetype:bitmap` / `filetype:video` (aramanın içinde) | yalnız fotoğraf/bitmap veya video | https://www.mediawiki.org/wiki/Help:CirrusSearch#Filetype |
| `prop=imageinfo`, `iiprop=url\|size\|mime\|mediatype\|extmetadata`, `iiurlwidth=1920` | dosya adresi, boyut, tür, 1920 px küçük resim (`thumburl`, `thumbwidth`, `thumbheight`), lisans bilgisi | https://www.mediawiki.org/wiki/API:Imageinfo |
| `iiextmetadatafilter` | `LicenseShortName`, `LicenseUrl`, `Artist`, `Credit`, `ImageDescription`, `ObjectName`, `NonFree`, `Restrictions`, `AttributionRequired` | https://www.mediawiki.org/wiki/Extension:CommonsMetadata |

- **User-Agent:** her istekte uygulamanın adı ve proje adresi gönderilir (`AIVideoStudio/1.0 (…; https://github.com/naman85331/video-ai-app)`). Bu, Wikimedia User-Agent politikasının istediği şeydir: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
- **İndirme:** dosyalar yalnız `upload.wikimedia.org` adresinden indirilir. Kaynak sayfası `commons.wikimedia.org` adresidir.

## Lisans kuralı (YouTube'da para kazanılan video için)
- **Kabul edilenler:** Public Domain, CC0, CC BY (her sürüm), CC BY-SA (her sürüm).
- **Elenenler:** NC veya ND içeren lisanslar, “fair use”, `NonFree` işaretli dosyalar, `Restrictions` (ör. marka/kişilik hakkı) dolu olanlar ve lisansı belirsiz olanlar.
- **Kaydedilenler:** her medya için yazar (`Artist`, yoksa `Credit`), lisans adı ve bağlantısı, dosya adı ve Commons sayfası. Bilgiler YouTube açıklamasına “Görsel kaynakları” bölümü olarak eklenir (Almanca videoda başlık “Bildquellen”).

## Görsel ve video
- **Görsel:** 1920 px küçük resim kullanılır. Videoda Pixabay görselleri gibi hafif kamera hareketiyle (yavaş zoom/kaydırma) gösterilir.
- **Video:** Commons videoları WebM biçimindedir. İndirilen WebM, FFmpeg ile ilk 60 saniyesi sessiz H.264 MP4'e çevrilir. Uygulamanın geri kalanı yalnız MP4 görür.
- **Alaka kontrolü:** Commons adayları diğer kaynaklarla aynı kontrolden geçer: üç kare, en az 7/10 puan ve ön eleme.

## Doğrulama durumu
Bu değişiklik yazılırken geliştirme ortamından Wikimedia'ya ağ erişimi yoktu. Testler belgelenmiş yanıt biçimini taklit eder. Canlı API'yi kendi bilgisayarınızda **Ayarlar → Wikimedia Commons → Bağlantıyı Test Et** ile bir kez doğrulayın.
