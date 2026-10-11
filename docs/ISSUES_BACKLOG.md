# Not edilen hatalar (6. aşamada düzeltilecek)

Her aşamada karşılaşılan, o aşamaya ait olmayan hatalar burada tutulur. Hiçbiri sessizce bırakılmaz; 6. aşamada düzeltilir ve buradan “Düzeltildi” olarak işaretlenir.

| # | Bulunduğu aşama | Hata | Etki | Durum |
|---|---|---|---|---|
| 1 | 1 (AI33) | FFmpeg 7'den eski sürümlerde render, `-/filter_complex` sözdizimi desteklenmediği için “FFmpeg işlemi başarısız oldu; hata türü belirlenemedi.” diye düşüyor. Ön kontrol FFmpeg sürümünü denetlemiyor. | Eski FFmpeg'li bilgisayarda anlaşılmaz hata. Sahibinin FFmpeg 9.0.2'si etkilenmez. | Açık |
| 2 | 1 (AI33) | Önceki PR'da birleştirme, son iki commit gönderilmeden yapıldı; güncelleme eksik kaldı (PR #32 ile giderildi). Süreç notu: her aşama sonunda “PR'a başka commit gelmeyecek” diye açıkça bildirilecek. | Süreç | Önlem alındı |
