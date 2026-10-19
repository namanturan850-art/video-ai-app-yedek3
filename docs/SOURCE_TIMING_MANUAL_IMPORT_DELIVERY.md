# Kaynak zamanlaması ve büyük Manuel Plan içe aktarma — teslim

Temel: güncel `main` / `b74e902`, PR #102 ve #103 korunarak `fix/source-timing-manual-import` dalında çalışıldı. Yeni editör veya menü eklenmedi. Yedi iz, oynatma kontrollerinin yeri, animasyon motoru, AI paketi ve mevcut onay akışı korundu.

## Bulunan nedenler ve düzeltmeler

1. **Video süresi ile dosya süresi farklı olabilir.** Eski kod bazı yerlerde dosyanın toplam süresini kullanıyordu; daha uzun ses akışı veya gecikmeli video başlangıcı bu süreyi büyütebiliyor. Proxy kısa kaynağı döngüye alırken final başka bir başlangıç hesabı yapıyordu. Yeni ortak `source_timing` yordamı gerçek görüntü akışını, başlangıç PTS farkını, `clip_start`, `clip_end`, hızı ve 30 FPS timeline süresini denetler. Video için başlangıç zamanı görüntünün ilk karesine göre hesaplanır. Normal hızda da PTS, FPS/trim işleminden önce sıfırlanır. Yeni yerel video yüklemeleri görüntü akışının süresini kaydeder; eski metadata yerinde değiştirilmez. MP4 başlığı son örneğin süresini eksik bildiriyorsa yalnız açık kare sayısı/FPS ile kanıtlanan tek karelik fark düzeltilir; dosyanın uzun sesinden görüntü süresi türetilmez.
2. **Yetersiz kesit başarılı sayılmaz.** Ana klipte 3 saniyelik kaynak / 6 saniyelik timeline otomatik döngüye alınmaz, birkaç saniyelik siyah veya donmuş görüntüyle gizlenmez. Sahne, saniye, gerçek kaynak/kesit, hız ve gereken süre bildirilir. Kullanıcı kesiti/timeline süresini kısaltabilir, hızı azaltabilir veya yeterli kaynak seçebilir. Bunların hiçbiri kendiliğinden uygulanmaz. Yalnız doğrulanmış tam kesitte, kodek/FPS hizalaması için yaklaşık bir karelik EOF toleransı vardır. Gerçek video süresi doğrulanamıyorsa FFprobe gereksinimi açıkça bildirilir.
3. **Birleştirme ve geçişlerin kare sınırı eşitlendi.** Birleştirme filtresinin mikrosaniye saati, 30 FPS katman saatiyle bazı karelerde önceki görüntüyü seçiyordu; 2× hız testi bu bir karelik geriliği yakaladı. Birleşmiş taban artık katmanlardan önce tam 30 FPS kare saatine bağlanır; final ana klip ayarları ve önizleme kaynak sesi de aynı yuvarlanmış kesim sınırlarını kullanır. Proxy'nin yuvarlanmamış sahne sınırı ve siyaha geçişte YUV siyah seviyesini sıfır sayması finalden farklı sonuç üretiyordu. Proxy ve örnek kare, finaldeki 30 FPS sınırını ve sınırlı YUV siyah seviyesi 16'yı kullanır. `clip_end` geçiş için kullanılabilecek kaynak ek süresine de sınır koyar. Crossfade, wipe ve yalnız seçilmiş dip-black gerçek final MP4 ile karşılaştırıldı. Yeni geçişlerin taslak ve onay doğrulaması da dosyadan okunan gerçek görüntü payını kullanır; eski uzun dosya/ses metadata değeriyle geçiş onaylanamaz. Yeni gerçek dosya süresi/pay denetimi ilgili geçiş önerilerinin kaynaklarıyla sınırlıdır. Manuel projeye yeni otomatik siyaha geçiş eklenmez.
4. **Hata, sesin tek başına ilerlemesini başlatmaz.** Kaynak hatası, proxy üretim hatası veya ağ/zaman aşımı halinde sürekli oynatıcı saati ve ses bekletilir. Bu hatalar otomatik olarak eski oynatıcıya geçip anlatımı görüntüsüz ilerletemez. Açıklanan codec/MediaSource desteği eksikliğinde önceki destek yolu korunur. JPEG/proxy kimlikleri ve render parmak izi güncellendi; eski çıktılar ve kullanıcı medyası silinmedi.
5. **20 saniye hatasının iş yükü giderildi.** Eski içe aktarma her öneride giderek büyüyen planı tekrar derliyordu; tek HTTP isteği tarayıcının 20 saniyelik sınırına takılabiliyordu. Geçerli paket artık tek toplu doğrulamadan geçer. Hatalı öneri varsa mevcut kayıpsız, tek tek ayırma yolu korunur. Arayüz kısa bir `202` isteğiyle yerel işi başlatır, durumunu sorgular ve mevcut mesaj alanında aşama/sayı gösterir. Sadece timeout artırılmadı.
6. **İçe aktarma işi sınırlı ve kalıcıdır.** Tek çalışan iş, en fazla iki aktif/kuyruktaki iş; aynı projenin aynı devam eden isteği tekrar iş başlatmaz. En fazla 2.000.000 karakter, dosya yükleme alanında 8 MB sınırı vardır. Mevcut 30 parça/500 öneri ve belge kapasitesi sınırları korunur; sınırsız plan desteği iddia edilmez. İş durumu mevcut cache tablosuna, taslak mevcut taslak tablosuna kaydedilir; şema göçü yok. Yeniden başlatılmış uygulama yarım işi tamamlandı diye göstermez. Geçersiz JSON/kayıt ve çakışmalar açıkça raporlanır; geçerli öneriler korunur. Uygulama yalnız mevcut seçme/onay adımıyla yapılır.

## Doğrulama

- **85 render testi geçti** (105,73 sn). Ortak pozitif test kaynağı artık yeterli uzunlukta; kısa kaynak için eski otomatik döngü beklentileri açık hata ve kaynakların korunması beklentisine çevrildi. Kısa kaynağı başarılı sayan test bırakılmadı.
- İlk **157 testlik** geniş kontrolde **156 geçti, bir crossfade kare hizası farkı bulundu**. Fark düzeltildi. Son **36 etkilenen regresyon testi geçti** (305,83 sn): gerçek kaynak süreleri/kesitleri, iki önizleme çözünürlüğü ve final, üç geçiş, ses önbelleği, büyük JSON işleri, eski oynatma testleri ve kısa kaynakların reddi.
- Gerçek kaynak payının taslakta kullanılması ve geçerli önerilerin kaybolmadan yalnız onayla uygulanması için **47 test daha geçti** (227,67 sn). Bunlar mevcut geçiş/Manuel Plan regresyonlarını ve yanıltıcı uzun ses metadata senaryosunu içerir.
- Son kare saati düzeltmesiyle **21 test geçti** (280,47 sn): 0,5×/2× hızda bütün karelerin proxy/final eşleşmesi, farklı ana klip konumlarının kesimin ilk/son karesine aynı uygulanması, gerçek kaynak/taslak geçiş payı, üç geçiş, ses miks durumu ve büyük JSON işleri.
- Sessiz video kaynakları anlatım miksinin gereksiz dosya/süre çözümlemesine katılmaz. Kaybolmuş bir sessiz videonun yalnız anlatım hazırlığını engellememesi ve ses açıldığında hatanın gizlenmemesi dahil **dört ses testi geçti** (11,36 sn).
- **86 Node testi geçti.** Yeni kontroller, kaynak veya ağ hatasının anlatım saatini serbest bırakmadığını doğrular.
- Son ek kontrolde **üç test daha geçti** (79,21 sn): 720p/1080p önizleme ile finalin bütün karelerinde istenmeyen siyah kontrolü ve içe aktarılan video kesitinde kaynakların korunması. Yeni yerel yüklemenin daha uzun ses yerine görüntü süresini kaydetmesi de ayrıca gerçek MP4 ile geçti (4,85 sn).
- Gerçek kaynaklar: farklı uzunlukta, 25/30 FPS hareketli MP4'ler; ilk videoda iki saniyelik başlangıç PTS farkı ve videodan uzun ses. `clip_start` 0,2/1 saniye ve ayrı `clip_end` değerleriyle önizleme/final kareleri karşılaştırıldı. Kliplerin başı/sonu ve parça sınırları denetlendi. 3 saniyelik gerçek dosyanın 6 saniyeyi karşılayamaması, yanıltıcı metadata ile örnek kare/proxy/final yollarında sınandı.
- Gerçek Chromium'da **352.841 karakter, 150 önerilik JSON dosyası** yüklendi. Arka plan işi/durum sorgusu, yalnız taslak aşaması, gerçek JPEG önizleme, 149 önerinin seçiminin kaldırılması ve yalnız bir önerinin açık onayla kaydı geçti. Kurgu onaydan önce değişmedi; medya/seslendirme/altyazı izleri korundu. Tarayıcı hatası yok. Akış 21,6 saniye sürdü; bu süre yalnız doğrulama süresi değil, arayüzde seçim/önizleme/onay işlemlerini de içerir.
- Yavaş doğrulama ayrı testte bilerek bekletildi; iş başlatma, durum sorgusu ve sağlık isteği açık kaldı. Geçerli 150 kayıt için derleyicinin yalnız bir kez çağrıldığı doğrulandı.
- Python/JavaScript sözdizimi, Windows workflow YAML yüklemesi ve `git diff --check` geçti. Bağımlılık deprecation uyarıları hata sayılmadı; sonuçlarda gizlenmedi.

Gerçek tarayıcıda soğuk önbellek, iki farklı video ve beş eşzamanlı ek katman:

| Ölçüm | 720p / 12 sn | 1080p / 12 sn |
| --- | ---: | ---: |
| Gösterim FPS ölçümü | 29,877 | 29,918 |
| Parça sınırında en uzun kare aralığı | 33,4 ms | 33,3 ms |
| Başlatma dahil en uzun kare aralığı | 99,9 ms | 83,3 ms |
| Oynatma içinde tampon beklemesi | Yok | Yok |
| İlk duraklatılmış proxy hazırlığı | 9,25 sn | 17,67 sn |
| Oynat sonrası ileri tampon hazırlığı | 15,26 sn | 22,18 sn |
| Tarayıcı hatası | 0 | 0 |

[720p ham sonuç](examples/source_timing_real720.json) · [1080p ham sonuç](examples/source_timing_real1080.json) · [Büyük JSON arayüz sonucu](examples/manual_import_large_job.json).

## Sınırlar

Testler geçici yerel projeler, üretilmiş hareketli video dosyaları ve gerçek FFmpeg/Chromium ile yapıldı; kullanıcının orijinal projesi veya saatler süren gerçek çekimleri çalıştırılmış değildir. Kaynağın kendisinde bulunan bilerek çekilmiş siyah kareler otomatik silinmez. İstenerek boş bırakılmış yuvalar korunur. İlk proxy ve ileri tampon hazırlığı anlık değildir; ölçümler yukarıda ayrı verildi. Yaklaşık 30 FPS ölçümü, her donanımda sınırsız katman/çözünürlük garantisi değildir.

Bu ortam Linux'tur. **Gerçek Windows ve GPU testi yapılmadı.** Mevcut Windows işine yeni Python/ön yüz testleri, gerçek videolarla 720p/1080p ve büyük dosya/onay tarayıcı adımları eklendi; yapılandırmanın hazırlanması çalıştırılmış Windows sonucu değildir. Canlı/ücretli Gemini çağrısı, uzun kullanıcı renderı veya kullanıcı verilerinde silme yapılmadı. Bu görevde `main`e merge yapılmadı.
