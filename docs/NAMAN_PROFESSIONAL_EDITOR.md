# NAMAN profesyonel kurgu editörü — doğrulama raporu

## Çalışan akışlar

- Zaman cetveline tıklama, playhead sürükleme, zaman kodu girişi, beş saniye ve tek kare ileri/geri hareket ortak seek işlevini kullanır.
- Ses, aktif video/motion önizlemesi, altyazı ve kelime vurgusu aynı global zamanı izler. Oynatma sırasında video zamanı her animasyon karesinde zorla yazılmaz; yalnız klip değişiminde, duraklatılmış seek'te veya anlamlı kaymada düzeltilir.
- Klip tutamaçları komşu sınırı birlikte taşır. Klip gövdesini sürüklemek aynı sahnedeki slot sırasını değiştirir ve sahneyi boşluksuz yeniden dizer.
- Backend güncel plan/revizyonu, çalışan medya işini, sahne ve klip kilitlerini, kare sınırını, ses sahnesi kapsamını ve kaynak video süresini doğrular.
- Otomatik motion klipleri kaynak metadata'sına göre doğru kanala gider. Motion önizleme gerçek üretilmiş dosyayı kullanır; basit “Harita” yazısı motion önizlemesi sayılmaz.
- Harita/infografik düzenleme mevcut güvenli motion şema doğrulamasını ve tek-slot `motion_edit` üretimini kullanır. Eski üretilmiş dosyalar proje arşivinde korunur; diğer slotlar yeniden hazırlanmaz.

## Bilerek sınırlı kalanlar

- Motion motorunun şemasında bulunmayan serbest renk, font boyutu ve keyfi Mapbox kamera/çizgi alanları eklenmedi. Bunları arayüzde varmış gibi gösterip render sırasında yok saymak yerine, mevcut motorun doğrulayabildiği `template`, `data`, `emphasis` alanları sunuldu.
- Harita yerleri ve sayısal olgular anlatımla mevcut validator üzerinden eşleşmek zorundadır.
- Gerçek Windows masaüstü görsel testi, canlı Mapbox/Gemini çağrısı ve uzun final MP4 üretimi bu Linux oturumunda yapılmadı.
- Arşivin “Ekran” ve “Sesler” sekmeleri yalnız gerçekten o medya türünde kayıt varsa içerik gösterir; uygulamada bulunmayan kayıt/yükleme altyapısı taklit edilmedi.

## Test özeti

- 11 ilgili Python testi geçti.
- 2 DOM kullanıcı etkileşimi testi geçti.
- JavaScript sözdizimi ve `git diff --check` geçti.
- Geniş render/motion paketi 69 testten sonra güncel şema 13'e rağmen 12 bekleyen eski testte durdu. Bu test bu dalın koduna dokunmayan veritabanı yükseltme beklentisidir.
