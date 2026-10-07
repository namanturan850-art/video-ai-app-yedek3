/* Credentials live only in blank password inputs until explicitly saved. */
if (window.location.pathname === '/settings') {
  const root = document.querySelector('#settings-content');
  const sections = document.querySelector('#settings-sections');
  const pageStatus = document.querySelector('#settings-status');
  const reload = document.querySelector('#settings-reload');
  root.hidden = false;
  const definitions = [
    {id: 'general', title: 'Genel', description: 'Varsayılan içerik dilini seçin. İçerik üretimi sonraki aşamalarda eklenecek.', fields: [{name: 'content_language', label: 'Varsayılan içerik dili', type: 'select'}]},
    {id: 'ollama', title: 'Ollama', description: 'İsteğe bağlı yerel senaryo hizmeti. Ollama kullanmayacaksanız model adını boş bırakın. Testten önce ayarları kaydedin.', fields: [{name: 'base_url', label: 'Yerel adres (Base URL)', type: 'url'}, {name: 'model', label: 'Bilgisayarınızda kurulu modelin adı', type: 'text'}], test: true},
    {id: 'openai', title: 'OpenAI (isteğe bağlı)', description: 'OpenAI zorunlu değildir. Burada yalnızca tercihlerinizi ve anahtarınızı kaydedebilirsiniz.', fields: [{name: 'enabled', label: 'İleride OpenAI kullanmak istiyorum', type: 'checkbox'}, {name: 'model', label: 'Model adı (isteğe bağlı)', type: 'text'}], secret: true, test: false},
    {id: 'pexels', title: 'Pexels', description: 'Stok medya bağlantısı için API anahtarınızı kaydedebilirsiniz. Medya araması henüz eklenmedi.', fields: [], secret: true, test: false},
    {id: 'pixabay', title: 'Pixabay', description: 'Alternatif stok medya bağlantısı için API anahtarınızı kaydedebilirsiniz. Medya araması henüz eklenmedi.', fields: [], secret: true, test: false},
    {id: 'ai33', title: 'AI33', description: 'Planlanan ana seslendirme sağlayıcısı. Bilgiler burada saklanabilir; gerçek bağlantı ve seslendirme kapalıdır.', fields: [{name: 'base_url', label: 'Base URL (belgelenmiş adres varsa)', type: 'url'}, {name: 'voice_id', label: 'Voice ID / Ses kimliği (isteğe bağlı)', type: 'text'}, {name: 'model', label: 'Model (isteğe bağlı)', type: 'text'}], secret: true, test: false}
  ];
  const forms = new Map();
  let loaded = false;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function addField(form, provider, field) {
    const wrapper = element('div', '', 'setting-field');
    const id = `${provider}-${field.name}`;
    const label = element('label', field.label);
    label.htmlFor = id;
    const input = document.createElement(field.type === 'select' ? 'select' : 'input');
    input.id = id;
    input.name = field.name;
    if (field.type !== 'select') input.type = field.type;
    if (field.type === 'select') {
      for (const [value, title] of [['de', 'Almanca'], ['tr', 'Türkçe'], ['en', 'İngilizce']]) {
        const option = element('option', title);
        option.value = value;
        input.append(option);
      }
    } else if (field.type !== 'checkbox') {
      input.maxLength = field.name === 'api_key' ? 4096 : field.type === 'url' ? 500 : 150;
      input.autocomplete = field.name === 'api_key' ? 'new-password' : 'off';
      input.spellcheck = false;
    }
    wrapper.append(label, input);
    form.append(wrapper);
  }
  for (const definition of definitions) {
    const form = element('form', '', 'settings-panel');
    form.id = `settings-${definition.id}`;
    form.autocomplete = 'off';
    form.append(element('h2', definition.title), element('p', definition.description, 'note'));
    const status = element('p', 'Yükleniyor…', 'provider-status');
    status.dataset.role = 'provider-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    form.append(status);
    for (const field of definition.fields) addField(form, definition.id, field);
    if (definition.secret) {
      addField(form, definition.id, {name: 'api_key', label: 'API anahtarı', type: 'password'});
      const keyInfo = element('p', '', 'note');
      keyInfo.dataset.role = 'key-info';
      form.append(keyInfo, element('p', 'Boş bırakırsanız kayıtlı anahtar korunur. Değiştirmek için yeni anahtarı girin. Temizle bu bölümdeki anahtarı ve ayarları siler.', 'note'));
    }
    const actions = element('div', '', 'settings-actions');
    const save = element('button', 'Kaydet');
    save.type = 'submit';
    const clear = element('button', 'Temizle', 'secondary');
    clear.type = 'button';
    clear.addEventListener('click', () => {
      if (window.confirm(`${definition.title} bölümündeki kayıtlı bilgiler silinsin mi?`)) {
        perform(definition, 'DELETE');
      }
    });
    actions.append(save, clear);
    if (definition.id !== 'general') {
      const test = element('button', 'Bağlantıyı Test Et', 'secondary');
      test.type = 'button';
      test.dataset.role = 'test';
      test.disabled = !definition.test;
      test.addEventListener('click', () => {
        if (form.dataset.dirty === 'true') {
          status.textContent = 'Önce Kaydet düğmesine basın; test kayıtlı bilgileri kullanır.';
        } else perform(definition, 'POST');
      });
      actions.append(test);
    }
    form.append(actions);
    if (definition.test === false) form.append(element('p', definition.id === 'ai33' ? 'AI33 API belgeleri gerekli' : 'API belgeleri gerekli. Bağlantı testi bu aşamada kullanılamaz.', 'note'));
    form.addEventListener('input', () => { form.dataset.dirty = 'true'; });
    form.addEventListener('submit', event => { event.preventDefault(); perform(definition, 'PUT'); });
    forms.set(definition.id, form);
    sections.append(form);
  }
  const ffmpeg = element('section', '', 'settings-panel');
  ffmpeg.id = 'settings-ffmpeg';
  ffmpeg.append(element('h2', 'FFmpeg'), element('p', 'Otomatik algılanır. Ayarları kullanmak için kurmanız gerekmez.', 'note'));
  const ffmpegStatus = element('p', 'Kontrol ediliyor…', 'provider-status');
  ffmpegStatus.setAttribute('role', 'status');
  ffmpegStatus.setAttribute('aria-live', 'polite');
  const ffmpegPath = element('p', '', 'executable-path');
  const ffmpegButton = element('button', 'Bağlantıyı Test Et');
  ffmpegButton.type = 'button';
  ffmpegButton.addEventListener('click', async () => {
    ffmpegButton.disabled = true;
    ffmpegStatus.textContent = 'FFmpeg kontrol ediliyor…';
    try {
      const result = await request('/api/settings/ffmpeg/test', 'POST');
      showSettings(result.settings);
      ffmpegStatus.textContent = `${result.result.status} · ${result.result.message}`;
    } catch (error) { ffmpegStatus.textContent = error.message; }
    finally { ffmpegButton.disabled = false; }
  });
  ffmpeg.append(ffmpegStatus, ffmpegPath, ffmpegButton);
  const youtube = element('section', '', 'settings-panel');
  youtube.id = 'settings-youtube';
  youtube.append(element('h2', 'YouTube'), element('p', 'Daha sonra', 'provider-status'), element('p', 'YouTube bağlantısı ve yükleme sonraki aşamalarda ele alınacak.', 'note'));
  sections.append(ffmpeg, youtube);

  function setBusy(form, busy, definition) {
    for (const control of form.querySelectorAll('input, select, button')) {
      control.disabled = busy || (control.dataset.role === 'test' && !definition.test);
    }
  }
  function showSettings(settings, resetSection = null) {
    for (const definition of definitions) {
      const form = forms.get(definition.id);
      const data = settings[definition.id];
      const reset = !loaded || resetSection === definition.id;
      if (reset) {
        for (const field of definition.fields) {
          const input = form.elements.namedItem(field.name);
          if (field.type === 'checkbox') input.checked = data[field.name];
          else input.value = data[field.name] || '';
        }
        if (definition.secret) form.elements.namedItem('api_key').value = '';
        form.dataset.dirty = 'false';
      }
      form.querySelector('[data-role="provider-status"]').textContent = definition.id === 'general' ? 'Tercihler hazır.' : `${data.status} · ${data.message}`;
      if (definition.secret) form.querySelector('[data-role="key-info"]').textContent = data.has_api_key ? `Kayıtlı anahtar: ${data.masked_api_key}` : 'Henüz anahtar kaydedilmedi.';
    }
    ffmpegStatus.textContent = settings.ffmpeg.message;
    ffmpegPath.textContent = settings.ffmpeg.executable_path ? `Algılanan dosya: ${settings.ffmpeg.executable_path}` : '';
    loaded = true;
  }
  async function request(url, method = 'GET', body) {
    const options = {method, cache: 'no-store', signal: AbortSignal.timeout(12000), headers: {'X-AI-Video-Studio': 'settings'}};
    if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    let response;
    try { response = await fetch(url, options); }
    catch { throw new Error('Uygulamaya ulaşılamadı. Uygulama penceresini ve bağlantınızı kontrol edip tekrar deneyin.'); }
    let result;
    try { result = await response.json(); }
    catch { throw new Error('Yanıt okunamadı. Sayfayı yeniden açıp tekrar deneyin.'); }
    if (!response.ok) throw new Error(result.message || 'İşlem tamamlanamadı. Bilgileri kontrol edip tekrar deneyin.');
    return result;
  }
  async function perform(definition, method) {
    const form = forms.get(definition.id);
    const status = form.querySelector('[data-role="provider-status"]');
    let body;
    if (method === 'PUT') {
      body = {};
      for (const field of definition.fields) {
        const input = form.elements.namedItem(field.name);
        body[field.name] = field.type === 'checkbox' ? input.checked : input.value;
      }
      if (definition.secret && form.elements.namedItem('api_key').value) body.api_key = form.elements.namedItem('api_key').value;
    }
    setBusy(form, true, definition);
    status.textContent = method === 'POST' ? 'Bağlantı kontrol ediliyor…' : 'Bilgiler kaydediliyor…';
    try {
      const result = await request(`/api/settings/${definition.id}${method === 'POST' ? '/test' : ''}`, method, body);
      showSettings(result.settings || result, method === 'POST' ? null : definition.id);
      if (method === 'POST') status.textContent = `${result.result.status} · ${result.result.message}`;
      pageStatus.textContent = method === 'POST' ? 'Bağlantı kontrolü tamamlandı.' : method === 'DELETE' ? 'Bu bölümdeki kayıtlı bilgiler temizlendi.' : 'Ayarlar kaydedildi. Anahtarlar yalnızca bu bilgisayarda saklanır.';
    } catch (error) { status.textContent = `Hata · ${error.message}`; }
    finally { setBusy(form, false, definition); }
  }
  async function load() {
    reload.disabled = true;
    for (const definition of definitions) setBusy(forms.get(definition.id), true, definition);
    pageStatus.textContent = 'Ayarlar yükleniyor…';
    try {
      const data = await request('/api/settings');
      loaded = false;
      showSettings(data);
      pageStatus.textContent = 'Ayarlar hazır. Kullanmak istemediğiniz hizmetleri boş bırakabilirsiniz.';
      for (const definition of definitions) setBusy(forms.get(definition.id), false, definition);
    } catch (error) { pageStatus.textContent = error.message; }
    finally { reload.disabled = false; }
  }
  reload.addEventListener('click', () => {
    if ([...forms.values()].some(form => form.dataset.dirty === 'true') && !window.confirm('Kaydedilmemiş değişiklikler kaldırılıp kayıtlı ayarlar yüklensin mi?')) return;
    load();
  });
  load();
}
