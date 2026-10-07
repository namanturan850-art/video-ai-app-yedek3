# Aşama 2 — Yerel ayarlar ve anahtarlar

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
- **AI33:** API anahtarı, belgelenmiş Base URL varsa adresi, isteğe bağlı Voice ID ve Model. **AI33 API belgeleri gerekli**; bağlantı testi kapalı, seslendirme yapılmaz. Belgelenmiş adres/kimlikler yoksa bu alanları boş bırakın.
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
- `POST /api/settings/{section}/test`: Ollama, Gemini, OpenAI ve FFmpeg kontrolü; stok/AI33 için açıklamalı yer tutucu.
- `POST /api/settings/gemini/models`: kayıtlı anahtarla resmi API'nin desteklediği metin üretim modellerini listeler; anahtarı döndürmez.
- Değiştirme/test istekleri `X-AI-Video-Studio: settings` başlığı gerektirir. API, gizli alanları hiçbir yanıtta geri döndürmez.
