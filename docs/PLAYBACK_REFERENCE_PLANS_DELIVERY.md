# Oynatma ve senaryoya uygun referans teknikleri — teslim

**Güncel devam:** Bu rapordaki parça geçişi ve ses durumu sınırları [kesintisiz önizleme düzeltmesinde](CONTINUOUS_PREVIEW_DELIVERY.md) ele alındı. Aşağıdaki ölçümler önceki sürümün tarihsel sonuçlarıdır.

Çalışma dalı: `fix/smooth-preview-reference-plans`.
Başlangıç: güncel `origin/main` (`27000f7`); `feature/manual-documentary-animations` içindeki `b14e611` ve `81c84c0` bu main sürümünde zaten bulunuyordu. Yedi izli editör, önceki güvenli içe aktarma ve geçiş düzeltmeleri korundu. Veritabanı şeması değiştirilmedi; kullanıcı verileri silinmedi.

## Bulunan nedenler ve değişiklikler

- Program proxy’si, herhangi bir motion veya geçiş görünce 5 FPS örnek kare yoluna dönüyordu. Motion artık asıl sahnenin saatini koruyarak yalnız gereken dört saniyelik aralıkta çiziliyor. Mevcut harita/infografik şablonları ve 15 belgesel bileşeni aynı çizim motorunu kullanıyor.
- Cross dissolve, wipe ve dip black kayıtları video proxy’sine taşındı. Kaynak kuyrukları doğrulanıyor; geçiş değiştirilmeden çiziliyor. Geçiş hesabı yalnız ilgili karelerde etkin. Kesirli klip sınırları 30 FPS kare düzlemine oturtuldu.
- Önceden yalnız 180p/360p/540p vardı. Otomatik önizleme artık 720p; seçilebilir 1080p eklendi. CRF 26 → 20; renk etiketleri mevcut final BT.709 zinciriyle eşleştirildi. Düşük çözünürlüklü kaynakta bulunmayan ayrıntı üretilmez. Otomatik olarak 180p’ye düşürme kaldırıldı; düşük kalite hâlâ açıkça seçilebilir.
- Sonraki parça bitiş noktasında isteniyordu. Artık önceden hazırlanıyor ve ikinci video öğesinde yükleniyor. Yeniden arama, kalite değişimi ve kurgu revizyonunda eski kuyruk kullanılmıyor.
- Bağımsız ses saati ile proxy video arasında sık sık seek yapılıyordu. Mikslenmiş videonun saati transportu yönetiyor; bağımsız sesler aynı anda çalmıyor. Hazırlık sırasında ses ve görüntü birlikte bekliyor. Kullanıcı seek, pause, stop ve hız kontrolleri korunuyor.
- Altyazı kelime vurgusunda, dört saniye sınırını geçen cümleler örnek kare yoluna düşüyordu. ASS, özgün cümle/kelime saatleriyle çizilip video zamanı pencereye geri taşınıyor; cümle kısaltılıp vurgu yeniden başlatılmıyor.
- Prosedürel sahnelerde sabit düğüm/yazı/kutu aktörleri her karede yeniden çiziliyordu. Her aktörün yalnız son rasterı, kamera/nesne durumu ve görünürlüğüyle önbellekleniyor; kompozit yalnız alfa sınır kutusunda yapılıyor. Kamera hareketi, görünürlük ve akışla birlikte optimizasyon öncesi çizimle birebir piksel testi eklendi.
- Her transport karesinde vurgu sınıfı kaldırılıp tekrar eklenerek zorunlu layout tetikleniyordu. Yalnız vurgu değişiminde güncelleniyor. Transport DOM güncellemeleri 30 Hz hedefiyle sınırlı; video tarayıcının yerel çözücüsünde oynuyor.
- Animasyon pencere önbelleği içerikle tanımlı ve 48 dosyayla sınırlı. Özgün medya ve final animasyon önbelleği temizlenmiyor. Aynı kaynak doğrulama ve kurgu kimliğiyle proxy yeniden kullanılabiliyor.

## Manuel Plan / AI Paketi

`app/animation/references.py`, incelenmiş 300 referansın teknik dizininden anlatım başına en fazla üç referans seçiyor. Türkçe/İspanyolca/İngilizce konu sözcükleri ve yaygın sözcük ekleri kullanılıyor; konu bulunamazsa sade açıklama/kamera/tipografi teknikleri öneriliyor. Bu bir anlamsal model veya video kalite sıralaması değildir.

Paketin `animation_reference_selection` alanında sahne kimliği, zaman, eşleşme gerekçesi, referans kimliği ve yalnız desteklenen soyut teknikler bulunur. Kaynak videolar, tam promptlar ve çalıştırılabilir kod aktarılmaz. Referansların kompozisyonunu, karakterlerini veya olaylarını kopyalamama kuralı açıkça pakete yazılır. Seçilen her teknik zorunlu efekt değildir; katkı sağlamıyorsa boş bırakılır.

Gemini mevcut açık paylaşım/kota onayıyla bu bağlamdan talimat hazırlar. Gerçek arşiv kimlikleri, harita, grafik, kamera ve animasyon kayıtları mevcut doğrulayıcıdan geçer. Paket hazırlama timeline’a yazmaz. Dış AI yanıtı → doğrulama → seçilebilir taslak → JPEG önizleme → açık onay → kayıt → final render zinciri korunmuştur. Hatalı işlemler ayrı gösterilir; geçerli öneriler kaybedilmez.

## Doğrulama

- 191 ayrı Python testi: oynatma/proxy, eski Manuel Plan, interval/transition, kilit/undo, mevcut kurgu, animasyon, açık onay ve render kapsamı.
- 70 Node ön yüz testi.
- Aynı yerel diyagramda 60 kare / üç tekrar medyanı: önceki `27000f7` çizicisi 1,1794 CPU saniye, yeni çizici 0,4293 CPU saniye (yaklaşık %64 azalma). Karşılaştırılan son RGBA karesi aynı; bu ölçüm bütün sahneler için hız garantisi değildir.
- Gerçek FFmpeg/ffprobe: 720p/30 FPS ve 1080p/30 FPS proxy; eksiksiz 120 kare/pencere; monoton 1/30 saniye zaman damgaları; ses/video süre farkı bir kareden az; gerçek hareketli 1080p kaynak.
- 12 saniyelik beş katmanlı animasyon: üç ayrı pencere, her pencere 120 kare. Her pencerenin ilk RGBA karesi, aynı motorun özgün 0/4/8 saniye çizimiyle birebir aynı. Animasyon saati parça başında sıfırlanmıyor.
- Bilim, grafik ve diyagram için üç ayrı JSON → taslak → gerçek JPEG → reddedilen onay → geçerli seçim/onay → gerçek 1080p/30 FPS MP4 testi. Final ses/video süreleri de ffprobe ile ölçülüyor.
- Chromium: mevcut Manuel Plan penceresinde dosya yükleme, hatalı kaydın ayrılması, iptal/onay, yedi iz ve özgün kaynakların korunması.
- Chromium uzun oynatma: 64 saniye / beş üst üste katman / 16 hazırlanmış 720p parça; 1904 görünen video kare bildirimi, ortalama **29,10 FPS**, en uzun kare aralığı **200 ms**, sıfır tarayıcı hatası. İzlenen akış yaklaşık 65,40 saniye duvar saati aldı; parça aralarında küçük beklemeler sürer. Sona kadar oynatma ve ardından 8. saniyeye geri arayıp yeniden oynatma geçti. [Ham ölçüm](examples/preview_playback_64s.json).
- Bulut testinde 64 saniyenin tüm proxy hazırlığı yaklaşık 273.88 saniye sürdü; bu işlem tarayıcı oynatma FPS’inden ayrıdır. Bu ölçüm sırasında diğer FFmpeg kontrolleri de çalışıyordu. Aktör önbelleği çizim CPU ölçümü ayrıca yukarıda verilmiştir.

Tekrar çalıştırma: `.venv/bin/python -m pytest -q tests/test_preview_playback.py tests/test_documentary_animation.py tests/test_editor_polish.py tests/test_transition_handles.py tests/test_manual_review.py tests/test_simple_workflow.py tests/test_plan_intervals.py tests/test_advanced_editing.py tests/test_manual_first.py`; `node --test tests/frontend/*.test.cjs`. Playwright/Chromium kurulu Python ile `scripts/preview_playback_browser_smoke.py` ve `scripts/documentary_animation_browser_smoke.py`. Python sözdizimi, JavaScript sözdizimi ve `git diff --check` kontrolleri de geçti.

## Pratik sınırlar

30 FPS dosya üretmek, her bilgisayarda kesintisiz 30 FPS görüntüleme garantisi değildir. Proxy hazırlama CPU işi gerektirir; soğuk önbellekte veya hazırlama oynatmadan yavaşsa açık hazırlık beklemesi olabilir. İlk eşzamanlı yoğun CPU testinde 24 saniyelik akış 25,06 FPS ve 2,77 saniye en uzun aralık verdi; bu sonuç başarılı sayılmadı. Hazır önbellekle aynı akış yaklaşık 29,2 FPS ve 183 ms en uzun aralık verdi. Parçalar arası sıfır milisaniye boşluk iddiası yoktur.

Eski otomatik dekorasyonların kullanıldığı projeler ile mevcut güvenlik sınırını aşan aralıklar (32 ek klip / 8 ek medya) hâlâ açık hata/açıklamayla örnek kare modunu kullanır. Desteklenmeyen efektler sessizce atılmaz. Relief/archive gibi özel şablonlar mevcut kendi çizicilerini kullanır ve hazırlıkları daha uzun sürebilir. Kısa proxy miksinin loudnorm/compressor başlangıç durumu final miksinden farklı olabilir; aynı mux içindeki ses/video saati korunur.

Canlı Gemini, Windows, gerçek donanım hızlandırma ve saatler süren kullanıcı projeleri bu bulut ortamında test edilmedi. Ücretli API çağrısı yapılmadı. 300 bağımsız efekt veya fizik/3D motoru eklenmedi; önceki MIT incelemesi ve lisans kaydı geçerli.

## GitHub teslimi

Uygulama ve test commit’i `1f955fe`, `fix/smooth-preview-reference-plans` dalına gönderildi; uzak dal SHA’sı `git ls-remote` ile doğrulandı. `main` hâlâ `27000f7`; bu çalışmada birleştirme yapılmadı.

Draft PR oluşturma denemesi GitHub GraphQL API’sinde `Forbidden` yanıtı aldı. Bu nedenle PR oluşturulmuş değildir. Kod ve rapor GitHub’da ayrı dalda bulunur: https://github.com/naman85331/video-ai-app/tree/fix/smooth-preview-reference-plans . Karşılaştırma/PR formu: https://github.com/naman85331/video-ai-app/compare/main...fix/smooth-preview-reference-plans?expand=1 .
