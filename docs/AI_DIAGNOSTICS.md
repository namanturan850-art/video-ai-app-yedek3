# AI Tanılama — canlı sağlayıcı kontrolü

Yeni bir yol haritası aşaması başlatılmaz. Mevcut projeler, senaryolar, sürümler ve şifreli ayarlar korunur. **Live provider test must be run by owner on Windows.** Taklit API yanıtları, canlı sağlayıcının çalıştığının kanıtı değildir.

## Windows'ta çok basit kullanım

1. Güncel uygulama klasöründe **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın. Siyah pencereyi açık bırakın.
2. **Ayarlar** ekranında kullandığınız sağlayıcının bilgilerini kontrol edip **Kaydet** deyin. Gemini'nin mevcut model listesini kullanın. OpenAI'de **Etkinleştir** açık olmalıdır. Ollama çalışıyor olmalı; sahibin doğruladığı model adı **qwen3.5:9b**'dir. Yeni model indirmek gerekmez.
3. **Ayarlar → AI Tanılama** açın. İlgili sağlayıcıda **1 — Ayarlar → Testi Çalıştır** deyin. Başarılı sonucu, maskeli anahtarı (bulut), modeli ve OpenAI etkin durumunu kontrol edin.
4. **2 — Bağlantı**, **3 — Basit Üretim**, **4 — JSON**, **5 — Tek Senaryo Bölümü** testlerini tek tek çalıştırın; her sonucun bitmesini bekleyin. Gemini/OpenAI için 3–5 testleri küçük de olsa API kotası/ücret kullanabilir; her biri açık onay ister. Bir hata diğer başarılı sonucu silmez. Kota/hız sınırında belirtilen süreyi bekleyin; beklemek günlük kotayı artırmaz.
5. Sorun varsa **Tanılama özetini kopyala** düğmesine basın. Özet hangi testin, hangi kategoride, ne kadar sürede başarısız olduğunu içerir. API anahtarı, Authorization, ham sağlayıcı yanıtı veya üretilen metin içermez. Anahtarınızı paylaşmayın.

Tam senaryo üretimi gerekmez. Kasa testinden sonra diğer testler bağımsız çalıştırılabilir. Uygulama yeniden açıldığında tanılama sonuçları **Bekliyor** olur; eski sonuç canlı doğrulama olarak sunulmaz. Kaydedilmiş ayarlar ve proje verileri kalır. Test sürerken sayfayı yeniden açarsanız **Sonuçları yenile** ile aynı oturumun sonucunu görebilirsiniz; ücretli test otomatik başlamaz.

## Kontrol edilen katmanlar

| Test | Yapılan işlem | Sonucun sınırı |
| --- | --- | --- |
| 1 — Ayarlar | Mevcut şifreli kasa atomik kaydedilir; YENİ SettingsStore okuyucusu açar; tüm kayıtlar karşılaştırılır | API yok. Anahtar/model eksik veya OpenAI kapalı olsa da kasa başarılı olabilir; eksik bilgiler ayrıca belirtilir |
| 2 — Bağlantı | Gemini resmi model listesi; OpenAI resmi model erişimi; Ollama yerel `/api/tags` ve seçilen model | Üretim kotası, bakiye veya üretim API uyumluluğu garanti edilmez |
| 3 — Basit Üretim | ScriptProvider ile yalnızca `TEST_OK` istenir ve son metin karşılaştırılır | YouTubeScriptEngine kullanılmaz |
| 4 — JSON | `{"status":"ok"}` istenir; ortak ayrıştırıcı ve katı şema doğrular | Tam senaryo/analiz/plan yok; eksik alanlar uydurulmaz |
| 5 — Tek Bölüm | Mevcut `YouTubeScriptEngine.section`, sabit tanılama konusu, yaklaşık 30 kelimelik tek bölüm | Konsept/plan/continuity/review çağrısı yok. Metin projeye kaydedilmez; uzun senaryo veya içerik kalitesi kanıtlanmaz |

Sonuçlar: **Başarılı, Hata, Kota sınırı, Model uyumsuz, Yanıt biçimi hatası, Bağlantı hatası, Ayar kaydetme hatası**. Çalışmamış test **Bekliyor**, devam eden test **Test ediliyor** gösterir. Her test güvenli mesaj, kategori, süre, zaman ve mevcutsa API HTTP durumunu ayrı tutar. Başarılı bağlantı, sonraki üretim hatasından ayrı kalır.

Kasa doğrulanmadan API testi çalışmaz. Model/anahtar/etkin durum değişirse kasa testi yenilenir. Aynı sağlayıcının eşzamanlı iki testi engellenir. Ağ çağrıları arka planda çalışır; tarayıcı kısa yerel isteklerle sonuçları takip eder. Normal Settings 20 saniye süresi uzun üretimi kesmez; sağlayıcı timeout'u ayrı gösterilir. Fetch başarısızlığında mevcut `/api/health` kontrolü yerel uygulamaya erişilememe durumunu ayırır.

## Kodda doğrulanan sorunlar ve düzeltmeler

- **Ollama istek katmanı:** Native `/api/generate`, `stream:false` vardı; resmi üst seviye **`think:false`** yoktu. Eklendi; `options.think` veya OpenAI uyumluluk API'si kullanılmaz. Son metin yalnızca `response` alanından alınır. Ayrı `thinking` birleştirilmez. Boş/tamamlanmamış yanıt, yanlış kanal veya son metindeki `<think>`/`<thinking>` başarısız sayılır.
- **Ollama uyumluluk katmanı:** Seçenek reddedilirse, yalnızca reasoning dönerse veya tanılamada `think:false` karşısında dolu `thinking` gözlenirse **“Bu Ollama modeli mevcut ayarlarla reasoning modunu kapatamıyor.”** gösterilir. Geçerli response yanında thinking varsa adaptör yalnızca son cevabı çıkarır; tanılama seçeneğe uyulmadığını ayrıca bildirir. Sessizce yok sayılan seçenek ancak gözlenebilir yanıt davranışıyla tespit edilebilir; model adı uyumluluk kanıtı değildir. Otomatik reasoning açık tekrar yoktur.
- **JSON katmanı:** Önceki ayrıştırıcı JSON çevresindeki açıklamaları reddediyordu. Artık tek, tam JSON nesnesinin çevresindeki zararsız açıklama ve JSON/etiketsiz fence kabul edilir. Bozuk dış JSON'dan iç nesne seçilmez; çoklu nesne, yinelenen alan, NaN/Infinity ve eksik gerekli alan reddedilir. JSON sözdizimi ile şema hatası ayrılır.
- **Gemini HTTP katmanı:** HTTP 400 otomatik anahtar reddi sayılıyordu. Resmi `google.rpc.ErrorInfo` içindeki `API_KEY_INVALID` ile geçersiz istek ayrılır. 401/403 erişim/anahtar, 404 model, timeout ve yanıt biçimi ayrı kalır.
- **Gemini kota katmanı:** HTTP 429 entegrasyon arızası değildir. Resmi `google.rpc.QuotaFailure` ayrıntısı varsa ücretsiz günlük/sıfır kota ile dakika/saniye hız sınırı ayrılır. Ayrıntı yoksa genel kota sınırı denir; ücretsiz kota tükendiği uydurulmaz. `Retry-After` en fazla 120 saniye dikkate alınır; hemen yeni tanılama çağrısı yapılmaz. Otomatik API tekrar/fallback yoktur.
- **HTTP taşıma katmanı:** Kesilmiş/protokolü bozuk HTTP bağlantısı JSON biçim hatasıyla birleşiyordu. Artık `network_error` gösterilir. Yerel Ollama bağlantı hatası, internet kotası veya FastAPI'nin kapalı olmasıyla karıştırılmaz.
- **OpenAI kayıt/API ayrımı:** Kasa yazımı, yeni okuyucuyla açılış, anahtar varlığı/maskesi, model ve etkin durum API'den önce doğrulanır. Kayıt başarılıyken model erişimi veya üretim başarısız olabilir; sonuçlar ayrıdır. Mevcut erişim testi, üretim kotası veya Chat Completions uyumluluğu garantisi sayılmaz.

Sahibin belirli Windows hatalarının kesin canlı nedeni, bu testlerin gerçek sonuçları olmadan henüz doğrulanmış değildir. Gemini Settings'in geçmişte çalışması üretim kotasının açık olduğunu; `ollama run qwen3.5:9b` çalışması uygulamanın HTTP/JSON/bölüm akışının uyumlu olduğunu kanıtlamaz.

## API ve gizlilik

- `GET /api/settings/ai-diagnostics`: sonuçlar; açılışta API çağrısı yapmaz.
- `POST /api/settings/ai-diagnostics/{provider}/{test}`: yalnızca seçilen testi başlatır (202). Testler: `settings`, `connection`, `simple_generation`, `json`, `script_pipeline`. Gemini/OpenAI üretim testlerinde `cost_confirmed:true` gerekir.
- Mevcut yerel Host, aynı köken, `X-AI-Video-Studio: settings` ve `Cache-Control: no-store` korumaları kullanılır.
- Ortak yapı: `provider`, `settings_status`, `connection_status`, `simple_generation_status`, `json_status`, `script_pipeline_status`, `safe_error_category`, `safe_message`, `elapsed_ms`; `tests` her testin ayrı ayrıntısını içerir.
- Mesaj ve kategori sabit güvenli katalogdan gelir. Log yalnızca sağlayıcı, işlem, sonuç, kategori, süre içerir. Ham hatalar, Authorization, reasoning veya üretilen metin loglanmaz. Anahtarlar mevcut şifreli kasada kalır. Yeni SQLite şeması/rapor dosyası yoktur.

Resmi sözleşmeler: [Ollama GenerateRequest/GenerateResponse — think, response/thinking](https://github.com/ollama/ollama/blob/main/api/types.go), [Ollama native server](https://github.com/ollama/ollama/blob/main/server/routes.go), [Google RPC ErrorInfo/QuotaFailure](https://github.com/googleapis/googleapis/blob/master/google/rpc/error_details.proto). Mevcut resmi Gemini/OpenAI kaynakları [GEMINI](GEMINI.md) ve [SCRIPT_ENGINE](SCRIPT_ENGINE.md) içinde korunur. Gemini web otomasyonu veya web aboneliği kullanılmaz.

## Doğrulama sınırı

Bulut ortamında gerçek Gemini/OpenAI anahtarı ve çalışan Ollama yoktur. Anahtarsız gerçek ulaşım denemeleri iki bulut API'sinde **ProxyError**, yerel Ollama'da bağlantı kurulamadı sonucu verdi. Bu bulut ortamına aittir; sahibin Windows bağlantısı veya hesabı hakkında sonuç değildir. Canlı üretim başarı iddiası yapılmaz. Otomatik test/tarayıcı sonuçları [STATUS](STATUS.md) içindedir; gerçek entegrasyon kanıtı sahibin Windows'ta çalıştırdığı karşılık gelen testin başarısıdır.
