# Video Oluştur / Render — Part 9 + 9.5 Smart YouTube Editing

Mevcut proje → **Video Oluştur / Render**. Bu işlem tamamen yereldir; AI33, Gemini, OpenAI, Ollama, Pexels veya Pixabay çağrısı yapmaz ve API kredisi kullanmaz. Part 10 başlamadı.

## Part 9.5 Windows kontrolü

Part 9 ve 9.5 render sahibi tarafından gerçek Windows'ta doğrulandı. Part 9: Gyan FFmpeg 9.0.2 + RTX 5070, yaklaşık 193 saniye, 1920×1080, gerçek NVIDIA NVENC, ses ve altyazılar başarılı. Yeni Part 6.5 + 9.5 kalite düzeltmesi için:

1. PR’ı birleştirin.
2. GitHub Desktop → Fetch / Pull.
3. AI Video Studio’yu tamamen kapatın.
4. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın.
5. Aynı projeyi açın.
6. Normal altyazı görünümünü eski başarılı Part 9 videosuyla karşılaştırın.
7. Stok medya bölümünü açın.
8. **Alakaya Göre Medyayı Yeniden Ara** düğmesine basın.
9. Birkaç Bermuda Triangle sahnesini kontrol edin.
10. İlgisiz şehir görüntülerinin tercih edilmediğini kontrol edin.
11. İlgili okyanus/harita/gemi/uçak/bağlam medyasının daha üstte olduğunu kontrol edin.
12. **Dengeli YouTube**, **Otomatik**, **altyazı açık**, **müzik kapalı** ile render oluşturun.
13. Normal altyazıların eski yazı tipi/stili koruduğunu kontrol edin.
14. Vurgu yazısının ayrı kaldığını kontrol edin.
15. Hareket/geçişlerin görünür ama aşırı olmadığını kontrol edin.
16. Önceki videoların hâlâ bulunduğunu kontrol edin.

**Kurgu Planını Gör** açılarak zaman, sahne, efekt, geçiş ve vurgu metni incelenebilir. Kurgu stilini değiştirince plan bu bilgisayarda yeniden hesaplanır; kredi harcanmaz. Tamamlanan videoda **Planlanan kurgu** ve **Uygulanan kurgu** ayrı gösterilir. Bir dekoratif efekt atlanırsa uyarı ve gerçek uygulanan sayı görünür.

## Smart Edit Plan nasıl çalışır?

Önceki Part 9'da kamera hareketi yalnız görsellerde uygulanıyordu; videolarda normalleştirme/kırpma vardı. Vurgu yalnız mevcut `overlay_text`'ten geliyordu. Bu yüzden 37 video, 0 görsel, 0 vurgu metinli bir proje görsel olarak sade kalabiliyordu.

Yeni plan, mevcut Part 8 zamanlaması ve Part 5 düzenleme ipuçlarını salt okunur kullanır. Aynı kaynak fingerprint'i ve stil aynı planı verir; rasgelelik, sağlayıcı çağrısı veya indirme yoktur. Stok yuva kimliği/sırası ve master süre değişmez. Plan render metadata JSON'unda tutulur; yeni veritabanı geçişi yapılmaz.

| Stil | Hareket ve tempo | Geçiş ve metin |
| --- | --- | --- |
| Temel | Önceki Part 9; videoda ek kamera yok, mevcut görsel hareketleri korunur | Mevcut geçiş ve vurgu metni |
| Dengeli YouTube (varsayılan) | Uygun kadrajlarda yaklaşık %4,5–5; ilk 15 saniye daha canlı | Yaklaşık her üçüncü sahne sınırı; vurgu yaklaşık 28 saniyede bir |
| Dinamik YouTube | Uygun kadrajlarda yaklaşık %7–8; daha sık kadraj değişimi | Yaklaşık her ikinci sahne sınırı; vurgu yaklaşık 18 saniyede bir |

Yakın/kişi/detay kadrajları en fazla yaklaşık %1,2 hareketle korunur; zaten hareketli sahneler sakin bırakılır. Önem düzeyi ve mevcut `motion / composition / transition` ipuçları hesaba katılır; kişi/yer/bilgi uydurulmaz. Yüzde/sıklıklar kalite hedefidir, katı rastgele kurallar değildir.

- **Video hareketi:** aynı hareketli video kareleri işlenir; `zoompan d=1` her giriş karesine bir çıktı karesi üretir. Yakınlaşma/uzaklaşma, dört yönde kayma ve hafif kadraj değişimi yüksek çözünürlükte ve sınırlandırılmış güvenli crop ile uygulanır. Slotun tam kare sayısı korunur; siyah kenar/aspect bozulması eklenmez. Ek vurgu yakınlaşması da Dengeli %5 / Dinamik %8 sınırını aşmaz; yakın/yüz kadrajı korunur.
- **Uzun klip:** yaklaşık 7 saniyeden sonra iki, 11 saniyeden sonra üç görsel işlem; açılışta daha erken değişim. Bunlar aynı dosyanın render içindeki parçalarıdır; yeni stok yuvası/indirme yaratmaz, anlatımı çoğaltmaz. Tek stok girişi ve tek core ara video kullanılır; parçalar frame sınırlarında birleşir.
- **Geçiş:** aynı sahne içindeki medya değişimleri genellikle temiz kesme. Seçilmiş sahne sınırlarında yaklaşık 0,43 saniye Dengeli / 0,53 saniye Dinamik crossfade veya kısa koyu geçiş; çok kısa yuvalarda kısaltılır/atlanır. Önceki klibin ek kuyruğu ve sonraki klibin başı kullanılır; master süre ve cue zamanları kaymaz.
- **Vurgu:** mevcut `overlay_text` önceliklidir ve aynen korunur. Yoksa onaylı anlatımda da bulunan tam kısa cue veya cue başındaki kısa cümlecik aynen seçilir. Genellikle 2–8, en fazla 10 kelime; uygun sayı/tarih tercih edilir. Yeni başlık/çeviri/özet/bilgi üretilmez. Uygun metin yoksa atlanır. Tam cue sınırları kullanılır; kelime zamanı tahmin edilmez. Yaklaşık 1,5–3 saniye üst-sol/üst-ortada kalın, kenarlı yazı ve 180 ms hafif fade/scale animasyonu; alt altyazıyla çakışmaz.
- **Altyazı:** üç profilde de başarılı Part 9 stili aynen: Arial/güvenli kurulu fallback, 48 px, normal ağırlık, outline 3, shadow 1, alt orta, 90/90/60 marj. Normal cue'ya animasyon eklenmez. Önceki regresyon profilin 50/52 px ve kalın yazı seçmesinden geliyordu. Üstteki büyük vurgu kendi ayrı stilini kullanır; geçiş seçilmesi vurgu üretmez. SRT/VTT metni ve Part 8 zamanları değişmez; karaoke/kelime zamanı tahmini yoktur.
- **Sürüm uyumluluğu:** yeni plan `smart_edit_v2`; eski tamamlanmış `v1` planı kaynakları aynıyken kendi fingerprint'iyle güncel/oynatılabilir/aktifleştirilebilir kalır. Stilsiz eski Part 9 fingerprint formülü aynen korunur. Yeni render yeni sürümdür; önceki video dosyası yeniden yazılmaz.
- **Güvenli geri dönüş:** hareket hatası → normal kadraj; geçiş hatası → temiz kesme; vurgu hatası → vurgusuz çıktı. Mevcut altyazı/ses ve ana video işlemi korunur; çekirdek işlem de başarısızsa eski aktif video korunarak hata gösterilir. Güvenli kodlar: `smart_motion_failed`, `smart_transition_failed`, `emphasis_render_failed`. Tam kaynak metni/raw stderr/sırlar günlükte yoktur.
- **NVENC ve FFmpeg 9:** filtreler yerel CPU'da çalışabilir; tüm ara ve son video encode seçilen encoder ile yapılır. Otomatik NVIDIA tercihi ve yalnız NVENC başlatma hatasında mevcut tek CPU tekrar denemesi korunur. `-/filter_complex` kullanımı sürer; kaldırılmış `-filter_complex_script` kullanılmaz. Sesin hızı/perdesi, stok sesinin dışlanması ve mevcut isteğe bağlı müzik davranışı değişmez.

193 saniye / 24 sahne / 37 VIDEO / 49 cue / 0 mevcut vurgu regresyon örneği Dengeli planda **33 hareket, 8 geçiş, 6 vurgu, 11 klip içi değişim** üretir. Bu sentetik kaynak biçimi testidir; sahibinin gerçek projesinde seçimler mevcut metin/kompozisyona göre değişir.

Gerçek FFmpeg testleri aynı VIDEO'nun Temel/Dengeli/Dinamik karelerini birden fazla zamanda karşılaştırır; kırmızı-mavi geçişte gerçek ara renkleri, vurgu piksellerinin görünmesini/kaybolmasını, uzun klibin farklı işlemlerini, yedi kamera hareketini ve güvenli geri dönüşleri sınar. Karma başarılı/başarısız slotta yalnız çıktı yolunda uygulanan hareket sayılır. FFmpeg 9.0.2 ayrı gerçek koşuda sınanır. Bu kalite düzeltmesinin Windows/NVENC görünümü için **Live render test must be run by owner on Windows.**

## İlk Part 9 Windows kontrolü

1. PR’ı birleştirin.
2. GitHub Desktop → Fetch / Pull.
3. AI Video Studio’yu tamamen kapatın.
4. START_AI_VIDEO_STUDIO.bat dosyasını açın.
5. Mevcut projeyi açın.
6. Video Oluştur / Render’a tıklayın.
7. FFmpeg durumunu kontrol edin.
8. Süre, ses, altyazı ve stok medyanın hazır olduğunu kontrol edin.
9. Encoder: Otomatik kalsın.
10. Altyazıları Videoya Yaz açık kalsın.
11. İlk testte müzik kapalı kalsın.
12. Videoyu Oluştur’a bir kez basın.
13. İlerlemeyi izleyin.
14. Tamamlandı yazısını bekleyin.
15. Videoyu oynatın.
16. Başlangıcı, ortayı ve sonu kontrol edin.
17. Ses ile görüntünün uyumunu kontrol edin.
18. Altyazıları kontrol edin.
19. Siyah boşluk olmadığını kontrol edin.
20. Kullanılan encoder: NVIDIA NVENC veya CPU / libx264 bilgisini kontrol edin.
21. Uygulamayı kapatıp yeniden açın.
22. Videonun hâlâ bulunduğunu kontrol edin.
23. Önceki ses, altyazı ve Pixabay dosyalarının korunduğunu kontrol edin.

**FFmpeg: Bulunamadı** görünürse video düğmesi kapalıdır ve “Video oluşturmak için FFmpeg gerekli.” mesajı gösterilir. Diğer ekranlar çalışır. Otomatik indirme yapılmaz. Terminal veya kaynak dosyası düzenleme gerekmez.

## Yerel dosyalar ve sürümler

Çıktı `data/projects/<proje-id>/renders/video-v1.mp4`, sonraki çıktılar `video-v2.mp4` şeklindedir. Geçerli önceki videolar silinmez; **Aktif Video Yap** ile seçilebilir. Kaynak değişince eski video korunur, “Eski kaynaklara ait” olur ve sonraki aşamaya hazır sayılmaz. Videoyu Aç ve Dosyayı İndir yalnız bu projenin doğrulanmış dosyasını sunar; oynatıcı ileri/geri sarabilir.

Her işte kısa FFmpeg komutları, UTF-8 filtre/ASS dosyaları ve küçük ara parçalar `renders/.job-<id>/` içinde tutulur. Başarı, hata, iptal ve yeniden açılma sonrası yalnız bu işe ait geçiciler temizlenir. `stderr.tmp` okununca silinir. `renders/render-vN.log` yalnız kontrollü olay, encoder, süre ve aşağıdaki güvenli tanıyı içerir; ham stderr, komut, dosya adı/yolu, anahtar, imzalı adres veya ortam değişkeni kaydedilmez.

## Windows render hatasını güvenli kontrol etme

1. Düzeltme PR’ını birleştirin.
2. GitHub Desktop → Fetch / Pull.
3. AI Video Studio’yu kapatın.
4. START_AI_VIDEO_STUDIO.bat dosyasını açın.
5. Proje → Video Oluştur / Render.
6. Encoder: **Otomatik**.
7. Altyazı: **açık**.
8. Müzik: **kapalı**.
9. **Videoyu Oluştur**’a bir kez basın.
10. Başarılıysa başarıyı bildirin. Hata varsa yalnız **Güvenli render tanısı** kutusundaki yazıyı kopyalayın.

Terminalde FFmpeg komutu çalıştırmanız gerekmez. Örnek: “Render aşaması: Medya işleme: Medya 5/37”, “Hata türü: FFmpeg filtre işlemi başarısız oldu.”, “Tanı kodu: filter_graph_failed”. Tanı yenileme/uygulamayı yeniden açma sonrası korunur. Eski videolar ve senaryo/ses/altyazı/stok dosyaları korunur.

Tanı alanları `phase`, `operation`, sıfırdan başlayan `slot_index`, `slot_count`, yalnız dahili 32 haneli hex `slot_id`, `media_type`, `encoder`, varsa sayısal `return_code`, `safe_error_code`, sabit Türkçe `safe_error_summary` ve `phase_label` olur. Ekrandaki medya sırası 1’den başlar. Yalnız izin verilen değerler saklanır; serbest FFmpeg metni kopyalanmaz. Kalıcılık mevcut `render_jobs.progress_json.diagnostic` alanındadır; SQLite şema 10 değişmez. NVENC veya dekoratif geçiş hatası başarıyla telafi edilirse güvenli tanı günlükte kalır, tamamlanmış işte hata kutusu gösterilmez.

Yerel hata sınıfları: `input_decode_failed`, `filter_graph_failed`, `filter_option_unsupported`, `scale_filter_failed`, `subtitle_filter_failed`, `concat_failed`, `audio_mix_failed`, `encoder_failed`, `nvenc_failed`, `output_mux_failed`, `output_validation_failed`, `unknown_ffmpeg_error`. Bunlar bir hata metninin güvenli sınıflandırmasıdır; bilinmeyen hatada neden uydurulmaz. Aşamalar medya ön kontrolü, altyazı ön kontrolü, yuva render, crossfade, son birleştirme ve çıktı doğrulaması olarak ayrılır.

Her stok dosyası işlenmeden önce ffprobe ile video/görsel akışı ve pozitif boyutları; videoda sonlu pozitif gerçek süre kontrol edilir. Bozuk dosya “Stok medya dosyalarından biri FFmpeg tarafından okunamadı.” tanısıyla durur. ffprobe yoksa tek kare yerel dekod kontrolü yapılır ve boyut/süre ön kontrolünün sınırlılığı açıklanır. Altyazı açıkken `ass` filtresi zorunludur; gerçek geçici ASS üzerinde tek yerel kare testi pahalı renderdan önce çalışır. Part 8 SRT/VTT değişmez; dış servis veya ücretli çağrı yoktur.

## FFmpeg 9 uyumluluk bulgusu

Resmî [FFmpeg n9.0.2 kaynak kodu](https://github.com/FFmpeg/FFmpeg/tree/n9.0.2) ayrı test klasöründe derlenerek sınandı. `-filter_complex_script` bu sürümde kaldırılmıştır: gerçek çağrı çıkış kodu **8**, “Unrecognized option” verir. Uygulama aynı UTF-8 filtre dosyasını artık **`-/filter_complex <dosya>`** ile okur; komut uzunluğu ve güvenli göreli dosya adları korunur. Resmî [CLI dosyadan seçenek okuma açıklaması](https://ffmpeg.org/ffmpeg.html#Options): seçenek adındaki başlangıç `/` dosya içeriğini okutur. Bu seçenek mevcut 7.1.5 sürümünde de gerçek komutla başarılıdır.

Scale/crop, setparams, split/trim, fade/xfade, concat demuxer, ASS, AAC ses karışımı ve H.264 çıktı sözdizimi değiştirilmedi. Linux üzerinde derlenmiş 9.0.2 ile gerçek CPU render testleri ayrıca çalıştırılır. Bu doğrulama sahibin Windows/Gyan build’i veya NVIDIA sürücüsündeki başka bir sorunu dışlamaz; kalan hata yeni güvenli tanıyla anlaşılır.

## Kaynak ve zamanlama sözleşmesi

Asıl kaynak **SubtitleService.handoff(project_id)** / `GET /api/projects/<id>/subtitles/handoff`, `contract_version=1`, `ready=true` şartıyla kullanılır. Senaryo/ses/altyazı/plan kimlikleri, yerel ses/SRT/VTT kimlikleri, gerçek `audio_duration`, aktif cue’lar, sahneler ve sıralı stok yuvaları salt okunur tüketilir. Production handoff yalnız düzenleme metadata’sını verir; `scene_id`, senaryo kimliği ve plan kimliği eşleşmelidir.

Ses süresi ana saattir. Yuvaların 0 → ses sonu kapsamı doğrulanır; yalnız 0,0011 saniyelik kayan nokta toleransı onarılır. Gerçek boşluk/örtüşme reddedilir. Sınırlar 30 fps karelerine birlikte yuvarlanır; toplam süre farkı en fazla yaklaşık 0,04 saniye kabul edilir. Altyazı/anlatım/medya yeniden üretilmez. Kaynak kimlikleri, gerçek dosya SHA-256 değerleri, yuva sırası, aktif cue’lar, düzenleme metadata’sı ve render seçenekleri deterministik fingerprint içindedir. Render sonunda tekrar kontrol edilir; arada değişen kaynakla video aktifleştirilmez.

## FFmpeg davranışı

- Ayarlar, Tanılama ve Render tek `app/rendering/tools.py:discover` algılayıcısını kullanır. PATH FFmpeg, güncel kullanıcının `%LOCALAPPDATA%/Microsoft/WinGet/Links/ffmpeg.exe` bağlantısı (eski PATH için), dahili onaylı konum ve mevcut `tools/ffmpeg/ffmpeg.exe` kontrol edilir. WinGet symlink/reparse bağlantısı `Path.resolve(strict=True)` ile çözülür; yalnız gerçek, normal yerel dosya sürüm çıktısı doğrulanınca çalıştırılır. UNC/ağ sürücüsü/URL/dizin/bozuk bağlantı reddedilir. HTTP executable yolu, indirme veya tüm diski tarama yoktur. ffprobe aynı güvenlik/sürüm kontrolüyle PATH, çözülmüş FFmpeg yanında ve WinGet Links içinde aranır. UI mutlak executable yolunu göstermez. **Durumu Yenile** 30 saniyelik render önbelleğini atlayarak yeni algılama yapar; FFmpeg’i yeniden kurmanız gerekmez.
- Otomatik, listelenen `h264_nvenc` encoder’ını tercih eder. Listelenmesi GPU sürücüsünün çalıştığını kanıtlamaz. Yalnız belirgin NVENC başlatma hatasında **aynı iş ve sürüm** bir kez libx264 ile denenir. Açık NVIDIA seçiminde veya farklı hatalarda otomatik tekrar yoktur.
- Video ve JPG/PNG/WEBP, oran korunarak 1920×1080’e ölçeklenir/kırpılır; kare hızı 30, piksel biçimi yuv420p, renk metadata’sı tutarlı BT.709/limited olur. Uzun videolar merkezden alınır; kısa videolar döngülenir. Stok sesi hiç kullanılmaz.
- Görsellerde mevcut `slow_zoom`, `ken_burns` ve `pan` için hafif hareket uygulanır. Destek yoksa durağan görsel ve uyarı kullanılır.
- Sahne içinde temiz kesme; sahne sınırında kısa fade/crossfade. Crossfade için ek görsel kuyruk ve sonraki yuvanın başı kullanılır; geçiş sonraki yuvanın başlangıç karelerini kaplar, toplam süreyi kısaltmaz. Çok kısa/desteksiz/uygulanamayan dekoratif geçiş temiz kesmeye döner.
- Aktif cue’lardan geçici Unicode ASS oluşturulur. Alt ortada 48px açık yazı/koyu kenar, güvenli alt boşluk ve kurulu Arial/font fallback kullanılır. SRT/VTT değiştirilmez. Kullanıcının değiştirdiği altyazı mevcut uyarısıyla korunur. Üstteki vurgu metni kendi sahnesinde en fazla 3 saniye gösterilir; geçersiz dekorasyon atlanır.
- Anlatım 0’da başlar, hızı değişmez. AAC 48 kHz stereo yaklaşık 192 kbps; H.264 MP4 `+faststart`.
- Müzik varsayılan kapalıdır. İstenirse MP3/WAV/M4A/OGG/FLAC en fazla 100 MB yüklenir ve **Bu müziği kullanma hakkına sahibim** onayı gerekir. Dosya proje müzik klasörüne güvenli kimlikle kaydedilir. Varsayılan seviye 0,12, giriş/çıkış fade ve konuşma sırasında ducking; sidechain yoksa düşük sesli karışım/uyarı kullanılır. Önceki müzik dosyası eski renderlar için korunur.

## İşler, güvenlik ve doğrulama

SQLite **9 → 10** eklemeli yükseltmesi: `render_versions`, `render_jobs`, `render_state`, `render_music` ve proje başına tek aktif iş indeksi. Bir render worker’ı kullanılır; başka projeler sıraya alınır. HTTP render tamamlanmasını beklemez. Yerel poll aşama/yüzde/geçen süre/gerçekte kullanılan encoder’ı gösterir; kesin bitiş tahmini verilmez.

İptal yalnız izlenen FFmpeg child process’i durdurur; gerekirse aynı child kill edilir. Global taskkill yoktur. Aktif render sırasında proje silinemez. Yeniden açılışta kalmış aktif işler kesildi/hata durumuna döner; eski aktif video korunur. Yeniden Render Et yeni yerel iş/sürüm oluşturur.

Dosyalar mevcut safe asset/audio/subtitle doğrulamasından geçer. Traversal, dış dosya ve symlink/junction reddedilir. Tüm subprocess çağrıları argüman listesi ve `shell=False` kullanır. Kullanıcı metni ASS verisidir, kabuk komutu değildir.

Sonuç önce geçici MP4’te üretilir. ffprobe ile akışlar, 1920×1080, 30 fps, H.264/yuv420p, AAC/48 kHz/stereo ve master süre kontrol edilir; ardından fsync ve atomik rename ile yeni sürüm kaydedilir. ffprobe yoksa biçim ayarları ve tam FFmpeg decode/süre kontrolü kullanılır, sınırlama uyarısı gösterilir. Başarısız çıktı aktifleştirilmez. Salt okunur `/render/handoff` yalnız güncel, mevcut aktif video için sonraki aşamanın kimlik/yerel yol/biçim bilgisini verir. Metadata/başlık/thumbnail üretimi uygulanmadı.

## Doğrulama sınırı

Bulut ortamında gerçek kısa CPU/libx264 videoları, MP4/JPG/PNG/WEBP, portre/yatay kaynaklar, kısa döngü/uzun kırpma, Unicode altyazı, geçiş, müzik, ses ayrımı, süre, sürümler, iptal, kalıcılık ve tarayıcı oynatma test edilir. Bunlar sahibin gerçek konuşmasında Windows senkronunu veya RTX 5070/NVENC sürücüsünü kanıtlamaz. **Live render test must be run by owner on Windows.**
