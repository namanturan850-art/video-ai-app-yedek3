# Kaynak video analizi ve YouTube kartı

## Ne yapar?
Projede bir **Referans YouTube linki** (ve isteğe bağlı **Transkript**) verirseniz “Kaynak analizi” kartında **Kaynağı analiz et** düğmesi şunları yapar:

1. **YouTube Data API v3** (anahtarınız varsa): başlık, açıklama, etiketler, süre, izlenme / beğeni / yorum sayıları ve yorumlar.
   - API “beğeniye göre sırala” seçeneği sunmaz. Bu yüzden en alakalı 100 yorum okunur, beğeniye göre sıralanır ve ilk 50'si kullanılır.
   - Anahtar yoksa bu kısım atlanır ve kısa bir uyarı gösterilir.
2. **İçerik**: Transkript yapıştırdıysanız o kullanılır. Yoksa Gemini **herkese açık linki** okur; video indirilmez.
   - Gemini linki okuyamazsa “Transkripti yapıştırın” uyarısı çıkar.
3. **Kart** iki bölüm gösterir:
   - *Neden tuttu?*: sayılar, başlık stratejisi, izleyici tepkisi.
   - *Ne anlatıyor?*: konu, bölüm sırası, açılış kancası, tempo, ton, kapanış, bilgiler (şüpheliler ⚠ ile) ve izleyici soruları.

Link de transkript de yoksa: “Kaynak video yok, senaryo sadece başlıktan üretilecek.”

## Senaryoya etkisi (özgünlük)
Yönetmen ve Senaryo ekranı analizi otomatik kullanır. Senaryo yazarına **transkript veya kaynak cümleleri verilmez**; yalnız soyut analiz verilir:
- yapı ve kanca tipi,
- bilgiler (şüpheli olanlar “kesin bilgi gibi sunma” notuyla),
- izleyici soruları,
- ton ve tempo.

Talimat açıktır: “uyarla, çevirme; yeni cümleler, hedef kitleye uygun yeni örnekler, aynı tipte kendi kapanışın”. Bu, AGENTS.md'deki özgünlük kuralına uygundur.

## Belgelenmiş API'ler
Kontrol tarihi 2026-10-11. Sayfalar bu ortamdan doğrudan açılamadı; resmî alan adlarına sınırlı arama sonuçlarıyla doğrulandı.

**Gemini, YouTube URL** ([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)):
- İstek biçimi: `generateContent` içinde ayrı bir parça, `{"file_data": {"file_uri": "https://www.youtube.com/watch?v=…"}}`.
- Durum: önizleme (preview), yalnız herkese açık videolar.
- Ücretsiz katmanda günde en fazla 8 saat YouTube videosu işlenebilir.
- Okuyamama hatası belgelenmemiş; her hata durumunda transkript istenir.

**YouTube Data API v3**:
- [videos.list](https://developers.google.com/youtube/v3/docs/videos/list): `part=snippet,statistics,contentDetails`. 1 kota birimi; sayılar metin olarak gelir.
- [commentThreads.list](https://developers.google.com/youtube/v3/docs/commentThreads/list):
  - Parametreler: `order=relevance`, `maxResults=100`, `textFormat=plainText`. 1 kota birimi.
  - Yorum metni `textDisplay` alanından okunur; `textOriginal` yalnız yorumu yazana görünür.
- Hatalar: `keyInvalid` (400), `quotaExceeded` (403), `commentsDisabled` (403), `videoNotFound` (404).

## YouTube kartı kuralları
- **Kapak üretimi kaldırıldı.** Kartta yalnız başlık, açıklama ve etiketler var.
- **Başlık en fazla 97 karakter** (boşluk ve emoji dahil).
  - Uzunluğu kod sayar. Aşan başlık yapay zekâya kısalttırılır.
  - Son çare olarak başlık tam bir kelimede biter; kelime ortadan kesilmez.
- **Etiketler toplam en fazla 500 karakter**, YouTube'un saydığı gibi: virgüller sayılır, boşluk içeren etiket +2 sayılır.
  - Aşarsa sondaki (en zayıf) etiketler çıkarılır.
  - `#` hiç kullanılmaz. Hashtag'ler açıklamadadır.
- **Son kontrol**: “Yayına hazır” gösterilmeden önce yapay zekâ başlıkları, kancayı, özeti, bölüm adlarını ve etiketleri anlam ve dil hatasına karşı kontrol eder ve düzeltir.
  - Elle değişiklik yaparsanız kontrol yenilenmeli (“Dil kontrolünü yap”).
