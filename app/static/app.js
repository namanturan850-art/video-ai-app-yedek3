const pages = {
  '/new-project': ['Yeni Proje', 'Video fikrinizi ve tercihlerinizi kaydedin. Bu adım video veya senaryo üretmez.'],
  '/projects': ['Projeler', 'Kaydettiğiniz projeleri açın veya istemediklerinizi silin.'],
  '/settings': ['Ayarlar', 'Kullanmak istediğiniz hizmetlerin bilgilerini buradan kaydedin. İstemediğiniz bölümleri boş bırakabilirsiniz.'],
  '/settings/ai-diagnostics': ['AI Tanılama', 'Ayar kaydını, bağlantıyı, kısa üretimi, JSON biçimini ve tek senaryo bölümünü ayrı ayrı kontrol edin.'],
  '/diagnostics': ['Tanılama', 'Bilgisayarınızın ve uygulamanın durumunu buradan kontrol edebilirsiniz.']
};
const path = window.location.pathname;
if (/^\/projects\/[^/]+$/.test(path)) pages[path] = ['Proje', 'Proje bilgileri ve üretim adımları.'];
if (/^\/projects\/[^/]+\/script$/.test(path)) pages[path] = document.body.dataset.scriptGeneration === '1' ? ['Senaryo', 'Konuya uygun özgün bir YouTube senaryosu oluşturun, düzenleyin ve onaylayın.'] : ['Metin', 'Kendi metninizi yapıştırın; seslendirme ve altyazı bu metni kelimesi kelimesine kullanır.'];
if (/^\/projects\/[^/]+\/production$/.test(path)) pages[path] = ['Görsel ve Kurgu Hazırlığı', 'Gemini sahne planı → video, görsel ve harita kaynakları → manuel kurgu.'];
if (/^\/projects\/[^/]+\/narration$/.test(path)) pages[path]=['Seslendirme','Onaylı senaryonuz için ses seçin, görev durumunu izleyin ve ses dosyanızı dinleyin.'];
if (/^\/projects\/[^/]+\/subtitles$/.test(path)) pages[path]=['Altyazı ve Zamanlama','Yerel sesinizin süresine göre yaklaşık altyazı zamanlarını oluşturun, dinleyin ve düzenleyin.'];
if (/^\/projects\/[^/]+\/youtube$/.test(path)) pages[path]=['YouTube','Başlık, açıklama ve etiket hazırlığı. Otomatik yükleme yapılmaz.'];
if (/^\/projects\/[^/]+\/render$/.test(path)) pages[path]=['Video Oluştur / Render','Mevcut yerel ses, altyazı ve medyayı tek videoda birleştirin. API kredisi kullanılmaz.'];
if (/^\/projects\/[^/]+\/editor$/.test(path)) pages[path]=['NAMAN Kurgu','Yedi izli zaman çizelgesinde ses, görüntü, altyazı ve animasyonları birlikte kontrol edin.'];
if (pages[path]) {
  document.querySelector('#dashboard').hidden = true;
  document.querySelector('#detail').hidden = false;
  document.querySelector('#page-title').textContent = pages[path][0];
  document.querySelector('#page-description').textContent = pages[path][1];
  document.title = `${pages[path][0]} · NAMAN`;
}
async function refreshDiagnostics() {
  const status = document.querySelector('#diagnostic-status');
  const button = document.querySelector('#refresh');
  button.disabled = true;
  status.textContent = 'Kontroller yapılıyor…';
  document.querySelector('#results').replaceChildren();
  try {
    const response = await fetch('/api/diagnostics', {cache: 'no-store', signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('request failed');
    const data = await response.json();
    const rows = [
      ['Uygulama sürümü', data.app_version], ['Python sürümü', data.python_version],
      ['İşletim sistemi', data.operating_system],
      ['Veritabanı', data.database_ok ? 'Hazır' : 'Kullanılamıyor. Uygulamayı yazma izniniz olan bir klasörde yeniden açın.'],
      ['Veri klasörü', data.data_directory_writable ? 'Dosya yazılabiliyor' : 'Dosya yazılamıyor. Uygulama klasörünü Belgeler klasörünüze taşıyıp yeniden açın.'],
      ['FFmpeg', data.ffmpeg_found ? 'Bulundu. Projenizde Video Oluştur / Render ekranını kullanabilirsiniz.' : 'Bulunamadı. Uygulama çalışabilir; video oluşturmak için daha sonra FFmpeg kurulması gerekecek.'],
      ['Sağlayıcılar', data.providers]
    ];
    for (const [label, value] of rows) {
      const title = document.createElement('dt');
      const description = document.createElement('dd');
      title.textContent = label;
      description.textContent = value;
      document.querySelector('#results').append(title, description);
    }
    status.textContent = data.database_ok && data.data_directory_writable ? 'Kontroller tamamlandı. Uygulamanın temel işlevleri hazır.' : 'Kontroller tamamlandı. Aşağıdaki açıklamalara göre sorunları giderebilirsiniz.';
  } catch {
    status.textContent = 'Uygulamaya ulaşılamadı. Siyah uygulama penceresinin açık olduğunu kontrol edip Tekrar kontrol et düğmesine basın.';
  } finally { button.disabled = false; }
}
if (path === '/diagnostics') {
  document.querySelector('#diagnostic-content').hidden = false;
  document.querySelector('#refresh').addEventListener('click', refreshDiagnostics);
  refreshDiagnostics();
}
