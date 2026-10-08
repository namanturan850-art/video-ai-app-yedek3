# AI33 / OpenSpeaker — canlı doğrulanmış Part 7 sözleşmesi

## Doğrulama kaynağı ve etkin sözleşme

Proje sahibi gerçek Windows bilgisayarında AI33 bağlantısını, v3 ses kitaplığını ve hesabında zaten oluşturduğu kısa TTS görevinin `/v1/tasks` kaydını doğruladı. Bu görüşmede sağladığı son canlı sözleşme, önceki belgesiz TTS çıktı kilidinin yerini alır. **OpenSpeakerProvider.contract_ready=true**; yeni görev hâlâ kullanıcı kredi onayı gerektirir. Tanılama veya rastgele sağlayıcı verisi bu sabiti değiştirmez.

**API hedefi `https://api.ai33.pro`, kimlik doğrulaması `xi-api-key`.** Eski `api.openspeaker.ai` adresi/JSON varsayımı kullanılmaz. Eski şifreli anahtar, base_url/model kayıtları, seçili sağlayıcı/ses/hız, projeler ve dosyalar korunur. Kayıtlı eski URL ağ hedefini değiştirmez.

İlk endpoint incelemesinin resmî kaynakları (2026-10-08): https://openspeaker.ai/developers, https://openspeaker.ai/api-guide.txt, https://openspeaker.ai/openapi-generation.json. Genel rehber/OpenAPI ayrıntılı yanıt alanlarını tanımlamıyordu. Son alan/değer doğrulamasının kaynağı **sahibinin canlı AI33 sonucu ve bu görüşmede sağladığı API belgeleri**dir. Sahibinin gerçek görev/ses kimliği veya özel çıktı URL'si kaynakta bulunmaz; test değerleri sentetiktir.

## TTS oluşturma: değiştirilmeden korunan FormData

`POST /v3/text-to-speech`, **multipart/form-data**, JSON değil. HTTP istemcisi boundary ve Content-Type başlığını kendisi oluşturur. Yalnız metin form alanları:

| Alan | Uygulamanın gönderdiği |
| --- | --- |
| text | Tam anlatımda yalnız güncel onaylı senaryo, aynen |
| voice_id | Keşfedilmiş ses kaydındaki zaten önekli kimlik |
| speed | 0,5–1,5; varsayılan 1,0 |
| with_transcript | false |

`receive_url`, `model`, `file_name`, `pronunciation_dictionary_id`, dosya/filename, webhook veya başka seçenek gönderilmez. Ses önekleri: `elevenlabs_`, `minimax_`, `clone_`, `edge_`, `kokoro_`, `vbee_`, `fishaudio_`. Önek tahmin edilerek eklenmez. Metin sınırı 1.000.000 karakter; otomatik birden çok ücretli göreve bölme yoktur.

Doğrulanmış oluşturma yanıtı: `{"success":true,"task_id":"..."}`. Kimlik güvenli 1–150 harf/rakam/tire/alt çizgi biçiminde olmalıdır. `creation_attempted` **POST öncesinde**, alınan `task_id` **ilk polling öncesinde** SQLite'a yazılır. Geçerli kimlik bozuk başarı yanıtında bile checkpoint için korunur. Kimlik alınmadan oluşturma belirsiz kalırsa otomatik yeni POST yapılmaz.

## Canlı doğrulanan görev kaydı

`GET /v1/tasks` kökü: `success:boolean`, `data:array`, `page:number`, `limit:number`, `total:string`.

Tamamlanan TTS öğesi: `id:string`, `created_at:string`, `status:string`, `credit_cost:number`, `metadata:object`, `progress:number`, `type:string`, `updated_at:string`, `text:string`, `text_length:number`, `text_truncated:boolean`.

Metadata: `v3:object`, `data:object`, `query:object`, `voice_id:string`, **audio_url:string**. Canlı değerler: **status="done", type="tts"**. Önceki örnek `text_to_speech` gerçek tür değildir; çıktı için `output_uri` veya başka görevlerin alanları kullanılmaz.

### GET /v1/task/{task_id} normalizasyonu

- İstek kimliği ağdan önce doğrulanır. Yanıt nesne olmalıdır. Yanıtta `id` varsa geçerli ve istenen kimlikle aynı olmalıdır. `type` varsa **tts** olmalıdır.
- Normal yanıtta status dolu string olmalıdır. **Yalnız tam done değeri** tamamlanmadır; büyük/küçük harf veya bilinmeyen durum eşdeğeri uydurulmaz.
- Done için metadata nesne ve `metadata.audio_url` boş olmayan, güvenli HTTPS string olmalıdır. Dahili sonuç `{state:"complete", audio_url:..., progress:...}`; URL yalnız backend indirme sınırına geçer, tarayıcıya/SQLite/günlüklere verilmez.
- Done dışındaki string durumlar, açık hata yoksa **pending** olur. Belgelenmemiş pending/failed durum listesi yoktur. Sahibinin istediği isteğe bağlı `error_message` dolu string veya açık `success=false` yapısı **failed** olur; ham hata metni gösterilmez. Başka hata alanı tahmin edilmez.
- İsteğe bağlı progress yalnız sonlu 0–100 sayıysa korunur; geçersiz değer None olur ve tamamlanmış sesi engellemez.
- Yanıt uyuşmazlığı safe `unexpected_task_schema` ve yalnız alan adı/türü tanısı döndürür. Anahtar, URL, provider text/full metadata/başlık döndürülmez.

Polling 3 saniye aralıklı, deneme başına 30 dakika sınırındadır. App restart/ağ kesintisi/polling veya ses indirme hatası sonrasında **Devam Et**, yalnız kayıtlı aynı görev için GET yapar; ikinci ücretli POST oluşturmaz. Yeniden üretim ancak ayrı kullanıcı onayıyla yeni sürüm/yeni görevdir.

## Ses indirme ve yerel oynatma

CDN adı tahmin edilmez. Başlangıç izni yalnız doğrulanmış kimlik doğrulamalı task yanıtının audio_url hostundan türetilir ve **o göreve** aittir; genel indirme allowlist'i oluşturulmaz. HTTPS/standart port, normal DNS hostname veya genel IP literal; kullanıcı/parola, fragment, kontrol karakteri, localhost/iç ağ adları, özel/loopback/link-local/reserved/multicast IP literal, file/data/javascript ve tehlikeli port reddedilir.

Yönlendirme en fazla üç kez izlenir. Aynı host tercih edilir; farklı host da HTTPS ve aynı adres kontrollerini geçmelidir. Her istekte cookie jar temizlenir; **xi-api-key, Authorization veya Cookie ses hostuna gönderilmez**. İndirme sırasında o işlem bağlamının HTTP debug günlükleri de bastırılır; farklı hosta Location ve Set-Cookie değerleri imzalı URL/çerez sızıntısı yapmaz. TLS doğrulaması kapatılmaz.

MP3/WAV/M4A/OGG/FLAC mevcut tür, imza, boyut ve eksik dosya kontrolleri korunur: geçici dosya → fsync → atomik rename → `data/projects/<id>/voice/<uuid>.<format>`. API anahtarı veya uzak URL yerel metadata'da bulunmaz. Windows bağlantı/junction'ları reddedilir. Tarayıcı ses oynatma yalnız yerel `/api/projects/<id>/narration/versions/<version>/audio` yoludur.

WAV süresi yerel ölçülür; diğer formatlarda varsa ffprobe kullanılır. Araç/ölçüm yoksa süre null ve açıklama olur; tamamlanmış dosya korunur. Bu durum yeniden ücretli görev oluşturmaz.

## Ses listesi, varsayılanlar ve arayüz performansı

`GET /v3/voices`: provider/search/page/page_size. Kök success:boolean/format_version:string/data:array/pagination:object; yalnız data[].voice_id → voice_id ve name → display_name. İsteğe bağlı description/language/locale/gender/age/accent/category/use_cases/descriptives/tags/languages/preview_url/avatar_url korunur. Eksik bilgi/null avatar listeyi bozmaz; dizi öğeleri için şema tahmini yoktur. Sesler/seçim şifreli kasada saklanır.

Yeni ayarın varsayılanı **ElevenLabs**; mevcut MiniMax/clone/Edge/Vbee/FishAudio tercihleri değişmez. Kokoro TTS öneki doğrulanmış, GET arama filtresi doğrulanmamış olduğundan yeni filtre eklenmez.

Tercih edilen kullanım: **ses adını ara → ilk 30 → gerekirse Daha Fazla Ses Yükle**. Önceki/Sonraki tek sayfa; Daha Fazla ekleme/voice_id tekilleştirme. İlk açılışta büyük eski cache'in tamamı çizilmez; ilk 30 ve kayıtlı seçili ses korunur. Her sayfada tüm Ayarlar/Gemini/model ekranı yenilenmez. Mevcut option düğümleri korunur, yalnız yeni düğümler DocumentFragment ile eklenir; aynı metadata yeniden çizilmez. Yalnız yükleme düğmeleri işlem boyunca kapanır, diğer ayarlar kullanılabilir. Sağlayıcı/arama değişince eski bağlam yanıtı reddedilir ve toplu işlem durur.

Tüm Sesleri Getir otomatik değildir; **“Çok sayıda ses yüklemek arayüzü yavaşlatabilir. Devam edilsin mi?”** onayı ister. Sıralı en fazla 10 sayfa/300 ses, boş dizide durur; sayfalar arasında browser'a yürütme hakkı verilir. Ses pagination alt alanları hâlâ doğrulanmadığından tahmin edilmez.

**Önizlemeyi Dinle** sağlayıcının hazır preview_url örneğidir; yalnız tıklama, preload=none, anonim crossorigin/referrer yok, kredi/TTS POST yok. Projedeki ayrı **Kısa TTS Testi (kredi kullanır)** kısa dil örneğini ayrı onay/sürüm/dosyayla üretir ve tam anlatımı aktif olarak değiştirmez.

## Salt okunur tanılama ve henüz kullanılmayan bilgiler

Mevcut Görevi İncele ve Görev Geçmişini İncele yalnız GET yapar; görev oluşturmaz. Kök/ilk kayıt ve metadata için bounded ad/tür tanısı, ayrıca güvenli status/type token değerleri gösterilir. Kullanıcı Task ID'si kaydedilmez. Ham yanıt, private URL değerleri, görev text alanı veya metadata değerleri gösterilmez. Ekran **“Canlı AI33 TTS görev yapısı doğrulandı.”** diyebilir; tanı hiçbir runtime ayarını/contract_ready'yi değiştirmez.

Kredi endpoint'i başarıyla okunur fakat kesin sayısal alan doğrulanmadığından **“Kredi bilgisi API tarafından döndürüldü ancak bu sürümde gösterilemiyor.”** korunur. Ses üretimi kredi sayısının gösterilmesine bağlı değildir. Kredi yetersizliği kodu, transcript/timing, yeni model/kalite veya diğer görev tipi çıktıları tahmin edilmez.

SQLite **şema 8 değişmedi**. Projeler, onaylı senaryolar, sahne planları, medya kilitleri ve Pixabay dosyaları korunur. Yalnız güncel onaylı metin ve SHA-256 fingerprint kullanılır; kaynak değişirse eski ses stale olur ve otomatik yeniden üretilmez. Yeni ses sürümleri eski dosyaları silmez.

Part 8 handoff: project_id/source_script_version_id/narration_version_id/audio_local_path/audio_duration/voice_id/voice_provider/speed/target_language, transcript=null, timing_source=audio_duration, hazır aktif ses için ready=true. Süre ölçülemediyse audio_duration null kalır; sahne süreleri hâlâ tahminidir. **Part 8 artık bu değişmeyen yerel handoff'u kullanır: [Altyazı ve zamanlama](docs/SUBTITLES.md). Part 9/render/müzik/YouTube başlamadı.**

Otomatik ve Chromium testlerindeki dış API/medya yanıtları sentetiktir. **Live provider test must be run by owner on Windows.** Sonraki Part 7 canlı Windows testi sahibi tarafından tamamlandı: görev/kredi, yerel indirme/oynatma, yeniden açılışta kalıcılık ve mevcut Pixabay korunumu başarılı. Bulutta yeni ücretli API çağrısı yapılmadı. [19 basit Windows adımı](docs/NARRATION.md).
