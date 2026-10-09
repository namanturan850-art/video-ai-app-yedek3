# Video Oluştur / Render — Part 9

Mevcut proje → **Video Oluştur / Render**. Bu işlem tamamen yereldir; AI33, Gemini, OpenAI, Ollama, Pexels veya Pixabay çağrısı yapmaz ve API kredisi kullanmaz. Part 10 başlamadı.

## İlk Windows kontrolü

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
