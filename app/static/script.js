/* Part 4: background jobs are polled locally; no browser-held provider credentials. */
if (/^\/projects\/[^/]+\/script$/.test(window.location.pathname)) {
  const id = window.location.pathname.split('/')[2];
  const base = `/api/projects/${id}/script`;
  const root = document.querySelector('#script-content'); root.hidden = false;
  let view = null, project = null, editing = false, dirty = false, timer = null, inFlight = false;
  const active = ['queued', 'analyzing', 'planning', 'generating', 'checking'];
  const phases = {queued: 'Sırada', concept: 'Konsept analizi', concept_complete: 'Konsept hazır', plan: 'Bölüm planı', plan_complete: 'Plan hazır', section: 'Bölüm yazımı', section_saved: 'Bölüm kaydedildi', continuity: 'Bağlam özeti', context_saved: 'Bağlam kaydedildi', review: 'Tutarlılık kontrolü', review_saved: 'Kontrol kaydedildi', saving: 'Sürüm kaydı', done: 'Tamamlandı'};
  function node(tag, text, className) { const item = document.createElement(tag); if (text) item.textContent = text; if (className) item.className = className; return item; }
  const back = node('a', '← Projeye dön', 'back'); back.href = `/projects/${id}`; root.append(back);
  const feedback = node('p', 'Senaryo yükleniyor…', 'provider-status'); feedback.id = 'script-feedback'; feedback.setAttribute('role', 'status'); root.append(feedback);
  const form = node('form', '', 'settings-panel script-form'); form.id = 'script-options'; form.noValidate = true;
  function field(name, label, type, value, choices = []) {
    const group = node('div', '', 'setting-field'); const caption = node('label', label); caption.htmlFor = `script-${name}`;
    const control = node(type === 'textarea' ? 'textarea' : type === 'select' ? 'select' : 'input'); control.name = name; control.id = `script-${name}`;
    if (type === 'select') for (const [key, text] of choices) { const option = node('option', text); option.value = key; control.append(option); }
    else if (type !== 'textarea') control.type = type;
    if (type === 'checkbox') control.checked = value; else control.value = value;
    if (type === 'textarea') { control.rows = name === 'owned_text' ? 10 : 4; control.maxLength = {instructions: 4000, reference_notes: 8000, reference_text: 30000, owned_text: 100000}[name]; }
    if (type === 'number') { control.min = 80; control.max = 220; control.step = 1; }
    if (type === 'text') control.maxLength = name === 'audience' ? 500 : 150;
    group.append(caption, control); form.append(group); return control;
  }
  field('provider', 'Senaryo Motoru', 'select', 'gemini', [['gemini', 'Gemini'], ['ollama', 'Ollama'], ['openai', 'OpenAI']]);
  field('mode', 'Çalışma modu', 'select', 'original', [['original', 'Konseptten Özgün Senaryo'], ['translate_owned', 'Kendi Metnimi Almancaya Çevir']]);
  field('language', 'Hedef dil', 'select', 'de', [['de', 'Almanca'], ['tr', 'Türkçe'], ['en', 'İngilizce']]);
  const target = node('p', '', 'note'); form.append(target);
  const contentType = field('content_type', 'İçerik türü — boş bırakırsanız AI otomatik algılasın', 'text', ''); contentType.placeholder = 'Otomatik Algıla';
  const formats = node('datalist'); formats.id = 'script-format-examples';
  for (const value of ['Bilgilendirici', 'Belgesel', 'Liste', 'İnceleme', 'Eğitim', 'Haber/Yorum', 'Hikâye']) { const option = node('option'); option.value = value; formats.append(option); }
  contentType.setAttribute('list', formats.id); form.append(formats, node('p', 'Bunlar örnektir; istediğiniz içerik türünü yazabilirsiniz. Senaryo planı konuya göre oluşturulur.', 'note'));
  field('tone', 'Ton (serbest seçim)', 'text', 'Otomatik'); field('audience', 'Hedef kitle (isteğe bağlı)', 'text', '');
  field('instructions', 'Ek talimatlar (isteğe bağlı)', 'textarea', '');
  const notes = field('reference_notes', 'Konsept / referans notları (isteğe bağlı)', 'textarea', '');
  const reference = field('reference_text', 'Üçüncü taraf referans metni — yalnızca kavram analizi için', 'textarea', '');
  form.append(node('p', 'Referans URL’sinden içerik alınmaz, video indirilmez. Buradaki notlar/metin yalnızca soyut fikir ve biçim analizi için kullanılır; rakip metni çevrilmez.', 'note'));
  const owned = field('owned_text', 'Size ait kaynak metin', 'textarea', '');
  const ownership = field('owns_text', 'Bu metnin bana ait olduğunu ve Almancaya çevrilmesini istediğimi onaylıyorum', 'checkbox', false);
  field('words_per_minute_min', 'Minimum konuşma hızı (kelime/dakika)', 'number', 125);
  field('words_per_minute_max', 'Maksimum konuşma hızı (kelime/dakika)', 'number', 145);
  const generateActions = node('div', '', 'settings-actions'); const buttons = {};
  function button(label, callback, where = generateActions) { const item = node('button', label); item.type = 'button'; item.addEventListener('click', callback); where.append(item); buttons[label] = item; return item; }
  button('Analiz Et', () => start('analyze')); button('Senaryo Oluştur', () => start('generate')); button('Yeniden Oluştur', () => start('generate'));
  const resume = button('Devam Et', resumeJob); resume.hidden = true;
  form.append(generateActions); root.append(form);
  const progress = node('progress'); progress.id = 'script-progress'; progress.max = 100; progress.value = 0;
  const progressText = node('p', '', 'note'); progressText.id = 'script-progress-text'; root.append(progress, progressText);
  const analysis = node('details', '', 'settings-panel'); analysis.append(node('summary', 'Konsept ve bölüm planı')); const analysisBody = node('div'); analysis.append(analysisBody); root.append(analysis);
  const editorPanel = node('section', '', 'settings-panel script-editor-panel'); editorPanel.append(node('h2', 'Senaryo metni'));
  const metadata = node('p', '', 'note'); metadata.id = 'script-metadata';
  const caption = node('label', 'Metin'); caption.htmlFor = 'script-editor';
  const editor = node('textarea'); editor.id = 'script-editor'; editor.rows = 22; editor.maxLength = 300000; editor.readOnly = true;
  const metrics = node('p', '', 'provider-status'); metrics.id = 'script-metrics';
  const warnings = node('ul', '', 'script-warnings'); warnings.id = 'script-warnings';
  const editActions = node('div', '', 'settings-actions');
  button('Düzenle', () => { editing = true; editor.readOnly = false; editor.focus(); syncButtons(); }, editActions);
  button('Kaydet', saveEdit, editActions); button('Onayla', approve, editActions);
  const versions = node('select'); versions.id = 'script-versions'; const versionLabel = node('label', 'Sürüm seçin'); versionLabel.htmlFor = versions.id;
  versions.addEventListener('change', selectVersion);
  editorPanel.append(metadata, caption, editor, metrics, warnings, editActions, versionLabel, versions,
    node('p', 'Kaydet her zaman yeni bir sürüm oluşturur. Onaylı sürümün metni korunur. İleride sahne planı yalnızca geçerli ve onaylı senaryoyu kullanacak; bu aşamada video üretilmez.', 'note'));
  root.append(editorPanel); button('Sayfayı yenile', () => load(true), root);
  form.addEventListener('submit', event => event.preventDefault());
  form.elements.mode.addEventListener('change', modeFields);
  form.addEventListener('input', () => updateMetrics());
  editor.addEventListener('input', () => { dirty = true; updateMetrics(); syncButtons(); });
  function modeFields() {
    const translate = form.elements.mode.value === 'translate_owned';
    for (const item of [owned, ownership]) item.parentElement.hidden = !translate;
    for (const item of [notes, reference, contentType]) item.parentElement.hidden = translate;
    if (translate) form.elements.language.value = 'de';
    syncButtons();
  }
  function options() {
    const result = {};
    for (const element of form.elements) if (element.name) result[element.name] = element.type === 'checkbox' ? element.checked : element.type === 'number' ? Number(element.value) : element.value;
    if (result.mode === 'original') { result.owned_text = ''; result.owns_text = false; }
    else { result.reference_notes = ''; result.reference_text = ''; result.content_type = ''; result.language = 'de'; }
    return result;
  }
  function confirmReplace() {
    return !view?.current || view.current.status !== 'approved' || window.confirm('Onaylı senaryo yerine yeni çalışma geçerli olacak. Eski onaylı sürüm korunur. Devam edilsin mi?');
  }
  function discard() { return !dirty || window.confirm('Kaydedilmemiş metin değişiklikleri kaldırılacak. Devam edilsin mi?'); }
  async function request(url, method = 'GET', body) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(15000), headers: {'Content-Type': 'application/json', 'X-AI-Video-Studio': 'projects'}, ...(body !== undefined ? {body: JSON.stringify(body)} : {})}); }
    catch { throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini açık tutup Sayfayı yenile deyin; başlamış üretim devam ediyor olabilir.'); }
    let data; try { data = await response.json(); } catch { throw new Error('Yerel yanıt okunamadı. Sayfayı yeniden açın.'); }
    if (!response.ok) throw new Error(data.message || 'Senaryo işlemi tamamlanamadı. Tekrar deneyin.');
    return data;
  }
  function syncButtons() {
    const working = inFlight || (view?.job && active.includes(view.job.status));
    for (const item of form.querySelectorAll('input,textarea,select,button')) item.disabled = Boolean(working);
    buttons['Analiz Et'].disabled = Boolean(working || form.elements.mode.value === 'translate_owned');
    buttons['Yeniden Oluştur'].hidden = !view?.current;
    buttons['Düzenle'].disabled = Boolean(working || !view?.current);
    buttons['Kaydet'].disabled = Boolean(working || !editing || !dirty);
    buttons['Onayla'].disabled = Boolean(working || !view?.current || dirty || view?.current?.status === 'approved');
    versions.disabled = Boolean(working || !view?.versions.length);
    editor.readOnly = Boolean(working || !editing);
    resume.hidden = view?.job?.status !== 'error';
  }
  function updateMetrics() {
    // JavaScript's \w is ASCII; use Unicode letters/numbers for German words.
    const unicodeCount = (editor.value.match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu) || []).length;
    const low = Number(form.elements.words_per_minute_min.value), high = Number(form.elements.words_per_minute_max.value);
    metrics.textContent = `${unicodeCount} kelime · Tahmini seslendirme: ${(unicodeCount / ((low + high) / 2)).toFixed(1)} dakika · Hedef: ${view?.target_minutes || 0} dakika (${Math.ceil((view?.target_minutes || 0) * low)}–${Math.floor((view?.target_minutes || 0) * high)} kelime)`;
  }
  function render(data, restoreForm = false) {
    const changed = view?.current?.id !== data.current?.id;
    view = data;
    if (restoreForm) {
      const saved = data.job && (active.includes(data.job.status) || ['error', 'analyzed'].includes(data.job.status)) ? data.job.options : data.current?.options || data.job?.options;
      if (saved) for (const [name, value] of Object.entries(saved)) { const element = form.elements.namedItem(name); if (element) { if (element.type === 'checkbox') element.checked = value; else element.value = value; } }
      else form.elements.provider.value = data.default_provider;
    }
    if (!dirty && (changed || restoreForm || !editing)) editor.value = data.current?.text || data.job?.partial_text || '';
    if (changed) { editing = false; dirty = false; }
    const job = data.job;
    progress.value = job?.progress.percent || 0;
    progressText.textContent = job ? `${job.status_label} · ${phases[job.progress.phase] || 'İşlem'} · ${job.progress.percent}% · ${job.completed_sections}/${job.progress.plan?.sections.length || 0} bölüm${job.progress.section_index ? ` · Bölüm ${job.progress.section_index}` : ''}` : 'Henüz senaryo oluşturulmadı.';
    metadata.textContent = data.current ? `Sürüm ${data.current.version} · ${data.current.status_label} · ${data.current.provider} · ${data.current.model} · ${data.current.content_type} · ${new Date(data.current.updated_at).toLocaleString('tr-TR', {timeZone: 'Europe/Istanbul'})}` : `Durum: ${data.status} · Motor: ${job?.provider || form.elements.provider.value}`;
    versions.replaceChildren();
    for (const version of data.versions) { const option = node('option', `Sürüm ${version.version} · ${version.provider} · ${version.status_label}`); option.value = version.id; versions.append(option); }
    if (data.current) versions.value = data.current.id;
    analysisBody.replaceChildren();
    if (job?.progress.blueprint) {
      const blueprint = job.progress.blueprint;
      analysisBody.append(node('p', `Algılanan biçim: ${blueprint.content_type}`), node('p', `Konu: ${blueprint.core_topic}`), node('p', `İzleyiciye vaat: ${blueprint.viewer_promise || 'Kaynak anlamı korunur.'}`), node('p', `Açılış: ${blueprint.main_hook || 'Çeviri modu'}`));
      const list = node('ol'); for (const section of job.progress.plan?.sections || []) list.append(node('li', `${section.title}${section.target_words ? ` — yaklaşık ${section.target_words} kelime` : ''}`)); analysisBody.append(list);
    }
    warnings.replaceChildren(); for (const message of data.current?.report?.issues || []) warnings.append(node('li', message));
    feedback.textContent = job?.status === 'error' ? `${job.error_message}${job.progress.section_index ? ` Kesilen bölüm: ${job.progress.section_index}.` : ''}` : data.current ? 'Senaryo sürümünüz hazır. Metni inceleyip düzenleyebilir ve onaylayabilirsiniz.' : job?.status_label || 'Konuya uygun analiz veya senaryo oluşturma ile başlayın.';
    modeFields(); updateMetrics(); syncButtons();
    clearTimeout(timer);
    if (job && active.includes(job.status)) timer = setTimeout(() => load(), 1500);
  }
  async function load(restore = false) {
    if (restore && !discard()) return;
    try {
      if (!project) project = await request(`/api/projects/${id}`);
      target.textContent = `Proje: ${project.name} · Konu: ${project.topic} · Hedef video süresi: ${project.target_duration_minutes} dakika`;
      if (restore) { dirty = false; editing = false; }
      render(await request(base), restore);
    } catch (error) { feedback.textContent = error.message; clearTimeout(timer); }
  }
  async function mutate(action) {
    inFlight = true; syncButtons();
    try { await action(); await load(); } catch (error) { feedback.textContent = error.message; }
    finally { inFlight = false; syncButtons(); }
  }
  async function start(action) {
    if (!discard() || (action === 'generate' && !confirmReplace())) return;
    const data = options(); data.confirm_replace_approved = view?.current?.status === 'approved';
    await mutate(async () => { await request(`${base}/${action}`, 'POST', data); dirty = false; editing = false; });
  }
  async function resumeJob() {
    if (!discard() || !confirmReplace()) return;
    await mutate(() => request(`${base}/jobs/${view.job.id}/resume`, 'POST', {confirm_replace_approved: view.current?.status === 'approved'}));
  }
  async function saveEdit() {
    if (!confirmReplace()) return;
    const text = editor.value;
    await mutate(async () => { await request(`${base}/versions`, 'POST', {text, base_version_id: view.current.id, confirm_replace_approved: view.current.status === 'approved'}); dirty = false; editing = false; });
  }
  async function approve() {
    if (!window.confirm('Bu sürümü son senaryo olarak onaylıyor musunuz? Gerçek bilgileri, özgünlüğü ve dili kontrol etmiş olmalısınız.')) return;
    await mutate(() => request(`${base}/versions/${view.current.id}/approve`, 'POST', {confirm: true}));
  }
  async function selectVersion() {
    const selected = versions.value;
    if (!discard() || !confirmReplace()) { versions.value = view.current.id; return; }
    await mutate(async () => { await request(`${base}/versions/${selected}/select`, 'POST', {confirm_replace_approved: view.current?.status === 'approved'}); dirty = false; editing = false; });
  }
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  load(true);
}
