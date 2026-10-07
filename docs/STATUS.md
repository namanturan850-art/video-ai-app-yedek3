# AI Video Studio — Durum

## 2026-10-07 — Minimum kelime hedefinin altındaki Ollama metinlerini düzeltme

- Sahibin gerçek Windows testi: Gemini/Ollama'nın beş tanılama testi, normal Ollama üretimi ve kısa Türkçe review sonuçları başarılı. Bu geçiş yalnızca kalan hedef süre davranışını düzeltir; sağlayıcı entegrasyonları değişmedi.
- Neden: süre düzeltmesi yalnız minimum kelime hedefinin %85'inden kısa metinde çalışıyordu. 340 kelime, 375 hedefinin altında olmasına rağmen bu koşulu geçiyordu. Artık minimum hedefin altında kalan her Ollama özgün senaryosunda bir deneme çalışır; 375 ve üzerindeyse çalışmaz.
- Uzatma isteğinde aralığın ortası açık sayısal hedeftir: 375–435 için **405 kelime**. Konu/bilgiler/yapı/ton/dil/içerik türü ve yararlı mevcut içeriği koruma, dolgu/tekrar/yeni bilgi uydurmama talimatları korunur/güçlendirilir. Mevcut tek deneme checkpoint'i devam/yeniden açılışta ikinci uzatmayı engeller.
- Son metin üzerinden aynı kayıt/rapor/süre/uyarı hesabı kullanılır: **340 → 400 / 2,96 dakika: kısa uyarısı yok; 340 → 360 / 2,67 dakika: kısa uyarısı var; 385: uzatma/uyarı yok.** Bu regresyonlar taklit üretimle doğrulandı. Minimuma bir kelime eksik (374), tam minimum (375), maksimum (435) ve maksimum üstü (436) sınırları da test edildi. 360 kelimelik sonuçtan devam ikinci deneme yapmaz.
- **Tam paket: 494 test; 492 geçti, 0 başarısız, 2 gerçek Windows/DPAPI testi Linux nedeniyle atlandı.** Yedi ek regresyon; önceki tüm testler ve pytest içindeki 34 JavaScript kontrolü geçti.
- Değişen uygulama kodu yalnız `app/scripts/service.py` ve `app/scripts/engine.py`; regresyonlar `tests/test_windows_live_fixes.py`, rehber `docs/SCRIPT_ENGINE.md`. Yeni özellik/aşama yok. Proje, senaryo, şifreli ayar, veritabanı ve Windows başlatıcısı korunur.
- Windows yeniden denemesi: güncel uygulamada **START_AI_VIDEO_STUDIO.bat → 3 dakikalık Ollama projesi → Senaryoyu Aç → Yeniden Oluştur**. Hedef 375–435; minimum altındaki metinde tek süre düzeltmesi, final sonuç aralıktaysa kısa uyarısı olmamalı.

## 2026-10-07 — Windows Gemini/Ollama üretim ve süre regresyonlarının düzeltmesi

- Aynı **provider-live-diagnostics** dalında devam edildi; yeni yol haritası aşaması/üretim özelliği yok. Mevcut projeler, senaryo sürümleri, SQLite şeması, şifreli kasa, Gemini/Ollama yapılandırmaları ve Windows başlatıcıları değiştirilmedi/sıfırlanmadı.
- **Gemini'de yeniden üretilen kod hatası:** Anahtar kayıtlı ama model boşken Ayarlar başarılı → bağlantı başarılı → Basit Üretim genel beklenmeyen backend hatası oluyordu. Eksik model varsayılan `provider_error` ile çıkıyor, tanılama bunu tanımıyordu. Artık `missing_model` / `configuration` ve açık model seçme talimatı var; bağlantı başarı sonucu korunur. Sahibin model/aşama bilgisi olmadan bunun Windows'taki kesin olay nedeni olduğu iddia edilmez. Native TLS/proxy/timeout/JSON hataları ve beklenmeyen gerçek istisnalar güvenli sınıf/aşamayla izlenebilir.
- **Gemini üretim ayrıştırması:** blocked_response/no_candidates/malformed_candidate/unexpected_finish_reason/output_limit/malformed_content/malformed_parts/thought_only_response/response_schema_mismatch/empty_response ayrı güvenli kategoriler. Resmi metin parçaları alınır, thought parçaları atılır. Anahtar/istek/model hatası ayrıdır. 429, hata gövdesi bozuk/derin veya Retry-After aşırı uzun olsa da kota olarak kalır; resmi ayrıntı varsa ücretsiz kota/hız sınırı ayrılır. Hiçbir ham gövde/başlık/reasoning paylaşılmaz. Günlük/arayüz aşama, güvenli sınıf, kategori, HTTP durumu ve süreyi gösterir.
- **Ollama'da doğrulanan yanlış ret:** Tanılama sarmalayıcısı geçerli final `response` yanında dolu `thinking` alanını uyumsuzluk sayıyordu; kaldırıldı. Native `/api/generate`, top-level `think:false`, `stream:false`, mevcut system/özgünlük talimatları korunur. Thinking + geçerli response kullanılabilir; yalnız response kaydedilir/gösterilir. Boş son yanıt açık `empty_response`; gerçek desteklenmeyen think/final reasoning uyumsuzluk mesajıyla kalır. qwen3.5:9b ve normal model, TEST_OK/JSON/tek bölüm/full kısa pipeline test edildi.
- **Kısa senaryo:** Önceden yalnız uyarı vardı. Bölüm hedefi güçlendirildi; Ollama özgün senaryosu alt hedefin %85'inden kısa olduğunda final assembly sonrası en fazla bir kontrollü uzatma. Deneme önce checkpoint'e yazılır; yeniden açma/Devam Et ikinci uzatma yapmaz. Konu/bilgiler/yapı/ton/dil korunması ve dolgu/tekrar olmaması istenir. Geçersiz/tekrarlı/uzamayan adayda eski metin korunur; hâlâ kısa final için Türkçe uyarı vardır. Çeviri ve bulutlarda ek otomatik ücretli çağrı yok.
- **Sayım ve inceleme:** Editör/SQLite/rapor/süre/uyarı aynı final metin ve sürümün konuşma hızıyla hesaplanır. Gelecek üretim formundaki hız eski metrikleri değiştirmez. 385 kelime, 3 dakika, 375–435 hedefte uyarısızdır. Son kontrol kısa sabit Türkçe mesajlara dönüştürülür; ham Almanca/İngilizce blueprint yorumları/özel reasoning API/normal UI'ya çıkmaz. Eski raporların güvenli API görünümü düzeltilir; eski DB metni/satırı/dosyası korunur.
- **Tam otomatik paket: 487 test; 485 geçti, 0 başarısız, 2 gerçek Windows/DPAPI testi Linux nedeniyle atlandı.** Bu düzeltmede 51 ek pytest regresyonu; frontend kontrolleri toplam **34 JavaScript testi**, tamamı geçti. Önceki testler de çalıştırıldı. Yeni testler resmi HTTP davranışını taklit eder; canlı sağlayıcı başarısı kanıtı değildir.
- **Gerçek Chromium + yerel FastAPI:** 15 bağımsız tanılama, 22 saniyelik üretim/polling, Gemini bağlantı/kota ayrımı, maskeli kasa, yeniden açılış/mobil geçti. Ek Ollama testinde thinking + final ile beş tanılama ve 184 → 385 tek düzeltme; UI/DB/rapor/dosya/2,85 dakika tutarlılığı, form hızı değişimi, canlı editörde uyarı kalkması, Türkçe review, yeniden açılış ve mobil geçti. JavaScript hatası/sır/reasoning sızıntısı yok. Dış HTTP yanıtları taklittir.
- **Live provider test must be run by owner on Windows.** Canlı anahtar/yerel Ollama yok; Gemini/OpenAI/Ollama'nın gerçek cihazda çalıştığı iddia edilmez. [Gemini ve Ollama için beş test, ardından gerçek üç dakika denemesi](AI_DIAGNOSTICS.md). Model/API kalitesi ve hedef uzunluk insan kontrolü gerektirir.

Değişen dosyalar:
- Sağlayıcı/tanılama: `app/main.py`, `app/provider_diagnostics.py`, `app/providers/base.py`, `app/providers/gemini.py`, `app/providers/text_api.py`.
- Senaryo ve kayıt: `app/scripts/engine.py`, `app/scripts/service.py`, `app/scripts/storage.py`, yeni `app/scripts/review.py`.
- Arayüz: `app/static/ai-diagnostics.js`, `app/static/index.html`, `app/static/script.js`, `app/static/settings-http.js`, yeni `app/static/script-metrics.js`.
- Regresyonlar: `tests/test_provider_diagnostics.py`, `tests/test_settings_frontend.py`, yeni `tests/test_windows_live_fixes.py`, `tests/frontend/script_metrics.test.cjs`.
- Belgeler: `docs/AI_DIAGNOSTICS.md`, `docs/SCRIPT_ENGINE.md`, `docs/STATUS.md`.

## 2026-10-07 — Sağlayıcı canlı tanılama ve entegrasyon düzeltmeleri

- **Ayarlar → AI Tanılama:** Gemini/Ollama/OpenAI için şifreli kayıt-yeni okuyucuyla açılış, bağlantı/model, TEST_OK, katı JSON ve mevcut YouTubeScriptEngine üzerinden tek kısa bölüm ayrı düğme/sonuç/süre/güvenli kategoriyle çalışır. Kasa doğrulanmadan API çağrısı yok; ayar değişince yeniden doğrulama gerekir. Gemini/OpenAI üretim testleri işlem başına maliyet onayı ister. Proje/senaryo verisi yazılmaz; anahtarlar korunur. Arka plan işleri ve kısa yerel polling 20 saniyelik Settings süresinden bağımsızdır.
- **Kodda bulunan katmanlar:** Ollama native isteğinde eksik üst seviye think:false eklendi; yalnızca response çıkarılır, reasoning son metne alınmaz; desteklenmeyen/yok sayılan seçenek güvenli uyumluluk mesajıyla tanılanır. JSON açıklama/fence ayrıştırması tek tam nesneye genişletildi; bozuk dış nesne, çoğaltılmış alan veya eksik şema onarılmaz. HTTP taşıma ile yanıt biçimi hatası ayrıldı. Gemini 400 anahtar/istek ayrımı ve resmi kota ayrıntısıyla ücretsiz kota/hız sınırı ayrımı; ayrıntısız 429 için kesin tür iddiası yok. OpenAI kasa, etkin durum, erişim ve üretim ayrı sonuçtur. Yeni hata kategorileri mevcut senaryo/devam ve kalite işlerinde korunur.
- **Tam otomatik paket: 436 test, 434 geçti, 0 başarısız, 2 gerçek Windows/DPAPI testi Linux nedeniyle atlandı.** 70 yeni sağlayıcı/tanılama/JSON regresyonu. Pytest içindeki frontend kontrolü 28 JavaScript HTTP testi çalıştırır; hepsi geçti.
- **Chromium + gerçek yerel FastAPI:** 15 ayrı tanılama testi, 22 saniyelik taklit Ollama üretimi boyunca sağlıklı yerel uygulama/polling, başarılı Gemini bağlantısından ayrı ücretsiz kota hatası, maskeli kayıt, mobil görünüm ve yeniden açılış geçti; JavaScript hatası yok. Dış API yanıtları taklit edildi; canlı sağlayıcı başarısı iddia edilmez.
- **Canlı ortam sınırı:** Bu bulut ortamında gerçek anahtarlar/Ollama yok. Gerçek anahtarsız ulaşım denemeleri Gemini/OpenAI için ProxyError, Ollama için bağlantı kurulamadı verdi. Bu sonuç Windows'a genellenmez. Sahibin belirli hatalarının kesin canlı katmanı yeni testlerin Windows sonuçlarıyla belirlenmelidir. **Live provider test must be run by owner on Windows.** [Tek basit rehber, katmanlar ve resmi sözleşmeler](AI_DIAGNOSTICS.md).
- Yeni roadmap aşaması, model indirme, render veya diğer üretim özelliği eklenmedi. Şema ve Windows başlatıcısı değişmedi; mevcut projeler, sürümler ve şifreli ayarlar korundu. Güvenli günlük/özet API anahtarı, Authorization, raw yanıt, stack trace veya tam üretilen metin içermez.

## 2026-10-07 — Kararlılık ve Geliştirme Paketi

Sıra ve doğrulama:
- A aşaması (kasa/Settings/sağlayıcı/üretim) kapısı **327 geçti, 0 başarısız, 2 Windows testi atlandı** ile tamamlandı; B bundan sonra başladı. B kapısı **339 geçti**. Son tam paket **366 test: 364 geçti, 0 başarısız, 2 gerçek Windows/DPAPI testi Linux nedeniyle atlandı**. Pytest içindeki frontend kontrolü **24 JavaScript testi** de çalıştırır; tamamı geçti.
- Chromium + gerçek yerel FastAPI + taklit resmi dış API: OpenAI erişim testi, yerel GPU/model ve Gemini görsel keşfi, ücretli kullanımın varsayılan kapalı olması, Fransızca proje/senaryo, retention/hooks/A-B/iddialar, onaylı metni koruyarak yeni sürüm, görsel plan/müzik tercihleri, yeniden başlatma ve mobil görünüm geçti; JavaScript hatası yok. Önceki uzun üretim/kota sonrası devam/düzenleme/sürümler/sağlayıcı değiştirme/çeviri tarayıcı regresyonu da geçti. Günlükte anahtar/stack trace yok.

Nedenler ve düzeltmeler:
- OpenAI Settings testi yer tutucuydu; resmi salt okunur model erişim testi eklendi. Etkinleştir tercihi, eksik/reddedilen anahtar, model, bakiye/kota, hız sınırı, zaman aşımı, internet/proxy ve sunucu/yanıt hatası ayrı güvenli Türkçe mesajlarla ele alınır. Test içerik üretmez; üretim kotası/bakiyesi ayrıca değerlendirilir.
- Kasa hataları tek genel mesajda birleşiyordu; key_decrypt_failed/folder_permission/temp_file_failed/atomic_replace_failed/encryption_failed/storage_locked ayrımı eklendi. Kapalı dosya tanıtıcısıyla atomik kayıt, Windows paylaşım kilidinde sınırlı bekleme/tekrar, eski key/vault koruması doğrulandı. Mevcut Gemini → OpenAI ekle/aç/model/kaydet → yeniden aç → anahtar güncelle → yalnız OpenAI temizle akışı ve sızıntı test edildi. Gerçek Windows'taki belirli hata burada gözlenemedi; DPAPI koruması kaldırılmadı, kasa sıfırlanmadı.
- Gemini 429 uygulama hatası değildir: hesap kota/hız sınırı olarak gösterilir. Çalışan keşif/test akışı korunur. Bölümler/parçalar ve eski sürümler saklanır; Retry-After veya sınırlı bekleme, açık Devam Et ve kullanıcı seçimiyle yeni sağlayıcı/üretim vardır. Sessiz ücretli fallback ve sonsuz tekrar yok.
- Güvenli sağlayıcı tanılaması yalnızca sağlayıcı/işlem/sonuç-kategori/süre; ham yanıt, anahtar veya Authorization yok.

Çalışan geliştirmeler:
- Ortak genişletilebilir dil kaydı: de/es/en/fr/tr. Almanca varsayılan; proje dili Senaryo'ya gelir. Senaryo, sahiplik onaylı çeviri, hooks/başlık/açıklama/CTA ve görsel vurgu seçilen dili kullanır; stok sorguları İngilizcedir.
- Genel amaçlı dinamik içerik motoru korunur; sabit küçük tür listesi/hikâye zorunluluğu yok.
- Sürüm bağlı Retention Analizi, üç hook, 2–3 A/B seçenekleri ve Claim Review. Öneriler ayrı, seçilen uygulama yeni taslak sürüm; onaylı sürümü değiştirmek açık onay ister. Alternatif seçimleri metni değiştirmez. İddialar Doğrulama gerektirebilir, verified=false ve gelecekte kaynak alanlarıyla saklanır; doğrulama iddiası yok.
- Güncel onaylı metinden görsel/kurgu planı: tam anlatım kapsamı, anlamsal İngilizce B-roll/fallback sorguları, amaç/duygu/görsel niyet/tür/kompozisyon/önem, hedef dilde sınırlı vurgu, geçiş/hareket önerileri. Kimlik tekrarını engelleyen medya kayıt API'si, görsel çeşitlilik/uzunluk uyarıları; tahmini süre veya sonradan sağlanan eşleşen gerçek TTS timing verisi.
- Görsel sağlayıcı Settings: otomatik/yerel GPU/Gemini/OpenAI/kapalı; ComfyUI adresi, kurulu model listesi, workflow/lisans tercihi, 16:9 çözünürlük; resmi Gemini keşfi ve OpenAI model erişimi. Anahtarlar mevcut şifreli kasadan kullanılır; bilinmeyen model indirilmez. Model erişimi görsel yeteneği/lisans garantisi değildir.
- Ücretli görsel kullanım varsayılan KAPALI; sor/izinli fallback tercihleri ve stok → yerel → izinli bulut seçimi. Bulut metin/kalite/planlama işlemlerinde işlem başına maliyet uyarısı/onayı; otomatik ücretli sağlayıcı geçişi yok.
- SQLite şema 5'e eklemeli işlemsel yükseltme, kalite/görsel plan kalıcılığı ve okunabilir JSON yansımaları. Mevcut proje/senaryo/ayar verileri ve Windows başlatıcısı korunur. Tek basit [Windows kontrol listesi ve resmi sözleşmeler](STABILITY_AND_ENHANCEMENTS.md).

Yalnızca hazırlanmış çalıştırma ve sınırlar:
- StockProvider/ImageProvider/TTSProvider/RenderProvider arayüzleri; yerel ComfyUI ve resmi Gemini/OpenAI görsel adaptörleri hazırlanmıştır. Bulut görsel sözleşmeleri taklit API'lerle test edildi; arayüzden/otomatik gerçek görsel üretimi henüz çalıştırılmaz. Yerel workflow API eşlemesi, stok arama/indirme, gerçek TTS/altyazı, müzik dosyası içe aktarma/işleme, FFmpeg render ve yükleme bağlı değildir.
- Müzik adı/lisans/duygu/volume/fade/ducking/bölüm değişimi tercihleri ve render öncesi eksik kontrolü çalışır; eksik dosyalar başarılı sayılmaz. Plan geçişleri gerçek video kurgu değildir.
- Bu Linux ortamında canlı anahtar/ödeme, gerçek Windows DPAPI/dosya kilidi veya RTX 5070/ComfyUI üretimi denenmedi. Gerçek cihaz/API kalite kontrolü için rehber hazır. AI bilgi/dil/özgünlük/retention kalitesi insan kontrolü gerektirir; Claim Review web araştırması yapmaz. Abonelik veya ücretli API zorunlu değildir; yerel Ollama kullanılabilir.

## 2026-10-07 — Aşama 4: Genel YouTube Senaryo Motoru

Tamamlandı:
- Sağlayıcıdan bağımsız `YouTubeScriptEngine`, `ContentAnalyzer`, dinamik `ConceptBlueprint`, `ScriptPlan` ve `ScriptSection`. Sistem hikâye odaklı değildir; belgesel, bilgi, karşılaştırma, liste ve serbest formatlara göre yapı seçilir. Hikâye alanları zorunlu değildir.
- Mevcut çalışan Gemini Ayarlar/model keşfi yeniden kullanıldı. Resmi Ollama/OpenAI üretim adaptörleri eklendi; üç sağlayıcı arayüzden değiştirilebilir, hepsi isteğe bağlıdır. API anahtarı olmadan uygulama açılır.
- Türkçe Proje → Senaryo ekranı: otomatik/serbest içerik türü, Almanca varsayılanı, projeden süre, ton, hedef kitle, talimatlar, not/kaynak alanları, konuşma hızı. Analiz Et, Senaryo Oluştur, Yeniden Oluştur, Devam Et, Düzenle, Kaydet ve Onayla.
- Soyut konsept analizi → özgün/dinamik plan → sıralı bölüm üretimi → kısa devamlılık özeti → birleştirme → tutarlılık/tekrar kontrolü. Referans kaynak metni yalnızca analizde kullanılır; URL içeriği indirilmez/kazınmaz veya görülmüş sayılmaz.
- Uzun üretimde bölüm/checkpoint kalıcılığı; kota/ağ/bağlam/son kontrol hatasından devam. Yeniden açılışta kesilen iş korunur; otomatik ücretli yeniden deneme yok. Devam aynı sağlayıcı/modelle yapılır.
- Kelime sayısı, hedef aralık ve tahmini süre; varsayılan 125–145 kelime/dakika, ayarlanabilir. Büyük editörde canlı ölçümler. Gerçek TTS üretimi yok.
- Değiştirilmeyen metin sürümleri, manuel kayıtla yeni sürüm, eski sürümü seçme, güncel sürüm onayı ve onaylı çalışmayı değiştirmek için açık onay. Gelecekte yalnızca güncel onaylı senaryoyu kullanacak API kontrolü hazır; sonraki aşama uygulanmadı.
- Ayrı Kendi Metnimi Almancaya Çevir modu: sahiplik onayı zorunlu, üçüncü taraf referansıyla karıştırılmaz, metin parçalara ayrılarak anlam/ayrıntı/yaklaşık uzunluk korunması istenir.
- SQLite şema 4'e işlemsel eklemeli yükseltme; üç yeni senaryo tablosu, okunabilir blueprint/plan/ilerleme/sürüm dosyaları. Eski projeler, ayarlar ve Windows başlatıcısı korunur. Üretim sürerken proje silme engellenir; silme yalnızca o projenin senaryo kayıtlarını temizler.
- Sırlar mevcut şifreli kasada kalır. Anahtar içeren girişler reddedilir, olası sağlayıcı yankıları temizlenir; API/proje dosyası/SQLite/istem/günlük sızıntısı test edildi. Beklenmeyen hatalar güvenli Türkçe JSON; ham API gövdeleri ve stack trace gösterilmez. Güvenli günlük işlem/sonuç/kategori/süre içerir.
- Başlangıç düzeyinde Windows/Gemini kullanım rehberi ve doğrulanmış resmi API kaynakları: [SCRIPT_ENGINE.md](SCRIPT_ENGINE.md). README ve Ayarlar/Projeler/Gemini rehberleri güncellendi.

Doğrulama:
- **Tam paket: 309 test; 308 geçti, 0 başarısız, 1 Windows DPAPI testi Linux nedeniyle atlandı.** Aşama 4 için 69 yeni test; önceki işlevler de geçti. Pakette ayrıca 19 JavaScript Settings kontrolünü çalıştıran test vardır; hepsi geçti.
- Üç sağlayıcının resmi HTTP sözleşmesi taklit API'lerle doğrulandı: otomatik/manuel/özel format, blueprint/plan, Almanca/bölümlü üretim, süre/bağlam, kısmi hata/devam, sürümler/düzenleme/onay, yeniden açılış, çeviri, güvenli yükseltme/silme ve sızıntı testleri.
- Chromium + gerçek yerel FastAPI + taklit dış API: 20 dakikalık üretim, kota hatasından devam, editör/sürümler/onay koruması, sağlayıcı değiştirme, ayrı çeviri, kalıcılık ve mobil görünüm geçti; JavaScript hatası yok. Sunucu günlüğünde anahtar/ham hata sızıntısı yok.
- Sahibi Aşama 1–3 ve Gemini Settings'i gerçek Windows'ta doğruladı. Yeni Aşama 4 üretimi bu Linux ortamında canlı anahtarla/Windows'ta denenmedi; [ilk gerçek Gemini Almanca senaryosu](SCRIPT_ENGINE.md) manuel doğrulama için hazır.

Sınırlar:
- AI çıktı kalitesi/doğruluk/yerel Almanca üslup insan tarafından kontrol edilmelidir. Tutarlılık kontrolü kısa özetler ve bölüm parçaları üzerinden yapılır; bağımsız araştırma değildir. Yerel uzun ifade/tekrar kontrolleri tam intihal veya dil değerlendirmesi sunmaz; hedef uzunluk sapmasında uyarı verilir.
- OpenAI'nin ayrı Settings bağlantı testi kapalıdır; Senaryo'da resmi API üretimi çalışır. Hiçbir model adı tahmin edilmez veya otomatik indirilmez. Pexels/Pixabay/AI33/FFmpeg üretimi/YouTube yükleme yok.
- **Aşama 5 başlatılmadı.** Sahne planı, stok, seslendirme, altyazı, render ve diğer sonraki aşamalar yer tutucudur.

## 2026-10-07 — Gemini Windows bağlantı düzeltmesi

Neden:
- Arayüz tüm ayar isteklerini 20 saniyede kesiyor, her fetch hatasını yerel uygulamaya ulaşılamaması olarak gösteriyordu. Bu mesaj gerçek hatayı ayırt etmiyordu.
- Gemini sunucu sorgusu 8 saniyelik HTTP süresi / 15 saniyelik sayfalama bütçesi kullanıyordu; yavaş bağlantılar için kısa kalıyordu.
- Serbest model alanındaki bir değer, API listesinden doğrulanmadan Hazır sayılabiliyordu. Genel Starlette sunucu-hata işleyicisi beklenmeyen hatayı tekrar yükseltebildiğinden Gemini için iç sınırda güvenli JSON koruması gerekiyordu.

Düzeltildi:
- Yalnızca Gemini model/test işlemleri için 60 saniyelik tarayıcı süresi; sunucuda 50 saniyelik HTTP/sayfalama bütçesi. Normal yerel ayar işlemleri 20 saniyede kalır.
- Fetch hatasında üç saniyelik yerel /api/health kontrolü; uygulama erişilemiyor, sağlık kontrolü gecikti, Gemini zaman aşımı, bağlantı kurulamadı, anahtar reddi, kota, model yok ve beklenmeyen sunucu hatası ayrı mesaj/kategorilerdir.
- İstenen zaman aşımı mesajı aynen kullanılır: Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.
- Gemini ayar yollarında beklenmeyen istisnalar middleware içinde güvenli JSON 500'e çevrilir. Sırlar, Google'ın ham yanıtı ve stack trace gösterilmez veya loglanmaz.
- Başlatıcının mevcut server.log günlüğüne yalnızca sabit işlem adı, sonuç, güvenli kategori ve süre kaydedilir.
- Önce anahtar kaydı, ardından resmi API model keşfi ve gerçek seçim listesi. Sunucu da yalnızca keşfedilmiş modelin kaydını kabul eder; eski `as` gibi değerler Hazır sayılmaz. Geçersiz kayıt varken discovery/test gerçek modelleri yine döndürür.
- Model listesi/doğrulama yerel şifreli kasada kalıcıdır. Anahtar değişince eski liste ve model sıfırlanır; eşzamanlı anahtar değişimi eski sonucu kaydetmez.
- Başlatıcı, proje davranışları, şifreli anahtar saklama ve Gemini'nin isteğe bağlı olması korunur. Yeni roadmap aşaması başlatılmadı.

Doğrulama:
- Tam pytest paketi: **239 geçti, 1 mevcut Windows DPAPI testi Linux nedeniyle atlandı; toplam 240 test.** Paketteki frontend kontrolü ayrıca **19 JavaScript regresyon testini** çalıştırır; tamamı geçti.
- Taklit API ve sanal saatle 20 saniyeyi aşan başarı, 60 saniye arayüz zaman aşımı, gerçek timeout mesajı, model doğrulama/discovery, anahtar/kota/bağlantı hataları, yerel sağlık sınıflandırması, güvenli JSON ve anahtar/günlük sızıntısı kontrol edildi.
- Chromium + gerçek yerel FastAPI: **23 saniye süren gerçek gecikmeli sorgu** 20. saniyede de çalışmaya devam edip tamamlandı. Eski model düzeltme, seçim temizliği, yeniden başlatma, hata sınıflandırması, maskeler ve mobil görünüm geçti; JavaScript hatası yok. Gerçek sunucu günlüğünde yalnızca güvenli alanlar olduğu doğrulandı.
- Google yanıtları taklit edildi; gerçek API anahtarı veya canlı Google bağlantısı kullanılmadı. Bu Linux ortamında gerçek Windows/DPAPI testi yapılamaz.

## 2026-10-07 — C) Gemini

Tamamlandı:
- İsteğe bağlı Gemini Ayarlar bölümü: web arayüzünden API anahtarı, mevcut şifreli yerel kasa, boş parola alanı ve yalnızca maskeli güvenli yanıtlar.
- Model alanı ve resmi Developer API'den alınan model listesi; sabit/tahmin edilen gerçek model kimliği yok.
- Kaydet, onaylı Temizle, Modelleri Getir ve salt okunur Bağlantıyı Test Et; Türkçe ilerleme, eksik ayar, erişim, kota ve ağ hata mesajları.
- `ScriptProvider` protokolü ve Gemini adaptörü: resmi `generateContent` çağrısı, özgün içerik talimatı, düşünce parçalarını dışlama, tamamlanmamış/engellenmiş çıktıyı reddetme ve olası anahtar yankısını maskeleme.
- Yalnızca resmi Google Gemini Developer API; web sitesi tarama/otomasyon veya Gemini Plus / Google AI Pro abonelik oturumu yok. API anahtarı yalnızca resmi HTTPS başlığında, yönlendirme takibi yok.
- Yeni Proje ve mevcut proje düzenleme ekranlarında Ollama / OpenAI / Gemini motor seçimi; seçim SQLite'ta kalıcıdır, anahtarlar projeye yazılmaz.
- Şema 1/2 → 3 güvenli yükseltme; eski projeler varsayılan Ollama ile korunur, yerel ayarlar ve dosyalar silinmez.
- Windows başlatıcısı ve mevcut Aşama 1–3 davranışları korunur; API anahtarı yokken uygulama açılır.
- Kullanım ve doğrulanmış resmi API sözleşmesi kaynakları: docs/GEMINI.md; README, Ayarlar ve Projeler rehberleri güncellendi.

Kapsam ve doğrulama:
- Gemini yalnızca sağlayıcı adaptörü/ayar/motor seçimi olarak eklendi. Uçtan uca Senaryo Oluştur ekranı ve diğer üretim aşamaları henüz yok; Ollama/OpenAI üretim adaptörleri bu değişiklikte eklenmedi.
- Tam test paketi: **215 geçti, 1 mevcut Windows DPAPI testi Linux nedeniyle atlandı; toplam 216 test, hata yok.** Gemini için 59 yeni test; gerçek anahtarlar yerine sentetik test verileri ve taklit Google API yanıtları kullanıldı.
- Testler: isteğe bağlı çevrimdışı başlangıç, şifreli kayıt, maskeleme, API/günlük/proje sızıntısı, doğrulama, kalıcılık, model listeleme/sayfalama, resmi istek sözleşmesi, erişim/kota/zaman aşımı/yönlendirme hataları, engellenmiş/eksik üretim, üç motor seçimi ve eski şema yükseltmesi.
- Chromium: anahtarsız açılış, maskeli kayıt, model listesi/seçimi, bağlantı testi, hata gövdesinin gizlenmesi, temizleme, üç motor, mevcut proje düzenleme, yeniden başlatmada kalıcılık ve mobil görünüm geçti; JavaScript hatası yok. Google API yanıtları taklit edildi.
- **Gerçek Google API anahtarıyla canlı bağlantı/üretim denenmedi.** Bu bulut ortamında Windows çift tıklama/DPAPI doğrulaması yapılamaz; önceki sürümlerin Windows testi sahibi tarafından tamamlanmıştır.

## 2026-10-07 — Aşama 3

Tamamlandı:
- Türkçe Yeni Proje formu: ad, konu, isteğe bağlı YouTube referansı, dil (varsayılan Almanca), hedef dakika, stil, minimum/maksimum sahne saniyesi, altyazı/müzik/küçük resim tercihleri.
- Alan doğrulaması, Türkçe alan hataları, kayıt sırasında ilerleme ve oluşturulan projeye yönlendirme.
- SQLite proje kaydı; benzersiz UUID, güvenli metaveri güncelleme ve UTC created_at/updated_at zamanları.
- Her proje için script, scenes, stock, voice, subtitles, music, render ve logs klasörleri.
- Projeler listesi: isim, konu, dil, hedef süre, Türkçe durum, oluşturulma/güncelleme tarihleri; açma ve açık Türkçe onayla silme.
- Yalnızca seçilen proje kaydı/klasörü silinir; eksik klasörler güvenle ele alınır. Sembolik bağlantı ve Windows reparse/junction denetimleri başka konuma silme yapılmasını engeller.
- Taslak/Hazır/İşleniyor/Tamamlandı/Hata durumları için veritabanı desteği. Yeni projeler Taslak; bu aşamada üretim durum geçişi yok.
- Detay ekranında dokuz üretim aşaması yalnızca Bekliyor / Hazır değil yer tutucusu.
- Eski şema 1'den 2'ye işlemsel, eklemeli yükseltme; mevcut tablolar, şifreli ayarlar ve yerel dosyalar korunur. Proje tablosunda API anahtarı alanı yoktur.
- Mevcut Windows başlatıcısı değiştirilmedi. Kullanım ve API açıklamaları docs/PROJECTS.md ve README'de.

Kapsam dışında:
- Referans analizi/indirme, senaryo üretimi, Ollama/OpenAI üretimi, stok medya, AI33, render, altyazı üretimi ve YouTube yükleme yok. **Aşama 4 başlatılmadı.**

Doğrulama:
- Aşama 1 ve 2 sahibi tarafından birleştirilip gerçek Windows bilgisayarında test edildi.
- Tam test paketi: **156 geçti, 1 mevcut Windows DPAPI testi Linux nedeniyle atlandı**. Aşama 1–2 testleri de dahil; hata yok.
- Chromium: eski şema yükseltme, Türkçe hatalar, oluşturma/yönlendirme, sekiz klasör, dokuz yer tutucu, düzenleme, listeleme, silme onayı/iptali, diğer projeyi koruma, yeniden başlatmada proje/ayar kalıcılığı, metinlerin güvenli gösterimi, ağ hatasında yeniden deneme ve mobil görünüm geçti. JavaScript hatası yok.
- Aşama 3 bu Linux makinesinde doğrulandı; yeni proje akışının gerçek Windows testi henüz burada yapılamadı.

## 2026-10-07 — Aşama 2 (geçmiş kayıt)

Tamamlandı:
- Türkçe Ayarlar: Genel, Ollama, OpenAI (isteğe bağlı), Pexels, Pixabay, AI33, FFmpeg ve YouTube (Daha sonra).
- Kaydet, onaylı Temizle ve desteklenen bölümlerde Bağlantıyı Test Et; ilerleme ve Türkçe hata mesajları.
- Web arayüzünden API anahtarı girişi; kayıttan sonra boş parola alanı ve yalnızca maskeli durum.
- Fernet ile şifrelenmiş yerel kasa; Windows'ta şifreleme anahtarı kullanıcı hesabına bağlı DPAPI ile korunur. POSIX'te özel dosya/klasör izinleri.
- Atomik kayıt, bölüm bazlı güncelleme, boş anahtarda mevcut değeri koruma, yeniden açılışta kalıcılık.
- Güvenli ayar API'leri; doğrulama hatalarında girilen anahtarların geri dönmemesi; köken/Host kontrolü ve önbelleğe alınmayan yanıtlar.
- Resmi API belgesi doğrulanarak yalnızca Ollama yerel model listesi bağlantı kontrolü. Model üretimi/indirme yok.
- FFmpeg otomatik durum/yol algılama ve sürüm komutuyla kontrol; FFmpeg veya API anahtarı yokken uygulama açılır.
- Yerel kasanın Git tarafından yok sayılması; başlangıç düzeyinde kullanım ve saklama dokümantasyonu.

Bilerek kapalı / sonraki aşamalar:
- AI33 bilgileri kaydedilebilir; **AI33 API belgeleri gerekli**. Gerçek test ve seslendirme yok.
- OpenAI/Pexels/Pixabay bağlantı testleri belgelenmiş sözleşme sağlanana kadar açıklamalı yer tutucudur; hiçbir gerçek çağrı yapılmaz.
- Yeni Proje, Projeler, senaryo, stok arama, seslendirme, altyazı, render ve YouTube yükleme geliştirilmedi. **Aşama 3 başlatılmadı.**

Doğrulama:
- Aşama 1 sahibi tarafından gerçek Windows bilgisayarında doğrulandı; çift tıklama başlatıcısı çalışıyor.
- Tam test paketi: **75 geçti, 1 Windows DPAPI testi Linux nedeniyle atlandı**; Aşama 1 testleri de dahil.
- Gerçek Chromium tarayıcısında sekiz bölüm, kaydetme/maskeleme, yeniden yükleme, temizleme, doğrulama, ağ hatası/yeniden deneme ve mobil görünüm geçti; JavaScript hatası yok.
- Ollama bağlantısı belgelenmiş yanıtı sunan yerel test sunucusuyla, FFmpeg bağlantısı gerçek çalıştırılabilir dosyayla doğrulandı.
- Windows başlatıcısının güncellenen bağımlılık kurulum akışı Linux üzerinde tekrar çalıştırılıp doğrulandı.
- Aşama 2'nin gerçek Windows DPAPI testi Windows gerektirir; Linux'ta açıkça atlanır.

## 2026-10-07 — Aşama 1 (geçmiş kayıt)

Tamamlandı:
- Python 3.12+ ve FastAPI ile yerel uygulama iskeleti.
- Türkçe, mobil ekranlara uyumlu ana sayfa: Yeni Proje, Projeler, Ayarlar, Tanılama.
- İlk açılışta SQLite veritabanı oluşturma; tekrar açılışta mevcut verileri koruma.
- `/api/health` ve güvenli `/api/diagnostics` uçları.
- Uygulama/Python sürümü, işletim sistemi, veritabanı, FFmpeg ve veri klasörü yazma kontrolü.
- FFmpeg yokken de açılış; Tanılama ekranında açıklama.
- Windows çift tıklama başlatıcısı: Python kontrolü, otomatik `.venv` ve bileşen kurulumu, hazır olunca tarayıcı açma, Türkçe hata ve ilerleme mesajları.
- Yerel veri, günlük ve gizli dosyaları Git dışında tutma.
- Yeni başlayanlar için Windows kullanım açıklamaları.

Yer tutucular:
- Yeni Proje, Projeler ve Ayarlar ekranları yalnızca açıklama gösterir.
- Hiçbir sağlayıcı bağlı değildir; sahte başarılı API işlemleri yoktur.

Kapsam dışında / henüz yapılmadı:
- Ayar veya anahtar kaydetme, proje oluşturma, senaryo, stok medya, AI33 seslendirme, altyazı, render ve YouTube yükleme.
- AI33 API davranışı uydurulmadı; mevcut entegrasyon notları geçerlidir.

Doğrulama:
- Backend, gerçek yerel HTTP sunucusu ve başlatıcı davranışları için 18 pytest testi: tamamı geçti; uyarı yok.
- Chromium tarayıcısında ana sayfa, yer tutucular, Tanılama, yenileme, bağlantı hatası/iyileşmesi ve mobil görünüm doğrulandı; JavaScript hatası yok.
- Sıfırdan `.venv` oluşturma ve kurulum ile tekrar açılış doğrulandı. Gerçek başlatıcı iki kez açılıp sağlıklı HTTP yanıtı alındı.
- Linux bulut makinesinde çalıştırıldı. Windows `.bat` dosyasının gerçek çift tıklama testi Windows makinesi gerektirir; bu makinede yapılamaz.

Aşama 1 tamamlandıktan sonra proje Aşama 2 geliştirmesine hazırdır. Aşama 2 başlatılmadı.
