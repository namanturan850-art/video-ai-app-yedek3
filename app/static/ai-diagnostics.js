/* Long provider calls run on the server; polling requests stay short/local. */
if (window.location.pathname === '/settings/ai-diagnostics') {
  const root = document.querySelector('#ai-diagnostic-content');
  root.hidden = false;
  const names = {gemini: 'Gemini', ollama: 'Ollama', openai: 'OpenAI'};
  const tests = [
    ['settings', '1 — Ayarlar', 'Şifreli kayıt → yeni okuyucuyla yeniden açılış. Mevcut anahtar, model ve OpenAI etkin seçimi korunur.'],
    ['connection', '2 — Bağlantı', 'API ve kayıtlı model erişimi. Metin üretmez; üretim kotasını garanti etmez.'],
    ['simple_generation', '3 — Basit Üretim', 'Yalnızca TEST_OK istenir. Senaryo motoru kullanılmaz.'],
    ['json', '4 — JSON', 'Yalnızca {"status":"ok"} istenir. JSON ve gerekli alan doğrulanır.'],
    ['script_pipeline', '5 — Tek Senaryo Bölümü', 'Mevcut motorla yaklaşık 30 kelimelik tek bölüm. Tam senaryo, analiz veya plan çalıştırılmaz.']
  ];
  const panels = new Map();
  let lastReport = null, polling = null;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const back = el('a', '← Ayarlara dön', 'back'); back.href = '/settings'; root.append(back);
  root.append(el('p', 'Önce Ayarlar ekranında bilgilerinizi Kaydet deyin. Burada her sağlayıcı için önce 1 — Ayarlar testini, ardından diğer testleri tek tek çalıştırın. Testler birbirinden bağımsızdır; bir üretim hatası başarılı bağlantı sonucunu değiştirmez.', 'note'));
  root.append(el('p', 'Gemini/OpenAI için 3, 4 ve 5 numaralı testler küçük de olsa API kotası veya ücret kullanabilir. Otomatik tekrar, sağlayıcı değişimi veya tam senaryo üretimi yapılmaz. Ollama yereldir.', 'note'));
  const pageStatus = el('p', 'Sonuçlar yükleniyor…', 'project-feedback'); pageStatus.setAttribute('role', 'status');
  const actions = el('div', '', 'settings-actions');
  const reload = el('button', 'Sonuçları yenile', 'secondary'); reload.type = 'button';
  const copy = el('button', 'Tanılama özetini kopyala', 'secondary'); copy.type = 'button'; copy.disabled = true;
  actions.append(reload, copy); root.append(pageStatus, actions);

  for (const [provider, name] of Object.entries(names)) {
    const panel = el('section', '', 'settings-panel'); panel.dataset.provider = provider;
    panel.append(el('h2', name));
    const progress = el('p', 'Bu oturumda henüz canlı test yapılmadı.', 'provider-status'); progress.setAttribute('aria-live', 'polite'); panel.append(progress);
    const rows = new Map();
    for (const [test, title, explanation] of tests) {
      const row = el('div', '', 'ai-test-row'); row.dataset.test = test;
      row.append(el('h3', title), el('p', explanation));
      const button = el('button', 'Testi Çalıştır'); button.type = 'button'; button.disabled = true;
      button.setAttribute('aria-label', `${name} ${title} testini çalıştır`);
      const status = el('p', 'Bekliyor', 'provider-status'); status.setAttribute('role', 'status');
      const reason = el('p', 'Henüz test edilmedi.');
      const technical = el('p', '', 'note');
      row.append(button, status, reason, technical); panel.append(row);
      rows.set(test, {button, status, reason, technical});
      button.addEventListener('click', () => runTest(provider, test));
    }
    panels.set(provider, {progress, rows}); root.append(panel);
  }

  function render(report) {
    if (!Array.isArray(report.providers)) throw new Error('invalid report');
    lastReport = report; copy.disabled = false;
    let running = false;
    for (const state of report.providers) {
      const panel = panels.get(state.provider); if (!panel) continue;
      running ||= Boolean(state.running_test);
      panel.progress.textContent = state.running_test ? 'Test sürüyor… Modelin yüklenmesi biraz zaman alabilir. Sayfayı açık bırakın; diğer testlere otomatik geçilmez.' : state.safe_message;
      for (const [test, row] of panel.rows) {
        const result = state.tests[test];
        row.status.textContent = result.status;
        row.reason.textContent = result.safe_message;
        row.button.disabled = Boolean(state.running_test) || (test !== 'settings' && state.settings_status !== 'Başarılı');
        row.technical.textContent = '';
        if (result.checked_at) {
          const details = [`Kategori: ${result.safe_error_category === 'none' ? 'yok' : result.safe_error_category}`, `Süre: ${result.elapsed_ms} ms`, new Date(result.checked_at).toLocaleString('tr-TR')];
          if (result.stage) details.push(`Aşama: ${result.stage}`);
          if (result.exception_class && result.exception_class !== 'none') details.push(`Hata türü: ${result.exception_class}`);
          if (result.upstream_http_status) details.push(`API HTTP: ${result.upstream_http_status}`);
          if (result.retry_after_seconds) details.push(`Tekrar öncesi en az ${result.retry_after_seconds} saniye bekleyin`);
          if (test === 'settings') {
            details.push(`Model: ${result.model || 'Kaydedilmemiş'}`);
            if (state.provider !== 'ollama') details.push(`Anahtar: ${result.has_api_key ? result.masked_api_key : 'Kaydedilmemiş'}`);
            if (state.provider === 'openai') details.push(`OpenAI: ${result.enabled ? 'Etkin' : 'Kapalı'}`);
          }
          row.technical.textContent = details.join(' · ');
        }
      }
    }
    clearTimeout(polling);
    if (running) polling = setTimeout(load, 1000);
  }

  async function load() {
    reload.disabled = true;
    try {
      render(await settingsRequest('/api/settings/ai-diagnostics'));
      pageStatus.textContent = 'Sonuçlar bu uygulama oturumuna aittir. Başarılı bağlantı, başarılı üretim anlamına gelmez. Canlı testleri Windows bilgisayarınızda siz çalıştırmalısınız.';
    } catch (error) {
      pageStatus.textContent = error.category ? error.message : 'Tanılama sonuçları okunamadı. Sonuçları yenile düğmesine basın.';
    } finally { reload.disabled = false; }
  }

  async function runTest(provider, test) {
    const paid = provider !== 'ollama' && ['simple_generation', 'json', 'script_pipeline'].includes(test);
    if (paid && !window.confirm(`${names[provider]} için bu kısa canlı test API kotası veya ücret kullanabilir. Yalnızca seçtiğiniz test çalıştırılacak. Devam edilsin mi?`)) return;
    for (const row of panels.get(provider).rows.values()) row.button.disabled = true;
    panels.get(provider).progress.textContent = 'Test başlatılıyor…';
    try {
      render(await settingsRequest(`/api/settings/ai-diagnostics/${provider}/${test}`, 'POST', {cost_confirmed: paid}));
    } catch (error) {
      const message = error.category ? error.message : 'Test başlatılamadı. Sonuçları yenileyip tekrar deneyin.';
      await load();
      pageStatus.textContent = message;
    }
  }
  reload.addEventListener('click', load);
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(lastReport, null, 2));
      pageStatus.textContent = 'Güvenli test özeti kopyalandı. Özet API anahtarı, Authorization veya üretilen metin içermez.';
    } catch { pageStatus.textContent = 'Özet kopyalanamadı. Test adı, sonuç ve altındaki güvenli kategori bilgisini paylaşabilirsiniz.'; }
  });
  window.addEventListener('pagehide', () => clearTimeout(polling));
  load();
}
