# NAMAN: kalıcı gelişmiş kurgu, keyframe ve gerçek efektler

Anlatım tabanlı yuvaların üzerine kalıcı ek kurgu katmanları ekler. Klip, keyframe, efekt, geçiş ve işaretleyici değişiklikleri proje/aktif plan kapsamında doğrulanır ve geri alınabilir; anlatım ve altyazı zamanları korunur. Dönüşümler ve katmanlar ortak FFmpeg graph ile örnek Program karelerine ve final montaja aktarılır.

Gerçek video thumbnail önbelleği, bağımsız Kaynak/Program monitörleri, güvenli dosya bırakma, tek tanımlı motion klip metriği ve kaynak/plan/ayar kimliğini kontrol eden render yeniden başlatma eklenir. SQLite 14→15 yükseltmesi eklemelidir. Eski kaynak ve tamamlanan çıktılar korunur.

Doğrulama: seçili Python paketi **192 geçti**, ek eski proje/render uyumluluğu **2 geçti**, DOM testleri **7 geçti**. Gerçek API/SQLite Chromium etkileşimleri ve dört viewport ölçümü geçti. Kısa gerçek FFmpeg testlerinde ilk/orta/son kare, geçiş, metin ve ses örnek sayısı doğrulandı.

Program önizlemesi en fazla 5 fps örnek karedir. Tam kareden render devamı, grup taşıma ve bezier editörü yoktur; desteklenmeyen Ease/fade bölmesi açık hata verir. Windows WebView2/GPU ve kurulu harici OpenMontage/Remotion bu Linux ortamında doğrulanmadı. Ücretli API veya uzun render çalıştırılmadı.

Kapsam, şema, değiştirilen dosyalar ve basit kullanıcı adımları: [teslim raporu](ADVANCED_EDITING.md).

Taslak olarak açılmalıdır. Kullanıcı ayrıca açıkça onaylamadan main'e birleştirilmez.
