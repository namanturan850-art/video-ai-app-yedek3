# Part 9.7 — Kısa Klipler + İsteğe Bağlı OpenMontage

**Görsel / Kurgu Planı → Alakaya Göre Medyayı Yeniden Ara**: belgesel/röportaj/eski gibi stil sözcükleri konu değildir. Kokpit/mürettebat sahnesine ilgisiz kişi veya manzara otomatik seçilmez. Projede kullanılan medya yeniden otomatik atanmaz; uygun benzersiz aday yoksa yuva boş kalır. Kilitli seçimler ve eski dosyalar korunur.

**Video Oluştur / Render → Uyarlanabilir YouTube** yeni renderların önerilen varsayılanıdır. İçeriğe göre B-roll, medya/metin, bilgi, büyük sayı, tarih, konum ve kısa vurgu düzenleri seçilir. **Yeni Kurgu Varyasyonu** yalnız yerel planı değiştirir; API/TTS/stok çağrısı yapmaz. **Altyazı Gösterimi**: Tam altyazı / Sadece önemli vurgular / Altyazı yok. Temel/Dengeli/Dinamik seçenekleri ve önceki videolar korunur.

[Basit Windows kontrolü](docs/RENDERING.md#part-96-windows-kontrolü) · [Medya V3 kuralları](docs/STOCK_MEDIA.md#media-relevance-v3). Yerel motor için yeni bağımlılık yok; OpenMontage ayrı ve isteğe bağlı kurulur. Ücretli API veya veritabanı sıfırlama yok. **Part 10 başlamadı.** Canlı Windows/sağlayıcı/NVENC doğrulamasını sahibi yapmalıdır.

# AI Video Studio

**Part 9.7 — Kısa klipler + isteğe bağlı OpenMontage:** render düğmesi eksik kaynakları açıklar; “Eksik Kısa Videoları Bul” uzun, kilitsiz görsel alanları yaklaşık 3–4 saniyelik farklı yatay medya alanlarına böler. İlgili uzun kaynaklar yerel kesilir; anlatım ve altyazılar değişmez. Varsayılan **Yerel Adaptif** motoru Node/Git/OpenMontage gerektirmez.

OpenMontage denemek isterseniz `INSTALL_OPENMONTAGE.bat` dosyasına çift tıklayın, ardından **Ayarlar → OpenMontage → Durumu Yenile**. İlk denemeyi kısa projede yapın. [Kurulum ve lisans](docs/OPENMONTAGE_INTEGRATION.md), [18 basit Windows kontrol adımı](docs/RENDERING.md#part-97-windows-kontrolü). **Part 10 başlamadı.**

Bilgisayarınızda çalışan, Türkçe arayüzlü video üretim çalışma alanı.

**Part 7 seslendirme:** Sahibinin canlı doğruladığı AI33 TTS sözleşmesi etkin: done/tts/metadata.audio_url. Onaylı senaryo ve seçili sesle, açık kredi onayından sonra görev oluşturma/izleme, güvenli indirme, yerel oynatma ve sürümler kullanılabilir. Devam Et aynı görevi kullanır. ElevenLabs yeni ayarın varsayılanıdır. Ses adı araması ve hızlı sayfalama; ücretsiz hazır örnek ile ücretli Kısa TTS Testi ayrı gösterilir. [19 basit Windows adımı](docs/NARRATION.md) ve [doğrulanmış sözleşme](AI33_INTEGRATION_NOTES.md). Part 7 sahibi tarafından gerçek Windows'ta ses üretimi/oynatma/kalıcılık ve Pixabay korunumu ile doğrulandı.

**Part 8 altyazı ve zamanlama:** Çalışan sesinizin projesinde **Altyazı ve Zamanlama → Altyazıları Oluştur**. Yerel sesin gerçek süresi ölçülüp kaydedilir; onaylı metin korunarak SRT/VTT, yerel sesle önizleme, zaman/metin editörü ve eski sürümler hazırlanır. İşlem kredi/API kullanmaz. **Ses süresine göre yaklaşık zamanlama**; kesin kelime hizalaması değildir. [15 çok basit Windows adımı](docs/SUBTITLES.md). Part 9 bu mevcut zamanlamayı salt okunur kullanarak video oluşturur.

**Sağlayıcı sorunlarını ayırmak için:** Ayarlar → **AI Tanılama**. Şifreli kayıt, bağlantı, kısa üretim, JSON ve tek senaryo bölümü ayrı test edilir. [Çok basit Windows adımları](docs/AI_DIAGNOSTICS.md). Canlı testleri sahibi Windows'ta çalıştırmalıdır; otomatik test başarısı canlı API başarısı değildir.

**Aşama 1–5 hazır; Aşama 6 stok medya eklendi:** ana sayfa, Tanılama, güvenli yerel Ayarlar, projeler, genel amaçlı YouTube senaryo motoru, düzenlenebilir sahne planları ve Pexels/Pixabay medya yuvaları. Gemini / Ollama / OpenAI ile içerik analizi, dinamik bölüm planı, özgün senaryo, düzenleme, sürümler ve onay kullanılabilir. Sistem yalnızca hikâyeler için değildir. Uygulamayı açmak için hiçbir API anahtarı zorunlu değildir. Part 9 yerel video üretimi sahibi tarafından Windows’ta doğrulandı; Part 9.5 görünür kurgu kontrolü için Render rehberini izleyin.

**Sahne planını denemek için:** Proje → **Senaryoyu Aç → Onayla** → **Görsel / Kurgu Planı → Ollama → Görsel / Kurgu Planını Hazırla**. Sahneyi düzenleyebilir, tek sahneyi yeniden planlayabilir, bölebilir/birleştirebilir, kilitleyebilir ve eski plan sürümünü seçebilirsiniz. Yukarı/Aşağı taşı görsel tasarımı taşır; anlatım sırası korunur. [12 basit Windows deneme adımı](docs/SCENE_PLANNING.md). Süreler tahminidir; ses ve video üretilmez.

**Stok medyayı denemek için:** **Ayarlar → Pexels / Pixabay → Kaydet → Bağlantıyı Test Et**. Ardından hazır sahne planında **Medyayı Otomatik Bul** deyin. Seçilen video/görseller yerel proje klasörüne indirilir; **Değiştir**, **Kilitle**, **Eksik Medyaları Tamamla** ve **Devam Et** kullanılabilir. [12 çok basit Windows adımı ve resmî API kaynakları](docs/STOCK_MEDIA.md). AI görsel üretimi henüz çalıştırılmaz; seslendirme Part 7, yerel render Part 9 ekranındadır.

**Kararlılık ve geliştirme paketi:** gerçek OpenAI erişim testi, güvenli kasa hata ayrımı, kota bekleme/devam, beş hedef dil, retention/hook/A-B/iddia araçları ve onaylı metinden görsel/kurgu planı eklendi. Görsel sağlayıcı ayarları ve kontrolleri çalışır; gerçek görsel üretimi ve yükleme sonraki aşamalar içindir; yerel müzik/render Part 9’da uygulanmıştır. Ücretli görsel fallback varsayılan **KAPALI**. Tek basit [Windows kontrol listesi](docs/STABILITY_AND_ENHANCEMENTS.md) tüm paketi anlatır.

## Windows'ta nasıl açılır?

1. Python yoksa [python.org](https://www.python.org/downloads/windows/) üzerinden **Python 3.12 veya daha yeni bir sürüm** kurun. Kurulumda **Add python.exe to PATH** kutusunu işaretleyin.
2. Proje ZIP dosyasını indirdiyseniz sağ tıklayıp **Tümünü ayıkla** seçin. Çıkarılan klasörü açın.
3. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın.

İlk açılışta internet bağlantısı gerekir. Gerekli bileşenler otomatik kurulur; pencere durum mesajları gösterir. Kurulum bitince tarayıcı kendiliğinden açılır. **Siyah pencereyi açık bırakın.** Sonraki açılışlarda da aynı dosyaya çift tıklamanız yeterlidir.

Uygulamayı kapatmak için siyah pencereyi kapatın veya pencerenin içinde **Ctrl+C** tuşlarına basın. Sonra tarayıcı sekmesini kapatabilirsiniz.

### Bir sorun olursa

- **Python bulunamadı:** Python'u yukarıdaki şekilde kurun, ardından tekrar çift tıklayın.
- **Kurulum tamamlanamadı:** İnternet bağlantınızı kontrol edip yeniden açın. Sorun sürerse `logs/installation.log` dosyasını destek için paylaşın.
- **Adres kullanımda:** Önceden açtığınız uygulamanın siyah penceresini kapatıp tekrar deneyin.
- **Tarayıcı açılmadı:** Tarayıcının adres çubuğuna `http://127.0.0.1:8000` yazın.
- **Veri klasörüne yazılamıyor:** Çıkarılan uygulama klasörünü Belgeler klasörünüze taşıyıp tekrar açın.
- **FFmpeg bulunamadı:** Uygulama açılır; video oluşturmak için FFmpeg gerekir. [Render rehberini](docs/RENDERING.md) açın.

Ana sayfadaki **Tanılama** kartı Python, işletim sistemi, veritabanı, veri klasörü ve FFmpeg durumunu gösterir. Gizli anahtarları göstermez.

## Projeleri Windows'ta deneme

1. Uygulamayı açıp **Yeni Proje** kartına tıklayın.
2. Proje adı ve konu yazın; diğer seçenekleri değiştirmeden **Proje Oluştur** deyin. Proje sayfası açılır.
3. **Projeler** ekranına gidin. Uygulamayı kapatıp yeniden açın; projeniz listede kalmalıdır.
4. İkinci bir deneme projesi oluşturun. İlk projede **Projeyi Sil** deyin. Önce **İptal** ile projenin kaldığını, sonra onay vererek yalnızca ilk projenin silindiğini kontrol edin.

**Senaryo → Senaryoyu Aç**, **Görsel / Kurgu Planı**, Stok medya, Seslendirme, Altyazı ve Zamanlama ve **Video Oluştur / Render** ekranları kullanılabilir. Ayrıntılar: [Projeler rehberi](docs/PROJECTS.md) ve [Render rehberi](docs/RENDERING.md).

## Ayarları Windows'ta deneme

1. Uygulamayı açıp **Ayarlar** kartına tıklayın.
2. **Genel** bölümünde bir dil seçip **Kaydet** deyin. Sayfayı yeniden açıp seçimin korunduğunu görün.
3. Pexels bölümünde yalnızca deneme için `deneme-anahtari-1234` yazıp **Kaydet** deyin. Alan boşalır, maskede yalnızca `1234` görünür. Uygulamayı kapatıp yeniden açın; maskeli kayıt korunmalıdır. Bu deneme anahtarı gerçek bir hizmet anahtarı değildir.
4. İsterseniz **Temizle** ile o bölümdeki bilgileri silin. Diğer bölümler değişmez.

Ollama kuruluysa bilgilerini kaydedip **Bağlantıyı Test Et** düğmesine basabilirsiniz. OpenAI için **Etkinleştir → anahtar/model → Kaydet → Bağlantıyı Test Et** resmi model erişimini kontrol eder. Üretim bakiyesi/kotası ayrıca değerlendirilir. FFmpeg otomatik algılanır. **AI33 bağlantı testi** yalnız kredi erişimini kontrol eder; ses üretmez. Seslendirme ayrı kredi onayı ister. Stok ayarları için [Part 6 rehberine](docs/STOCK_MEDIA.md) bakın. Ayrıntılar: [Ayarlar rehberi](docs/SETTINGS.md).

## Gemini'yi Windows'ta deneme

1. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın.
2. **Ayarlar → Gemini** bölümünde [Google AI Studio](https://aistudio.google.com/apikey) API anahtarınızı girip **Kaydet** deyin. Tam anahtar tekrar gösterilmez.
3. **Modelleri Getir** deyin. **Model** alanında listeden bir model seçip **Kaydet** deyin.
4. **Bağlantıyı Test Et** düğmesine basın; **Hazır** mesajını kontrol edin. Gemini sorguları internet durumuna göre 60 saniyeye kadar sürebilir.
5. **Yeni Proje → Senaryo motoru (Script Engine)** bölümünde **Gemini** seçip projenizi oluşturun. Seçim proje sayfasında görünür ve yeniden açılışta korunur.

Gemini isteğe bağlıdır. Gemini Plus / Google AI Pro web aboneliği yerine ayrı bir Developer API anahtarı kullanılır. Bağlantı testi senaryo üretmez. Ayrıntılar ve doğrulanmış resmi API kaynakları: [Gemini rehberi](docs/GEMINI.md).

Eski modeliniz listede yoksa listeden yeni bir model seçip **Kaydet** deyin. Gemini zaman aşımı artık uygulamanın kapalı olduğu şeklinde gösterilmez; arayüz gerektiğinde yerel uygulamayı ayrıca kontrol eder.

## Gemini ile ilk Almanca senaryo

1. Gemini **Hazır** ise mevcut anahtar/modeli kullanın.
2. **Yeni Proje**: bir ad ve konu yazın; örneğin **Elektrikli ve hibrit otomobillerin günlük kullanım karşılaştırması**. İlk denemede süre **5 dakika**, motor **Gemini** olsun. **Proje Oluştur** deyin.
3. **Senaryoyu Aç**: **Gemini**, **Almanca**, **Konseptten Özgün Senaryo** seçili olsun. İçerik türünü **AI otomatik algılasın** olarak bırakın.
4. **Analiz Et**, ardından **Senaryo Oluştur** deyin. Siyah pencereyi açık bırakıp ilerlemeyi takip edin.
5. Metni okuyun. Gerekirse **Düzenle → Kaydet**, sonra **Onayla** deyin. Her kayıt yeni sürümdür.

Kesilirse bölümler korunur; kota durumunda bekleyip **Devam Et** deyin. Onaylı sürüm açık onayınız olmadan değiştirilmez. Kendi metniniz için ayrıca **Kendi Metnimi Seçili Dile Çevir** modu ve sahiplik onayı vardır. Almanca varsayılandır; İspanyolca, İngilizce, Fransızca ve Türkçe de seçilebilir. Referans URL'den video/transcript alınmaz. Bulut üretim/kalite/planlama işlemleri API kotası veya ücret kullanabilir; işlem başında onay gösterilir. Ayrıntılı basit kullanım ve sınırlar: [Senaryo rehberi](docs/SCRIPT_ENGINE.md).

## Yerel dosyalar

Veritabanı otomatik olarak `data/app.db` dosyasında oluşur. Proje klasörleri `data/projects` içindedir. Güncelleme yaparken mevcut `data` klasörünüzü koruyun; eski veritabanı otomatik ve güvenli biçimde yükseltilir. Python bileşenleri `.venv` klasöründe, başlatma kayıtları `logs` klasöründe tutulur. Bu dosyalar ve gizli ayarlar Git'e dahil edilmez. Anahtarlar **Ayarlar** ekranından girilir; `.env` veya kod düzenlemeyin. Şifreli yerel ayarlar `data/secrets` klasöründedir. Bu klasör Git’e dahil edilmez; paylaşmayın. Windows’ta şifreleme anahtarı kullanıcı hesabıyla korunur.

## Geliştiriciler için

Python 3.12+ kullanın. Node.js ve Docker gerekmez.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python start.py
# Linux/macOS:
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python start.py
```

Başlatıcı, sunucuyu yalnızca `127.0.0.1` adresinde açar. `/api/health` başarılı olduktan sonra tarayıcı açılır. Tanılama verisi `/api/diagnostics` adresindedir. Testlerde geçici veritabanları kullanılır; gerçek HTTP başlangıç testi yerel, Git tarafından yok sayılan veritabanını da doğrular.

Geliştirme makinesinde Node.js varsa pytest, Settings HTTP yardımcısının 24 zaman aşımı/hata sınıflandırma testini de çalıştırır. Node yoksa yalnızca bu ek kontrol atlanır; Windows başlatıcısı Node gerektirmez.

Proje kuralları: [AGENTS.md](AGENTS.md). Kapsam: [ROADMAP.md](ROADMAP.md). Tamamlananlar: [docs/STATUS.md](docs/STATUS.md).
