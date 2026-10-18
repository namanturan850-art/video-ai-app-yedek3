# NAMAN 2.0 — sade belgesel iş akışı

18 Ekim 2026. Temel: güncel `origin/main` (`3f21b2b`, PR #95 dahil).
Dal: `feature/naman-simple-workflow`. Mevcut proje verileri üzerinde silme veya toplu dönüşüm yapılmadı.

## Kullanım

1. Proje oluşturun ve metni yapıştırın.
2. Seslendirmeyi, ardından altyazıyı oluşturun.
3. **Görsel / Kurgu Hazırlığı** ekranında Gemini ile sahne planını hazırlayın. İnternetsiz yerel plan seçeneği korunur.
4. **Medyayı Tamamla** ile video/görsel kaynaklarını ve planın haritalarını hazırlayın. Manuel modda uygun kaynak bulunamazsa yuva boş kalır; otomatik infografik veya yaratıcı montaj yapılmaz.
5. **Kurgu** ekranında yedi izi düzenleyin. Oynatma kontrolleri program monitörünün altındaki yerindedir.
6. İsterseniz **Manuel Plan / AI paketi → Paketi Hazırla** kullanın. Gemini, paylaşım ve kota/ücret onayından sonra görev talimatlarını hazırlar. Paket hazırlamak timeline'ı değiştirmez.
7. Paketi dış yapay zekâya verin. Dönen cevabı yapıştırın veya **Dosyadan yükle (.json)** kullanın. **Cevabı içe aktar** önce taslak oluşturur. Önizleyip seçtiğiniz önerileri uygulayın.
8. Final videoyu Render ekranından alın.

## Uygulanan değişiklikler

- Üst menü **Dosya / Düzen / Görünüm** olarak sadeleştirildi. Klip, Sekans, İşaretleyiciler ve Yardım menüleri kaldırıldı; panel görünürlüğü gerekli Görünüm seçeneklerinde kaldı.
- Yeni manuel projelerde otomatik kurgu düğmesi ve eski moda dönüş seçeneği kaldırıldı. Eski/onaylanmış projelerin kayıtları korunur; eski projeyi manuel moda geçirme önizlemesi çalışır. Eski kayıtları açmak kendiliğinden dönüştürmez.
- Sağ panelde Özellikler, Düzenle, Motion, Metin ve işe yarayan ses miks erişimi korundu. Genel JSON sekmesi kaldırıldı. AI/JSON plan girişi Manuel Plan penceresinde toplandı. Sağ sekmeler bağımsız kliplerin gerçek formlarını da açar.
- Harita ve temel infografik verilerindeki yer adı, enlem/boylam, metin, değer ve etiket normal form alanlarından girilir. Karmaşık veriler için gelişmiş JSON bölümü korunur.
- Çoklu klip taşımada Snap düğmesinin durumu gerçekten okunur. Reddedilen ek klip sürüklemesi kayıtlı konuma döner; hata mesajı yeniden yüklemede kaybolmaz.
- Altyazı seçiliyken çoğalt/kilitle gibi görüntü işlemlerinin yanlışlıkla alttaki görüntü klibine uygulanması engellendi. Altyazı bölme, sol kesme aracı ve Ctrl+K üzerinden gerçek altyazı sürümüne kaydedilir. Kare sınırındaki ortak zamanların milisaniye yuvarlaması nedeniyle yanlış örtüşme hatası vermesi düzeltildi. Sürüm kaydı/yüklemesi tamamlanırken eski timeline üzerinde ikinci işlem yapılması engellenir. Metin sekmesinden altyazıya geçerken formun gizlenmesi düzeltildi. Yakınlaştırma veya timeline yeniden çiziminde altyazı trim tutamaçları korunur. Altyazının gövdesini sürükleyerek taşıma eklendi; kenarlardan süre düzenleme korunur. Çakışan/geçersiz aralıklar sunucuda reddedilir.
- Sol araç çubuğundaki seçim, kesme, taşıma, trim, çoğaltma, silme, kilit, yazı ve Snap; mevcut sürümlü API'leri kullanır. Silme kaynak dosyasını yok etmez. Ana görüntü yuvası boşaltılabilir; anlatım saati korunur. Ek klipler bağımsız düzenlenir.
- Manuel kaynak hazırlığında yalnız planda/yer işaretinde istenen haritalar için yerel harita üretimine izin verildi. Sayı, alıntı ve diğer infografikler otomatik eklenmez. Belirsiz yer için yakın başka yer haritası uydurulmaz. Mevcut geçerli/kilitli kaynaklar korunur.
- Paket artık sahne cümleleri ve gerçek zamanları, altyazılar, arşiv kimlikleri/lisansları, görsel/ses listeleri, mevcut kurgu ve medya yuvalarını içerir. Yerel dosya yolları ve API anahtarı eklenmez. Desteklenen çıktı alanları açıkça belirtilir.
- Gemini tek talimat isteği kullanır; model zincirinde gizli tekrar yapmaz. Paket büyükse veya istek sırasında proje değişirse anlaşılır hata verir. Tarayıcı bekleme süresi sağlayıcı süresinden uzundur.
- Yapıştırılmış metnin içindeki tek JSON nesnesi ve Markdown JSON kod bloğu kabul edilir. Bozuk, birden fazla veya eski plana ait yanıt uygulanmaz. Var olan manuel öğeler ve kilitler korunur; yinelenen nesneler reddedilir.
- Proje ekranındaki varsayılan sıra sadeleştirildi; Kurgu adımı render önüne kondu. YouTube araçlarının mevcut adresleri korunur, sade varsayılan akışta ek adım olarak gösterilmez. Müzik tercihleri hazırlık ekranında kapalı bir ayrıntı bölümünde tutulur.

## Kapsam sınırları

- Serbest düzyazıdan tahmini kurgu üretilmez. Dış yapay zekâ cevabı paketin şemasında tek JSON planı içermelidir; açıklama metniyle birlikte yapıştırılabilir.
- Mevcut AI plan sözleşmesi beş bölüm kullanır. Sahne kompozisyonunda `wide`, temel kamera hareketleri ve geçişler; harita bölümünde `map` desteklenir. Diğer harita şablonları manuel Harita Ekle üzerinden kullanılabilir. Paket uygulanamayan seçenekler önermemesi için bu sınırları bildirir.
- Ana görüntülerin sırası/kesitleri sahne süresi içinde düzenlenir. Temel anlatım dosyasını timeline'dan silmek veya anlatım saatini serbestçe bozmak desteklenmez. Bağımsız ek ses/müzik, metin, harita ve grafikler düzenlenebilir. Altyazı çoğaltma/kilitleme yerine kendi metin/zaman/böl/birleştir/sil araçları kullanılır; görüntüye yanlış işlem gönderilmez.
- Eski `legacy` projelerin eski davranışı, kaynakları ve render tercihleri korunur. Manuel davranışa geçiş açık işlem gerektirir. Otomatik kurgu arka uç uyumluluğu silinmedi; yeni sade arayüzden otomatik taslak üretilmez.
- Canlı Gemini, ücretli API, gerçek kullanıcı projesi ve Windows/WebView2 çalıştırması bu teslimde kullanılmadı. Gemini sözleşmesi sahte sağlayıcıyla; dosyalar ve kayıtlar geçici sentetik projelerle doğrulandı.

## Doğrulama

- İlgili Python test gruplarının toplamı: **295 farklı test geçti, 3 atlandı**. Gruplar kısmen örtüşür; sayılar mükerrer toplanmadı. Ana gruplar 85 passed ve 141 passed / 3 skipped; son altyazı/paket grubu 102 passed. Son grup yeni kesim sınırı regresyon testini içerir. Toplam 298 testin toplandığı ayrıca kontrol edildi.
- Atlamalar: bu ortamda yerel Remotion kurulumu yok; iki eski marker örneği ek görsel/yer verisi gerektiriyor.
- `node --test tests/frontend/*.test.cjs`: **70 passed**.
- `scripts/editor_polish_browser_smoke.py`: gerçek Chromium, 503 arşiv kaydı / 200 katman / 480 saniye proje, gruplar, eğriler, proxy, gerçek program karesi; JavaScript hatası yok. Bu uzun proje tam render edilmedi.
- `scripts/manual_editor_browser_smoke.py`: sentetik proje üzerinde düzenleme, taslak içe aktarma, salt okunur Gemini paket taklidi, beş pencere boyutu ve **4 saniyelik gerçek FFmpeg final çıktısı**. Canlı bulut çağrısı yapılmaz.
- JavaScript sözdizimi, Python derleme ve `git diff --check` kontrolleri.

**GitHub teslimi:** uygulama commit `6a78399` ile [geliştirme dalına](https://github.com/naman85331/video-ai-app/tree/feature/naman-simple-workflow) gönderildi. Son Chromium turu geçti. Draft PR oluşturma hem GitHub GraphQL hem REST API üzerinden `403 Forbidden` ile engellendi; PR oluşturulmuş gibi gösterilmedi. [Değişiklikleri incele / PR aç](https://github.com/naman85331/video-ai-app/compare/main...feature/naman-simple-workflow). `main`e merge yapılmadı.
