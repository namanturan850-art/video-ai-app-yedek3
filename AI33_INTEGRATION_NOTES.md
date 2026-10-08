# AI33 / OpenSpeaker — doğrulanmış sözleşme ve eksik belgeler

## Güncel sözleşme: sahibinin doğruladığı AI33 v3 belgesi

**API hedefi `https://api.ai33.pro`, TTS isteği `multipart/form-data` / FormData, kimlik doğrulaması `xi-api-key`.** Sahibinin bu görüşmede sağladığı yeni doğrulanmış belge, önceki OpenSpeaker hedefi/JSON varsayımının yerini aldı. Ücretli üretim ve önizleme hâlâ kapalıdır; ses kaydı kimlik/ad alanları ve tamamlanan TTS görevinin ses çıktı alanı doğrulanmadan açılmaz.

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

## Uygulanan ağ sözleşmesi

| İşlem | Resmî endpoint | Doğrulanan giriş / durum |
| --- | --- | --- |
| Salt okunur bağlantı | `GET /v1/credits` | `xi-api-key`; geçerli HTTP/JSON yanıtı. Bakiye alanı bilinmediği için sayı gösterilmez. |
| Ses arama | `GET /v3/voices` | `provider`, `search`, `page`, `page_size`. Canlı tanı kök success/format_version/data/pagination türlerini doğruladı; data[0] kimlik/ad anlamı henüz doğrulanmadı. |
| Görev oluşturma | `POST /v3/text-to-speech` | FormData: `text`, `voice_id`, `speed`, `with_transcript=false`; yanıt `success: true`, kök `task_id`. Ücretli yol eksik çıktı sözleşmesi yüzünden kapalıdır. |
| Aynı görevi izleme | `GET /v1/task/{task_id}` | Belgelenmiş görev kimliği; yanıt alanları/durumları eksik, kimlik korunarak güvenli hata döner. |

`GET /v1/tasks` ve `GET /v1/health-check` belgede bulunur; bu sürüm görev geçmişi veya ek health çağrısı yapmaz. Bağlantı için kredi endpoint'i yeterlidir. Uzak görev silme/iade, webhook, yeni ses klonlama veya metin dışı toplu giriş uygulanmadı.

Ses sağlayıcısı seçenekleri: `elevenlabs`, `minimax`, `clone`, `edge`, `vbee`, `fishaudio`. `clone` yalnız mevcut izinli seslerin listesi için hazırlanmıştır. Sayfa en az 1, sayfa boyutu 1–100 (arayüzde 30). Dil sorgu parametresi yok. Hız 0,5–1,5; varsayılan 1,0. Metin sınırı görev başına 1.000.000 karakter. `receive_url`, `model` ve kalite seçenekleri gönderilmez; transcript üretimi `with_transcript=false` ile kapalıdır. Kokoro öneki TTS için doğrulandı; ses araması sağlayıcı filtresinin Kokoro değeri bu belgeyle doğrulanmadığından yeni arama parametresi eklenmedi.

## Tamamlamak için gereken resmî örnekler

1. `GET /v3/voices`: `data` dizisindeki bir ses kaydının **kimlik/ad alanları**; varsa sağlayıcı, dil, cinsiyet ve önizleme alanları.
2. `GET /v1/task/{task_id}`: bekleyen, tamamlanan ve başarısız görev örnekleri; **durum alanı ve gerçek değerleri**, **ses dosyası çıktı alanı**.
3. Çıktı indirme adresinin resmî host/CDN bilgisi ve yönlendirme davranışı. Örnekleri gerçek imzalı URL/token olmadan paylaşın.
4. İsteğe bağlı: kredi bakiye alanı, belgelenmiş kota/kredi hata kodları ve transcript/timing yanıtı. Bunlar bilinmeden sayı, kredi yetersizliği kodu veya transcript uydurulmaz.

**Gerçek API anahtarı veya özel indirme URL'si paylaşmayın.** Gerçek alanlar doğrulanmadan `OpenSpeakerProvider.contract_ready` açılmamalıdır. Bu kilit anahtarın doğruluğundan bağımsızdır ve önizleme dahil hiçbir ücretli görev başlatmaz. İç `Voice` alanları ve `pending / complete / failed` durumları yalnız uygulamanın sağlayıcı soyutlamasıdır; OpenSpeaker'ın yanıt şeması oldukları iddia edilmez.

## Koruma ve tanılama

- Anahtar mevcut şifreli yerel kasada; Windows'ta kullanıcı hesabına bağlı DPAPI koruması. API yanıtına yalnız maske döner. SQLite, dosya metadata'sı ve günlüklerde anahtar yok.
- Şema 8 yalnız seslendirme sürümü/iş/aktif seçim tabloları ekler; eski proje/senaryo/sahne/stok/ayar verisini silmez.
- Tam üretim yalnız güncel onaylı metni **aynı haliyle**, SHA-256 iziyle tek görev olarak kullanır. Önizleme ayrı kısa dil örneği, ayrı sürüm ve dosyadır.
- Ücretli POST en fazla bir kez denenir. Kimlik alınırsa hemen SQLite'a kaydedilir. Yanıt beklenmeyen biçimde olsa bile doğrulanabilir kök kimlik korunur. Kimlik alınamayan oluşturma zaman aşımı otomatik tekrar edilmez.
- İzleme 3 saniye aralıklı, 30 dakika sınırında; görev kimliğiyle Devam Et. Tarayıcıdaki kısa yerel istekler bu işlemi beklemez. Yeniden açılışta yarım işler güvenli hata durumuna geçer; aynı uzak görev sürdürülebilir.
- Ses listesinin doğrulanan kök şekli: `success: boolean`, `format_version: string`, `data: array`, `pagination: object`. Tanı yalnız `data[0]` kaydının alan adlarını/türlerini ekler (`data_first_item_fields`); ikinci ses veya iç içe alanlar incelenmez. Kimlik/ad eşleştirmesi yapılmaz.
- Görev tanısı kök alan adları/türleri ve `metadata` nesnesinin ilk düzey alan adları/türlerini ekler (`metadata_fields`). Çıktı alanının hangisi olduğu veya durumların anlamı tahmin edilmez. HTTP durumu, işlem ve görev kimliği varlığı korunur. Alan sayısı her konumda en fazla 40; sır içeren veya geçersiz alan adları atılır. Ham gövde, alan değerleri, başlık, imzalı URL, tam metin veya sır kaydedilmez. Tanı Ayarlar ve Seslendirme ekranında güvenli metin olarak gösterilir.
- Ses dosyası güvenli `voice/<uuid>.<format>` adıyla geçici dosya, imza/tür/boyut kontrolü ve atomik rename kullanır. Windows klasör bağlantıları/junction'lar reddedilir; indirilen dosyaya API başlığı gönderilmez. İzinli çıktı host'ları henüz belgelendirilmediği için üretim adaptörünün listesi boştur.
- WAV süresi yerel ölçülür; diğer dosyalarda varsa ffprobe kullanılır. Araç eksikliği sesi başarısız saymaz. Render veya altyazı yapılmaz.

Otomatik testler resmî doğrulanan girişleri ve iç iş akışını sınar. **Live provider test must be run by owner on Windows.** Sahip anahtarı olmadan canlı OpenSpeaker başarısı iddia edilmez. [Basit Windows kontrolleri](docs/NARRATION.md).
