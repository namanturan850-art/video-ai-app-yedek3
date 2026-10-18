# Uzun önizleme: kalan güvenilirlik düzeltmeleri

Temel: güncel `main` / `a15f6e8` (PR #102). Ayrı dal: `fix/long-preview-rebuffer`.
Önceki oynatma, animasyon, AI paketi ve ses önbelleği değişiklikleri korunur.

## Kod

- Tampon tükendikten sonra yeniden başlatma kararı, ilk parçadan itibaren üretilmiş toplam süre yerine mevcut video saatinden sonraki gerçek kesintisiz tampona bakar. Oynanmış veya silinmiş parçalar hazır süre sayılmaz; tampon aralıkları arasındaki boşluklar gizlenmez.
- Yeniden hazırlama hedefi mevcut oynatma konumundan kalan süreye göre hesaplanır. Filmin sonuna yakın, artık hazırlanamayacak kadar uzun bir tampon beklenmez.
- Hazırlama hızı geçmişi kullanılan son üç ölçümle sınırlıdır; oturum uzadıkça kullanılmayan ölçümler birikmez.
- Windows işine ön yüz testleri eklendi. Manuel çalıştırmada 64 veya 180 saniye soğuk önbellek kontrolü seçilebilir; PR kontrolü 64 saniyede kalır. Bu yapılandırma tek başına Windows test sonucu değildir.

## Dış sınırlar

İlk görüntü ve ileri tampon hazırlığının maliyeti devam eder; donanımdan bağımsız anında oynatma vaadi yoktur. Bu değişiklik, hazırlama işlemini gizlemek yerine tampon tükendikten sonraki davranışı düzeltir. Saatler süren gerçek kullanıcı projeleri burada denenmedi.

Bu Linux ortamında gerçek Windows ve GPU çalışması yapılmadı. Canlı Gemini çağrısı, kullanıcının ayrıca ücret onayı kuralı nedeniyle yapılmadı. Mevcut Gemini onay/yanıt akışı yerel testlerde servis yanıtı taklidiyle doğrulanır. Kullanıcı projesi değiştirilmez veya silinmez; testler geçici sentetik projeler kullanır.

## Yeni doğrulama

- **84 Node testi geçti.** Yeni dört test eski kod üzerinde dört hatayı da yeniden üretti; güncel kodda geçti. Bunlar tampon tükenmesi/son bölüm/ayrık tampon/ölçüm geçmişi regresyonlarıdır.
- **Gerçek Chromium + FFmpeg, 180 saniye, beş eşzamanlı ek katman, 720p:** 5400 kare, ortalama 29,990 FPS; parça sınırında en uzun kare aralığı 50,1 ms. Başlatma dahil en uzun kare aralığı 100 ms. Oynatma içinde yeniden tampon beklemesi yok, tarayıcı hatası yok. Tek video/blob, sonda geri arama/yeniden oynatma ve gerçek ses miks formu kaydı kontrolleri geçti.
- Soğuk başlangıç ayrıca ölçüldü: ilk duraklatılmış görüntü **11,58 sn**, Oynat sonrası ileri tampon hazırlığı **82,21 sn**. Üç dakikalık projede başlangıç hazırlığı sıfırlanmadı; bu sonuç gizlenmiyor.
- [180 saniye ham ölçüm](examples/continuous_preview_cold180.json). Bu sentetik kontrol, saatler süren kullanıcı projesi veya gerçek Windows/GPU sonucu değildir.
- JavaScript sözdizimi, Windows iş akışı YAML yükleme ve `git diff --check` kontrolleri geçti.
- **Dört gerçek MP4 uçtan uca testi geçti** (121,18 sn): üç animasyon örneğinde JSON → doğrulama → taslak → gerçek JPEG → onaysız uygulamanın reddi → seçim/onay → 1080p/30 FPS final; ayrıca tam paket → taklit Gemini yanıtı → içe aktarma → taslak/onay → kısa gerçek render. Gerçek Gemini çağrısı yapılmadı. Bir bağımlılık deprecation uyarısı var; hata veya atlanan test yok.
- GitHub Actions sonuç sorgusu bu oturumda `Forbidden` yanıtı verdi; uzak Windows işi çalışmış kabul edilmedi.
