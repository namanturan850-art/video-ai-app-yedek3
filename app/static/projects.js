/* Part 3: local project metadata only. No provider or production requests. */
if (['/new-project', '/projects'].includes(window.location.pathname) || /^\/projects\/[^/]+$/.test(window.location.pathname)) {
  const container = document.querySelector('#projects-content');
  container.hidden = false;
  const feedback = make('p', '', 'project-feedback');
  feedback.id = 'projects-feedback';
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  container.append(feedback);
  const dateFormat = new Intl.DateTimeFormat('tr-TR', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Istanbul'});

  function make(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function link(text, href, className) {
    const anchor = make('a', text, className);
    anchor.href = href;
    return anchor;
  }
  function field(form, name, label, type, initial, options = {}) {
    const group = make('div', '', 'setting-field');
    const caption = make('label', label);
    const id = `${form.id}-${name}`;
    caption.htmlFor = id;
    let input;
    if (type === 'select') {
      input = make('select');
      for (const [value, title] of options.choices) {
        const option = make('option', title); option.value = value; input.append(option);
      }
    } else if (type === 'textarea') input = make('textarea');
    else { input = make('input'); input.type = type; }
    input.id = id; input.name = name;
    if (type === 'checkbox') input.checked = initial;
    else input.value = initial;
    if (type === 'number') { input.min = options.min; input.max = options.max; input.step = options.step || '0.5'; }
    if (options.maxLength) input.maxLength = options.maxLength;
    if (options.required) input.required = true;
    if (type === 'textarea') input.rows = 5;
    const error = make('p', '', 'field-error');
    error.id = `${id}-error`; error.dataset.field = name;
    input.setAttribute('aria-describedby', error.id);
    group.append(caption, input, error);
    form.append(group);
    return input;
  }
  function busy(form, value) {
    for (const element of form.querySelectorAll('input, textarea, select, button')) element.disabled = value;
  }
  function errors(form, details = {}) {
    for (const input of form.querySelectorAll('input, textarea, select')) input.removeAttribute('aria-invalid');
    for (const label of form.querySelectorAll('[data-field]')) label.textContent = details[label.dataset.field] || '';
    for (const name of Object.keys(details)) {
      const input = form.elements.namedItem(name);
      if (input) input.setAttribute('aria-invalid', 'true');
    }
    if (details.scene_range) {
      form.querySelector('[data-field="max_scene_duration_seconds"]').textContent = details.scene_range;
    }
  }
  async function request(url, method = 'GET', body) {
    let response;
    try {
      response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(15000),
        headers: {'Content-Type': 'application/json', 'X-AI-Video-Studio': 'projects'},
        ...(body !== undefined ? {body: JSON.stringify(body)} : {})});
    } catch {
      throw new Error(method === 'POST' ? 'Uygulamaya ulaşılamadı. Projeler ekranını kontrol edin; kaydınız oluşmuş olabilir. Uygulama penceresini açık tutun.' : 'Uygulamaya ulaşılamadı. Uygulama penceresini açık tutup tekrar deneyin.');
    }
    let result;
    try { result = await response.json(); }
    catch { throw new Error('Yanıt okunamadı. Uygulama penceresini kontrol edip sayfayı yeniden açın.'); }
    if (!response.ok) {
      const error = new Error(result.message || 'İşlem tamamlanamadı. Bilgileri kontrol edip tekrar deneyin.');
      error.fields = result.fields || {}; throw error;
    }
    return result;
  }
  function information(items) {
    const list = make('dl', '', 'project-information');
    for (const [title, value] of items) list.append(make('dt', title), make('dd', String(value)));
    return list;
  }
  function timestamps(project) {
    return [['Oluşturulma (Türkiye saati)', dateFormat.format(new Date(project.created_at))], ['Son güncelleme (Türkiye saati)', dateFormat.format(new Date(project.updated_at))]];
  }
  async function remove(project, button, onRemoved) {
    if (!window.confirm(`“${project.name}” projesi ve bu projeye ait tüm yerel dosyalar kalıcı olarak silinsin mi? Bu işlem geri alınamaz. Diğer projeler silinmez.`)) return;
    button.disabled = true;
    feedback.textContent = 'Proje ve yerel dosyaları siliniyor…';
    try {
      await request(`/api/projects/${project.id}`, 'DELETE', {confirm: true});
      await onRemoved();
    } catch (error) { feedback.textContent = error.message; button.disabled = false; }
  }

  if (window.location.pathname === '/new-project') {
    const form = make('form', '', 'settings-panel project-form');
    form.id = 'new-project-form'; form.noValidate = true;
    const channelSelect = field(form, 'channel_id', 'Kanal', 'select', '', {choices: [['', 'Varsayılan kanal']]});
    form.append(make('p', 'Kanal seçince dil ve hedef süre kanaldan gelir; seslendirmede kanalın sesi seçili olur. Kanalları “Kanallar” sayfasından yönetin.', 'note'));
    field(form, 'name', 'Proje adı', 'text', '', {maxLength: 120, required: true});
    field(form, 'topic', 'Konu', 'textarea', '', {maxLength: 5000, required: true});
    field(form, 'reference_url', "Referans YouTube URL’si (isteğe bağlı)", 'url', '', {maxLength: 2000});
    form.append(make('p', 'Referans yalnızca kaydedilir. Video analiz edilmez, indirilmez veya kopyalanmaz.', 'note'));
    field(form, 'language', 'Hedef Dil', 'select', 'de', {choices: [['de', 'Almanca'], ['es', 'İspanyolca'], ['en', 'İngilizce'], ['fr', 'Fransızca'], ['tr', 'Türkçe']]});
    field(form, 'script_engine', 'Senaryo motoru (Script Engine)', 'select', 'gemini', {choices: [['gemini', 'Gemini (ücretsiz kota — önerilen)'], ['ollama', 'Ollama (yerel yedek)'], ['openai', 'OpenAI']]});
    field(form, 'target_duration_minutes', 'Hedef video süresi (dakika)', 'number', 5, {min: 1, max: 180});
    field(form, 'content_style', 'İçerik türü / stil', 'text', 'Otomatik', {maxLength: 120, required: true});
    field(form, 'min_scene_duration_seconds', 'Minimum sahne süresi (saniye)', 'number', 4, {min: 1, max: 120});
    field(form, 'max_scene_duration_seconds', 'Maksimum sahne süresi (saniye)', 'number', 8, {min: 1, max: 120});
    field(form, 'subtitles_enabled', 'Altyazı planlansın', 'checkbox', true);
    field(form, 'background_music_enabled', 'Arka plan müziği planlansın', 'checkbox', false);
    field(form, 'thumbnail_planning_enabled', 'Küçük resim (thumbnail) planlansın', 'checkbox', true);
    form.append(make('p', 'Proje oluşturduktan sonra Senaryo aşamasını açabilirsiniz. Ses ve video üretimi daha sonra eklenecek.', 'note'));
    let channelList = [];
    request('/api/channels').then(result => {
      channelList = result.channels; channelSelect.replaceChildren();
      for (const c of channelList) { const o = make('option', c.name + (c.is_default ? ' (varsayılan)' : '')); o.value = c.id; channelSelect.append(o); }
      const wanted = new URLSearchParams(window.location.search).get('channel');
      channelSelect.value = channelList.some(c => c.id === wanted) ? wanted : channelList.find(c => c.is_default)?.id || '';
      applyChannel();
    }).catch(() => {});
    function applyChannel() {
      const c = channelList.find(item => item.id === channelSelect.value); if (!c) return;
      form.elements.namedItem('language').value = c.language; form.elements.namedItem('target_duration_minutes').value = c.target_duration_minutes;
    }
    channelSelect.addEventListener('change', applyChannel);
    const submit = make('button', 'Proje Oluştur'); submit.type = 'submit';
    form.append(submit); container.append(form);
    form.addEventListener('submit', async event => {
      event.preventDefault(); errors(form); busy(form, true);
      feedback.textContent = 'Proje ve klasörleri oluşturuluyor…';
      const data = {};
      for (const input of form.querySelectorAll('input, textarea, select')) {
        data[input.name] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
      }
      try {
        const project = await request('/api/projects', 'POST', data);
        window.location.assign(`/projects/${project.id}`);
      } catch (error) {
        feedback.textContent = error.message; errors(form, error.fields); busy(form, false);
        form.querySelector('[aria-invalid="true"]')?.focus();
      }
    });
  } else if (window.location.pathname === '/projects') {
    const controls = make('div', '', 'settings-actions');
    const reload = make('button', 'Listeyi yenile'); reload.type = 'button';
    controls.append(link('Yeni Proje', '/new-project', 'action-link'), reload);
    const list = make('div', '', 'project-list'); list.id = 'project-list';
    container.append(controls, list);
    async function load(afterDelete = false) {
      reload.disabled = true; feedback.textContent = 'Projeler yükleniyor…';
      try {
        const data = await request('/api/projects');
        list.replaceChildren();
        for (const project of data.projects) {
          const card = make('article', '', 'settings-panel project-card'); card.dataset.projectId = project.id;
          card.append(make('h2', project.name), make('p', project.topic, 'topic-preview'));
          card.append(information([['Dil', project.language_label], ['Hedef süre', `${project.target_duration_minutes} dakika`], ['Durum', project.status_label], ...timestamps(project)]));
          const actions = make('div', '', 'settings-actions');
          const removeButton = make('button', 'Projeyi Sil', 'danger'); removeButton.type = 'button';
          removeButton.addEventListener('click', () => remove(project, removeButton, () => load(true)));
          actions.append(link('Projeyi Aç', `/projects/${project.id}`, 'action-link'), removeButton);
          card.append(actions); list.append(card);
        }
        feedback.textContent = afterDelete ? 'Proje silindi. Diğer projeleriniz korundu.' : data.projects.length ? `${data.projects.length} proje bulundu.` : 'Henüz projeniz yok. Yeni Proje düğmesiyle başlayabilirsiniz.';
      } catch (error) { feedback.textContent = error.message; }
      finally { reload.disabled = false; }
    }
    reload.addEventListener('click', () => load()); load();
  } else {
    const id = window.location.pathname.split('/')[2];
    container.append(link('← Projelere dön', '/projects', 'back'));
    const detail = make('div'); detail.id = 'project-detail'; container.append(detail);
    function render(project) {
      detail.replaceChildren();
      document.querySelector('#page-title').textContent = project.name;
      document.title = `${project.name} · AI Video Studio`;
      detail.append(information([
        ['Konu', project.topic], ['Referans YouTube URL’si', project.reference_url || 'Eklenmedi'],
        ['Kanal', project.channel_name || 'Varsayılan kanal'], ['Dil', project.language_label], ['Hedef video süresi', `${project.target_duration_minutes} dakika`],
        ['Senaryo motoru', project.script_engine_label], ['İçerik türü / stil', project.content_style],
        ['Sahne süresi', `${project.min_scene_duration_seconds} – ${project.max_scene_duration_seconds} saniye`],
        ['Altyazı', project.subtitles_enabled ? 'Açık' : 'Kapalı'], ['Arka plan müziği', project.background_music_enabled ? 'Açık' : 'Kapalı'],
        ['Küçük resim planlama', project.thumbnail_planning_enabled ? 'Açık' : 'Kapalı'],
        ['Durum', project.status_label], ...timestamps(project)
      ]));
      const edit = make('details', '', 'settings-panel');
      const planning = make('a', 'Görsel / Kurgu Planı ve Kalite Kontrolü', 'back'); planning.href = `/projects/${project.id}/production`; detail.append(planning);
      edit.append(make('summary', 'Proje bilgilerini düzenle'));
      const form = make('form'); form.id = 'edit-project-form'; form.noValidate = true;
      field(form, 'name', 'Proje adı', 'text', project.name, {maxLength: 120, required: true});
      field(form, 'topic', 'Konu', 'textarea', project.topic, {maxLength: 5000, required: true});
      field(form, 'script_engine', 'Senaryo motoru (Script Engine)', 'select', project.script_engine, {choices: [['gemini', 'Gemini (ücretsiz kota — önerilen)'], ['ollama', 'Ollama (yerel yedek)'], ['openai', 'OpenAI']]});
      const save = make('button', 'Bilgileri Kaydet'); save.type = 'submit'; form.append(save); edit.append(form); detail.append(edit);
      form.addEventListener('submit', async event => {
        event.preventDefault(); errors(form); busy(form, true); feedback.textContent = 'Proje bilgileri kaydediliyor…';
        try {
          const updated = await request(`/api/projects/${id}`, 'PATCH', {name: form.elements.namedItem('name').value, topic: form.elements.namedItem('topic').value, script_engine: form.elements.namedItem('script_engine').value});
          render(updated); feedback.textContent = 'Proje bilgileri kaydedildi.';
        } catch (error) { feedback.textContent = error.message; errors(form, error.fields); busy(form, false); }
      });
      detail.append(make('h2', 'Üretim aşamaları'), make('p', 'Senaryo aşamasını açıp metninizi hazırlayabilirsiniz. Diğer üretim aşamaları daha sonra eklenecek.', 'note'));
      const pipeline = make('ol', '', 'pipeline'); pipeline.id = 'project-pipeline';
      for (const stage of project.pipeline) {
        const item = make('li'); item.append(make('h3', stage.name), make('span', stage.status, 'badge'), make('p', stage.message, 'note'));
        if (stage.name === 'Senaryo') item.append(link('Senaryoyu Aç', `/projects/${id}/script`, 'action-link'));
        if(stage.name==='Seslendirme')item.append(link('Seslendirmeyi Aç',`/projects/${id}/narration`,'action-link'));
        if(stage.name==='Render')item.append(link('Video Oluştur / Render',`/projects/${id}/render`,'action-link'));
        if(stage.name==='Render')item.append(link('YouTube hazırlığı (başlık, açıklama, kapak)',`/projects/${id}/youtube`,'action-link'));
        if(stage.name==='Altyazı')item.append(link('Altyazı ve Zamanlama',`/projects/${id}/subtitles`,'action-link'));
        pipeline.append(item);
      }
      detail.append(pipeline);
      const removeButton = make('button', 'Projeyi Sil', 'danger'); removeButton.type = 'button';
      removeButton.addEventListener('click', () => remove(project, removeButton, async () => window.location.assign('/projects')));
      detail.append(removeButton);
    }
    async function load() {
      feedback.textContent = 'Proje yükleniyor…';
      try { render(await request(`/api/projects/${id}`)); feedback.textContent = 'Proje bilgileri yüklendi. Üretim özellikleri sonraki aşamalarda eklenecek.'; }
      catch (error) { feedback.textContent = error.message; }
    }
    const retry = make('button', 'Projeyi tekrar yükle', 'secondary'); retry.type = 'button';
    retry.addEventListener('click', load); container.append(retry); load();
  }
}
