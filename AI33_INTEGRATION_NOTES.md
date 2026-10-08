# AI33 / OpenSpeaker — doğrulanmış sözleşme ve eksik belgeler

## Güncel sözleşme: sahibinin doğruladığı AI33 v3 belgesi

**API hedefi `https://api.ai33.pro`, TTS isteği `multipart/form-data` / FormData, kimlik doğrulaması `xi-api-key`.** Sahibinin bu görüşmede sağladığı yeni doğrulanmış belge, önceki OpenSpeaker hedefi/JSON varsayımının yerini aldı. Sahibinin yeni canlı Windows doğrulaması ses kaydı şemasını da doğruladı. Ses listesi, seçim ve sağlayıcının hazır örneği kullanılabilir. Ücretli üretim/üretim önizlemesi hâlâ kapalıdır; tamamlanan TTS görevinin ses çıktı alanı doğrulanmadan açılmaz.

## İlk incelemenin kaynakları (önceki sözleşme)

2026-10-08 tarihinde aşağıdaki resmî kaynaklar doğrudan incelendi:

- https://openspeaker.ai/developers
- https://openspeaker.ai/api-guide.txt
- https://openspeaker.ai/openapi-generation.json

Genel rehberin kendi son kaynak doğrulama tarihi 2026-07-13. Giriş gerektiren ayrıntılı belgeye bağlantı var; herkese açık sayfa bu yanıt sözleşmelerini göstermiyor. İncelenen OpenAPI yanıtları `type: object, additionalProperties: true`; **ses kaydı, görev durumları, ses çıktı adresi ve kredi bakiye alanı tanımlanmıyor**. Genel endpoint açıklaması, bu alanları tahmin etmek için yeterli değildir.

Proje sahibinin bu görüşmede API belgesinden paylaştığı görev oluşturma başarı örneği doğrulandı:

```json
{"success": true, "task_id": "uuid_task_id"}
```

Yeni doğrulanan TTS isteği metin form alanları içerir: `text`, **zaten önekli** `voice_id`, `speed`, `with_transcript=false`. HTTP istemcisi multipart boundary ve Content-Type başlığını kendisi oluşturur; dosya yükleme/filename yoktur. `model`, `receive_url`, `file_name` ve `pronunciation_dictionary_id` gönderilmez. Yerel uygulama webhook kullanmaz; görev kimliğini saklayıp polling yapar.

Geçerli kimlik önekleri: `elevenlabs_`, `minimax_`, `clone_`, `edge_`, `kokoro_`, `vbee_`, `fishaudio_`. Kimliğe önek tahmin edilerek eklenmez; geçersiz/eksik önek ağ çağrısından önce reddedilir. Eski şifreli API anahtarı, kayıtlı base_url/voice_id/model ve projeler korunur. Varsayılan ve etkin hedef `https://api.ai33.pro`; eski kayıtlı URL gelişmiş bölümde korunur, ağ hedefini değiştirmez.

## Canlı doğrulanan v3 ses yanıtı

Kök: `success: boolean`, `format_version: string`, `data: array`, `pagination: object`.

Her `data[]` kaydında **voice_id → iç voice_id**, **name → display_name**. Diğer doğrulanan alanlar: `description`, `language`, `locale`, `gender`, `age`, `accent`, `category`, `use_cases`, `descriptives`, `tags`, `languages`, `preview_url`, `avatar_url`. Son alan string veya null; dört dizi alanının iç öğe şeması verilmediği için öğeler çevrilmeden/alanları tahmin edilmeden korunur. Eksik metinler boş, diziler boş liste, avatar null olabilir. Eksik ek bilgiler ses listesini bozmaz. Kök success/format/data/pagination türleri ve gerekli kimlik/ad denetlenir; bozuk yanıtta eski seçim korunur.

İç sağlayıcı, belgelenmiş aramada kullanıcının seçtiği sağlayıcıdır; yanıt kaydında doğrulanmamış bir `provider` alanı okunmaz. Ham kök yanıt/pagination/ek bilinmeyen alanlar tarayıcıya veya kasaya kopyalanmaz. Yalnız normalize sesler şifreli ayar kasasında saklanır, seçim/hız yeniden açılışta korunur.

**Önizlemeyi Dinle**, doğrulanan `preview_url` için sağlayıcının hazır örneğini açar. HTTPS, kullanıcı/parola içermeyen, standart portlu ve yerel/özel adres olmayan URL kabul edilir; uygunsuz URL boş bırakılır ve liste başarısız sayılmaz. Örnek yalnız kullanıcı tıklayınca tarayıcıda yüklenir (`preload=none`, anonim crossorigin, referrer yok); anahtar/Authorization/cookie eklenmez, backend URL proxy'si veya TTS POST'u kullanılmaz. Avatar URL'si metadata olarak korunur; otomatik dış avatar yüklemesi yapılmaz. Gerçek CDN'nin tarayıcı/CORS davranışı sahibinin Windows kontrolünde doğrulanmalıdır.

## Uygulanan ağ sözleşmesi

| İşlem | Resmî endpoint | Doğrulanan giriş / durum |
| --- | --- | --- |
| Salt okunur bağlantı | `GET /v1/credits` | `xi-api-key`; geçerli HTTP/JSON yanıtı. Bakiye alanı bilinmediği için sayı gösterilmez. |
| Ses arama | `GET /v3/voices` | `provider`, `search`, `page`, `page_size`. Sahibinin canlı doğruladığı data[] voice_id/name ve ek alanlar normalize edilir; ham yanıt döndürülmez. |
| Görev oluşturma | `POST /v3/text-to-speech` | FormData: `text`, `voice_id`, `speed`, `with_transcript=false`; yanıt `success: true`, kök `task_id`. Ücretli yol eksik çıktı sözleşmesi yüzünden kapalıdır. |
| Görev geçmişi tanısı | `GET /v1/tasks` | Resmî salt okunur yol; filtre değeri/kayıt şeması tahmin edilmez. Yalnız alan adları/türleri. |
| Aynı görevi izleme | `GET /v1/task/{task_id}` | Belgelenmiş görev kimliği; yanıt alanları/durumları eksik, kimlik korunarak güvenli hata döner. |

`GET /v1/tasks` resmî genel rehber ve OpenAPI ile doğrulanmıştır. Bu sürüm **Görev Geçmişini İncele** ile salt okunur tanı yapar; belgelenmiş type filtresinin TTS değeri bilinmediğinden filtre gönderilmez. `GET /v1/health-check` için ek çağrı yapılmaz. Bağlantı için kredi endpoint'i yeterlidir. Uzak görev silme/iade, webhook, yeni ses klonlama veya metin dışı toplu giriş uygulanmadı.

Ses sağlayıcısı seçenekleri: `elevenlabs`, `minimax`, `clone`, `edge`, `vbee`, `fishaudio`. `clone` yalnız mevcut izinli seslerin listesi için hazırlanmıştır. Sayfa en az 1, sayfa boyutu 1–100 (arayüzde 30). Dil sorgu parametresi yok. Hız 0,5–1,5; varsayılan 1,0. Metin sınırı görev başına 1.000.000 karakter. `receive_url`, `model` ve kalite seçenekleri gönderilmez; transcript üretimi `with_transcript=false` ile kapalıdır. Kokoro öneki TTS için doğrulandı; ses araması sağlayıcı filtresinin Kokoro değeri bu belgeyle doğrulanmadığından yeni arama parametresi eklenmedi.

## Tamamlamak için gereken resmî örnekler

1. `GET /v1/task/{task_id}`: bekleyen, tamamlanan ve başarısız görev örnekleri; **durum alanı ve gerçek değerleri**, **ses dosyası çıktı alanı**.
2. Çıktı indirme adresinin resmî host/CDN bilgisi ve yönlendirme davranışı. Örnekleri gerçek imzalı URL/token olmadan paylaşın.
3. İsteğe bağlı: kredi bakiye alanı, belgelenmiş kota/kredi hata kodları ve transcript/timing yanıtı. Bunlar bilinmeden sayı, kredi yetersizliği kodu veya transcript uydurulmaz.

**Gerçek API anahtarı veya özel indirme URL'si paylaşmayın.** Gerçek alanlar doğrulanmadan `OpenSpeakerProvider.contract_ready` açılmamalıdır. Bu kilit anahtarın doğruluğundan bağımsızdır ve üretim önizlemesi dahil hiçbir ücretli görev başlatmaz. Sağlayıcının mevcut preview_url örneği bu ücretli yoldan bağımsızdır. İç `Voice` alanları ve `pending / complete / failed` durumları yalnız uygulamanın sağlayıcı soyutlamasıdır; OpenSpeaker'ın yanıt şeması oldukları iddia edilmez.

## Koruma ve tanılama

- Anahtar mevcut şifreli yerel kasada; Windows'ta kullanıcı hesabına bağlı DPAPI koruması. API yanıtına yalnız maske döner. SQLite, dosya metadata'sı ve günlüklerde anahtar yok.
- Şema 8 yalnız seslendirme sürümü/iş/aktif seçim tabloları ekler; eski proje/senaryo/sahne/stok/ayar verisini silmez.
- Tam üretim yalnız güncel onaylı metni **aynı haliyle**, SHA-256 iziyle tek görev olarak kullanır. Önizleme ayrı kısa dil örneği, ayrı sürüm ve dosyadır.
- Ücretli POST en fazla bir kez denenir. Kimlik alınırsa hemen SQLite'a kaydedilir. Yanıt beklenmeyen biçimde olsa bile doğrulanabilir kök kimlik korunur. Kimlik alınamayan oluşturma zaman aşımı otomatik tekrar edilmez.
- İzleme 3 saniye aralıklı, 30 dakika sınırında; görev kimliğiyle Devam Et. Tarayıcıdaki kısa yerel istekler bu işlemi beklemez. Yeniden açılışta yarım işler güvenli hata durumuna geçer; aynı uzak görev sürdürülebilir.
- Ses listesi doğrulanan şemadan ayrıştırılır. Bozuk yanıt tanısı yalnız data[0] alan adları/türleriyle sınırlıdır; ham değerler döndürülmez. Normal ses adları ve doğrulanan ek metadata, kullanıcı seçimi için normalize sonuçta bulunur.
- Görev geçmişi (`GET /v1/tasks`) şeması hâlâ bilinmiyor. Gözlenen kök dizi alanlarının her birinde yalnız ilk kayıt ve onun metadata adları/türleri incelenir (`task_array_samples`); kök doğrudan dizi ise aynı işlem uygulanır. Dizi kapsayıcısına data/tasks adı veya TTS türü tahmin edilmez. En fazla dört dizi ve konum başına 40 alan; sonraki kayıtlar/derin metadata incelenmez. Dizi konumu görülmezse boş tanı listesi döner, kayıt uydurulmaz. 404/405 geçmişe erişilememe hatası ses ayarlarını değiştirmez.
- Görev tanısı kök alan adları/türleri ve `metadata` nesnesinin ilk düzey alan adları/türlerini ekler (`metadata_fields`). Çıktı alanının hangisi olduğu veya durumların anlamı tahmin edilmez. HTTP durumu, işlem ve görev kimliği varlığı korunur. Alan sayısı her konumda en fazla 40; sır içeren veya geçersiz alan adları atılır. Ham gövde, alan değerleri, başlık, imzalı URL, tam metin veya sır kaydedilmez. Tanı Ayarlar ve Seslendirme ekranında güvenli metin olarak gösterilir.
- Ses dosyası güvenli `voice/<uuid>.<format>` adıyla geçici dosya, imza/tür/boyut kontrolü ve atomik rename kullanır. Windows klasör bağlantıları/junction'lar reddedilir; indirilen dosyaya API başlığı gönderilmez. İzinli çıktı host'ları henüz belgelendirilmediği için üretim adaptörünün listesi boştur.
- WAV süresi yerel ölçülür; diğer dosyalarda varsa ffprobe kullanılır. Araç eksikliği sesi başarısız saymaz. Render veya altyazı yapılmaz.

Otomatik testler resmî doğrulanan girişleri ve iç iş akışını sınar. **Live provider test must be run by owner on Windows.** Sahip anahtarı olmadan canlı OpenSpeaker başarısı iddia edilmez. [Basit Windows kontrolleri](docs/NARRATION.md).
