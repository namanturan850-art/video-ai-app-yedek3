# Video Oluştur / Render — Part 9–9.9

Mevcut proje → **Video Oluştur / Render**. Bu işlem tamamen yereldir; AI33, Gemini, OpenAI, Ollama, Pexels veya Pixabay çağrısı yapmaz ve API kredisi kullanmaz. Part 10 başlamadı.


## Part 9.9 — Pürüzsüz kamera ve konuya göre kurgu ritmi

**Ne değişti?**

- **Kamera titremesi giderildi.** Yakınlaşma/kaydırma artık FFmpeg `perspective` filtresiyle piksel altı hassasiyette çizilir. Eski `zoompan` pencereyi tam piksele yuvarlıyordu; aynı hareket için ölçülen kareden kareye sarsıntı ~0,76 pikselden ~0,13 piksele indi (hız aynı).
- **Uyarlanabilir YouTube artık slayt gösterisi değil.** Önceden B-roll videoların çoğu tamamen sabitti. Şimdi her çekim tek yönlü, yavaş başlayıp yavaş biten bir kamera hareketi alır (fotoğraflar videodan biraz daha fazla; hızlı hareketli ve yakın çekimler çok az). Aynı hareket art arda gelmez.
- **Kurgu ritmi konudan seçilir.** Sahne duyguları (Almanca/İngilizce/İspanyolca/Fransızca/Türkçe) okunur: *gizemli/sakin* → **Sakin belgesel ritmi** (daha sık yumuşak geçiş, yavaş yaklaşma); *heyecanlı/dramatik* → **Hızlı ve enerjik ritim** (daha çok kesme, kaydırma); diğerleri → **Dengeli anlatım ritmi**. Render ekranında “Kurgu ritmi” satırında görünür.
- **Uzun çekimler bölünür.** 5–6 saniyeden uzun tek çekim, aynı klipte belirgin bir yakına geçiş kesmesiyle (punch-in) ikiye/üçe ayrılır. Küçük, kaza gibi görünen zıplama yapılmaz.
- **Yazı kartları:** kart yazısı sabit ve net kalır, arkadaki görüntü hafifçe hareket eder. Bir geçiş, kart yazısıyla çakışacaksa yapılmaz ve bir sonraki uygun sahne sınırına taşınır (yazı geçişte asla “parlamaz”).
- **OpenMontage (ana motor) artık aynı kurguyu uygular.** Önceden OpenMontage yolu her çekimi sabit ve sert kesmeyle gösteriyordu. Kompozisyon artık aynı kamera hesaplarını, yumuşak geçişleri, koyu geçişleri, punch-in kesmeleri ve vurgu yazılarını çizer. Burada gerçek bir Remotion 4.0 render'ı ile doğrulandı (sizin Windows kurulumunuzda değil).

Ses, altyazı zamanları, sahne sınırları ve kare sayıları değişmez; kaynak dosyalara dokunulmaz. Eski videolar korunur.

### Part 9.9 Windows kontrolü

1. GitHub Desktop'ta **Fetch origin** → **Pull origin** yapın (PR birleştikten sonra).
2. Açık uygulama penceresini kapatın, `START_AI_VIDEO_STUDIO.bat` dosyasına çift tıklayın.
3. Medyası tamamlanmış bir projeyi açın → **Video Oluştur / Render**.
4. Kurgu stili **Uyarlanabilir YouTube (önerilen)** olsun. Kurgu özetinde **Kurgu ritmi: …** satırını görün.
5. Önce motor olarak **Yerel Adaptif — FFmpeg / NVIDIA** seçip **Render Başlat**'a basın. Bitince önizlemede: çekimlerin yavaşça yaklaştığını/kaydığını, sarsılma olmadığını, uzun çekimlerin bir yakın kesmeyle bölündüğünü kontrol edin.
6. OpenMontage kuruluysa motoru **OpenMontage — Ana Motor** yapıp tekrar render alın; aynı hareketleri ve yumuşak geçişleri görmelisiniz. Kurulu değilse ekranda açıkça “kurulmamış” yazar.
7. Kart yazısı olan anlarda yazının geçiş sırasında bir kare bile parlamadığını kontrol edin.
8. Sorun görürseniz videonun hangi dakikasında olduğunu ve Kurgu özetindeki sayıları bana yazın.

## Part 9.8 — Ana motor ve etkin kapsama

Yeni render varsayılanı **OpenMontage — Ana Motor**. Gerçek ayrı `VideoCompose/Remotion` kompozisyonu kullanılır; FFmpeg teslim biçimi/encoder doğrulamasını yapar. **Yerel Adaptif — FFmpeg / NVIDIA** elle seçilen alternatiftir. Eksik dış motor: **OpenMontage ana montaj motoru olarak seçildi ancak kurulmamış.** Kurulum için `INSTALL_OPENMONTAGE.bat`; başarısız harici işte sessiz motor değişimi yoktur. Eski renderlar kendi motor/metadata/dosyalarını korur.

**Eksik Medyaları Akıllı Tamamla** sonrası ham seçim sayısı aynı kalabilir. Etkin kurgu 193 sn sesin tamamını güvenle kapatırsa 13 ham boş alan renderı tek başına engellemez. Kesin kare/scene sınırları, ana ses ve altyazı cue'ları korunur. Gerçek dosya/decode/konu/benzersizlik/kaynak süreleri doğrulanır; kaynak değişirse plan geçersizdir. Eksik etkin süre, geçersiz kilitli medya, eksik ses/altyazı/FFmpeg/OpenMontage açık engeldir. Henüz geçerli recovery planı yoksa eski katı ham hazırlık uygulanır.

Sayı kartı fallback'i yalnız **Uyarlanabilir YouTube** ile ve mevcut kısa aynen sayısal cue'dan çizilir; dekoratif render başarısız olursa boş arka planla başarılı sayılmaz. Kaynaklar, stok arşivleri, şifreli kasa, senaryo, AI33 ses, Part 8 dosyaları ve eski MP4 silinmez. [Kurtarma kuralları](STOCK_MEDIA.md#part-98-akıllı-kurtarma).

### Part 9.8 Windows kontrolü

1. GitHub'daki taslak PR'da **Ready for review**, ardından **Merge pull request** deyin.
2. GitHub Desktop'ta **Fetch origin**, sonra **Pull origin** yapın.
3. Uygulamanın siyah penceresini kapatın; **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın.
4. **Ayarlar → OpenMontage → Durumu Yenile** deyin.
5. Hazır değilse **INSTALL_OPENMONTAGE.bat** dosyasına çift tıklayın. Açıklamayı okuyup kuruluma **E** ile onay verin; eksik Git/Node varsa pencerenin gösterdiği siteden kurun. Sonra uygulamayı yeniden açın. Kare analizi isterseniz ayrıca **INSTALL_OPENMONTAGE_SEMANTIC.bat** ile büyük indirmeyi açıkça onaylayıp Ayarlar'dan etkinleştirin; zorunlu değildir.
6. Mevcut 55 alanlı projenizi açın.
7. **Görsel / Kurgu Planı → Eksik Medyaları Akıllı Tamamla** deyip onaylayın.
8. Mevcut 42 geçerli seçimin korunduğunu kontrol edin.
9. Kalan alanların Türkçe nedenlerini ve kurtarma raporunu okuyun.
10. **Eksik süre: 0 sn** olmasını kontrol edin. Değilse gösterilen alanı elle tamamlayın; yeniden aynı aramaya basmanın çözüm olduğu varsayılmaz.
11. **Video Oluştur / Render** ekranını açın.
12. Motorun **OpenMontage — Ana Motor** olduğunu kontrol edin.
13. **Uyarlanabilir YouTube**, **Sadece önemli vurgular**, **Otomatik** seçin; müzik kapalı kalsın.
14. **Videoyu Oluştur** düğmesine bir kez basıp tamamlanmasını bekleyin.
15. Başını, ortasını ve sonunu izleyin: anlatım eksiksiz, görseller ilgili, yanlışlıkla siyah boşluk yok.
16. Önceki video sürümlerinizin hâlâ açıldığını kontrol edin.
17. İsterseniz motoru kendiniz **Yerel Adaptif — FFmpeg / NVIDIA** yapıp ikinci sürümle karşılaştırın.

Bulutta gerçek FFmpeg 9.0.2 ve ayrı sabit OpenMontage/Remotion ile CPU çıktısı doğrulanır. **Live provider test must be run by owner on Windows. Live render test must be run by owner on Windows. Live OpenMontage test must be run by owner on Windows.** RTX 5070/NVENC ve gerçek CLIP kare kalitesi burada doğrulanmış sayılmaz. **Part 10 başlamadı.**

## Part 9.6 — Uyarlanabilir Kurgu

Yeni render varsayılanı **Uyarlanabilir YouTube** (`adaptive`). Temel, Dengeli YouTube ve Dinamik YouTube korunur; eski tamamlanmış/stilsiz/v1/v2/v3 planları kendi fingerprint ve metadata'sıyla kullanılmaya devam eder. Kaynakları açmak yeniden üretim yapmaz.

`app/rendering/adaptive.py` sadece mevcut Part 8 timeline/cue'ları, Part 5 metni/önemi ve yerel seçilmiş medya kanıtını tüketir. AI, cloud editor, yeni medya veya TTS çağrısı yoktur. Plan render metadata JSON'una eklenir; SQLite şema **10** değişmez.

| Düzen | İçerik şartı |
| --- | --- |
| Tam B-roll | Betimleme veya güvenilir kısa vurgu yok |
| Medya ve metin | Önemli, kısa, aynen kaynak cue; yön seed ve sıraya göre değişir |
| Bilgi kartı | 2–3 kısa kaynak cümlesi; paragraf/bilgi uydurma yok |
| Büyük sayı | Cue'da birebir sayı/değer ve aynı kaynak destek cümlesi |
| Zaman çizelgesi | Aynı kısa kaynaktaki en az iki farklı, sıralı yıl/tarih parçası |
| İki medya | Aynı semantik sahnenin zaten indirilen, farklı byte kimlikli ikinci medyası |
| Kısa başlık / vurgu | Kısa önemli cue veya önceden onaylı overlay |
| Konum kartı | Aynen kaynak konumu ve uyumlu map/konum medya metadata'sı; harita üretmez |

Her görünen metin bir kaynak cue'ya veya onaylı overlay'e bağlanır; sayı ve tarih parçaları aynen kopyalanır. Yeni bilgi, özetleyici cümle veya madde icat edilmez. Metin gösterimi cue aralığında kalır; kelime zamanları tahmin edilmez. B-roll dışında düzenler yalnız kısa pencerelerde gösterilir, toplam grafik süresi en fazla yaklaşık %30; uygun içerik yoksa daha az olur. Aralıklar ve tekrar kapısı slayt gösterisini engeller. Tema (`minimal_dark`, `clean_light`, `soft_documentary`, `grid_dark`) özgün yerel renk/panel/çizgilerden oluşur; herhangi bir referans kare/şablon kopyalanmaz. Kart yazıları hafif fade ile girer; kart üstüne kamera/punch/geçiş yığılmaz. B-roll çoğunlukta kalır.

**Yeni Kurgu Varyasyonu** sadece yerel seed'i değiştirir. Varsayılan seed değişmez kaynak içeriklerinden hesaplanır; encoder veya müzik ayarını değiştirmek kurgu tercihlerini değiştirmez. Aynı kaynak + stil + seed aynı planı verir. Açık altyazı modu eski checkbox değerini de belirler; önizleme ve render aynı sunum ayarını kullanır. Uygun alternatiflerde düzen/yön/tema değişir; gerçek bilgi/metin ve Part 8 zamanı değişmez. Son seçilen seed bu tarayıcıda saklanır; render edildiğinde `options.edit_variation_seed` ve plan metadata'sında kalıcıdır. Önceki videolar/senaryo/ses/medya/altyazı sürümleri korunur. Kaynak aynı olsa da farklı seed yeni render sürümü oluşturabilir.

**Altyazı Gösterimi:** Tam altyazı alt cue'ları yazar; Sadece önemli vurgular alt sürekli altyazıyı kapatır, içerik kartlarını/vurguları korur; Altyazı yok metin vurgularını da kapatır. Dosyalar/timing silinmez. Adaptive varsayılanı Sadece önemli vurgular. Temel/Dengeli/Dinamik geçişte önceki tam altyazı davranışı korunur; açık kullanıcı seçimi stili değiştirirken kaybolmaz. Tam altyazıda Adaptive/Dengeli 50px kalın, Dinamik 52px kalın, Temel 48px normal.

Önizlemede varyasyon, planlanan düzen/efekt sayıları, grafik/B-roll süreleri ve Zaman/Sahne/Düzen/Medya/Efekt/Geçiş/Metin gösterilir. Her tamamlanmış videoda **Planlanan kurgu / Uygulanan kurgu** ayrılır; gerçek düzen hata sayısı vardır. Ham FFmpeg metni veya sırlar gösterilmez.

Her yuva bir sınırlı 1080p FFmpeg graph'ıyla işlenir; düzenler frame timestamp veya toplam frame sayısını değiştirmez. Text yalnız escaped Unicode ASS dosyasıdır. İkinci medya sadece yerel dosyadan gelir, sesi kapalıdır. Dekoratif düzen başarısız olursa aynı medya/süre B-roll olarak render edilir ve uygulanan sayaç bunu bildirir. Smart Edit v3 nötr kamera uçları, tutulmuş geçiş kolları, punch çakışma engeli ve `(N-1)/30` crossfade uç düzeltmesi korunur. FFmpeg 9 `-/filter_complex` kullanılır. Auto→NVENC ve yalnız NVENC başlatma hatasında CPU tekrar davranışı değişmez.

### Part 9.6 Windows kontrolü

1. PR'ı birleştirin. GitHub Desktop'ta **Fetch → Pull** yapın.
2. Uygulamayı kapatın; **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın. Siyah pencere açık kalsın.
3. Aynı projede **Görsel / Kurgu Planı → Alakaya Göre Medyayı Yeniden Ara** deyip onaylayın.
4. Eski havacılık sahnelerinde ilgisiz kişi/manzara ve otomatik tekrar olmadığını kontrol edin. Uygun benzersiz aday yoksa boş yuva beklenir; uygun medyayı elle seçin. Video çoğunlukta olmalı, oran için ilgisiz aday seçilmemeli.
5. **Render → Uyarlanabilir YouTube → Sadece önemli vurgular → Otomatik** seçin. Müzik kapalı kalsın.
6. **Kurgu Planını Gör** deyin; içeriğe uygun farklı düzenleri ve metinleri kontrol edin.
7. **Videoyu Oluştur** deyin. Başını, ortasını ve sonunu izleyin: B-roll çoğunlukta, kısa anlamlı kartlar, sürekli alt yazı yok, titreme/medya tekrarı yok.
8. **Yeni Kurgu Varyasyonu** deyin; plan/yön/tema değişebilmeli, API/TTS/stok işlemi başlamamalı.
9. Önceki videoların hâlâ açıldığını kontrol edin.

Bulut doğrulaması gerçek kısa CPU FFmpeg çıktısını ve taklit edilmiş sağlayıcı metadata'sını kapsar. Sahibin Gyan FFmpeg 9.0.2 + RTX 5070/NVENC ortamı burada mevcut değildir. **Live provider test must be run by owner on Windows. Live render test must be run by owner on Windows.**


## Part 9.5 Windows kontrolü

Önceki Part 9/9.5 render sahibi tarafından Windows/Gyan FFmpeg 9.0.2 + RTX 5070/NVENC ile doğrulandı. Bu son kalite düzeltmesini şu adımlarla kontrol edin:

1. PR’ı birleştirin.
2. GitHub Desktop → Fetch / Pull.
3. AI Video Studio’yu kapatıp **START_AI_VIDEO_STUDIO.bat** ile tekrar açın.
4. Aynı projeyi açın.
5. **Alakaya Göre Medyayı Yeniden Ara** düğmesine basın.
6. Sorunlu kokpit/navigasyon sahnesini kontrol edin.
7. Köpek ve tren yolcusu seçilmediğini doğrulayın.
8. Medya toplamlarına bakın.
9. Uygun video bulunduğunda videoların çoğunlukta olduğunu doğrulayın.
10. **Dengeli YouTube**, **Otomatik**, **altyazı açık**, **müzik kapalı** ile render oluşturun.
11. Altyazının istediğiniz kalın stile döndüğünü kontrol edin.
12. Birkaç geçişi izleyin.
13. Görünür titreme olmadığını kontrol edin.
14. Ses/altyazı zamanlamasının doğru kaldığını kontrol edin.
15. Önceki videoların hâlâ bulunduğunu kontrol edin.

**Kurgu Planını Gör** açılarak zaman, sahne, efekt, geçiş ve vurgu metni incelenebilir. Kurgu stilini değiştirince plan bu bilgisayarda yeniden hesaplanır; kredi harcanmaz. Tamamlanan videoda **Planlanan kurgu** ve **Uygulanan kurgu** ayrı gösterilir. Bir dekoratif efekt atlanırsa uyarı ve gerçek uygulanan sayı görünür.

## Smart Edit Plan nasıl çalışır?

Önceki Part 9'da kamera hareketi yalnız görsellerde uygulanıyordu; videolarda normalleştirme/kırpma vardı. Vurgu yalnız mevcut `overlay_text`'ten geliyordu. Bu yüzden 37 video, 0 görsel, 0 vurgu metinli bir proje görsel olarak sade kalabiliyordu.

Yeni plan, mevcut Part 8 zamanlaması ve Part 5 düzenleme ipuçlarını salt okunur kullanır. Aynı kaynak fingerprint'i ve stil aynı planı verir; rasgelelik, sağlayıcı çağrısı veya indirme yoktur. Stok yuva kimliği/sırası ve master süre değişmez. Plan render metadata JSON'unda tutulur; yeni veritabanı geçişi yapılmaz.

| Stil | Hareket ve tempo | Geçiş ve metin |
| --- | --- | --- |
| Temel | Önceki Part 9; videoda ek kamera yok, mevcut görsel hareketleri korunur | Mevcut geçiş ve vurgu metni |
| Dengeli YouTube (Part 9.5 varsayılanı) | Uygun kadrajlarda yaklaşık %4,5–5; ilk 15 saniye daha canlı | Yaklaşık her üçüncü sahne sınırı; vurgu yaklaşık 28 saniyede bir |
| Dinamik YouTube | Uygun kadrajlarda yaklaşık %7–8; daha sık kadraj değişimi | Yaklaşık her ikinci sahne sınırı; vurgu yaklaşık 18 saniyede bir |

Yakın/kişi/detay kadrajları en fazla yaklaşık %1,2 hareketle korunur; zaten hareketli sahneler sakin bırakılır. Önem düzeyi ve mevcut `motion / composition / transition` ipuçları hesaba katılır; kişi/yer/bilgi uydurulmaz. Yüzde/sıklıklar kalite hedefidir, katı rastgele kurallar değildir.

- **Video hareketi:** aynı hareketli video kareleri işlenir; `zoompan d=1` her giriş karesine bir çıktı karesi üretir. Yakınlaşma/uzaklaşma, dört yönde kayma ve hafif kadraj değişimi yüksek çözünürlükte ve sınırlandırılmış güvenli crop ile uygulanır. Slotun tam kare sayısı korunur; siyah kenar/aspect bozulması eklenmez. Ek vurgu yakınlaşması da Dengeli %5 / Dinamik %8 sınırını aşmaz; yakın/yüz kadrajı korunur.
- **Uzun klip:** yaklaşık 7 saniyeden sonra iki, 11 saniyeden sonra üç görsel işlem; açılışta daha erken değişim. Bunlar aynı dosyanın render içindeki parçalarıdır; yeni stok yuvası/indirme yaratmaz, anlatımı çoğaltmaz. Tek stok girişi ve tek core ara video kullanılır; parçalar frame sınırlarında birleşir.
- **Geçiş:** aynı sahne içindeki medya değişimleri genellikle temiz kesme. Seçilmiş sahne sınırlarında yaklaşık 0,43 saniye Dengeli / 0,53 saniye Dinamik crossfade veya kısa koyu geçiş; çok kısa yuvalarda kısaltılır/atlanır. Önceki klibin ek kuyruğu ve sonraki klibin başı kullanılır; master süre ve cue zamanları kaymaz.
- **Vurgu:** mevcut `overlay_text` önceliklidir ve aynen korunur. Yoksa onaylı anlatımda da bulunan tam kısa cue veya cue başındaki kısa cümlecik aynen seçilir. Genellikle 2–8, en fazla 10 kelime; uygun sayı/tarih tercih edilir. Yeni başlık/çeviri/özet/bilgi üretilmez. Uygun metin yoksa atlanır. Tam cue sınırları kullanılır; kelime zamanı tahmin edilmez. Yaklaşık 1,5–3 saniye üst-sol/üst-ortada kalın, kenarlı yazı ve 180 ms hafif fade/scale animasyonu; alt altyazıyla çakışmaz.
- **Altyazı:** sahibin son tercihiyle Dengeli Arial/fallback 50px, Bold=-1, outline=3,5, shadow=1, alt orta 100/100/72 marj; Dinamik 52px kalın. Temel başarılı Part 9 48px, normal, outline=3, shadow=1, 90/90/60 marjı aynen korur. Kurgu Stili altında Klasik / Kalın YouTube / Kalın büyük YouTube özeti gösterilir. Normal cue animasyonu yok; metin ve Part 8 zamanları/SRT/VTT değişmez. Üst vurgu kendi ayrı stilindedir, geçiş vurgu yaratmaz.
- **Sürüm uyumluluğu:** yeni plan `smart_edit_v3`; eski tamamlanmış `v1`/`v2` planı kaynakları aynıyken kendi fingerprint'iyle güncel/oynatılabilir/aktifleştirilebilir kalır. Stilsiz eski Part 9 fingerprint formülü aynen korunur. Yeni render yeni sürümdür; önceki video dosyası yeniden yazılmaz.
- **Güvenli geri dönüş:** hareket hatası → normal kadraj; geçiş hatası → temiz kesme; vurgu hatası → vurgusuz çıktı. Mevcut altyazı/ses ve ana video işlemi korunur; çekirdek işlem de başarısızsa eski aktif video korunarak hata gösterilir. Güvenli kodlar: `smart_motion_failed`, `smart_transition_failed`, `emphasis_render_failed`. Tam kaynak metni/raw stderr/sırlar günlükte yoktur.
- **NVENC ve FFmpeg 9:** filtreler yerel CPU'da çalışabilir; tüm ara ve son video encode seçilen encoder ile yapılır. Otomatik NVIDIA tercihi ve yalnız NVENC başlatma hatasında mevcut tek CPU tekrar denemesi korunur. `-/filter_complex` kullanımı sürer; kaldırılmış `-filter_complex_script` kullanılmaz. Sesin hızı/perdesi, stok sesinin dışlanması ve mevcut isteğe bağlı müzik davranışı değişmez.

193 saniye / 24 sahne / 37 VIDEO / 49 cue / 0 mevcut vurgu regresyon örneği Dengeli planda **33 hareket, 8 geçiş, 6 vurgu, 11 klip içi değişim** üretir. Bu sentetik kaynak biçimi testidir; sahibinin gerçek projesinde seçimler mevcut metin/kompozisyona göre değişir.

Gerçek FFmpeg testleri aynı VIDEO'nun Temel/Dengeli/Dinamik karelerini birden fazla zamanda karşılaştırır; kırmızı-mavi geçişte gerçek ara renkleri, vurgu piksellerinin görünmesini/kaybolmasını, uzun klibin farklı işlemlerini, yedi kamera hareketini ve güvenli geri dönüşleri sınar. Karma başarılı/başarısız slotta yalnız çıktı yolunda uygulanan hareket sayılır. FFmpeg 9.0.2 ayrı gerçek koşuda sınanır. Bu kalite düzeltmesinin Windows/NVENC görünümü için **Live render test must be run by owner on Windows.**

## Titreme nedeni ve düzeltmesi

Eski v2 kamera yolu gerçek hareketli sentetik videoda tekrarlandı: push-in bitişinden pan-right başlangıcına geçince aynı kaynağın crop konumu sıfırlanıyordu. 192px küçültülmüş karede işaret merkezi tek karede 4,99px (1920px çıktıda yaklaşık 50px) sıçradı. Aynı kaynakla v3 ölçümü 0,45px; kalan hareket kaynak videodaki hareket ve ölçek/kodlama yuvarlamasıdır. Sahibin gerçek kareleri/ham medya olmadan her Windows geçişinin tek nedenini kesinleştiremeyiz.

Yeni `neutral_cycle` smoothstep yolu her iç parça başında/sonunda nötr kadraja yumuşakça ulaşır; aynı kaynakta kamera yönünün sıfırlanması görünür sıçrama yaratmaz. 3840×2160 çalışma ölçeği ve çift piksele yuvarlanan crop adımlarını küçültür. `d=1` hareketli girdiyi dondurmaz. Giriş/çıkış crossfade ve fade tutamaçlarında kamera kadrajı sabittir; gerçek video hareketi devam eder. Çakışan punch bastırılır; vurgu kelimeleri/sıklığı/zamanları değişmez.

Kare sayısı/PTS 30fps ve 1/30 zaman tabanıyla normalize edilir. N karelik crossfade son karesini `(N−1)/30` zamanda ikinci kaynağa tamamen ulaştırır; eski N/30 rampası son karenin ardından core'a küçük artık karışım sıçraması bırakabiliyordu. Master süre kısaltılmaz. Dengeli 12 kare (0,40sn), Dinamik 14 kare (0,47sn); kısa slotlarda eski güvenli sınır devam eder. Desteksiz/başarısız efekt temiz kesmeye döner, uygulanan sayım atlanan efekti saymaz.

`tests/test_transition_stability.py` gerçek iki hareketli kaynak/crossfade ve 12sn iç parça renderlarını dekod eder: monotonik tam 30fps, tam kare sayısı/boyut/süre, siyah veya beklenmeyen yinelenen kare yok, ölçülen marker/crop sürekliliği ve tam crossfade uçları. Ardışık 16 geçiş karesi ayrıca görsel olarak incelendi. FFmpeg 7.1.5 ve kaynak derlemesi 9.0.2 CPU yolları kontrol edilir; Windows GPU sürücü görünümü için sahibin canlı denemesi gerekir.

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

## Part 9.7 — Hazırlık ve kısa kaynak kesitleri

Düğmenin pasif kalma nedeni, `_inputs()` kaynağının tüm medya alanları ve dosyaların hazır olmasını istemesi; Part 9.6 alaka kapısının uygun olmayan alanları bilinçli olarak boş bırakabilmesiydi. Eski ekran yalnız `ready=false` ile düğmeyi kapatıyordu. Şimdi **Video henüz oluşturulamıyor.** altında gerçek güvenli neden, eksik alan sayısı ve ilgili ekran bağlantısı görünür. Sahibin veritabanı burada yok; herhangi bir özel canlı projenin engelini yeni ekran göstermelidir. Eksikliği atlayarak render başlatılmaz.

Salt okunur model: `ready`, `narration_ready`, `subtitles_ready`, `stock_ready`, `ffmpeg_ready`, `unresolved_stock_slots`, `stale_stock_slots`, `missing_files`, `blockers`. Her blocker kontrollü kod/Türkçe mesaj/ekran içerir: narration_missing, subtitle_missing/stale, stock_unresolved/stale, media_file_missing, ffmpeg_missing; seçilmiş dış motor veya aktif iş ayrıca engel olabilir. Mutlak dosya yolu ve secret içermez. `ready`, tüm kaynak doğrulamaları ve seçilmiş motor hazır olduğunda true olur.

Bazı alanlar eksikken mümkün olan mevcut timeline ve cue'lar üzerinden **Tahmini plan** gösterilir. Bu önizleme render yetkisi vermez; kaynak çözülmezse POST reddedilir. **Yeni Kurgu Varyasyonu** yerel planı değiştirir ve örneğin **Kurgu varyasyonu hazırlandı ancak 3 medya alanı tamamlanmadan render başlatılamaz.** gösterir. Stil/varyasyon/altyazı modu değişimi kaynakları kendiliğinden eski yapmaz. Varsayılan adaptive + emphasis + auto + müzik kapalı korunur.

`source_duration`, `source_in/out`, `source_trim_start/end`, `used_duration` yeni render planında saklanır. Pencere medya byte kimliği + slot kimliğine göre deterministik, mümkün olduğunda kaynağın orta kısmındadır. Native transition tutamaçları için yer ayrılır; gerçek ffprobe süresine göre sınırlandırılır. Kaynak 22sn olabilir, çıktı yalnız 3,7sn kullanabilir. `playbackRate=1`, hızlandırma yok; yeni normal stok kaynağı yuvayı gerçekten karşılar. Eski kısa kaynakların oynatılması korunur; eski plan metadata/fingerprint yeniden yazılmaz.

25fps kaynağın sonuna yakın kesitte 30fps çıktı bir kare eksilebilmesin diye küçük çözümleme payı ve sınırlı son-kare hizalaması kullanılır. Bu, kısa kaynakla uzun yeni alanı doldurma veya döngüleme değildir; çıktı tam kare sayısı/master süre kontrolünden geçer.

**Montaj Motoru**: varsayılan **Yerel Adaptif — FFmpeg**; isteğe bağlı **OpenMontage — Deneysel**. OpenMontage eksikse Yerel Adaptif etkilenmez. Açık OpenMontage seçimi başarısızsa kendiliğinden motor değiştirilmez; önceki video aktif kalır. [Ayrı kurulum, doğrulanmış adaptör sözleşmeleri ve AGPL ayrımı](OPENMONTAGE_INTEGRATION.md). Her ikisi mevcut ana sesi ve Part 8 zamanlamasını kullanır. Native FFmpeg/NVENC yolu korunur.

### Part 9.7 Windows kontrolü

1. PR'yi birleştirin.
2. GitHub Desktop'ta **Fetch / Pull** yapın.
3. Uygulamayı kapatıp **START_AI_VIDEO_STUDIO.bat** ile açın.
4. Aynı projeyi açın.
5. **Görsel / Kurgu Planı → Eksik Kısa Videoları Bul** deyip onaylayın. Kilitli uzun bir seçimi değiştirmek isterseniz önce yalnız onun kilidini açın.
6. Video/görsel/benzersiz sayılarını, daha kısa ortalama kullanımını, kaynak/kullanılan süre ayrımını kontrol edin. Otomatik dikey/kare video ve tekrar olmamalı. Eksik ilgili medya kalması mümkün; alaka kapısı korunur.
7. **Video Oluştur / Render** ekranını açın.
8. Düğme pasifse üstündeki açık nedeni okuyun.
9. İstenen eksik medyayı **Eksik Kısa Videoları Bul** bağlantısıyla tamamlayın veya uygun adayı elle seçin.
10. **Montaj Motoru: Yerel Adaptif; Kurgu Stili: Uyarlanabilir YouTube; Altyazı: Sadece önemli vurgular; Encoder: Otomatik** bırakın.
11. **Videoyu Oluştur** deyin; başlangıç/orta/son ses, tempo, kartlar ve süreyi kontrol edin.
12. İsteğe bağlı dış motor için **INSTALL_OPENMONTAGE.bat** dosyasına çift tıklayın; açıklamayı okuyup **E** seçin. İlk denemede CLIP için **H** seçebilirsiniz.
13. Uygulamayı yeniden açın.
14. **Ayarlar → OpenMontage → Durumu Yenile**: **Hazır** görünmeli. Eksik bileşen yazarsa kurulum ekranındaki basit adresleri izleyin.
15. Kısa bir test projesinde **Montaj Motoru: OpenMontage** seçin.
16. **Videoyu Oluştur** deyin ve pencereyi açık bırakın.
17. Yerel Adaptif ve OpenMontage sonuçlarının ses/süre/altyazı modu ve görsel düzenlerini karşılaştırın; görünüm birebir aynı olmak zorunda değildir.
18. Önceki video sürümlerinin açıldığını ve mevcut projeler/anahtarların korunduğunu kontrol edin.

**Live provider test must be run by owner on Windows. Live render test must be run by owner on Windows. Live OpenMontage test must be run by owner on Windows.** Buluttaki gerçek CPU/Remotion testleri canlı Windows/RTX 5070 veya gerçek stok hesaplarını doğrulamaz.
