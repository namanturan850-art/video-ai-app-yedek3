# Aşama 2 — Yerel ayarlar ve anahtarlar

Sağlayıcı sorununda **Ayarlar → AI Tanılama** ile kasa kaydı, bağlantı, TEST_OK üretimi, JSON ve tek bölümü ayrı test edin. [Basit Windows rehberi](AI_DIAGNOSTICS.md). Canlı testleri sahibi Windows'ta çalıştırmalıdır; bağlantı başarısı üretim kotası garantisi değildir.

## Kullanıcı için

1. `START_AI_VIDEO_STUDIO.bat` dosyasına çift tıklayın.
2. Ana sayfada **Ayarlar** kartına tıklayın.
3. Kullanmak istediğiniz hizmetin bilgilerini girip o bölümde **Kaydet** düğmesine basın. Diğer hizmetler boş kalabilir.

Anahtar alanı kayıttan sonra boşalır; altında yalnızca maskeli kayıt görünür. Sayfayı yeniden açtığınızda da tam anahtar görünmez. Anahtar alanını boş bırakarak **Kaydet** demek mevcut anahtarı korur. **Temizle**, onay verdikten sonra yalnızca seçilen bölümün anahtarını ve tercihlerini siler.

- **Genel:** dil tercihi; Yeni Proje ve Senaryo ilk açılış varsayılanı Almanca kalır. Arayüz Türkçedir.
- **Ollama:** yerel adres ve bilgisayarda kurulu modelin tam adı. Varsayılan adres `http://127.0.0.1:11434`. Kullanmayacaksanız model boş kalabilir. Önce **Kaydet**, ardından **Bağlantıyı Test Et**. Ollama'nın açık olması gerekir. Test yalnızca yerel model listesini kontrol eder; metin üretmez veya model indirmez.
- **OpenAI:** Etkinleştir, model ve API anahtarı. Senaryo için etkinleştirip hesabınızda erişilebilir Chat Completions model adını kaydedin. Bağlantı testi resmi model erişimini kontrol eder; içerik üretmez. Bakiye/kota ve üretim uyumluluğu gerçek üretimde ayrıca kontrol edilir. Kullanmak zorunda değilsiniz.
- **Gemini:** isteğe bağlı Google Gemini Developer API anahtarı ve model. Anahtarı **Kaydet**, **Modelleri Getir**, API listesinden bir model seçip tekrar **Kaydet**, ardından **Bağlantıyı Test Et**. Yalnızca keşfedilen modeller seçilebilir; eski geçersiz değerler Hazır sayılmaz. Sorgular için 60 saniye beklenebilir. Test yalnızca resmi API model listesini okur; senaryo üretmez. Gemini Plus / Google AI Pro web aboneliği API anahtarının yerine geçmez. Ayrıntılar: [Gemini rehberi](GEMINI.md).
- **Pexels / Pixabay:** API anahtarını kaydetme. Medya araması ve gerçek bağlantı testleri henüz eklenmedi.
- **AI33 / OpenSpeaker:** API anahtarını Kaydet; varsayılan ElevenLabs veya kayıtlı sağlayıcınızla ad araması → Sesleri Getir → ses seç → Kaydet. Kayıtlı diğer sağlayıcılar korunur. Daha Fazla Ses Yükle yeni 30 sesi ekler; Tüm Sesleri Getir onaylı ve en fazla 300 sestir. Bağlantı testi yalnız kredi erişimini kontrol eder. Önizlemeyi Dinle ücretsiz hazır örnektir. Onaylı projede gerçek TTS ayrı kredi onayıyla çalışır; Kısa TTS Testi de kredi kullanır. Eski Base URL/model gelişmiş bölümde korunur, gerçek hedef api.ai33.pro ve model gönderilmez. [Basit Windows rehberi](NARRATION.md).
- **FFmpeg:** otomatik algılanan durum ve dosya yolu. Test düğmesi yalnızca sürüm komutunun çalışmasını kontrol eder. Bulunmasa da uygulama ve Ayarlar açılır.
- **YouTube:** Daha sonra.
- **Görsel Üretimi:** otomatik/yerel GPU/Gemini/OpenAI/kapalı; yerel ComfyUI, model/workflow/lisans ve 16:9 çözünürlük; mevcut şifreli Gemini/OpenAI anahtarlarının kullanımı. Bağlantı/model kontrolleri çalışır, gerçek görsel çalıştırma daha sonra. Ücretli fallback varsayılan KAPALI. Ayrıntılar: [paket rehberi](STABILITY_AND_ENHANCEMENTS.md).

**Hazır**, gerekli bilgilerin kaydedildiği anlamına gelir. Bağlantı doğrulanmadıysa yanında açıkça belirtilir. Ollama ve Gemini'de test sonucuna göre **Hazır** veya **Hata** gösterilir. Gemini'de modelin API listesinden doğrulanmış olması da gerekir; anahtar kayıtlı fakat model seçilmemiş/doğrulanmamışsa **Yapılandırılmadı** gösterilir. Anahtarları başka bir yere yapıştırmanız, `.env` dosyası düzenlemeniz veya kod değiştirmeniz gerekmez.

## Gizli bilgilerin saklanması

Ayarlar ve anahtarlar `data/secrets/settings.enc` içinde Fernet ile şifrelenir. Şifreleme anahtarı `data/secrets/vault.key` içinde tutulur:

- Windows'ta bu anahtar Windows DPAPI ile **geçerli kullanıcı hesabına** bağlı olarak korunur; düz şifreleme anahtarı dosyaya yazılmaz.
- Linux/macOS'ta klasör yalnızca sahibi tarafından erişilebilir (`0700`), dosyalar yalnızca sahibi tarafından okunup yazılabilir (`0600`). Yerel anahtar dosyası bu izinlerle korunur.

Kayıt geçici dosyaya yazılır, ardından atomik olarak değiştirilir. Hatalı giriş veya açılamayan kasa mevcut kayıtların üzerine yazmaz. Aynı uygulamadaki eşzamanlı kayıtlar kilitle korunur. **Şifreleme, bilgisayarınızda hesabınıza erişebilen bir kişiye karşı tam koruma sağlamaz.** Yerel ayar klasörünü, anahtarını veya günlükleri herkese açık olarak paylaşmayın. Windows'ta başka hesap/makineye kopyalanan kasa aynı şekilde açılamayabilir; anahtarları yeni hesabın arayüzünden yeniden girin. Bozuk/kayıp kasayı uygulama otomatik silmez.

Gizli bilgiler SQLite'a, kaynak dosyalara ve uygulama günlüklerine yazılmaz. `data/secrets/`, şifreli dosyalar, `.env`, günlükler ve yerel veritabanları Git tarafından yok sayılır. API, kayıt sonrası tam anahtar döndürmez; yalnızca kayıt durumu ve son dört karakteri maskeyle gösterir. Sekiz karakterden kısa değerler kabul edilmez. Bozuk eski kısa değerlerin maskesi hiçbir karakter göstermez.

Ayar API yanıtlarında `Cache-Control: no-store` vardır. Değişiklik istekleri aynı köken ve özel istek başlığı kontrolüyle korunur. Sunucu yerel adrese bağlanır; farklı Host başlıkları engellenir. İstek doğrulama hataları girilen değerleri yanıta eklemez. Hiçbir API anahtarı tarayıcı depolamasına yazılmaz.

## Doğrulanmış bağlantı kontrolü kaynağı

Ollama kontrolü, resmi dokümandaki **List Local Models** işlemini kullanır:
- Kaynak: https://github.com/ollama/ollama/blob/main/docs/api.md#list-local-models (2026-10-07 tarihinde kontrol edildi).
- İşlem: `GET /api/tags`.
- Belgelenmiş yanıt: `models` listesi ve her modelin `name` alanı.

Yalnızca loopback adresleri (`localhost`, `127.0.0.1`, `::1`) kabul edilir. Proxy ortam değişkenleri kullanılmaz, yönlendirmeler takip edilmez, zaman aşımı 5 saniyedir. Yanıt veya ağ hatasının ham içeriği kullanıcıya verilmez.

Pexels/Pixabay testleri kapalı ve açıklamalıdır. OpenAI salt okunur testi resmi `GET /v1/models/{model}` kullanır. Metin/görsel adaptörleri, ComfyUI kontrolleri ve kaynaklar [paket rehberinde](STABILITY_AND_ENHANCEMENTS.md). AI33 için [AI33_INTEGRATION_NOTES.md](../AI33_INTEGRATION_NOTES.md) kuralları geçerlidir. Hiçbir belgelenmemiş uç, model, ses kimliği veya kimlik doğrulama biçimi varsayılmadı.

Gemini kontrolü resmi Google Gemini Developer API `GET /v1beta/models` işlemini kullanır. Anahtar yalnızca HTTP başlığında gönderilir; model listesi API'den alınır. Resmi sözleşme kaynakları ve güvenlik ayrıntıları [Gemini rehberinde](GEMINI.md) bulunur.

## Backend

- `GET /api/settings`: güvenli tercihler, maskeler, durumlar ve FFmpeg bilgisi.
- `PUT /api/settings/{section}`: yalnızca gönderilen alanları günceller. `api_key` boş/null veya yoksa eski anahtarı korur.
- `DELETE /api/settings/{section}`: o bölümü varsayılan değerlere döndürür; diğer bölümlere dokunmaz.
- `POST /api/settings/{section}/test`: Ollama, Gemini, OpenAI ve FFmpeg kontrolü; AI33 salt okunur kredi erişimi kontrolü. Stok ayrıntıları için Part 6 rehberine bakın.
- `POST /api/settings/gemini/models`: kayıtlı anahtarla resmi API'nin desteklediği metin üretim modellerini listeler; anahtarı döndürmez.
- Değiştirme/test istekleri `X-AI-Video-Studio: settings` başlığı gerektirir. API, gizli alanları hiçbir yanıtta geri döndürmez.

## Hangi yapay zekâ kullanılır? (ücret)

- **Varsayılan: Gemini.** Yönetmen (amaç, senaryo, kurgu planı) ve **Medyayı Tamamla** (aday görsellere bakıp onaylama, yeni arama kelimeleri, bütün video kontrolü) Gemini ile çalışır. Ayarlar → Gemini bölümüne aistudio.google.com'dan aldığınız ücretsiz anahtarı yapıştırın, **Modelleri Getir** ile bir model seçip **Kaydet** deyin.
- Gemini ücretsiz kotasının dakika ve gün sınırı vardır. Dakika sınırında uygulama kısa süre bekleyip devam eder. Günlük kota dolarsa boş yuvalar anlatımdan kartla doldurulur; ertesi gün **Medyayı Tamamla**'ya tekrar basınca bu kartlar stok medyayla değiştirilmeye çalışılır. Bir 3 dakikalık video yaklaşık 45–90 Gemini isteği kullanır (sahte testlerdeki ölçüm); günlük sınırınız AI Studio'da görünür.
- **Claude isteğe bağlıdır ve ücretlidir.** Claude API, claude.ai aboneliğinden (Pro/Max) ayrı ücretlendirilir. Yalnızca Ayarlar → Claude bölümünde **Gemini yerine Claude kullan (ücretli)** kutusunu işaretlerseniz kullanılır.

## Claude (Anthropic) — isteğe bağlı, ücretli

Claude; senaryoyu, kurgu planını ve medya seçimini yapar. Kurulum:

1. https://console.anthropic.com adresinde oturum açın → **API Keys** → **Create Key**. Anahtarı kopyalayın.
2. Uygulamada **Ayarlar → Claude (Anthropic) — Yönetmen** bölümüne yapıştırın, **Kaydet** deyin. Anahtar şifreli saklanır; ekranda yalnız son 4 karakteri görünür.
3. **Bağlantıyı Test Et**: ücretsizdir (metin üretmez), anahtar ve model erişimini kontrol eder.
4. **Model**: Opus 5.5 (en iyi kalite, önerilen), Sonnet 5.5 (daha ucuz), Haiku 5.5 (en ucuz).
5. **Gemini yerine Claude kullan (ücretli)** kutusunu işaretlemezseniz Claude hiç kullanılmaz. Varsayılan motor Gemini'dir (ücretsiz kota).

Claude bir isteği güvenlik nedeniyle reddederse, aynı istek Anthropic'in önerdiği yedek Claude modelinde otomatik yeniden denenir (`fallbacks: "default"`). Claude hiç çalışmazsa (anahtar, kredi, internet, yoğunluk) senaryo ekranı **Gemini / Ollama ile devam et** düğmelerini gösterir; yedeğe **siz onaylamadan geçilmez**.

**Maliyet:** her Claude çağrısının token sayısı ve tahmini maliyeti (liste fiyatı) kaydedilir. Senaryo ekranında “Bu projede Claude/AI tahmini maliyeti” satırı görünür. Fatura değildir; kesin tutar Anthropic konsolundadır.

### Claude Yönetmen'i kullanmak (senaryo sayfası)

1. Projeyi açın → **Senaryo**. En üstte **Claude Yönetmen** paneli vardır.
2. **Yönetmeni Başlat** deyin ve ücret onayını verin. Başka bir şey girmeniz gerekmez (konu, dil ve süre projeden alınır).
3. Panel adım adım ilerler: **Amaç belirleniyor → Senaryo yazılıyor → Senaryo onaylanıyor → Kurgu planı hazırlanıyor**.
4. **Videonun amacı** bölümünü açıp hedef kitle, ana mesaj, ton ve açılış kancasını değiştirebilir, **Amacı Kaydet** diyebilirsiniz. Sonraki çalıştırmada senaryo bu özete göre yazılır.
5. **Senaryoyu otomatik onayla** kutusunu kaldırırsanız yönetmen senaryodan sonra durur; metni okuyup **Onayla** dedikten sonra **Yönetmeni Devam Ettir** deyin.
6. Bir adım hata verirse tamamlanan adımlar korunur; **Yönetmeni Devam Ettir** kaldığı yerden sürer. Claude hiç çalışmıyorsa panel **Gemini/Ollama ile devam et** düğmelerini gösterir (yalnız siz seçerseniz).

Kurgu planında her sahne için: görsel türü (stok video / stok görsel / üretilmiş kart: harita, sayı, başlık/alıntı), İngilizce somut arama sözcükleri + 2–3 yedek, **mutlaka göster / gösterme** notları ve çekim sayısı vardır. Az stok bulunan konularda daha az ama daha uzun çekim planlanır (çekim başına 2,5–10 sn). Kart yazısı yalnızca anlatımda geçen bir ifade olabilir; uydurma sayı veya alıntı kabul edilmez. Plan şemaya uymazsa Claude bir kez otomatik düzeltir.

## NAMAN içinde Mapbox stil seçimi

1. **Ayarlar → Mapbox (harita stilleri)** bölümünü açın. Anahtarınızı kaydedin.
2. Uydu, uydu + yollar, arazi, sokak, koyu, açık veya navigasyon stilinin
   kartına tıklayın. Seçim hemen kaydedilir; tekrar Kaydet gerekmez.
3. Görsel karşılaştırma için **Önizlemeleri yükle** düğmesine basın. Bu işlem
   Mapbox kullanımına sayılır; alınan resimler yerelde önbelleğe alınır.
4. Kendi stiliniz için Studio’daki yayımlanmış stilin **Share → Style URL**
   bağlantısını yapıştırıp **Studio stilini ekle** deyin. İsterseniz adını yazın.
   Özel stil eklenince seçilir; kendi kartından kaldırılabilir.
5. Projede **Video Oluştur / Render → Mapbox harita görünümünü seç / Studio
   stili ekle** bölümünden de aynı kartlara ulaşılır. Buradan kart seçmek,
   projenin harita kaynağını Mapbox’a da geçirir. Ayarlar bölümündeki seçim
   küreseldir: Mapbox kullanan projelerin yeni haritaları aynı stili kullanır.

Önceden üretilmiş video dosyaları değiştirilmez; yeni grafikler üretildiğinde
seçilen stil kullanılır. Harita kaynağı koyu/renkli yerel harita olan projeler
Mapbox’a kendiliğinden geçirilmez. **Mevcut uydu ayarı** kartı, önceki özel
adres şablonlarını kullanmaya devam eder.

Hesaptaki stilleri otomatik listeleme yoktur; hazır kartlar ve elle eklenen
Studio bağlantıları kullanılır. `styles:list` izni istemez. Geçerli ve yetkili
Mapbox anahtarı gerekir; anahtar resim bağlantılarına veya tarayıcıya çıkarılmaz.
3B Studio görünümü ile statik video haritası aynı özellikleri göstermeyebilir.
