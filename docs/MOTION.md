# Motion grafikler (Aşama 2)

Stokta bulunamayan veya bilgi anlatan sahneler için kanalın **Tarzım** kitiyle (renk, font, hareket süresi/eğrisi, ses efektleri) çizilen animasyonlu sahneler.

## Şablonlar (serbest kod yok)
Yapay zekâ yalnızca alanları doldurur; uygulama doğrular. **Sayı, tarih, yer ve alıntılar o sahnenin anlatımında geçmek zorundadır** — geçmiyorsa şablon kullanılmaz (uydurma bilgi yok).

| Şablon | Alanlar | Vurgu anı |
|---|---|---|
| Büyüyen sayı | sayı (ör. 1945, %40), kısa açıklama | sayı tam değere ulaşır, darbe sesi |
| Harita + işaret | yer adı, enlem/boylam, etiket | dünyadan bölgeye yakınlaşma, iğne düşer |
| Başlık / alıntı | anlatımdan birebir ifade | vurgu kelimesi vurgu renginde belirir |
| Zaman çizelgesi | 2–5 tarih + açıklama | çizgi ilerler, vurgu tarihi büyür |
| Karşılaştırma | 2 öğe (karşı karşıya) veya 2–5 sayılı çubuk | çubuk/taraf vurgulanır |
| Madde listesi | 2–4 madde | maddeler sırayla belirir |

Harita verisi: Natural Earth 1:110m kara poligonları (kamu malı).

## Nerede kullanılır?
- **Yönetmen** (kurgu planı) motion grafiği yalnız sayı, tarih, yer, liste veya karşılaştırma geçen sahnelerde ister: en fazla ~%20 (en az %80 stok video). Yazı kartı (alıntı) son seçenektir.
- **Metindeki işaretler** (`[HARİTA]`, `[SAYI]`, `[ÇİZELGE]`, `[KARŞILAŞTIR]`, `[LİSTE]`) doğrudan ilgili şablonu üretir.
- **Dokuz işaret şablonu** (`app/motion/templates_extra.py`): `[ROTA]`, `[İMPARATORLUK]`, `[YAKINLAŞ]`, `[İŞARETLE]`, `[ÖNCESONRA]`, `[İKON]`, `[ORAN]`, `[HANEDAN]`, `[BİLGİ]`. Hepsi Tarzım renk/yazı tipleriyle **yerel çizimle** (Pillow + FFmpeg) üretilir; OpenMontage kullanılmaz. Ayrıntı: [PASTE_AND_RELEVANCE.md](PASTE_AND_RELEVANCE.md).
- **Medyayı Tamamla**: işaretli ve planlanmış motion sahneleri önce çizilir. Diğer yuvalar motion'a yalnız onaylı stok bulunamazsa düşer; o zaman da önce sayı/harita/çizelge aranır, yazı kartı motion yuvalarının en fazla ~%30'u olur.
- Motion oranı yuvaların %25'ini aşarsa ekranda uyarı çıkar. Eski “%40'a tamamlama” kaldırıldı.
- **Sayılar yazıyla da tanınır**: “neunzehnhundertfünfundvierzig” = 1945, “vierzig Prozent” = %40 (Almanca; İngilizce, İspanyolca, Fransızca ve Türkçe temel düzeyde).
- Medya ekranında her yuvada: **Yeniden seçtir**, **Motion’a çevir** / **Stok videoyla değiştir**, motion önizlemesi ve **Motion metnini düzenle**.

## Zamanlama ve ses
Animasyonun vurgu anı, vurgu kelimesinin seslendirmede söylendiği ana oturtulur (render sırasında altyazı zamanlarından yeniden hesaplanır; klip gerekirse yeniden çizilir). Vurgu anında kitin ses efekti (yükseliş/darbe/tık) **seslendirmenin altına**, düşük ve sabit seviyede eklenir; seslendirme kısılmaz.

## Render
1. **OpenMontage (Remotion)** kurulu ve hazırsa motion sahneleri onunla çizilir (`app/motion/motion.tsx`).
2. Yoksa veya hata verirse **yerel yedek**: Pillow ile kare kare çizim + FFmpeg kodlama (`app/motion/raster.py`). Ek bir program gerekmez.

İki yöntem aynı sahne tanımından çizer; testlerde aynı kare karşılaştırılır. Motion klipler kurguya normal video klip olarak girer.
