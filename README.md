# AI Video Studio

Bilgisayarınızda çalışan, Türkçe arayüzlü video üretim çalışma alanı.

**Aşama 1–3 hazır:** ana sayfa, Tanılama, güvenli yerel Ayarlar ve proje oluşturma/listeleme/açma/silme. Proje sayfasında üretim aşamaları henüz yer tutucudur; video veya senaryo oluşturulmaz. Hiçbir API anahtarı zorunlu değildir.

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

Üretim aşamalarında **Bekliyor / Hazır değil** görünmesi normaldir. Ayrıntılar: [Projeler rehberi](docs/PROJECTS.md).

## Ayarları Windows'ta deneme

1. Uygulamayı açıp **Ayarlar** kartına tıklayın.
2. **Genel** bölümünde bir dil seçip **Kaydet** deyin. Sayfayı yeniden açıp seçimin korunduğunu görün.
3. Pexels bölümünde yalnızca deneme için `deneme-anahtari-1234` yazıp **Kaydet** deyin. Alan boşalır, maskede yalnızca `1234` görünür. Uygulamayı kapatıp yeniden açın; maskeli kayıt korunmalıdır. Bu deneme anahtarı gerçek bir hizmet anahtarı değildir.
4. İsterseniz **Temizle** ile o bölümdeki bilgileri silin. Diğer bölümler değişmez.

Ollama kuruluysa bilgilerini kaydedip **Bağlantıyı Test Et** düğmesine basabilirsiniz. FFmpeg otomatik algılanır. **AI33 API belgeleri gerekli** mesajı beklenen durumdur; AI33 testi kapalıdır. Pexels, Pixabay ve OpenAI testleri de bu aşamada açıklamalı yer tutucudur. Ayrıntılar: [Ayarlar rehberi](docs/SETTINGS.md).

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

Proje kuralları: [AGENTS.md](AGENTS.md). Kapsam: [ROADMAP.md](ROADMAP.md). Tamamlananlar: [docs/STATUS.md](docs/STATUS.md).
