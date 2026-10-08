# AI Video Studio

Bilgisayarınızda çalışan, Türkçe arayüzlü video üretim çalışma alanı.

**Part 7 seslendirme taslağı:** AI33 / OpenSpeaker ayarları, salt okunur bağlantı testi ve yerel seslendirme iş/sürüm altyapısı eklendi. Resmî ses listesi ve görev çıktı alanları bekleniyor; ücretli üretim kapalı, henüz birleştirmeye hazır değil. [Basit Windows kontrolü](docs/NARRATION.md) ve [eksik API belgeleri](AI33_INTEGRATION_NOTES.md).

**Sağlayıcı sorunlarını ayırmak için:** Ayarlar → **AI Tanılama**. Şifreli kayıt, bağlantı, kısa üretim, JSON ve tek senaryo bölümü ayrı test edilir. [Çok basit Windows adımları](docs/AI_DIAGNOSTICS.md). Canlı testleri sahibi Windows'ta çalıştırmalıdır; otomatik test başarısı canlı API başarısı değildir.

**Aşama 1–5 hazır; Aşama 6 stok medya eklendi:** ana sayfa, Tanılama, güvenli yerel Ayarlar, projeler, genel amaçlı YouTube senaryo motoru, düzenlenebilir sahne planları ve Pexels/Pixabay medya yuvaları. Gemini / Ollama / OpenAI ile içerik analizi, dinamik bölüm planı, özgün senaryo, düzenleme, sürümler ve onay kullanılabilir. Sistem yalnızca hikâyeler için değildir. Uygulamayı açmak için hiçbir API anahtarı zorunlu değildir. Gerçek video üretimi henüz yoktur. Yeni stok akışının canlı Windows kontrolü sahibi tarafından yapılmalıdır.

**Sahne planını denemek için:** Proje → **Senaryoyu Aç → Onayla** → **Görsel / Kurgu Planı → Ollama → Görsel / Kurgu Planını Hazırla**. Sahneyi düzenleyebilir, tek sahneyi yeniden planlayabilir, bölebilir/birleştirebilir, kilitleyebilir ve eski plan sürümünü seçebilirsiniz. Yukarı/Aşağı taşı görsel tasarımı taşır; anlatım sırası korunur. [12 basit Windows deneme adımı](docs/SCENE_PLANNING.md). Süreler tahminidir; ses ve video üretilmez.

**Stok medyayı denemek için:** **Ayarlar → Pexels / Pixabay → Kaydet → Bağlantıyı Test Et**. Ardından hazır sahne planında **Medyayı Otomatik Bul** deyin. Seçilen video/görseller yerel proje klasörüne indirilir; **Değiştir**, **Kilitle**, **Eksik Medyaları Tamamla** ve **Devam Et** kullanılabilir. [12 çok basit Windows adımı ve resmî API kaynakları](docs/STOCK_MEDIA.md). AI görsel üretimi, TTS ve render henüz çalıştırılmaz.

**Kararlılık ve geliştirme paketi:** gerçek OpenAI erişim testi, güvenli kasa hata ayrımı, kota bekleme/devam, beş hedef dil, retention/hook/A-B/iddia araçları ve onaylı metinden görsel/kurgu planı eklendi. Görsel sağlayıcı ayarları ve kontrolleri çalışır; gerçek görsel/TTS, müzik işleme, render ve yükleme sonraki çalıştırma için hazırlanmıştır. Ücretli görsel fallback varsayılan **KAPALI**. Tek basit [Windows kontrol listesi](docs/STABILITY_AND_ENHANCEMENTS.md) tüm paketi anlatır.

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
- **FFmpeg bulunamadı:** Bu aşamada sorun değildir; uygulama yine açılır. Video oluşturma özelliği geldiğinde FFmpeg gerekecektir.

Ana sayfadaki **Tanılama** kartı Python, işletim sistemi, veritabanı, veri klasörü ve FFmpeg durumunu gösterir. Gizli anahtarları göstermez.

## Projeleri Windows'ta deneme

1. Uygulamayı açıp **Yeni Proje** kartına tıklayın.
2. Proje adı ve konu yazın; diğer seçenekleri değiştirmeden **Proje Oluştur** deyin. Proje sayfası açılır.
3. **Projeler** ekranına gidin. Uygulamayı kapatıp yeniden açın; projeniz listede kalmalıdır.
4. İkinci bir deneme projesi oluşturun. İlk projede **Projeyi Sil** deyin. Önce **İptal** ile projenin kaldığını, sonra onay vererek yalnızca ilk projenin silindiğini kontrol edin.

**Senaryo → Senaryoyu Aç** ve **Görsel / Kurgu Planı** çalışır. Medya, seslendirme ve render aşamalarında **Bekliyor / Hazır değil** görünmesi normaldir. Ayrıntılar: [Projeler rehberi](docs/PROJECTS.md).

## Ayarları Windows'ta deneme

1. Uygulamayı açıp **Ayarlar** kartına tıklayın.
2. **Genel** bölümünde bir dil seçip **Kaydet** deyin. Sayfayı yeniden açıp seçimin korunduğunu görün.
3. Pexels bölümünde yalnızca deneme için `deneme-anahtari-1234` yazıp **Kaydet** deyin. Alan boşalır, maskede yalnızca `1234` görünür. Uygulamayı kapatıp yeniden açın; maskeli kayıt korunmalıdır. Bu deneme anahtarı gerçek bir hizmet anahtarı değildir.
4. İsterseniz **Temizle** ile o bölümdeki bilgileri silin. Diğer bölümler değişmez.

Ollama kuruluysa bilgilerini kaydedip **Bağlantıyı Test Et** düğmesine basabilirsiniz. OpenAI için **Etkinleştir → anahtar/model → Kaydet → Bağlantıyı Test Et** resmi model erişimini kontrol eder. Üretim bakiyesi/kotası ayrıca değerlendirilir. FFmpeg otomatik algılanır. **AI33 API belgeleri gerekli** mesajı beklenen durumdur; AI33 testi kapalıdır. Pexels/Pixabay testleri yer tutucudur. Ayrıntılar: [Ayarlar rehberi](docs/SETTINGS.md).

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
