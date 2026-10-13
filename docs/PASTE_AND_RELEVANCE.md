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
| `[HARİTA: Bermuda Triangle]` | O cümle söylenirken **harita** infografiği (iğne yerin üstünde). Konum uygulamanın yer listesinden, yoksa yapay zekâdan alınır. |
| `[SAYI: %40]` | **Büyüyen sayı** infografiği. Yazıyla yazılmış sayı da olur: `[SAYI: vierzig Prozent]`. |
| `[ÇİZELGE: 1945, 1962, 1991]` | **Zaman çizelgesi** (2–5 tarih). `1945 Flug 19; 1962 Tanker` gibi açıklama da eklenebilir. |
| `[KARŞILAŞTIR: Rom \| Karthago]` | **Karşılaştırma** (A ile B). Sayı da verilebilir: `Rom: 1000000 \| Karthago: 400000` → çubuk grafik. |
| `[LİSTE: Stürme; Strömungen; Fehler]` | **Madde listesi** (2–4 madde). |
| `[ROTA: Ninive > Babil > Kudüs]` | Haritada **rota**: çizgi yerden yere çizilir, durakların adı çıkar (2–6 yer). |
| `[İMPARATORLUK: Assyrien 911-612 v. Chr.]` | **Zamanla büyüyen sınır** ve akan yıl. Bilinen imparatorluklarda (Roma, Osmanlı, Asur, Babil, Pers, Bizans, Moğol, Hitit, Mısır, Makedonya) sınır yerleri hazırdır; diğerlerinde yerleri siz yazın: `[İMPARATORLUK: Urartu 860-590 | Tuşpa, Erzurum, Urmiye]`. Sınır yaklaşıktır ve ekranda öyle yazar. |
| `[YAKINLAŞ: Babil]` | **Dünyadan yere yakınlaşma**: dünya → ülke → yer; çevredeki bilinen yerler de görünür. |
| `[İŞARETLE: Tapınağın sütunları]` | Sahnenin **görselinde yavaş yakınlaşma + daire + ok + etiket**. Görsel, nota uygun stok fotoğraf olarak bulunur; daire konumunu Medya ekranında “Odak noktası” ile düzeltebilirsiniz. |
| `[ÖNCESONRA: Antik liman \| Bugünkü kıyı]` | İki görsel arasında **kayan perde** (“Önce / Sonra”). |
| `[İKON: 10000 asker]` | **Çoğalan ikonlar + sayaç** (asker, insan, gemi, ev, bina, para, ağaç, hayvan, kitap, gezegen). Büyük sayılarda “1 ikon = 500” gibi açıklama çıkar. |
| `[ORAN: %40 nüfus kıyıda]` | **Pasta grafik** ve yüzde. |
| `[HANEDAN: Davud > Süleyman > Rehavam, Yeroboam]` | **Hanedan ağacı**: “>” yeni kuşak, “,” kardeşler. |
| `[BİLGİ: Babil surları iki araba genişliğindeydi.]` | **“Biliyor muydunuz?” kartı.** |
| `[GİRİŞ]` veya `[GİRİŞ: Özel başlık]` | **Açılış animasyonu** (3–5 sn): video başlığı + kanal adı, kanalın Tarzım renk/fontuyla. Yazılmazsa başlık proje adıdır. |
| `[KAPANIŞ]` | **Kapanış:** “Abone ol” düğmesi basılır → “Abone olundu” → zil çalar. Ardından videonun sonuna **20 sn YouTube bitiş ekranı** eklenir (sade arka plan, ortası boş). Yalnız videonun **sonunda** çalışır; ortaya yazarsanız yok sayılır. |

- İnfografik işaretleri Medyayı Tamamla'da **önce** çizilir; yapay zekâ gerekmez.
- **Yerler** uygulamayla gelen çevrimdışı listeden bulunur (ülkeler, 15 000+ nüfuslu şehirler, bölgeler, denizler, önemli antik yerler; antik ↔ bugünkü adlar: Kudüs/Jerusalem/Hierosolyma, Byzanz/İstanbul, Ninova/Ninive). Bulunamayan yer **uyarıyla** bildirilir, tahmin edilmez.
- **Öneri:** işaret yoksa sahne planı sayı, tarih, yer veya rota geçen cümleler için uygun infografiği kendisi önerir (en fazla sahnelerin %25'i). Medya ekranında “Öneriyi onayla” deyin, metnini düzenleyin veya “Stok videoyla değiştir” ile vazgeçin.
- Her infografik Medya ekranında **önizlenir**; “Motion metnini düzenle” ile işaret metni değiştirilip yeniden çizilir.
- İşaret adı büyük/küçük harf ve Türkçe harf fark etmez (`[cizelge: …]`, `[Liste: …]`).
- Bir sahnede görüntü yeri kalmazsa işaret en yakın yuvaya gider; hiç yer yoksa ekranda yazılır.

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
- **Arama dili:** stok sitelerine yalnız **İngilizce** sorgu gider. Almanca/Türkçe kelimeler çevrilir veya atılır, yer adları İngilizce adıyla yazılır, sayılar ve “v. Chr.” gibi ifadeler silinir (“Christus Handvoll Stadttor” → “jesus christ city gate”). Çeviri bulunamazsa konuya uygun genel İngilizce sorgular kullanılır.
- **Yerel görüntü modeli (CLIP):** `INSTALL_OPENMONTAGE_SEMANTIC.bat` ile kurulursa, her adayın başlangıç/orta/son kareleri cümleyle ve [GÖRSEL] notunuzla karşılaştırılır. Puan (0–10) Medya ekranında görünür; düşük puanlılar (köpek, ofis, modern şehir…) elenir. İnternet ve kota gerekmez. Kurulu değilse ekranda kurulum önerisi çıkar, iş yine durmaz (etiket/kelime eşleşmesi kullanılır).
- **Gemini görsel kontrolü varsayılan olarak KAPALI.** Ayarlar → Genel'den açılırsa Gemini yalnızca CLIP'in kararsız kaldığı adaylara bakar; 60 sn içinde yanıt gelmezse o bakış atlanır. Gemini artık esas olarak yalnızca sahne planı için kullanılır (video başına birkaç istek).
- **Gemini hiç yanıt vermezse:** işin başında 60 sn içinde cevap yoksa bütün iş yerel modda sürer; görsel isteklerde HTTP zaman aşımı 45 sn; yedek zincirde en fazla 3 model, her biri 1 kez denenir. Ekran hangi modelin denendiğini ve kalan saniyeyi gösterir. Görsel toplu istek “503 sunucu meşgul” verirse küçük bir metin isteğiyle neden kontrol edilir; metin çalışıyorsa adaylar tek tek gönderilir (her istekte en fazla 4 görsel, en fazla 512 px JPEG).
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


## Giriş / kapanış anları (işaretsiz de çalışır)

- Tüm yazılar **videonun dilindedir** (Almanca, İspanyolca, Fransızca, İngilizce, Türkçe).
- İşaret yazmazsanız videonun dilindeki kalıplar otomatik tanınır:
  - Giriş (ilk cümleler): *willkommen / bienvenidos / bienvenue / welcome / hoş geldiniz*
  - Abone ol (son cümleler): *abonniert / suscríbete / abonnez-vous / subscribe / abone ol*
  - Veda (son cümleler): *bis zum nächsten Mal / hasta la próxima / à bientôt / see you next time / görüşmek üzere*
- Tanınan cümle için **stok video aranmaz**; o cümlede ilgili şablon (açılış, abone ol + zil, teşekkür) gösterilir. Cümle yine seslendirilir ve altyazıda görünür; `[GİRİŞ]`/`[KAPANIŞ]` işaretleri ise okunmaz.
- Videonun ortasındaki bir “abone olun” cümlesi animasyon almaz.
- **Yeni dil / yeni kalıp eklemek:** yalnız `app/moments/phrases.py` dosyasındaki `LANGUAGE_DATA` listesine yazın (dosyanın başındaki açıklamaya bakın).
