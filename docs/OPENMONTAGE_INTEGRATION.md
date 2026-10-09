# OpenMontage — isteğe bağlı ayrı yerel motor

AI Video Studio varsayılan olarak **Yerel Adaptif / FFmpeg** kullanır. OpenMontage kurulmadan da mevcut çalışma akışı, CPU ve NVIDIA NVENC çalışır. Bu ekleme yalnız Part 9.7'dir; Part 10 başlamadı.

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

**Semantik — OpenMontage** yalnız ayrı CLIP bağımlılıkları kuruluysa kullanılır. Doğrulanmış `CorpusBuilder.execute` ile aynı filtreler ve `max_new_clips=4`; `ClipSearch.execute(operation=rank_for_slot, query_text, kind=video, k=4)` sonucunun `results[].record` / `local_path` sözleşmesi mevcut alaka/tekrar kapısına girer. Torch/transformers/OpenCV zorunlu değildir, açılışta yüklenmez veya kurulmaz. Model ağırlıkları ilk açık semantik aramada indirilebilir; indirme tamamlanamazsa güvenli hata görünür. Hızlı seçeneğine kendiniz dönebilirsiniz. Otomatik testler semantik ayar kaydını ve eksik paket engelini sınar; gerçek CLIP model/kaynak kalitesi canlı doğrulanmış sayılmaz.

## Kesme ve Remotion kompozisyonu

- `VideoTrimmer.execute`: `operation=cut`, onaylı yerel `input_path`, işin kendi `output_path`, `start_seconds/end_seconds`, `codec=libx264`. Kaynak dosya yerinde değiştirilmez; kesit uzunluğu timeline karelerinden gelir.
- `VideoCompose.execute`: `operation=render`, `edit_decisions.render_runtime=remotion`, `composition_mode=atelier`, `renderer_family=bespoke`, uygulamanın özgün giriş TSX/props dosyası, yalnız işin kendi küçük public_dir'i ve output_path. Tam documentary agent pipeline çağrılmaz.
- Interchange: bizim timeline/scene/slot kimlikleri, 30fps tam kare sayısı, master ses, mevcut cue metni/altyazı modu, seçilmiş yerel medya, Adaptive düzen/pencere/theme/variant. Harici motora arama/senaryo/TTS görevi verilmez.
- Mevcut dokuz Adaptive düzeni güvenilir kısa metin ve yerel varlıklarla çizilir. Açık/karanlık temalar, bölünmüş medya, sayı/bilgi/tarih/konum ve vurgu kartları; vurgu penceresinde giriş/çıkış opacity. Yerel FFmpeg'in kamera hareketi/crossfade sayıları OpenMontage için uygulanmış gibi raporlanmaz; iki motorun görünümü birebir aynı değildir. Her iki yol aynı onaylı içeriği, kare aralıklarını ve altyazı modunu korur.
- `none` altyazısız; `emphasis` mevcut kısa kart/vurgu; `full` mevcut tam cue'ları ekler. Altyazı dosyaları veya anlatım değiştirilmez. Stok sesleri kapalı, video playbackRate=1. Ana ses yeniden oluşturulmaz.
- Son teslim mevcut yerel FFmpeg ile 1920×1080/30fps H.264/AAC, 48kHz stereo ve master süre doğrulamasına girer. Encoder/Otomatik NVENC→CPU kuralı ve müzik/ducking bizim hattımızda kalır. Bu teslim normalizasyonu, başarısız OpenMontage seçimini sessizce yerel kurguya çevirmez.
- OpenMontage seçildiğinde eksik/başarısız dış motor açık hata verir: **OpenMontage hazır değil. Ayarlar bölümünden kurulumu tamamlayın veya Yerel Adaptif motorunu seçin.** Önceki video aktif kalır.

Her iş yalnız kendi UUID staging klasörünü yaratır/temizler; upstream takipli kaynaklar değiştirilmez. `subprocess` list argümanı ve `shell=False`; yerel Remotion CLI doğrudan Node ile çağrılır, Windows `.cmd`/shell yürütülmez. Browser/FFmpeg güvenilir yerel kurulumdan bulunur, kullanıcıdan yürütülebilir dosya alınmaz. İptal yalnız uygulamanın başlattığı process ağacını hedefler. Alt işlemin ham stdout/stderr'i API/güvenli log'a taşınmaz.

## Doğrulama sınırı

Otomatik testler: kısa alan/zamanlama/tekrar, yatay seçim, trimming penceresi, render hazırlık/partial preview, güvenli yapılandırma/secret çevresi ve mocked dış araç sözleşmeleri. Ayrı sabit checkout gerçekten kurulup Linux üzerinde 6sn Remotion→FFmpeg H.264/AAC çıktısı üretildi; onaylı kaynak SHA-256 değerleri aynı kaldı. Ayrıca gerçek harici render regresyonu video + dikey görsel + tam altyazıyı teslim biçimi/süre/piksel ve kaynak özetleriyle doğrular. Bu, Windows sürücüsü veya sahibin canlı kaynak/API hesabını doğrulamaz.

**Live provider test must be run by owner on Windows. Live render test must be run by owner on Windows. Live OpenMontage test must be run by owner on Windows.** İlk OpenMontage denemesini kısa projeyle yapın; [18 adımlı kontrol](RENDERING.md#part-97-windows-kontrolü). Dış motor kurulmamış geliştirme ortamında yalnız harici gerçek smoke atlanır; çekirdek uygulama/testler çalışır. Gerçek semantik CLIP araması bu bulut geçişinde çalıştırılmadı.
