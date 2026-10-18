# Manuel Plan — kısa kaynak videoda geçiş düzeltmesi

Temel: `fix/manual-plan-interval-import`. Düzeltme dalı: `fix/manual-plan-transition-handles`.

## Kullanıcı akışı

1. Manuel Plan / AI paketi içinden JSON cevabını içe aktarın.
2. Kaynak süresi yetersiz geçişler taslakta **bekleyen sorun** olarak görünür. Mesajda sahne, saniye, iki yuva ve gereken/kullanılabilir ek süre vardır. Süre bilgisi yoksa bilinmediği açıkça belirtilir.
3. Sunulan seçeneklerden birini seçin: sığıyorsa aynı geçişin daha kısa süresi, ek kaynak kuyruğu gerektirmeyen siyaha geçiş veya hard cut.
4. **Yalnız bu geçişin düzeltmesini onayla** düğmesi yalnız o öneriyi taslakta değiştirir; timeline'a henüz yazmaz. Diğer işaretli/işaretsiz öneriler korunur.
5. Taslağı önizleyin. **Seçilen önerileri onayla** ile seçtiklerinizi kurguya kaydedin ve render alın.

Sorunları çözmeden diğer geçerli önerileri uygulamak isterseniz ayrıca uyarı/onay gösterilir. Uygulanmayan geçişler **kayıtlı taslakta beklemeye devam eder**; atılmış gibi gösterilmez. Manuel Plan penceresindeki kayıtlı taslaklardan geri dönülebilir. Sonradan başka manuel düzenleme veya kaynak/kesit/kilit değişikliği olursa eski taslak yerine güncel paket gerekir.

## Teknik düzeltme

- `advanced.py` ve AI aralık derleyicisi aynı kaynak kuyruğu hesabını kullanır. Video süresi, kaynak başlangıcı, oynatma hızı ve native render'ın 30 fps kare saati dikkate alınır.
- Komşu kliplerin dörtte biri sınırı ve en az iki kare korunur. Güvenli süre aşağı doğru tam kareye indirilerek hesaplanır; uygulanabilir daha kısa süre açık onay için önerilir. Başta üretilen normal geçiş süresi de kareye uygundur.
- Yetersiz yeni geçiş, tüm planı hataya düşürmek yerine asıl isteği ve düzeltme seçenekleriyle taslağa kaydedilir. Geçerli kamera/katman/geçiş önerileri korunur. Önizleme bekleyen geçişi uygulamadığını açıkça bildirir.
- Düzeltme API'si yalnız sunulmuş seçenek ve açık `confirmed=true` kabul eder. Kullanıcıdan keyfi süre/tür alıp güvenlik kontrolünü atlamaz. Seçilen düzeltme güncel belgeye karşı tekrar doğrulanır.
- Düzeltme kararı ayrı taslak geçmişi olayı olarak saklanır. Programı/ekranı yeniden açma, kısmi onay, eski taslak denetimi ve timeline geri alma korunur. Veritabanı şema geçişi yoktur.
- Doğrudan belge kaydındaki `short_transition` koruması kaldırılmadı; hata artık sahne/saniye ve düzeltme yolunu açıklar.
- Render sırasında açıkça onaylanan geçişin FFmpeg desteği veya işlemi başarısızsa geçiş hard cut ile değiştirilmez. Açık hata verilir; kayıtlı kurgu ve kaynaklar korunur. Eski otomatik dekoratif efektlerin uyumluluk davranışı bu düzeltmenin kapsamı dışındadır.
- Arayüzde yalnız mevcut taslak penceresine gerekli geçiş sorun/seçim/onay alanı eklendi. Başka özellik, menü veya düzenleme sistemi eklenmedi. Gemini paket kuralları bu davranışı açıklar.

## Doğrulama

- İlgili Python gruplarında toplam **156 farklı test geçti**: 62 mevcut aralık/düzenleme/polish testi; 92 testlik geçiş/manuel kurgu/paket/projeksiyon/render/kalite grubu ve eklenen iki odaklı test. Bu gruplar birbirinden farklı test dosyalarıdır; toplam collection ayrıca kontrol edildi.
- Yeni 21 test: sıfır/kısa/bilinmeyen kaynak kuyruğu, güvenli kısa süre, kaynak başlangıcı/hız/kare saati, küçük klip, onaysız/keyfi/tekrarlı düzeltmenin reddi, stale kaynak/kilit, başka manuel ayarların korunması, yeniden açma/undo, kısmi uygulama, iki sorun içinden yalnız birini düzeltme ve yalnız geçiş içeren plan.
- Üç seçenek için gerçek **JSON → doğrulama → taslak → JPEG önizleme → düzeltme onayı → uygulama → 4 saniyelik FFmpeg render** testi.
- Onaylanan geçişte eksik FFmpeg filtresi ve gerçek crossfade çalıştırma hatası enjekte edilerek sessiz hard cut geri dönüşü engellendiği test edildi.
- **70 frontend testi** geçti. `scripts/transition_handles_browser_smoke.py`, gerçek Chromium'da mesaj/seçim, onaysız değişmeme, kısmi uygulamayı iptal etme, işareti kaldırılmış önerinin korunması, gerçek önizleme ve yalnız seçili düzenlemelerin uygulanmasını doğruladı; JavaScript hatası ve dış istek yok.
- Python derleme, JavaScript sözdizimi ve `git diff --check` kontrolleri. Canlı/ücretli API, uzun render, kullanıcı verisi silme veya main merge işlemi yapılmadı. Test projeleri geçici ve sentetiktir.

## GitHub teslimi

Kod commit `4d80ed2` ile [fix/manual-plan-transition-handles](https://github.com/naman85331/video-ai-app/tree/fix/manual-plan-transition-handles) dalına gönderildi. Temel dala draft PR oluşturma hem GraphQL hem REST API üzerinden `403 Forbidden` ile reddedildi; PR oluşturulduğu iddia edilmez. [Değişiklikleri incele / PR aç](https://github.com/naman85331/video-ai-app/compare/fix/manual-plan-interval-import...fix/manual-plan-transition-handles). Main'e merge yapılmadı.
