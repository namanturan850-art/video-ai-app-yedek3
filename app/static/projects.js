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
  async function request(url, method = 'GET', body, timeout = 15000) {
    let response;
    try {
      response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(timeout),
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

  // “Kaynak analizi”: reference video → why it worked + what it tells.
  function sourceCard(project) {
    const card = make('section', '', 'settings-panel source-card'); card.id = 'source-analysis';
    const status = make('p', '', 'provider-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const body = make('div'); body.id = 'source-result';
    const urlForm = make('form', '', 'project-form'); urlForm.id = 'source-form'; urlForm.noValidate = true;
    field(urlForm, 'reference_url', 'Referans YouTube linki', 'url', project.reference_url || '', {maxLength: 2000});
    field(urlForm, 'transcript', 'Transkript (yapıştır, isteğe bağlı — varsa önce bu kullanılır)', 'textarea', '', {maxLength: 60000});
    const save = make('button', 'Kaydet'); save.type = 'submit';
    const analyze = make('button', 'Kaynağı analiz et'); analyze.type = 'button'; analyze.id = 'source-analyze';
    urlForm.append(save, analyze);
    card.append(make('h2', 'Kaynak analizi'), make('p', 'Tutmuş bir videoyu kaynak alın: yapı, kanca, bilgiler ve izleyici tepkisi analiz edilir; senaryo hedef dilde yeni cümlelerle yazılır (çeviri değil). Şüpheli bilgiler işaretlenir.', 'note'), urlForm, status, body);
    const transcript = urlForm.elements.namedItem('transcript');
    const list = (title, items, cls) => { if (!items?.length) return null; const box = make('div'); box.append(make('h3', title)); const ul = make('ul', '', cls || ''); for (const t of items) ul.append(make('li', t)); box.append(ul); return box; };
    function show(view) {
      transcript.value = view.transcript || '';
      body.replaceChildren();
      const a = view.analysis;
      const warnings = [...(a?.warnings || [])]; if (!a && view.hint) warnings.push(view.hint);
      if (!view.youtube_key && view.reference_url && !a) warnings.push('YouTube API anahtarı yok: sayılar ve yorumlar atlanacak, analiz Gemini ile sürecek.');
      if (warnings.length) { const w = make('ul', '', 'source-warnings'); for (const t of warnings) w.append(make('li', '⚠ ' + t)); body.append(w); }
      if (!a) { status.textContent = view.reference_url || view.has_transcript ? 'Henüz analiz edilmedi. “Kaynağı analiz et” deyin.' : ''; return; }
      const r = a.analysis, m = a.metadata;
      status.textContent = a.mode === 'title_only' ? 'Kaynak yok: senaryo yalnız konudan/başlıktan üretilecek.' : a.status === 'needs_transcript' ? 'İçerik okunamadı. Transkripti yapıştırıp yeniden analiz edin.' :
        `✓ Analiz hazır (${{video: 'Gemini videoyu okudu', transcript: 'transkriptten', metadata: 'yalnız başlık/açıklama/yorumlardan'}[a.mode]}). Yönetmen ve Senaryo ekranı bu analizi otomatik kullanır.`;
      if (m) {
        const nf = n => n == null ? '—' : Number(n).toLocaleString('tr-TR');
        body.append(make('h3', 'Kaynak video'), information([['Başlık', m.title], ['Kanal', m.channel || '—'], ['Süre', m.duration_seconds ? `${Math.floor(m.duration_seconds / 60)}:${String(m.duration_seconds % 60).padStart(2, '0')} dk` : '—'],
          ['İzlenme', nf(m.views)], ['Beğeni', nf(m.likes)], ['Yorum', nf(m.comments)], ['Okunan yorum', String(a.comments_used || 0)]]));
      }
      if (!r) return;
      body.append(make('h3', 'Neden tuttu?'));
      for (const part of [list('', r.why_it_works), r.title_strategy ? make('p', 'Başlık stratejisi: ' + r.title_strategy) : null, list('İzleyici tepkisi (yorumlar)', r.audience_reactions)]) if (part) body.append(part);
      body.append(make('h3', 'Ne anlatıyor?'), make('p', r.summary));
      if (r.hook?.type) body.append(make('p', `Açılış kancası: ${r.hook.type} — ${r.hook.description}`));
      body.append(make('p', `Tempo: ${r.pacing || '—'} · Ton: ${r.tone || '—'} · Kapanış: ${r.ending || '—'}`));
      const sections = list('Bölüm sırası', r.sections.map((x, i) => `${i + 1}. ${x.title}: ${x.summary}`)); if (sections) body.append(sections);
      const facts = list('Bilgiler (⚠ = şüpheli, senaryoda kesin bilgi gibi sunulmaz)', r.facts.map(f => (f.doubtful ? '⚠ ' : '✓ ') + f.claim + (f.note ? ` (${f.note})` : '')), 'source-facts'); if (facts) body.append(facts);
      const questions = list('İzleyicilerin sorduğu / eksik bulduğu (senaryoya eklenir)', r.viewer_questions); if (questions) body.append(questions);
    }
    async function load() { try { show(await request(`/api/projects/${project.id}/source`)); } catch (error) { status.textContent = error.message; } }
    async function store() {
      const url = urlForm.elements.namedItem('reference_url').value.trim();
      if (url !== (project.reference_url || '')) { project = await request(`/api/projects/${project.id}`, 'PATCH', {reference_url: url}); }
      return request(`/api/projects/${project.id}/source/transcript`, 'PUT', {transcript: transcript.value});
    }
    urlForm.addEventListener('submit', async event => { event.preventDefault(); errors(urlForm); try { show(await store()); status.textContent = 'Kaydedildi.'; } catch (error) { status.textContent = error.message; errors(urlForm, error.fields); } });
    analyze.addEventListener('click', async () => {
      analyze.disabled = save.disabled = true; status.textContent = 'Analiz ediliyor… Gemini videoyu okurken 1–3 dakika sürebilir. Sayfayı kapatmayın.';
      try { await store(); show(await request(`/api/projects/${project.id}/source/analyze`, 'POST', {}, 300000)); }
      catch (error) { status.textContent = error.message; } finally { analyze.disabled = save.disabled = false; }
    });
    load();
    return card;
  }

  // AI script writing is behind a flag (default off): projects start from the owner's own text.
  const GEN = document.body.dataset.scriptGeneration === '1';

  if (window.location.pathname === '/new-project') {
    const form = make('form', '', 'settings-panel project-form');
    form.id = 'new-project-form'; form.noValidate = true;
    field(form, 'name', GEN ? 'Proje adı' : 'Başlık', 'text', '', {maxLength: 120, required: true});
    if (GEN) {
    field(form, 'topic', 'Konu', 'textarea', '', {maxLength: 5000, required: true});
    field(form, 'reference_url', "Referans YouTube URL’si (isteğe bağlı)", 'url', '', {maxLength: 2000});
    field(form, 'reference_transcript', 'Transkript (yapıştır, isteğe bağlı)', 'textarea', '', {maxLength: 60000});
    form.append(make('p', 'Referans video analiz edilir ama indirilmez: Gemini herkese açık linki okur (transkript yapıştırdıysanız o kullanılır), YouTube API anahtarınız varsa izlenme/beğeni sayıları ve en çok beğenilen yorumlar da okunur. Senaryo bu analizden yeni cümlelerle, hedef dilde yazılır; birebir çeviri yapılmaz. Link ve transkript boşsa senaryo yalnız konudan üretilir.', 'note'));
    }
    field(form, 'language', 'Hedef Dil', 'select', 'de', {choices: [['de', 'Almanca'], ['es', 'İspanyolca'], ['en', 'İngilizce'], ['fr', 'Fransızca'], ['tr', 'Türkçe']]});
    if (GEN) {
    field(form, 'script_engine', 'Senaryo motoru (Script Engine)', 'select', 'gemini', {choices: [['gemini', 'Gemini (ücretsiz kota — önerilen)'], ['ollama', 'Ollama (yerel yedek)'], ['openai', 'OpenAI']]});
    field(form, 'target_duration_minutes', 'Hedef video süresi (dakika)', 'number', 5, {min: 1, max: 180});
    field(form, 'content_style', 'İçerik türü / stil', 'text', 'Otomatik', {maxLength: 120, required: true});
    field(form, 'min_scene_duration_seconds', 'Minimum sahne süresi (saniye)', 'number', 4, {min: 1, max: 120});
    field(form, 'max_scene_duration_seconds', 'Maksimum sahne süresi (saniye)', 'number', 8, {min: 1, max: 120});
    field(form, 'subtitles_enabled', 'Altyazı planlansın', 'checkbox', true);
    field(form, 'background_music_enabled', 'Arka plan müziği planlansın', 'checkbox', false);
    }
    form.append(make('p', GEN ? 'Proje oluşturduktan sonra Senaryo aşamasını açabilirsiniz.' : 'Proje oluşturduktan sonra “Metni yapıştır” ekranında kendi metninizi yapıştırın; ardından Seslendirme → Altyazı → Sahne planı → Medyayı Tamamla → Video.', 'note'));
    const submit = make('button', 'Proje Oluştur'); submit.type = 'submit';
    form.append(submit); container.append(form);
    form.addEventListener('submit', async event => {
      event.preventDefault(); errors(form); busy(form, true);
      feedback.textContent = 'Proje ve klasörleri oluşturuluyor…';
      const data = {};
      for (const input of form.querySelectorAll('input, textarea, select')) {
        data[input.name] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
      }
      const transcript = (data.reference_transcript || '').trim(); delete data.reference_transcript;
      try {
        const project = await request('/api/projects', 'POST', data);
        if (transcript) await request(`/api/projects/${project.id}/source/transcript`, 'PUT', {transcript});
        window.location.assign(GEN ? `/projects/${project.id}` : `/projects/${project.id}/script`);
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
          card.append(information([['Dil', project.language_label], ...(GEN ? [['Hedef süre', `${project.target_duration_minutes} dakika`]] : []), ['Durum', project.status_label], ...timestamps(project)]));
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
        ...(GEN ? [['Konu', project.topic], ['Referans YouTube URL’si', project.reference_url || 'Eklenmedi']] : []),
['Dil', project.language_label], ...(GEN ? [['Hedef video süresi', `${project.target_duration_minutes} dakika`]] : []),
        ...(GEN ? [['Senaryo motoru', project.script_engine_label], ['İçerik türü / stil', project.content_style]] : []),
        ['Sahne süresi', `${project.min_scene_duration_seconds} – ${project.max_scene_duration_seconds} saniye`],
        ['Altyazı', project.subtitles_enabled ? 'Açık' : 'Kapalı'], ['Arka plan müziği', project.background_music_enabled ? 'Açık' : 'Kapalı'],
        ['Durum', project.status_label], ...timestamps(project)
      ]));
      const edit = make('details', '', 'settings-panel');
      const planning = make('a', 'Görsel / Kurgu Planı ve Kalite Kontrolü', 'back'); planning.href = `/projects/${project.id}/production`; detail.append(planning);
      edit.append(make('summary', 'Proje bilgilerini düzenle'));
      const form = make('form'); form.id = 'edit-project-form'; form.noValidate = true;
      field(form, 'name', 'Proje adı', 'text', project.name, {maxLength: 120, required: true});
      if (GEN) {
        field(form, 'topic', 'Konu', 'textarea', project.topic, {maxLength: 5000, required: true});
        field(form, 'script_engine', 'Senaryo motoru (Script Engine)', 'select', project.script_engine, {choices: [['gemini', 'Gemini (ücretsiz kota — önerilen)'], ['ollama', 'Ollama (yerel yedek)'], ['openai', 'OpenAI']]});
      }
      const save = make('button', 'Bilgileri Kaydet'); save.type = 'submit'; form.append(save); edit.append(form); detail.append(edit);
      form.addEventListener('submit', async event => {
        event.preventDefault(); errors(form); busy(form, true); feedback.textContent = 'Proje bilgileri kaydediliyor…';
        try {
          const changes = {name: form.elements.namedItem('name').value};
          if (GEN) Object.assign(changes, {topic: form.elements.namedItem('topic').value, script_engine: form.elements.namedItem('script_engine').value});
          const updated = await request(`/api/projects/${id}`, 'PATCH', changes);
          render(updated); feedback.textContent = 'Proje bilgileri kaydedildi.';
        } catch (error) { feedback.textContent = error.message; errors(form, error.fields); busy(form, false); }
      });
      if (GEN) detail.append(sourceCard(project));
      detail.append(make('h2', 'Üretim aşamaları'), make('p', GEN ? 'Senaryo aşamasını açıp metninizi hazırlayabilirsiniz.' : 'Sıra: Metni yapıştır → Seslendirme → Altyazı → Sahne planı → Medyayı Tamamla → Video → YouTube.', 'note'));
      const pipeline = make('ol', '', 'pipeline'); pipeline.id = 'project-pipeline';
      // Owner's flow: Metin → Seslendirme → Altyazı → Sahne planı → Medya → Video.
      const flow = ['Senaryo', 'Seslendirme', 'Altyazı', 'Sahne Planı', 'Stok Medya', 'Render'];
      const stages = GEN ? project.pipeline : [...project.pipeline].sort((a, b) => flow.indexOf(a.name) - flow.indexOf(b.name));
      for (const stage of stages) {
        if (!GEN && (stage.name === 'Konsept' || stage.name === 'Metadata' || stage.name === 'Export')) continue;
        const item = make('li'); item.append(make('h3', !GEN && stage.name === 'Senaryo' ? 'Metin' : stage.name), make('span', stage.status, 'badge'), make('p', stage.message, 'note'));
        if (stage.name === 'Senaryo') item.append(link(GEN ? 'Senaryoyu Aç' : 'Metni Yapıştır', `/projects/${id}/script`, 'action-link'));
        if (stage.name === 'Sahne Planı' || stage.name === 'Stok Medya') item.append(link(stage.name === 'Sahne Planı' ? 'Sahne Planını Aç' : 'Medyayı Tamamla', `/projects/${id}/production`, 'action-link'));
        if(stage.name==='Seslendirme')item.append(link('Seslendirmeyi Aç',`/projects/${id}/narration`,'action-link'));
        if(stage.name==='Render')item.append(link('Video Oluştur / Render',`/projects/${id}/render`,'action-link'));
        if(stage.name==='Altyazı')item.append(link('Altyazı ve Zamanlama',`/projects/${id}/subtitles`,'action-link'));
        pipeline.append(item);
      }
      // Last step of every project: YouTube title, description, tags.
      const youtube = make('li', '', 'pipeline-youtube'); youtube.id = 'project-youtube';
      youtube.append(make('h3', 'YouTube'), make('span', 'Başlık · Açıklama · Etiketler', 'badge'),
        make('p', '5 başlık önerisi (en fazla 97 karakter), bölüm zamanlı açıklama ve etiketler (en fazla 500 karakter), yapay zekâ dil kontrolüyle.', 'note'),
        link('YouTube Başlık, Açıklama ve Etiketler', `/projects/${id}/youtube`, 'action-link'));
      pipeline.append(youtube);
      detail.append(pipeline);
      const removeButton = make('button', 'Projeyi Sil', 'danger'); removeButton.type = 'button';
      removeButton.addEventListener('click', () => remove(project, removeButton, async () => window.location.assign('/projects')));
      detail.append(removeButton);
    }
    async function load() {
      feedback.textContent = 'Proje yükleniyor…';
      try { render(await request(`/api/projects/${id}`)); feedback.textContent = 'Proje bilgileri yüklendi.'; }
      catch (error) { feedback.textContent = error.message; }
    }
    const retry = make('button', 'Projeyi tekrar yükle', 'secondary'); retry.type = 'button';
    retry.addEventListener('click', load); container.append(retry); load();
  }
}
