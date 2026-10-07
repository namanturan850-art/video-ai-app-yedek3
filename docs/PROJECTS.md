# Aşama 3 — Projeler

## Windows'ta kullanma

1. `START_AI_VIDEO_STUDIO.bat` dosyasına çift tıklayın.
2. **Yeni Proje** kartını açın. Bir **Proje adı** ve **Konu** yazın.
3. Diğer seçenekleri kontrol edip **Proje Oluştur** düğmesine basın. Proje sayfası kendiliğinden açılır.
4. **Projeler** ekranından kayıtlı projeleri açabilirsiniz. Proje sayfasındaki **Proje bilgilerini düzenle** bölümünden metinleri ve senaryo motorunu değiştirebilirsiniz.

Varsayılan dil **Almanca**, hedef süre **5 dakika**, içerik türü **Otomatik**, sahne süresi **4–8 saniye**. Altyazı ve küçük resim planlama açık, müzik kapalıdır. Süre/dil senaryo ekranında kullanılabilir; sahne ve medya tercihleri gelecekteki üretim için saklanır. Genel Ayarlar'daki dil tercihi Yeni Proje'nin Almanca varsayılanını değiştirmez.

**Senaryo motoru (Script Engine): Ollama, OpenAI veya Gemini.** Varsayılan Ollama'dır; eski projelerde de bu tercih eklenir. Seçim projede kalıcı olarak saklanır, anahtarlar projeye kopyalanmaz. Sağlayıcı henüz yapılandırılmamış olsa bile proje oluşturulabilir. Motor seçmek üretimi başlatmaz. Gemini ayarları ve adaptörü için [Gemini rehberi](GEMINI.md).

Referans YouTube URL'si boş bırakılabilir. YouTube izleme, kısa bağlantı, shorts, live veya embed video adresleri kabul edilir. Bağlantının biçimi kontrol edilir; videonun gerçekten mevcut olduğu kontrol edilmez. **Video analiz edilmez veya indirilmez.**

Proje adı ve konu zorunludur. Hedef süre 1–180 dakika, sahne süreleri 1–120 saniye olmalıdır. Minimum sahne süresi maksimumdan, maksimum sahne süresi toplam video süresinden büyük olamaz. İstenmeyen alanlar ve API anahtarları proje API'sine kabul edilmez.

## Proje listesi ve detay

Projeler en yeni oluşturulandan başlayarak listelenir. İsim, konu, dil, hedef süre, durum ve oluşturulma/son güncelleme tarihleri gösterilir. Tarihler Türkiye saatiyle gösterilir; veritabanında UTC olarak saklanır.

Durum karşılıkları:

| Kayıt değeri | Ekranda |
| --- | --- |
| draft | Taslak |
| ready | Hazır |
| processing | İşleniyor |
| completed | Tamamlandı |
| error | Hata |

Yeni proje **Taslak** olur. Proje oluşturmak üretimi başlatmaz. Detayda **Senaryo → Senaryoyu Aç** genel amaçlı senaryo ekranını açar; Konsept/Senaryo durumu analiz ve üretime göre görünür. Sahne Planı, Stok Medya, Seslendirme, Altyazı, Render, Metadata ve Export **Bekliyor / Hazır değil** yer tutucularıdır. Senaryonun taslak/onay durumu ayrı tutulur; senaryo onayı bütün videoyu Tamamlandı yapmaz. Kullanım: [Senaryo rehberi](SCRIPT_ENGINE.md).

## Silme

**Projeyi Sil** düğmesi, proje adını içeren Türkçe onay ister. **İptal** hiçbir şeyi silmez. **Tamam**, yalnızca o projeye ait kayıt ve dosyaları kalıcı olarak siler. Bu işlem geri alınamaz.

Klasörü zaten eksik olan bir proje kaydı güvenle silinebilir. Sembolik bağlantılar ve Windows junction/reparse bağlantıları tespit edilirse işlem durdurulur. Başka projelerin klasörleri ve yerel gizli ayarlar silinmez. Açık/kilitli dosya nedeniyle silme başarısız olursa kayıt korunur; bazı dosyalar temizlenmiş olabilir. Açık dosyaları kapatıp yeniden deneyin. SQLite ile dosya sistemi tek bir ortak atomik işlem sunmadığından elektrik kesintisi gibi bir kesinti eksik klasör bırakabilir; uygulama bunu başka klasöre yönelerek telafi etmez.

Senaryo üretimi sürerken proje silme engellenir. Silinen projenin senaryo işleri ve sürümleri de yalnızca o projeye bağlı SQLite kayıtlarıyla temizlenir.

## Yerel saklama ve güvenli yükseltme

Veritabanı: `data/app.db`. Tercihler proje tablosundadır; API anahtarları bu tabloya kopyalanmaz. Her projeye kullanıcı adından bağımsız, benzersiz bir UUID verilir:

```text
data/projects/<project-id>/
  script/
  scenes/
  stock/
  voice/
  subtitles/
  music/
  render/
  logs/
```

Güncel şema sürümü **4**. Eski sürüm 1/2 önce proje tablosu ve `script_engine` sütunuyla sürüm 3'e, ardından senaryo tabloları eklenerek sürüm 4'e yükseltilir. Eski sürüm 3 doğrudan yeni senaryo tablolarını alır. İşlem eklemeli ve işlemseldir; mevcut tablolar, kullanıcı verileri, zamanları, klasörler ve şifreli ayarlar korunur. Yükseltme başarısızsa işlem geri alınır. Bilinmeyen daha yeni şema sürümü otomatik düşürülmez veya silinmez. Uygulamayı güncellerken mevcut `data` klasörünü koruyun.

Yeni proje klasörü oluşturulamazsa kayıt eklenmez. Kayıt eklenemezse yalnızca o oluşturma denemesinin yeni klasörü temizlenir; önceden var olan klasörlere dokunulmaz. Proje adı hiçbir dosya yoluna dönüştürülmez. SQLite bağlantıları işlemler bittikten sonra kapatılır; Windows'ta gereksiz dosya kilitleri tutulmaz.

## Backend

- `POST /api/projects`: doğrulayıp oluşturur; HTTP 201 ve proje bilgisi döndürür.
- `GET /api/projects`: proje listesi.
- `GET /api/projects/{id}`: tüm tercihler ve dokuz aşamanın güncel durumu.
- `PATCH /api/projects/{id}`: güvenli proje metaverisini doğrulayarak günceller; `updated_at` değişir, `created_at` korunur. Kimlik, durum ve anahtar güncellenemez.
- `DELETE /api/projects/{id}`: yalnızca `{"confirm": true}` gövdesiyle siler.

Değişiklik isteklerinde `X-AI-Video-Studio: projects` başlığı gerekir. Aynı köken ve yerel Host koruması Ayarlar ile birlikte uygulanır. Yanıtlar önbelleğe alınmaz; doğrulama hataları Türkçedir ve gönderilen gizli değerleri geri yansıtmaz.

Uçtan uca senaryo ve Gemini/Ollama/OpenAI üretim adaptörleri Aşama 4'te eklendi. Stok medya, AI33, FFmpeg render, altyazı üretimi ve YouTube yükleme **uygulanmadı**. **Aşama 5 başlatılmadı.**
