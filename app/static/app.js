const pages = {
  '/new-project': ['Yeni Proje', 'Video fikrinizi ve tercihlerinizi kaydedin. Bu adım video veya senaryo üretmez.'],
  '/projects': ['Projeler', 'Kaydettiğiniz projeleri açın veya istemediklerinizi silin.'],
  '/settings': ['Ayarlar', 'Kullanmak istediğiniz hizmetlerin bilgilerini buradan kaydedin. İstemediğiniz bölümleri boş bırakabilirsiniz.'],
  '/diagnostics': ['Tanılama', 'Bilgisayarınızın ve uygulamanın durumunu buradan kontrol edebilirsiniz.']
};
const path = window.location.pathname;
if (/^\/projects\/[^/]+$/.test(path)) pages[path] = ['Proje', 'Proje bilgileri ve ileride kullanılacak üretim aşamaları.'];
if (/^\/projects\/[^/]+\/script$/.test(path)) pages[path] = ['Senaryo', 'Konuya uygun özgün bir YouTube senaryosu oluşturun, düzenleyin ve onaylayın.'];
if (/^\/projects\/[^/]+\/production$/.test(path)) pages[path] = ['Görsel ve Kurgu Hazırlığı', 'Planları ve eksikleri inceleyin. Medya arama, seslendirme ve render henüz çalıştırılmaz.'];
if (pages[path]) {
  document.querySelector('#dashboard').hidden = true;
  document.querySelector('#detail').hidden = false;
  document.querySelector('#page-title').textContent = pages[path][0];
  document.querySelector('#page-description').textContent = pages[path][1];
  document.title = `${pages[path][0]} · AI Video Studio`;
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
      ['FFmpeg', data.ffmpeg_found ? 'Bulundu. Video düzenleme özelliği ileride eklenecek.' : 'Bulunamadı. Uygulama çalışabilir; video oluşturmak için daha sonra FFmpeg kurulması gerekecek.'],
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
