# Altyazı ve Zamanlama — Part 8

Çalışan seslendirmesi olan projenizde **Altyazı ve Zamanlama** ekranını açın. Ses süresi otomatik ölçülür ve seslendirme sürümüne kaydedilir. **Altyazıları Oluştur** tamamen yerel çalışır; AI33 kredisi kullanmaz, yeni ses görevi oluşturmaz, dosya indirmez. Mevcut ses ve Pixabay/Pexels dosyaları aynı kalır.

## Zamanlama ne kadar doğru?

**Ses süresine göre yaklaşık zamanlama.** AI33 şu anda doğrulanmış kelime zamanları vermiyor; `with_transcript=false` ve `transcript=null` korunur. Uygulama kesin kelime zamanlaması veya konuşma hizalaması iddia etmez. Metnin uzunluğu ve noktalaması konuşma ağırlıklarına çevrilir; zamanlar gerçek sesin toplam süresine oturtulur. Sessizliklerin ve tek tek kelimelerin yeri ölçülmez. Başlangıç, orta ve son bölümleri dinleyin; gerekirse zamanları düzeltin.

**Whisper, GPU modeli, bulut STT veya yeni API yoktur. Video render Part 9'dur ve bu aşamada uygulanmadı.**

## Çok basit Windows denemesi

1. GitHub'da Part 8 PR'ını birleştirin (Merge).
2. GitHub Desktop'ta **Fetch origin**, ardından gerekiyorsa **Pull origin** deyin.
3. AI Video Studio'nun siyah penceresini ve tarayıcı sekmesini tamamen kapatın.
4. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın. İlk açılışta küçük yeni ses okuma bileşeni otomatik kurulur; siyah pencereyi açık bırakın.
5. Seslendirmesi zaten çalışan projenizi açın.
6. **Altyazı ve Zamanlama** bağlantısına tıklayın.
7. Üstte ses süresinin artık göründüğünü kontrol edin; yaklaşık 3:13 olan sesiniz benzer süre göstermelidir.
8. **Altyazıları Oluştur** deyin. Ücret/API onayı çıkmaz.
9. Yerel ses oynatıcısında oynat düğmesine basın; altyazı önizlemesini izleyin.
10. Başlangıç, orta ve son bölümleri kontrol edin. Zamanlar yaklaşık olduğu için gerekiyorsa düzeltin.
11. **SRT Dosyasını Aç** ile SRT dosyasını açın/indirin.
12. **VTT Dosyasını Aç** ile VTT dosyasını açın/indirin.
13. Uygulamayı kapatıp aynı `.bat` dosyasıyla tekrar açın.
14. Aynı projede altyazı sürümünün hâlâ bulunduğunu kontrol edin.
15. Seslendirmeyi dinleyin ve mevcut Pixabay videolarının değişmediğini kontrol edin.

Kod, `.env`, terminal veya API anahtarı değişikliği gerekmez. Güncellemede **data** klasörünü silmeyin.

## Düzenleme ve sürümler

- Her satırda **Başlangıç**, **Bitiş** ve **Metin** bulunur. Zaman biçimi `00:00:04,120` (4 saniye 120 milisaniye).
- Başlangıç negatif olamaz; bitiş daha büyük olmalı, ses süresini aşmamalı. Altyazılar sıralı olmalı ve örtüşmemeli. Boş metin kaydedilmez. Aralarda boşluk bırakabilirsiniz.
- **Değişiklikleri Kaydet** yeni sürüm oluşturur; önceki sürümün dosyası ve kayıtları korunur. Sürüm 1'i düzenlerseniz Sürüm 2 oluşur.
- Metni farklılaştırabilirsiniz; **“Altyazı metni seslendirme metninden farklı.”** uyarısı görünür. Senaryo ve ses değişmez. Önizleme kaydedilmemiş değişiklikleri de gösterebilir; dosyaları güncellemek için Kaydet gerekir.
- **Altyazıları Yeniden Oluştur** mevcut sürümü koruma onayı ister. İşlem yereldir ve kredi kullanmaz.
- Eski sürümde **Aktif Altyazı Olarak Seç** kullanılabilir. Kaynak senaryo/ses farklıysa açıkça eski sürüm olarak işaretlenir; farklı sesle yanıltıcı önizleme yapılmaz. Eşleşen güncel seslendirmeyi seçin veya yeniden oluşturun.
- Kaydedilmemiş düzenleme varken yenileme/sürüm seçimi/çıkış için uyarı vardır.
- **Ses Süresini Ölç** yalnız yerel metadata'yı okur; mevcut geçerli süreyi korur. Altyazı ekranı ilk açılışta da bunu yapar. Sonra Seslendirme ekranını yeniden açınca ölçülen süre görünür.

## Teknik sözleşme ve koruma

SQLite şema **8 → 9**, yalnız eklemeli/işlemsel: `subtitle_versions`, `subtitle_cues`, `subtitle_state`. Kaynak proje/senaryo/ses sürümü, SHA-256 script fingerprint ve yerel ses SHA-256 kimliği, dil, gerçek ses süresi, timing_source, metin eşleşmesi ve zaman damgaları saklanır. Sürümler değiştirilemez; manuel kayıt yeni sürümdür. Mevcut veritabanı, ayar kasası ve Part 1–7 kayıtları sıfırlanmaz.

Süre sırası: geçerli kayıt → PATH ffprobe → algılanmış/yapılandırılmış ffmpeg'in yanındaki ffprobe/ffprobe.exe → uygulama tarafından bilinen konum (varsa) → yerel WAV okuyucu / **mutagen 1.47.0** (MP3, M4A, OGG, FLAC). Bu uygulama şu anda ffmpeg'i PATH'ten algılar; ayrı FFmpeg konumu ayarı veya uygulama paketi yoktur, sahte konum eklenmez. Araç bulunmazsa mutagen yeterlidir. Ölçülemeyen dosyada önceki ses korunur ve açıklama gösterilir; altyazı oluşturulmaz. Ses dosyasının SHA-256/boyut/yol kimliği doğrulanır; yeniden TTS veya indirme yapılmaz.

Otomatik altyazı yalnız aktif tamamlanmış sesin **aynı kaynak onaylı senaryosunu** kullanır. Metin çevirisi, özet veya AI yeniden yazımı yoktur; yalnız boşluklar normalize edilir. Paragraf/cümle/noktalama/kelime sınırları tercih edilir, kelime içinden kesilmez. Genelde 1–2 satır, satır başına yaklaşık 42, cue başına yaklaşık 84 karakter hedeflenir. Çok uzun tek kelime veya metin/süre çelişkisi bu hedefleri aşabilir; kelimeler silinmez. Zaman ağırlığı sözcükteki harf/rakam + sözcük tabanı; virgül/kısmi durak/cümle/paragraf için küçük ekler. Eşit cue zamanları kullanılmaz. Yaklaşık .8 saniye alt sınırı mümkünse komşularla dengelenir; çok kısa ses için cue birleştirilir. Son cue sesin sonunda biter, milisaniye hassasiyetiyle örtüşme yoktur.

Gelecekteki doğrulanmış alignment adaptörü için timing_source `exact_provider` türü ayrılmıştır; **bu sürüm onu üretmez**. Depolama sağlayıcıdan bağımsızdır.

Dosyalar yalnız `data/projects/<project-id>/subtitles/subtitles-v<N>.srt` ve `.vtt`: UTF-8, LF; SRT virgül, WebVTT nokta zaman ayracı. VTT metnindeki literal `<`, `>`, `&` güvenle escape edilir. Geçici dosya → flush/fsync → atomic replace. İki dosya ve SQLite yazımı tamamlanmadan yeni sürüm aktif olmaz; ikinci dosya/DB hatasında önceki sürüm aktif kalır. Kesinti sonrası DB'ye ait olmayan çıktı varsa üzerine yazılmaz, sıra atlanır. Yol traversal, haricî mutlak yol, dosya/klasör symlink ve Windows junction reddedilir. Yerel API yolu dosya adı kabul etmez, sürüm + srt/vtt seçimi kullanır.

### API

Hepsi yerel `/api/projects/<id>/subtitles` altında:

- `GET /`: aktif ses/süre, güvenli durum, sürümler ve aktif cue editörü; eksik süre yerel ölçülür.
- `POST /duration`: yerel süreyi keşfet/kaydet.
- `POST /versions`: `{regenerate_confirmed:false}`; sonraki üretimde açık onayla true.
- `POST /versions/<id>/edit`: `{cues:[{start,end,text},...]}`; doğrula ve yeni sürüm yap.
- `POST /versions/<id>/activate`: `{confirm:true}`.
- `GET /versions/<id>/files/srt` veya `/vtt`: yalnız doğrulanmış yerel dosya.
- `GET /handoff`: Part 9'a aşağıdaki yerel sözleşme.

Mutasyonlarda mevcut aynı köken/Host ve `X-AI-Video-Studio: projects` koruması aynen geçerlidir. Anahtarlar, imzalı AI33 ses adresi, ham sağlayıcı yanıtı veya stack trace dönmez. Günlükler yalnız işlem, güvenli kategori ve süre içerir.

### Part 9 için tek zamanlama aktarımı

`GET /api/projects/<id>/subtitles/handoff`: proje/senaryo/ses/altyazı sürümleri, dil, proje içi audio/SRT/VTT yolları, audio_duration, `timing_source=approximate_audio_duration`, cues, scenes, stock_slots ve ready/warnings. Render veya AI33 çağrısı yoktur.

Sahne metni onaylı kaynağın **sıralı sözcük aralıklarıyla** bire bir eşleştirilir; yinelenen ifadeler aramayla karıştırılmaz. Cue içindeki sözcük ağırlıkları aynı gerçek audio timeline'ına yansıtılır. Sahne kimliği/anlatımı/sırası korunur; son sahne ses sonunda biter. Eski tahmini başlangıç/bitiş ayrıca aktarılır; Part 5 planına yazılmaz. Aynı metinle manuel zaman düzenlenirse aktarım yeniden hesaplanır. Görüntü metni farklılaştırılırsa özgün anlatım zamanları korunur ve uyarı verilir.

Stok yuvaları yalnız kayıtlı eşleşen plan tablosundan **salt okunur** alınır; StockService'in arama/ensure/güncelleme yolu çağrılmaz. Sahne içindeki sıra ve eski süre oranları yeni sahne aralığına oturtulur. Slot/scene kimliği, medya yerel kimliği, kilit ve eski tahminler korunur. Görsel değiştirme, indirme veya kilit açma yoktur. `ready=true` yalnız güncel geçerli altyazı/ses/sahne ve tüm seçili stok dosyaları mevcutsa döner; eksikler açık uyarıyla false olur. Altyazı tek başına sahne/stok henüz hazır değilken de oluşturulabilir.

## Doğrulama sınırı

Part 7'nin canlı Windows başarısı **sahibinin testiyle doğrulandı**: görev/kredi/yerel ses/oynatma/kalıcılık ve Pixabay korunumu. Part 8 testleri gerçek yerel formatlar, veritabanı, dosyalar ve FastAPI/Chromium kullanır; AI servisleri çağrılmaz. Sentetik konuşma olmayan sesler süre/dosya/arayüzü doğrular, gerçek konuşmada senkron doğruluğunu kanıtlamaz. Part 8'in gerçek sesle yaklaşık senkronu yukarıdaki adımlarla Windows'ta sahibi tarafından kontrol edilmelidir.
