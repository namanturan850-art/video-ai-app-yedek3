# Internet Archive (stok kaynağı, film arşivi)

Anahtar gerekmez. Medyayı Tamamla, Pixabay / Wikimedia Commons / NASA'nın yanında Internet Archive'daki
filmlerde de **video** arar. Tarih/arkeoloji/müze sahnelerinde Wikimedia ile birlikte önce bakılır.
Görsel aranmaz (yalnız film).

## Kullanılan resmî uç noktalar

1. **Arama:** `https://archive.org/advancedsearch.php` (GET)
   - `q` = `(<sorgu kelimeleri>) AND mediatype:(movies) AND (licenseurl:*publicdomain* OR licenseurl:*licenses\/by\/* OR licenseurl:*licenses\/by-sa\/*)`
     (joker içindeki `/` işaretleri `\/` diye yazılmalı; yazılmazsa arama `BACKEND_ERROR` döner — 2026-10-20'de canlı doğrulandı)
   - `fl[]=identifier`, `fl[]=title`, `fl[]=licenseurl`, `rows=12`, `page`, `output=json`
   - Yanıt: `response.docs[]` (her biri `identifier`, varsa `title`, `licenseurl`).
   - Belge: https://archive.org/advancedsearch.php , alanlar: https://archive.org/developers/metadata-schema/index.html
2. **Öğe bilgisi:** `https://archive.org/metadata/<identifier>` (GET) — her arama sonucu için bir istek, en fazla 6'sı aynı anda.
   - Kullanılan alanlar: `metadata.licenseurl`, `metadata.title`, `metadata.description`, `metadata.creator`,
     `server` (dosyanın bulunduğu veri düğümü, ör. `ia800300.us.archive.org`), `dir` (ör. `/21/items/<identifier>`),
     `files[]` içinde `name`, `format`, `size`, `width`, `height`, `length` (saniye).
   - Belgeler: https://doc-tools.readthedocs.io/en/ia-test-gsod/md-read.html ,
     `width`/`height`/`length` için: https://blog.archive.org/2013/02/09/files-xml-and-metadata-api-now-showing-video-files-width-height-and-duration/
3. **İndirme:** `https://<server><dir>/<dosya adı>` — veri düğümünden doğrudan (yönlendirme yok).
   Düğüm adresi yalnız `ia<rakamlar>.us.archive.org` biçiminde kabul edilir. Yöntem: https://blog.archive.org/2012/04/26/downloading-in-bulk-using-wget/

## Lisans kuralı (YouTube'da para kazanılan video için)
- **Kabul:** Public Domain Mark (`creativecommons.org/publicdomain/mark/`), CC0 (`publicdomain/zero/`),
  CC BY (`licenses/by/`), CC BY-SA (`licenses/by-sa/`).
- **Elenen:** NC veya ND içeren lisanslar, lisans adresi olmayanlar, başka her şey. Arama sorgusu zaten süzer,
  öğe bilgisindeki `licenseurl` ayrıca tekrar kontrol edilir.
- **Kaydedilen:** yazar (`creator`), lisans adı ve adresi, film adı ve `archive.org/details/<identifier>` sayfası.
  YouTube açıklamasına “Görsel kaynakları” bölümünde yazılır.

## Dosya seçimi
- Yalnız `.mp4` dosyalar; `width`, `height`, `length` ve `size` bilinmeli; en fazla 250 MB.
- Eski filmler çoğu zaman 4:3 ve SD'dir. Bu kaynak için kalite kontrolü 4:3–16:9 oran ve en az 640×480 kabul eder
  (diğer kaynaklar için kural değişmez: 16:9 ve en az 1280×720). Videoda kırpılarak 16:9 ekranı doldurur.
- HD (genişlik ≥ 1280) varsa en küçük HD dosya, yoksa en yüksek çözünürlüklü dosya seçilir.
- Önizleme: öğedeki `Thumbnail` biçimli JPG'lerden başlangıç/orta/son üçü (CLIP ve AI kontrolü için).

## Doğrulama durumu
2026-10-20'de canlı doğrulandı: arama yanıtı (`response.docs[]` içinde `identifier`, `title`, `licenseurl`) ve
öğe bilgisi (`server`, `dir`, `files[]` içinde `width`/`height`/`length`/`size` metin olarak, `format: "Thumbnail"`
önizlemeler, `metadata.licenseurl`/`creator`) beklenen biçimde. Testler bu biçimi taklit eder.
