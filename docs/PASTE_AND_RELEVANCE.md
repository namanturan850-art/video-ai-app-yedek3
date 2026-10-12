# Metni yapıştır ve medya alakası

## Akış
Yeni proje (başlık, dil) → **Metni yapıştır** → Seslendirme → Altyazı → Sahne planı → Medyayı Tamamla → Video → YouTube.

- **Yapay zekâyla senaryo yazımı kapalı.** Kod duruyor; varsayılan kapalı bir bayrakla gizlenir: `general.script_generation`.
  - Geliştirici açmak isterse `AVS_SCRIPT_GENERATION=1` ortam değişkenini kullanır.
  - Bayrak kapalıyken senaryo üretimi, AI Yönetmen'in amaç/senaryo adımları, senaryo motoru seçimi ve kaynak video analizi ekranda görünmez.
- **Yapıştırılan metin temizlenir:**
  - Markdown işaretleri, başlık satırları ve “1.”, “Kapitel 2” gibi numara kalıntıları atılır.
  - Fazla boşluklar birleştirilir.
  - Kaydedilen metin yeni ve onaylı bir senaryo sürümü olur. Eski sürümler durur ve “Bu sürümü kullan” ile geri seçilebilir.
- **Tahmini süre** dilin ölçülmüş konuşma hızıyla hesaplanır (Almanca ~130 kelime/dk; 385 kelime ≈ 2:58).

## İşaretler
| İşaret | Etkisi |
|---|---|
| `[GÖRSEL: airplane cockpit at night]` | O cümlenin sahnesinde ilk arama sorgusu ve “mutlaka görünmeli” notu olur. |
| `[HARİTA: Bermuda Triangle]` | Görsel ipucu olarak saklanır ve “… map” araması eklenir (ileride motion şablonu). |
| `[SAYI: %40]` | Görsel ipucu olarak saklanır (ileride motion şablonu). |

- **Hangi cümleye bağlanır?**
  - Bir cümlenin hemen arkasına yazılan işaret o cümleye aittir.
  - Paragraf başındaki işaret, sonraki cümleye aittir.
- **Seslendirme ve altyazı** işaretleri asla görmez.
- **Tanınmayan işaret** uyarı verir ve yine okunmaz.
- **Metin kutusunda** bilinen işaretler mavi, tanınmayanlar kırmızı görünür.

## Sahne planı
- **Kaynak:** Plan yapıştırılan metinden üretilir. Gemini varsayılandır; Claude yalnız ayardan ücretli olarak seçilirse kullanılır. Metnin kelimeleri değişmez; uygulama yalnız böler ve planlar.
- **Her sahne için üretilenler:**
  - somut İngilizce görsel tarif: nesne, yer, eylem, dönem, ortam, gündüz/gece. Soyut kavram görsele çevrilir.
  - “kesinlikle görünmemeli” listesi;
  - 3 kademeli sorgu: çok spesifik → orta → genel;
  - özel isimler.
- **Bağlam:** Önceki ve sonraki cümle ile videonun konusu da değerlendirilir.

## Medya seçimi
- **Ön eleme:** Pexels/Pixabay sonuçları önce metadata ile elenir:
  - sizin reddettikleriniz,
  - filigran veya logo izi,
  - “görünmemeli” listesindeki şeyler.
- **Değerlendirme:**
  - İlk sayfa zayıfsa 2. sayfa da taranır; arama sonuçları önbellekte tutulur.
  - Gemini'ye yuva başına en fazla 6 aday gider.
  - Video adaylarından başlangıç/orta/son olmak üzere 3 kare gönderilir. Pixabay tek önizleme verdiği için bu kareler küçük sürümünden geçici olarak çıkarılır.
- **Puanlama:** Gemini 0–10 puan verir ve tek cümlelik gerekçe yazar. Ölçütler:
  1. anlatılanı gösteriyor mu;
  2. dönem ve ortam uyuyor mu;
  3. “görünmemeli” listesinden bir şey var mı;
  4. yazı, filigran veya logo var mı;
  5. kalite.
- **Eşik 7:**
  - 7'nin altındaki stok medya hiçbir yolla kullanılmaz.
  - Kademede eşiği geçen aday yoksa sonraki sorgu kademesine geçilir.
  - Hiçbiri geçmezse zincir şöyle sürer: görsel → geniş konu → motion grafik.
- **Sahne içi uyum:**
  - Aynı sahnede önceki çekimin renk tonuna yakın adaylar tercih edilir.
  - Önceki çekimle neredeyse aynı kadraj elenir. Bu kontrol, gökyüzü ya da deniz gibi dokusuz karelere uygulanmaz.
- **“Yeniden seçtir”:**
  - Reddettiğiniz medya bu projede bir daha önerilmez.
  - Yazdığınız neden, sonraki seçimde yapay zekâya söylenir.
- **Ekranda:**
  - Her yuvada alaka puanı ve gerekçe görünür.
  - 7–8 puanlı yuvalar sarı kenarlıkla işaretlenir.
  - Özette ortalama alaka puanı yazar.
