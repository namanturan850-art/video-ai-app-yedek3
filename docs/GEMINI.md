# Gemini — isteğe bağlı senaryo sağlayıcısı

## Windows'ta kullanma

1. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın.
2. **Ayarlar → Gemini** bölümüne gidin. [Google AI Studio](https://aistudio.google.com/apikey) üzerinden aldığınız **Gemini Developer API anahtarını** buraya girip **Kaydet** deyin.
3. **Modelleri Getir** düğmesine basın. **Model** alanında API'nin döndürdüğü listeden bir model seçip **Kaydet** deyin. Model alanına serbest metin yazılmaz.
4. **Bağlantıyı Test Et** düğmesine basın. Başarılıysa **Hazır** görünür. Hata mesajı anahtar, model, internet veya kota için neyi kontrol edeceğinizi açıklar.
5. **Yeni Proje** ekranında **Senaryo motoru (Script Engine)** olarak **Gemini** seçin. Mevcut projelerde **Proje bilgilerini düzenle** bölümünden motoru değiştirebilirsiniz.

Gemini zorunlu değildir; alanları boş bırakırsanız uygulama ve projeler çalışmaya devam eder. **Gemini Plus / Google AI Pro web aboneliği, Developer API anahtarının yerine geçmez.** API erişimi ve kotası ayrı yönetilir. Model listesi ve bağlantı testi yalnızca model bilgilerini okur; senaryo üretmez.

Eski kayıtta `as` gibi bir değer varsa bu, doğrulanmış model olarak kabul edilmez. Model API listesinde yoksa açıklama gösterilir ve seçim boş bırakılır. Listeden geçerli bir model seçip **Kaydet** deyin. Anahtarı değiştirdiğinizde eski model seçimi ve listesi temizlenir; yeni anahtarla **Modelleri Getir** işlemini tekrarlayın. Model listesi ve seçim yeniden açılışta korunur.

## Bağlantı hataları

Gemini **Modelleri Getir / Bağlantıyı Test Et** işlemlerinde tarayıcı 60 saniye bekler. Normal yerel ayar işlemlerinin süresi 20 saniyedir. Sunucu model sorgusunda 50 saniyelik HTTP zaman aşımı/sayfalama bütçesi kullanır; beş sayfadan fazla sorgulamaz. Beklenmeyen sunucu hataları da güvenli JSON olarak döner.

| Durum | Açıklama / yapılacak işlem |
| --- | --- |
| Gemini zaman aşımı | **Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.** |
| İnternet bağlantısı kurulamadı | İnternet, güvenlik duvarı ve varsa proxy ayarlarını kontrol edin. Bu kategori Google'a bağlantı kurulamamasını ifade eder; tüm internetin kapalı olduğunu kesin olarak belirlemez. |
| Anahtar reddedildi | Google AI Studio API anahtarını ve API kısıtlamalarını kontrol edin. |
| Kota / istek sınırı | Bir süre bekleyip Google AI Studio kotasını kontrol edin. |
| Model bulunamadı | Modelleri tekrar getirip API listesinden bir model seçin ve kaydedin. |
| Beklenmeyen sunucu hatası | Tekrar deneyin; sorun sürerse Tanılama ekranını kontrol edin. |
| Yerel uygulamaya ulaşılamadı | İşlem isteği ve kısa yerel sağlık isteği ikisi de başarısızsa gösterilir. Uygulama penceresini kontrol edip yeniden açın. |

Bir `fetch` başarısız olduğunda arayüz yalnızca yerel `/api/health` adresini üç saniyelik süreyle kontrol eder. Yerel sunucu yanıt veriyorsa Gemini hatası **Uygulamaya ulaşılamadı** olarak gösterilmez. Sağlık isteğinin kendisi zaman aşımına uğrarsa ayrı bir **Yerel uygulama sağlık kontrolüne zamanında yanıt vermedi** mesajı gösterilir.

Başlatıcının mevcut `logs/server.log` dosyasında güvenli Gemini tanılama satırları vardır: işlem adı, başarı/başarısızlık, sabit hata kategorisi ve geçen milisaniye. Anahtar, model/istek gövdesi, Google'ın ham yanıtı veya stack trace bu satırlara yazılmaz. Örnek: `gemini_settings operation=list_models result=failure category=gemini_timeout elapsed_ms=50000`.

Aşama 4'te **Proje → Senaryo → Senaryoyu Aç** üzerinden uçtan uca genel amaçlı senaryo akışı eklendi. Mevcut anahtar ve keşfedilip kaydedilmiş model yeniden kullanılır; Settings model keşfi/bağlantı akışı korunur. Üretim arka planda bölümler halinde ilerler; üretim çağrısının HTTP süresi 120 saniyedir, Settings süreleri yukarıdaki gibi kalır. Ollama ve OpenAI üretim adaptörleri de isteğe bağlıdır. Kullanım: [Senaryo rehberi](SCRIPT_ENGINE.md). Motor seçmek tek başına üretim başlatmaz.

## Güvenlik

- Anahtar mevcut şifreli yerel kasada saklanır; Windows'ta kasa anahtarı kullanıcı hesabına bağlı DPAPI ile korunur. Ayrıntılar: [Ayarlar](SETTINGS.md).
- Kayıttan sonra anahtar alanı boşalır; tarayıcıya sadece maske ve durum döner. Boş anahtarla **Kaydet**, önceki anahtarı korur. Onaylı **Temizle** yalnızca Gemini bilgilerini siler.
- Anahtar proje tablosuna, tarayıcı depolamasına veya Git'e yazılmaz. Model alanına API anahtarı girilmesi reddedilir.
- Sunucu anahtarı yalnızca resmi Google API isteğinin `x-goog-api-key` başlığında kullanır; URL'ye eklemez. HTTPS sertifika doğrulaması açıktır, yönlendirmeler izlenmez.
- Ham Google hata gövdeleri kullanıcıya veya günlüğe aktarılmaz. Model adları doğrulanır, anahtar içeren model adları gösterilmez. Üretim adaptörü çıktıda olası anahtar yankısını da maskeler; düşünce parçalarını ve eksik/engellenmiş çıktıları kabul etmez.
- Gemini sitesi taranmaz veya tarayıcıyla otomatikleştirilmez; web hesabı/abonelik oturumu kullanılmaz. Gerçek API anahtarınızı destek mesajına veya kaynak dosyaya yapıştırmayın.

## Doğrulanan resmi API sözleşmesi

2026-10-07 tarihinde Google'ın resmi API tanımları ve resmi Python SDK kaynağı kontrol edildi:

| İşlem | Resmi Developer API |
| --- | --- |
| Temel adres | `https://generativelanguage.googleapis.com/v1beta` |
| Kimlik doğrulama | `x-goog-api-key` HTTP başlığı |
| Model listesi / bağlantı testi | `GET /models`, `pageSize`, isteğe bağlı `pageToken` |
| Liste yanıtı | `models`, isteğe bağlı `nextPageToken`; modelin `name` ve `supportedGenerationMethods` alanları |
| Senaryo adaptörünün üretim çağrısı | `POST /models/{model}:generateContent` |
| Üretim isteği | `systemInstruction.parts[].text`, `contents[].role`, `contents[].parts[].text` |
| Üretim yanıtı | `candidates[].finishReason`, `candidates[].content.parts[].text`, isteğe bağlı `thought` ve `promptFeedback.blockReason` |

Kaynaklar:

- [Google resmi SDK: adres, API sürümü ve anahtar başlığı](https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py)
- [Google resmi ModelService: listModels HTTP yolu ve sayfalama](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/model_service.proto)
- [Google resmi Model: model adı ve desteklenen üretim işlemleri](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/model.proto)
- [Google resmi GenerativeService: generateContent yolu, istek ve yanıt](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/generative_service.proto)
- [Google resmi Content/Part tanımları](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/content.proto)

Gerçek model kimliği tahmin edilmez veya varsayılan olarak sabitlenmez. Liste, hesabın API yanıtından alınır; yalnızca `generateContent` destekleyen modeller seçime sunulur. Sayfalama beş sayfa ve toplam zaman sınırıyla korunur. Bağlantı testi erişimi ve seçilen modelin listede bulunmasını denetler; sonraki bir üretim çağrısının kotasını veya başarısını garanti etmez. Otomatik ücretli yeniden deneme yapılmaz.

## Geliştiriciler için

- `app/providers/base.py`: `ScriptProvider` protokolü ve güvenli Türkçe `ScriptProviderError`.
- `app/providers/gemini.py`: model listeleme, salt okunur bağlantı testi ve `generate_script(prompt)` adaptörü. Özgün içerik sistem talimatı kullanır.
- `app/providers/factory.py`: açık sağlayıcı seçimi; hata durumunda başka sağlayıcıya sessiz geçiş yoktur.
- `GET /api/settings`: güvenli Gemini model/maske/durum bilgisi, keşfedilen `models` ve `model_verified`. Yerel listede bulunmadan model kaydı doğrulanmış sayılmaz.
- `PUT /api/settings/gemini`, `DELETE /api/settings/gemini`: mevcut şifreli ayar API'si.
- `POST /api/settings/gemini/models`: güvenli model kimlikleri listesi ve maskeli ayarlar; mevcut modelden bağımsız olarak yalnızca kayıtlı anahtarı kullanır. Sonucu şifreli yerel ayarlarda saklar.
- `POST /api/settings/gemini/test`: güvenli sonuç, model listesi ve maskeli ayarlar.
- Değişiklik/test/listeleme istekleri mevcut aynı köken, yerel Host ve `X-AI-Video-Studio: settings` korumasını kullanır; yanıtlar önbelleğe alınmaz.
- Projedeki `script_engine`: `ollama`, `openai` veya `gemini`. Şema 2 → 3 yükseltmesi mevcut projelere `ollama` varsayılanını ekler; eski kayıtları, zamanları, klasörleri ve şifreli ayarları korur.

Testlerdeki model kimlikleri ve anahtarlar yalnızca uydurma test verileridir. Gemini HTTP yanıtları taklit edilerek başarı, kota/erişim/ağ hataları, yanıt doğrulaması ve gizli bilgi sızıntısı test edilir. Chromium kontrolünde de Google yanıtları taklit edilmiştir. Sahibi Gemini Settings bağlantısını gerçek Windows'ta başarıyla doğruladı. **Bu bulut ortamında yeni senaryo akışı canlı Google API anahtarıyla veya gerçek Windows'ta denenmedi.**

`tests/frontend/settings_http.test.cjs`, gerçek arayüz istek yardımcısını sanal saatle çalıştırır; 25/60 saniyelik senaryolar için beklemek gerekmez. Pytest, Node.js varsa bu 19 testi de çalıştırır; Node yoksa bu geliştirici kontrolünü açıkça atlar. Node uygulamayı başlatmak için gerekli değildir. Chromium kontrolünde ayrıca gerçek 23 saniyelik gecikme uygulanıp 20. saniyede yanlış uygulama hatası çıkmadığı doğrulandı.
