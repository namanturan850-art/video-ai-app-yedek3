# Kalite ve uzun video kontrolleri

Bu geliştirme `improve/video-quality-performance` dalındadır. Ana dala gönderilmedi. Mevcut projeler üzerinde toplu dönüştürme veya canlı servis denemesi yapılmadı.

## Neler değişti?

| Sorun | Kodda bulunan neden | Uygulanan değişiklik |
| --- | --- | --- |
| Alakasız medya | Bir sahnenin farklı cümleleri aynı görsel onayını paylaşabiliyor; genişletilmiş sorgular ve gevşetilmiş dönem/yer filtresi yanlış adayı geçirebiliyordu. | Her yuva kendi anlatım cümlesiyle değerlendirilir. Onay önbelleği cümle sırası, kişi/yer ve kısıtları içerir. Otomatik gevşetme kaldırıldı; uygun stok yoksa mevcut motion/kart akışı kullanılır. |
| Kesilen yazılar | Karakter sayısına göre kesme, satırları atma ve CSS ellipsis kullanılıyordu. Alt bant altyazıya çok yakındı. | Paylaşılan piksel ölçümüyle satır kırma ve yazı boyutu hesaplanır. Tam metin gösterilir; alt bant yukarı taşınır. Kaynak senaryo ve SRT metni değiştirilmez. |
| Karışık görüntü kalitesi | Portre kaynaklar bulanık arka planla kabul edilebiliyor, gerçek indirilen dosyanın netliği kontrol edilmiyordu. | Yeni otomatik videolarda yatay oran ve en az 720p aranır; indirilen dosyanın gerçek boyutu, süresi ve örnek kareleri kontrol edilir. Fotoğraflarda kaliteli 3:2 yatay kaynak da korunur. |
| Çok uzun hazırlık | Tekrarlanan model başlatma, kare/metin kodlama, sorgu yeniden yazma, seri sağlayıcı araması ve aynı kararları yeniden hesaplama vardı. | Kalıcı CLIP işçisi, sınırlı embedding önbelleği, paylaşılan karar önbelleği, iki işçili arama ve önce yerel sorgu üretimi eklendi. Yeni adayların ücretli görsel değerlendirmesi cümle/koşul başına bir grupla sınırlanır; önceden seçili medyanın açık yeniden kontrolü ayrıdır. |

Görsel değerlendirme bütçesinin dolması görsel onay sayılmaz. CLIP/önbellekten doğrulanamayan ek adaylar bu nedenle otomatik kabul edilmez. Yapay zekâ kapalıyken mevcut etiket tabanlı yerel mod kalır ve görsel doğrulama iddia etmez.

Görsel istek sınırı cümle, sahne ve koşullar birlikte değerlendirilerek uygulanır. Farklı sahnelerde geçen aynı cümle tüm film boyunca tek bir aday grubuna mahkûm edilmez. Pozitif bulut yanıtının da cümlenin konusunu destekleyen kaynak etiketleri olması gerekir. Bu ihtiyatlı seçim, yeterli ilgili kaynak olmayan konularda daha çok motion üretebilir; yüzdeyi düşürmek için filtreler gevşetilmez.

Açık yıl sözcüğü taşıyan 1–999 tarihleri de dönem denetimine katılır; kişi/mesafe sayıları yıl sayılmaz. Kullanıcının cümleye bağlı `[GÖRSEL]` notu otomatik sorguya göre önceliklidir.

İlgili kodlar: `app/stock/shot.py`, `director_media.py`, `quality.py`, `verdict_cache.py`, `clip_check.py`; `app/integrations/openmontage/frames_process.py`, `visual_engine.py`; `app/text_layout.py`, `app/rendering/ass.py`, `app/motion/templates*.py`.

## Kullanım ve korunan kayıtlar

1. Senaryonuzu mevcut yönteminizle ekleyin; otomatik senaryo üretimini açmanız gerekmez.
2. Medya ekranındaki kullanıcı kilitleri ve mevcut dosyalar korunur. Eski/dikey manuel seçimler için kalite uyarısı gösterilebilir; otomatik silinmezler.
3. Eksikleri tamamlama/devam işlemi, aynı cümleye ait geçerli tamamlanmış yerel seçimi yeniden kullanır. Metin veya kalite koşulu değiştiğinde ilgili onay yeniden gerekir.
4. Render öncesi eksik kaynak ve açık kalite reddi kontrol edilir. 10 dakika ve üzeri yeni çıktılar aktif yapılmadan önce tüm ses/görüntü akışı çözülerek denetlenir. Bu kontrol çıktı büyüklüğüne göre ek süre kullanır.
5. İlerlemeyen alt işlemler süre sınırıyla durdurulur; kaynaklar korunur. Bu, kesilmiş renderın aynı kareden devam edeceği anlamına gelmez: mevcut medya/motion önbelleği kullanılır, çıktı yeniden hazırlanabilir.

OpenMontage ve FFmpeg motor seçimi korunur. Pixabay, Wikimedia, motion, elle senaryo hazırlama ve eski kayıt biçimleri korunur. Avatar, Pexels ve otomatik senaryo üretimi yeniden açılmadı.

## Doğrulama sınırları

- Sentetik kaynaklarla gerçek FFmpeg kullanılarak 15 dakika, 1920×1080, 30 fps çıktı üretildi; süre, kare sayısı, son kare ve tam ses/görüntü çözümlemesi doğrulandı. Bu test gerçek 338 farklı medya seçimini veya içerik kalitesini temsil etmez.
- 338 cümle/900 saniye zaman çizelgesi ve metin korunumu; gerçek net/bulanık/portre dosyaları; önbellek, paralellik, iptal ve takılan süreç kontrolleri yerel testlerle kapsanır.
- Canlı Pixabay/Wikimedia/ücretli servisler çağrılmadı. Gerçek CLIP modeli ve Remotion tarayıcı çizimi bu ortamda doğrulanmadı; Windows testi yapılmadı.
- Zamanlama mevcut yaklaşık konuşma zamanlamasına dayanır; kesin kelime hizalaması değildir. CLIP tarih, kimlik veya olay doğruluğunun kanıtı değildir.
- Bulanıklık ölçümü örnek karelerden elde edilen bir sezgiseldir; her sahne için kusursuz sınıflandırma garantisi yoktur. Çok uzun metin en küçük güvenli boyutta da sığmıyorsa sessizce kesilmek yerine açıklayıcı hata üretilir.
- Gerçek 338 işlemin önceki 2–2,5 saatlik çalışmasının ölçüm kaydı bulunmadığından yüzde hızlanma iddia edilmez. Yeni tanılama kayıtlarındaki `timings` alanı arama, değerlendirme, CLIP, indirme/kalite ve motion sürelerini ayırır; iç içe süreler toplanarak toplam süre hesaplanmamalıdır.

Gerçek bir proje üzerinde canlı sağlayıcı ve ücretli deneme yapılması için ayrıca kullanıcı onayı gerekir. İlk deneme mevcut projelerin kopyasında yapılmalıdır.
