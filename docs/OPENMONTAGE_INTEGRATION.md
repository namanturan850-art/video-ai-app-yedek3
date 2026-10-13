# OpenMontage — ana montaj motoru, ayrı yerel kurulum

Part 9.8 yeni renderlarında **OpenMontage — Ana Motor** varsayılandır. Kurulmadığında uygulama/projeler açılır, bu motorla render açık kurulum mesajıyla engellenir. **Yerel Adaptif / FFmpeg / NVIDIA** elle seçilebilir. Eski video motorları değişmez; sessiz motor dönüşü yoktur. Part 10 başlamadı.

## Basit Windows kurulumu

1. Uygulama klasöründeki **INSTALL_OPENMONTAGE.bat** dosyasına çift tıklayın.
2. Açıklamayı okuyup kurmak istiyorsanız **E** yazın.
3. Eksik bileşen gösterilirse belirtilen siteden kurun: Git for Windows (git-scm.com), Python ≥3.10 (python.org), Node.js LTS ≥18 (nodejs.org). FFmpeg uygulamanın Ayarlar ekranında bulunmuş olmalı. Kurulum dosyasını yeniden açın.
4. İsteğe bağlı büyük CLIP paketleri sorulursa ilk denemede **H** seçin. Hızlı arama CLIP gerektirmez.
5. Bitince uygulamayı yeniden açın: **Ayarlar → OpenMontage → Durumu Yenile**. **Hazır · Sürüm 9327439** görünmeli.
6. Render ekranında **Montaj Motoru → OpenMontage** seçin. Önce kısa bir test projesinde video oluşturun. Önceki videolar ayrı sürüm olarak kalır.

Varsayılan ayrı kurulum: `%LOCALAPPDATA%\AI-Video-Studio\external\OpenMontage`. Uygulamanın `.venv` ortamı değiştirilmez. Kurulum Git kaynağı, ayrı `.venv`, Node bağımlılıkları ve Remotion render tarayıcısını hazırlar. Uzun ilk indirmede pencereyi açık bırakın. İleri ayarda güvenilir başka **yerel** klasör seçilebilir; URL, UNC/ağ sürücüsü ve bağlantılı klasör kabul edilmez. Kaynak dosyası veya `.env` düzenlemeniz gerekmez.

Normal başlatıcı bu kurulumu çalıştırmaz; açılışta clone/update/indirme yoktur. Kaynak sürümü tutmuyorsa veya kaynak dosyaları değiştirilmişse motor hazır sayılmaz. İleri ayarda özel klasör boş bırakılarak varsayılan kullanılır; kayıtlı özel klasörü sıfırlamak için **Varsayılan klasöre dön** düğmesi vardır.

## Doğrulanmış sürüm ve lisans

- Resmî proje: [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage).
- Sabitlenmiş/incelenmiş sürüm: [`9327439db69021ab4b0e2776729bf3b58fdb5a87`](https://github.com/calesthio/OpenMontage/tree/9327439db69021ab4b0e2776729bf3b58fdb5a87).
- OpenMontage lisansı: **GNU AGPL v3**. Ayrı checkout'taki upstream telif ve lisans dosyaları korunur. AI Video Studio içine upstream kaynak/template kopyalanmaz; uygulamanın lisansı değiştirilmedi.
- Remotion ayrı bağımlılıktır ve [kendi lisans koşullarına](https://www.remotion.dev/docs/license) tabidir.
- `worker.py`, medya/kompozisyon adaptörleri ve `composition.tsx` AI Video Studio'nun özgün adaptör kodudur. Harici araçlar yalnız ayrı Python sürecinde içe alınır; ana uygulama ortamına yüklenmez. Kaynak kod/ajan yönergeleri uygulamanın iş akışını değiştirmez.

## Medya arama sözleşmesi

**Ayarlar → OpenMontage medya araması** açıkça etkinleştirilir. **Hızlı** varsayılandır. Doğrulanmış `tools/video/direct_clip_search.py` aracının `DirectClipSearch.execute(inputs)` sözleşmesi:

| Alan | Değer |
| --- | --- |
| queries | Mevcut sahneye bağlı İngilizce query, kind=video |
| output_dir | Bu projede oluşturulmuş geçici çalışma klasörü |
| clips_per_query | 4 |
| filters.orientation | landscape |
| filters.min_duration / max_duration | 3 / 12 saniye |
| filters.min_width | 1280 |
| extract_thumbnails / skip_existing | false / true |
| timeout_seconds | 60 |

Yalnız kullanılabilir ve izin verilen kaynaklar: **Archive.org, Wikimedia Commons, NASA**. Ek olarak Pexels/Pixabay Video ancak **Anahtarlarımı yalnız arama sırasında kullan** açık onayıyla kullanılabilir. Anahtarlar şifreli kasadan okunup yalnız alt işlemin ortamına verilir; argv/JSON/log/.env dosyasına yazılmaz. Ambient diğer AI anahtarları ve harici checkout `.env` değerleri kullanılmaz. Ücretli stok kaynakları veya tam ajan hattı çalıştırılmaz.

Araç sonucundaki `success/data.clips` ve doğrulanmış kaynak kimliği, kaynak sayfası, yerel path, creator/license/source_tags alanları kullanılır. Dört adayla sınırlı; gerçek dosya yolu, boyut, MP4 imzası, ffprobe süre/boyut ve yatay/minimum 720p şartı tekrar doğrulanır. Yalnız güvenli halka açık kaynak sayfası ve normalize metadata tarayıcıya döner; ham yanıt, indirme URL'si veya dış mutlak path dönmez. Yeni MP4'ler mevcut `stock_assets` önbelleğine alınır; render yalnız bu yerel dosyaları tüketir. Eksik/bozulmuş import, yalnız açık yeniden aramada arama önbelleğini atlayıp yeni UUID dosyasıyla onarılır; önceki dosyalar/sürümler silinmez. Bu sürümde WebM/OGV gibi diğer kapsayıcılar içe alınmaz. Kaynak erişimi, lisans uygunluğu ve konu alakası garanti edilmez; kaynak sayfasını inceleyin.

**Semantik — OpenMontage** yalnız ayrı CLIP bağımlılıkları kuruluysa kullanılır. Doğrulanmış `CorpusBuilder.execute` ile aynı filtreler ve `max_new_clips=4`; `ClipSearch.execute(operation=rank_for_slot, query_text, kind=video, k=4)` sonucunun `results[].record` / `local_path` sözleşmesi mevcut alaka/tekrar kapısına girer. Torch/transformers/OpenCV zorunlu değildir, açılışta yüklenmez veya kurulmaz. Part 9.8 model ağırlıkları yalnız açık installer onayıyla indirilir. Model yoksa semantik arama/analiz engellenir; açılışta veya aramada model indirilmez. Hızlı seçeneğine kendiniz dönebilirsiniz. Otomatik testler semantik ayar kaydını ve eksik paket engelini sınar; gerçek CLIP model/kaynak kalitesi canlı doğrulanmış sayılmaz.

## Kesme ve Remotion kompozisyonu

- `VideoTrimmer.execute`: `operation=cut`, onaylı yerel `input_path`, işin kendi `output_path`, `start_seconds/end_seconds`, `codec=libx264`. Kaynak dosya yerinde değiştirilmez; kesit uzunluğu timeline karelerinden gelir.
- `VideoCompose.execute`: `operation=render`, `edit_decisions.render_runtime=remotion`, `composition_mode=atelier`, `renderer_family=bespoke`, uygulamanın özgün giriş TSX/props dosyası, yalnız işin kendi küçük public_dir'i ve output_path. Tam documentary agent pipeline çağrılmaz.
- Interchange: bizim timeline/scene/slot kimlikleri, 30fps tam kare sayısı, master ses, mevcut cue metni/altyazı modu, seçilmiş yerel medya, Adaptive düzen/pencere/theme/variant. Harici motora arama/senaryo/TTS görevi verilmez.
- Mevcut dokuz Adaptive düzeni güvenilir kısa metin ve yerel varlıklarla çizilir. Açık/karanlık temalar, bölünmüş medya, sayı/bilgi/tarih/konum ve vurgu kartları; vurgu penceresinde giriş/çıkış opacity. Yerel FFmpeg'in kamera hareketi/crossfade sayıları OpenMontage için uygulanmış gibi raporlanmaz; iki motorun görünümü birebir aynı değildir. Her iki yol aynı onaylı içeriği, kare aralıklarını ve altyazı modunu korur.
- `none` altyazısız; `emphasis` mevcut kısa kart/vurgu; `full` mevcut tam cue'ları ekler. Altyazı dosyaları veya anlatım değiştirilmez. Stok sesleri kapalı, video playbackRate=1. Ana ses yeniden oluşturulmaz.
- Son teslim mevcut yerel FFmpeg ile 1920×1080/30fps H.264/AAC, 48kHz stereo ve master süre doğrulamasına girer. Encoder/Otomatik NVENC→CPU kuralı ve müzik/ducking bizim hattımızda kalır. Bu teslim normalizasyonu, başarısız OpenMontage seçimini sessizce yerel kurguya çevirmez.
- OpenMontage seçildiğinde eksik/başarısız dış motor açık hata verir: **OpenMontage ana montaj motoru olarak seçildi ancak kurulmamış. INSTALL_OPENMONTAGE.bat ile kurulumu tamamlayın veya Yerel Adaptif motorunu seçin.** Önceki video aktif kalır.

Her iş yalnız kendi UUID staging klasörünü yaratır/temizler; upstream takipli kaynaklar değiştirilmez. `subprocess` list argümanı ve `shell=False`; yerel Remotion CLI doğrudan Node ile çağrılır, Windows `.cmd`/shell yürütülmez. Browser/FFmpeg güvenilir yerel kurulumdan bulunur, kullanıcıdan yürütülebilir dosya alınmaz. İptal yalnız uygulamanın başlattığı process ağacını hedefler. Alt işlemin ham stdout/stderr'i API/güvenli log'a taşınmaz.

## Doğrulama sınırı

Otomatik testler: kısa alan/zamanlama/tekrar, yatay seçim, trimming penceresi, render hazırlık/partial preview, güvenli yapılandırma/secret çevresi ve mocked dış araç sözleşmeleri. Ayrı sabit checkout gerçekten kurulup Linux üzerinde 6sn Remotion→FFmpeg H.264/AAC çıktısı üretildi; onaylı kaynak SHA-256 değerleri aynı kaldı. Ayrıca gerçek harici render regresyonu video + dikey görsel + tam altyazıyı teslim biçimi/süre/piksel ve kaynak özetleriyle doğrular. Bu, Windows sürücüsü veya sahibin canlı kaynak/API hesabını doğrulamaz.

**Live provider test must be run by owner on Windows. Live render test must be run by owner on Windows. Live OpenMontage test must be run by owner on Windows.** İlk OpenMontage denemesini kısa projeyle yapın; [18 adımlı kontrol](RENDERING.md#part-97-windows-kontrolü). Dış motor kurulmamış geliştirme ortamında yalnız harici gerçek smoke atlanır; çekirdek uygulama/testler çalışır. Gerçek semantik CLIP araması bu bulut geçişinde çalıştırılmadı.


## Part 9.8 — Açık onaylı yerel model kurulumu

1. Önce temel motor için **INSTALL_OPENMONTAGE.bat** çalıştırın; Ayarlar'da **Hazır** görünmeli.
2. İsteğe bağlı gerçek kare analizi için **INSTALL_OPENMONTAGE_SEMANTIC.bat** dosyasına çift tıklayın.
3. Paket/model indirme açıklamasını okuyun. Kabul ederseniz sorularda **E** yazın; varsayılan **H** indirmez.
4. Paketler (birkaç GB olabilir) ve **openai/clip-vit-base-patch32** (yaklaşık 350 MB ağırlık) ayrı kurulumun `.venv/.models` alanlarına iner. Uygulamanın normal `.venv` ortamı değişmez.
5. Uygulamayı yeniden açıp **Ayarlar → OpenMontage → Durumu Yenile** deyin. **Semantik medya analizi: Hazır** görünce **Yerel semantik kare analizi** kutusunu işaretleyip **Kaydet** deyin.

Upstream `lib/clip_embedder.py` içindeki gerçek model kimliği, `embed_images`, `embed_texts`, `model_info` sözleşmeleri incelendi. Özgün adaptör bunları ayrı süreçte, yalnız yerel indirilen model path'iyle çağırır; `HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE` açık, upstream takipli kaynaklara patch yoktur. Model manifestinde SHA-256 ve boyut; analizde ağırlık hash'i doğrulanır. Gerçek video %20/%50/%80 kareleri, 512px örnekler; en fazla dört aday, kare batch'i, SHA/model/descriptor cache'i, CUDA tercih ve bir CPU fallback'i. Model yoksa metadata/elle inceleme; API/GPU/model başarı iddiası yoktur. Benzerlik olgusal/tarihî doğrulama değildir.

Semantik corpus yolu aynı önceden kurulu yerel modeli kullanır: `CorpusBuilder.execute` ve `ClipSearch.execute(rank_for_slot)` önceki doğrulanmış araçlar olarak kalır. Hızlı çok-kaynak araması isteğe bağlıdır; yalnız mevcut açık kaynak araçları çağrılır. Yerel kare analizi cloud anahtarı veya ücretli görsel API istemez. Yeni video kompozisyonu `VideoCompose.execute`/Remotion üzerinden gerçekten yapılır; kaynak senaryo/altyazı kimliği, ana ses, etkin yeniden düzenlenmiş timeline, approved yerel medya ve Adaptive layout'lar uygulama tarafından sağlanır. Ses/senaryo tekrar üretilmez.

Gerçek bulut testi 10 sn kompozisyonda kesintisiz uzatılan iki B-roll segmenti, kısa aynen kaynak sayı kartı, narrator audio ve önemli vurgu modu içerir; final 1080p/30fps H.264/AAC/master süre ve ara piksel kontrolü yapılır. Önceki çıktı ve kaynak hash'leri korunur. Bu gerçek harici CPU render kanıtıdır; CLIP ağırlıkları açık sahibi onayı olmadan indirilmedi. Frame-verdict/GPU fallback testleri sözleşme testidir. **RTX 5070/PyTorch CUDA uyumluluğu ve gerçek görsel doğruluk deneysel, Windows'ta sahibi tarafından denenmeli.** Motorlar birebir aynı efekt görünümünü vaat etmez.

[Part 9.8 için 17 basit Windows adımı](RENDERING.md#part-98-windows-kontrolü).


## Hibrit montaj (hızlı render)

OpenMontage motoru artık **tüm videoyu** Remotion'da kare kare çizmez:

1. Yalnız **grafik düzenli sahneler** (panel yazı, bölünmüş ekran, büyük sayı…) Remotion ile çizilir. Bunlar birkaç parçaya bölünüp **aynı anda** çizilir (her parça kendi tarayıcısında).
2. Geri kalan **B-roll**, geçişler, altyazı, vurgu yazıları, müzik ve teslim **FFmpeg** (NVIDIA kartta **NVENC**) ile yapılır; sahne parçaları da birkaç tane **paralel** kodlanır.
3. Grafik sahne yoksa Remotion hiç çalışmaz. Bir Remotion parçası çizilemezse o sahneler FFmpeg'in kendi düzeniyle yapılır (uyarı gösterilir).

Render süresi video sürümü kartında görünür: toplam, Remotion/FFmpeg payı ve paralel parça sayısı.
Eski davranışla (tüm video Remotion'da) karşılaştırmak için ortam değişkeni: `AVS_REMOTION_SCOPE=all`. Paralel parça sayısı otomatiktir; elle: `AVS_RENDER_WORKERS` (FFmpeg, 1–8), `AVS_REMOTION_WORKERS` (Remotion, 1–4).
