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
- **Yönetmen** (kurgu planı) her sahne için stok mu motion mı karar verir; hedef %60 stok, %40 motion; az planlanırsa uygulama aralıklı motion ekleyip %40’a tamamlar (rakam, tarih, yer, liste, karşılaştırma, önemli cümle).
- **Medyayı Tamamla**: planlanmış motion sahneleri doğrudan çizilir. Zincirin son basamağı artık basit kart değil, anlatımdan seçilen motion şablonudur (dış servise bağlı değildir, başarısız olmaz).
- Medya ekranında her yuvada: **Yeniden seçtir**, **Motion’a çevir** / **Stok videoyla değiştir**, motion önizlemesi ve **Motion metnini düzenle**.

## Zamanlama ve ses
Animasyonun vurgu anı, vurgu kelimesinin seslendirmede söylendiği ana oturtulur (render sırasında altyazı zamanlarından yeniden hesaplanır; klip gerekirse yeniden çizilir). Vurgu anında kitin ses efekti (yükseliş/darbe/tık) **seslendirmenin altına**, düşük ve sabit seviyede eklenir; seslendirme kısılmaz.

## Render
1. **OpenMontage (Remotion)** kurulu ve hazırsa motion sahneleri onunla çizilir (`app/motion/motion.tsx`).
2. Yoksa veya hata verirse **yerel yedek**: Pillow ile kare kare çizim + FFmpeg kodlama (`app/motion/raster.py`). Ek bir program gerekmez.

İki yöntem aynı sahne tanımından çizer; testlerde aynı kare karşılaştırılır. Motion klipler kurguya normal video klip olarak girer.
