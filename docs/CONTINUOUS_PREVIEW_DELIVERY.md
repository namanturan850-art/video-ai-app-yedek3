# Soğuk önbellek ve kesintisiz önizleme — teslim

Dal: `fix/gapless-cold-preview`; önceki `fix/smooth-preview-reference-plans` çalışmasının `69ce896` commit’i üzerinden devam edildi. Mevcut yedi izli editör, AI paketi, 300 teknik referans seçimi, taslak/onay zinciri ve final render motoru korundu. Veritabanı şeması veya kullanıcı verisi değiştirilmedi/silinmedi.

## Tamamlanan düzeltmeler

1. **Parça başında video değiştirme kaldırıldı.** Destekleyen tarayıcılarda mevcut dört saniyelik proxy’ler, tek video öğesinde MediaSource tamponuna ekleniyor. Parça sınırında yeni çözücü/ses oynatıcısı başlatılmıyor. Proxy yeniden kodlanmadan parçalı MP4’e paketleniyor. Zaman damgaları, AAC priming/edit list ve kare aralıkları gerçek FFmpeg/ffprobe ile doğrulanıyor.
2. **Soğuk önbellek oynatma gibi gösterilmiyor.** Hazırlama hızı ölçülerek yeterli ileri tampon hazırlanıyor. Mevcut Oynat/Duraklat kontrolleri korunuyor; hazırlık metni ve saniye ilerlemesi gösteriliyor. Ses tek başına ilerlemiyor. Bekleme, başlangıç hazırlığına ayrılıyor; uzun testte oynatma sırasında yeniden tampon beklemesi olmaması ayrıca denetleniyor. İleri tampon 60 saniyeyle, geri tampon oynanmış yaklaşık sekiz saniyeyle sınırlı. Hazırlanmış fakat henüz oynanmamış kareler silinmiyor.
3. **Hazırlama maliyeti azaltıldı.** Belgesel aktörleri proxy’de doğrudan seçilen çözünürlükte çiziliyor; keyframe/kamera koordinatları 1920×1080 düzleminden ölçekleniyor. Final çizimi 1080p yolunu koruyor. Uygun, arka arkaya gelen sabit metinler yalnız geçici proxy belgesinde tek RGBA katmanına birleştiriliyor; boş ekran yerine yalnız içeriğin sınır kutusu işleniyor. Hareketli, farklı zamanlı, efektli katmanlar ve araya giren öğeler birleştirilmiyor. Özgün belge, katman sırası ve kilitler değişmiyor. Örnek dört saniyelik beş katmanlı profil, bu birleştirme öncesi yaklaşık 11,7 saniye, birleştirme sonrası 5,7 saniye ve yalnız dolu alanı işleme sonrası 4,6 saniye sürdü; bütün sahneler için sabit hız garantisi değildir.
4. **Ses hesapları parça başında başlamıyor.** Editörün kayıtlı ses miksinin normalizasyon, fade ve ducking durumu tüm proje saatiyle bir kez hesaplanıp önbellekleniyor; proxy’ler bu miksin kesitini kullanıyor. Mevcut final ses operatörleri paylaşılıyor; yeni bir ses motoru yok. 24 bit FLAC önbellek ile tam kayan noktalı referans arasındaki fark testte 3×10⁻⁷’den küçük. AAC paketleme gecikmesi ayrıca korunuyor. Görsel değişiklikler ses önbelleğini gereksiz yere bozmaz; ses ayarı değişiklikleri yeni miks oluşturur ve timeline revizyonu değişmese bile tarayıcıdaki ses tamponunu yeniler.
5. **Taşıma kontrolleri tamamlandı.** Duraklatılmış görüntüde arama, oynarken hız değişimi, durdurma, geri arama, kalite ve kurgu revizyonu değişikliği aynı çözücüye uygulanıyor. Ses panelindeki “Klip seçin” seçeneğinin geçersiz SFX kimliği gönderip kaydı engellemesi de düzeltildi. Ses ayarı kaydı, timeline revizyonu aynı kalsa bile mevcut ses tamponunu yeniler. Eski istekler iptal ediliyor; geç gelen eski sonuç yeni kurguya eklenmiyor. Normal `play()`/pause iptali çözücü hatası sayılmıyor. Geçici dolu çözücü kuyruğu yeniden deneniyor. MediaSource/codec desteği yoksa açıklamayla önceki parça oynatıcısı kullanılıyor; destek varmış gibi davranılmıyor.
6. **Windows test yolu hazırlandı.** Tarayıcı testinin Python, tarayıcı ve geçici klasör yolları taşınabilir hale getirildi. Mevcut Windows GitHub Actions işine yeni FFmpeg/ses testleri ve 64 saniyelik soğuk önbellek Chromium ölçümü eklendi. Test ölçümü artifact olarak kaydediliyor. Bu, Windows testinin burada çalıştırıldığı anlamına gelmez.

## Doğrulama

- **199 ayrı Python testi geçti.** Önce 195 testlik regresyon grubu; ardından ek testler ve değişen proxy/ses/render yolları yeniden çalıştırıldı. Manuel Plan, interval/geçiş, onay, kilit, seslendirme, altyazı, undo ve görüntü korunması kapsandı.
- **80 Node testi geçti.** Yeni testler soğuk tampon, oynatma saati, duraklatılmış arama, hız, revizyon/istek iptali, geç gelen sonuç, tampon temizliği, normal pause ve geçici kuyruk durumlarını içerir.
- Gerçek FFmpeg: 720p/1080p 30 FPS; tek tip 1/30 saniye video paketleri; AAC ilk paket saati; RGBA geometri/kamera/etiket/alfa; sabit metinlerin sırası ve özgün belgenin korunması; tam miks ile dört saniyelik ses kesitlerinin karşılaştırması.
- Üç gerçek JSON → doğrulama → taslak → JPEG → reddedilen onay → geçerli seçim/onay → **1080p/30 FPS final MP4** testi yeniden geçti. Gerçek ffprobe ses/video sürelerini de denetledi.
- Gerçek ses miks formu Chromium testinde kaydedildi; ayar veritabanında doğrulandı, özgün timeline belgesi değişmedi ve mevcut video/ses tamponu yenilendi. [Ham kontrol sonucu](examples/continuous_preview_mix_controls.json).
- Mevcut Manuel Plan penceresi Chromium testi geçti: yedi iz, dosya yükleme, hatalı önerinin ayrılması, önizleme, iptal/onay ve kaynakların korunması; dış ağ/AI çağrısı yok.

Son kodla gerçek ölçümler:

| Kontrol | 720p / 64 sn | 1080p / 12 sn |
| --- | ---: | ---: |
| Gösterilen kare bildirimi | 1920 | 360 |
| Ortalama FPS | 29,98 | 29,84 |
| Parça sınırında en uzun kare aralığı | 33,4 ms | 33,3 ms |
| İlk başlatma dahil en uzun aralık | 83,4 ms | 100 ms |
| İlk duraklatılmış proxy hazırlığı | 10,49 sn | 18,24 sn |
| Oynat sonrası ileri tampon hazırlığı | 49,66 sn | 20,77 sn |
| Oynatma sırasında yeniden tampon bekleme | Yok | Yok |
| Tarayıcı hatası | 0 | 0 |

[64 saniye ham sonuç](examples/continuous_preview_cold64.json) · [1080p ham sonuç](examples/continuous_preview_1080p12.json).

Hazırlama süreleri özellikle gizlenmedi: ilk görüntünün hazır olması ve Oynat sonrası güvenli ileri tampon ayrı ölçüldü. Bu iki iş tamamlanınca ölçülen oynatma yaklaşık 30 FPS; başlangıç hazırlığı sıfır saniye değildir. Test, arşiv/proxy önceden ısıtılmadan yeni bir sentetik proje oluşturur; videoları uygulama kendisi hazırlar. Oynatma öncesi bekleme ile oynatma FPS’i ayrı ölçülür. Tek video/blob kullanımı, parça sınırı kare aralığı, oynatma sırasında `waiting` olmaması ve sonda geri arayıp yeniden oynatma zorunlu kontrollerdir.

## Sınırlar ve dış doğrulama

İlk proxy ve ileri tampon hazırlığının süresi işlemci, çözünürlük, kaynak ve katmanlara bağlıdır; sıfır başlangıç beklemesi iddiası yoktur. Hazırlığı sonradan oynatma içine yayarak akıcıymış gibi gösterme kaldırıldı. Gerçek zamanlı kodlamayı kaldıramayan donanımda hazırlık gerekir; hiçbir yazılım bütün donanım ve sınırsız katmanda 30 FPS garantisi veremez.

Mevcut eski otomatik dekorasyonlar ve güvenlik/katman sınırları korunur; desteklenmeyen işlem sessizce atılmaz. Harita/infografik ve AI planı için mevcut destek sınırları geçerlidir. Serbest AI kodu çalıştırılmaz; yeni editör veya 300 ayrı efekt/3D motoru eklenmedi.

Bu Linux bulutunda **gerçek Windows, gerçek GPU ve canlı Gemini testi çalıştırılmadı**. Windows otomasyonu eklendi; sonucu ancak Windows işi çalışınca doğrulanabilir. Ücretli API çağrısı yapılmadı; önceki açık ücret onayı kuralı korundu. Saatler süren gerçek kullanıcı projeleri kullanılmadı. `main`e birleştirme yapılmadı.

## GitHub teslimi

Uygulama/test commit’i `3d7efe0`, `fix/gapless-cold-preview` dalına gönderildi; uzak SHA `git ls-remote` ile doğrulandı. Kod: https://github.com/naman85331/video-ai-app/tree/fix/gapless-cold-preview . `main` bu çalışmada birleştirilmedi.

Draft PR oluşturma denemesi GitHub GraphQL API’sinde `Forbidden` yanıtıyla engellendi. PR oluşturulmuş değildir; bu erişim engeli uygulama koduyla giderilemez. Hazır karşılaştırma/PR formu: https://github.com/naman85331/video-ai-app/compare/main...fix/gapless-cold-preview?expand=1 . Windows CI işi de ancak GitHub üzerinde çalıştırıldığında gerçek Windows sonucu verebilir.
