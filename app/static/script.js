/* Part 4: background jobs are polled locally; no browser-held provider credentials. */
if (/^\/projects\/[^/]+\/script$/.test(window.location.pathname)) {
  const id = window.location.pathname.split('/')[2];
  const base = `/api/projects/${id}/script`;
  const root = document.querySelector('#script-content'); root.hidden = false;
  let view = null, project = null, editing = false, dirty = false, timer = null, inFlight = false;
  const active = ['queued', 'analyzing', 'planning', 'generating', 'checking'];
  const phases = {queued: 'Sırada', concept: 'Konsept analizi', concept_complete: 'Konsept hazır', plan: 'Bölüm planı', plan_complete: 'Plan hazır', section: 'Bölüm yazımı', section_saved: 'Bölüm kaydedildi', continuity: 'Bağlam özeti', context_saved: 'Bağlam kaydedildi', duration_correction: 'Hedef süre düzeltiliyor', duration_corrected: 'Süre kontrol edildi', review: 'Tutarlılık kontrolü', review_saved: 'Kontrol kaydedildi', saving: 'Sürüm kaydı', done: 'Tamamlandı'};
  function node(tag, text, className) { const item = document.createElement(tag); if (text) item.textContent = text; if (className) item.className = className; return item; }
  const back = node('a', '← Projeye dön', 'back'); back.href = `/projects/${id}`; root.append(back);
  const feedback = node('p', 'Senaryo yükleniyor…', 'provider-status'); feedback.id = 'script-feedback'; feedback.setAttribute('role', 'status'); root.append(feedback);
  // Claude failed: offer configured backups, never switch silently.
  const fallback = node('div', '', 'settings-actions'); fallback.id = 'script-fallback'; fallback.hidden = true; root.append(fallback);
  const usage = node('p', '', 'note'); usage.id = 'script-ai-usage'; root.append(usage);
  const engineNames = {gemini: 'Gemini', ollama: 'Ollama', openai: 'OpenAI'};
  function renderFallback(data) {
    const job = data.job; fallback.replaceChildren();
    const offer = job?.status === 'error' && job.provider === 'claude' ? (data.director?.backup_providers || []) : [];
    fallback.hidden = !offer.length;
    if (!offer.length) return;
    fallback.append(node('p', 'Claude bu işlemi tamamlayamadı. İsterseniz aynı işlemi yedek motorla yeniden başlatabilirsiniz:'));
    for (const name of offer) {
      const b = node('button', `${engineNames[name]} ile devam et`); b.type = 'button';
      b.addEventListener('click', () => {
        if (!window.confirm(`Claude yerine ${engineNames[name]} kullanılsın mı? Aynı işlem baştan başlar; ${name === 'ollama' ? 'yerel çalışır' : 'API kotası veya ücret kullanabilir'}.`)) return;
        form.elements.provider.value = name; start(job.action === 'analyze' ? 'analyze' : 'generate');
      });
      fallback.append(b);
    }
  }
  async function loadUsage() {
    try { const u = await request(`/api/projects/${id}/ai-usage`); usage.textContent = u.total_calls ? `Bu projede Claude/AI tahmini maliyeti: $${u.total_cost_usd.toFixed(4)} · ${u.total_calls} çağrı` : ''; }
    catch { usage.textContent = ''; }
  }
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
  field('provider', 'Senaryo Motoru', 'select', 'gemini', [['gemini', 'Gemini (ücretsiz kota)'], ['ollama', 'Ollama (yerel yedek)'], ['openai', 'OpenAI'], ['claude', 'Claude (ücretli)']]);
  field('mode', 'Çalışma modu', 'select', 'original', [['original', 'Konseptten Özgün Senaryo'], ['translate_owned', 'Kendi Metnimi Seçili Dile Çevir']]);
  field('language', 'Hedef Dil', 'select', 'de', [['de', 'Almanca'], ['es', 'İspanyolca'], ['en', 'İngilizce'], ['fr', 'Fransızca'], ['tr', 'Türkçe']]);
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
  const ownership = field('owns_text', 'Bu metnin bana ait olduğunu ve seçili dile çevrilmesini istediğimi onaylıyorum', 'checkbox', false);
  field('words_per_minute_min', 'Minimum konuşma hızı (kelime/dakika)', 'number', 125);
  field('words_per_minute_max', 'Maksimum konuşma hızı (kelime/dakika)', 'number', 145);
  // Language default speech rate until the user edits a rate field.
  let rateEdited = false;
  for (const name of ['words_per_minute_min', 'words_per_minute_max']) form.elements[name].addEventListener('input', () => { rateEdited = true; });
  function applyLanguageRate() { if (rateEdited) return; const [low, high] = scriptSpeechRate(form.elements.language.value); form.elements.words_per_minute_min.value = low; form.elements.words_per_minute_max.value = high; }
  form.elements.language.addEventListener('change', applyLanguageRate);
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
  const toolPanel = node('section', '', 'settings-panel'); toolPanel.id = 'script-tools';
  toolPanel.append(node('h2', 'YouTube kalite araçları'), node('p', 'Seçili senaryo sürümünü analiz eder. Öneriler ayrı gösterilir; metin ancak seçiminizle yeni sürüme uygulanır. Bulut AI işlemleri API kotası veya ücret kullanabilir.', 'note'));
  const toolActions = node('div', '', 'settings-actions'); const toolButtons = [];
  for (const [kind, label] of [['retention', 'Retention Analizi'], ['hooks', '3 Açılış Hooku'], ['alternatives', 'A/B Alternatifleri'], ['claims', 'İddia / Bilgi İncelemesi']]) {
    const item = node('button', label); item.type = 'button'; toolButtons.push(item);
    item.addEventListener('click', () => runTool(kind)); toolActions.append(item);
  }
  const toolResults = node('div'); toolPanel.append(toolActions, toolResults); root.append(toolPanel);
  function costConfirm(provider) { return provider === 'ollama' || window.confirm('Bu işlem seçilen bulut API’sinde kota veya ücret kullanabilir. Bu işlem için devam etmek istiyor musunuz?'); }
  async function runTool(kind) {
    if (dirty) { feedback.textContent = 'Önce metin değişikliklerinizi Kaydet deyin.'; return; }
    const provider = form.elements.provider.value;
    if (!costConfirm(provider)) return;
    await mutate(() => request(`${base}/tools/${kind}`, 'POST', {provider, cost_confirmed: true}));
  }
  function renderTools() {
    toolResults.replaceChildren();
    const labels = {retention: 'Retention Analizi', hooks: 'Açılış Hookları', alternatives: 'A/B Alternatifleri', claims: 'İddia / Bilgi İncelemesi'};
    const optionLabels = {opening: 'Açılış', title: 'Başlık', thumbnail_text: 'Küçük resim yazısı', intro: 'Giriş', CTA: 'CTA', description: 'Açıklama'};
    for (const artifact of view.artifacts || []) {
      if (artifact.kind === 'visual') continue;
      if (artifact.version_id !== view.current?.id) continue;
      const panel = node('details'); panel.append(node('summary', labels[artifact.kind] || 'Analiz sonucu'));
      const result = artifact.result;
      const inputs = [];
      if (artifact.kind === 'retention' || artifact.kind === 'hooks') {
        if (result.ratings) { const ratings = node('ul'); for (const [name, rating] of Object.entries(result.ratings)) ratings.append(node('li', `${({opening_10_30_seconds:'İlk 10–30 saniye',hook:'Hook gücü',slow_sections:'Yavaş bölümler',repetition:'Tekrar',transitions:'Geçişler',overload:'Bilgi yoğunluğu',pacing:'Tempo',section_length:'Bölüm uzunluğu',curiosity:'Merak',payoff:'Vaat karşılığı',ending:'Bitiş'})[name]}: ${rating}`)); panel.append(ratings); }
        const items = result.suggestions || result.hooks;
        items.forEach((item, index) => { const label = node('label'); const input = node('input'); input.type = artifact.kind === 'hooks' ? 'radio' : 'checkbox'; input.name = artifact.id; input.value = index; inputs.push(input); label.append(input, document.createTextNode(typeof item === 'string' ? item : `${item.scope}: ${item.suggestion}`)); panel.append(label, node('br')); });
        const apply = node('button', 'Seçilenleri yeni sürüme uygula'); apply.type = 'button';
        apply.addEventListener('click', async () => { const selection = inputs.filter(item => item.checked).map(item => Number(item.value)); if (!selection.length || !discard() || !confirmReplace() || !costConfirm(view.current.provider)) return; await mutate(() => request(`${base}/tools/${artifact.id}/apply`, 'POST', {selection, confirm_replace_approved: view.current.status === 'approved', cost_confirmed: true})); });
        panel.append(apply, node('p', 'Hiçbir öneriyi seçmeden mevcut senaryonuzu kullanmaya devam edebilirsiniz.', 'note'));
      } else if (artifact.kind === 'alternatives') {
        const selects = {};
        for (const [key, label] of Object.entries(optionLabels)) {
          panel.append(node('p', label)); const select = node('select'); selects[key] = select;
          result[key].forEach((text, index) => { const option = node('option', text); option.value = index; select.append(option); });
          if (result.selected?.[key] !== undefined) select.value = result.selected[key];
          panel.append(select);
        }
        const save = node('button', 'Alternatif seçimlerini kaydet'); save.type = 'button';
        save.addEventListener('click', () => mutate(() => request(`${base}/tools/${artifact.id}/select`, 'POST', {choices: Object.fromEntries(Object.entries(selects).map(([key, value]) => [key, Number(value.value)]))})));
        panel.append(save, node('p', 'Seçimler saklanır; senaryo metni kendiliğinden değiştirilmez.', 'note'));
      } else if (artifact.kind === 'claims') {
        panel.append(node('p', 'Bu bir doğrulanmış bilgi raporu değildir. Kaynaklar bağımsız olarak kontrol edilmelidir.', 'note'));
        for (const item of result.claims) panel.append(node('p', `${item.statement} — ${item.status} ${item.reason}`));
        if (!result.claims.length) panel.append(node('p', 'AI işaretlenecek iddia bulmadı; bu doğruluk garantisi değildir.'));
      }
      toolResults.append(panel);
    }
  }
  form.addEventListener('submit', event => event.preventDefault());
  form.elements.mode.addEventListener('change', modeFields);
  form.addEventListener('input', () => updateMetrics());
  editor.addEventListener('input', () => { dirty = true; updateMetrics(); syncButtons(); });
  function modeFields() {
    const translate = form.elements.mode.value === 'translate_owned';
    for (const item of [owned, ownership]) item.parentElement.hidden = !translate;
    for (const item of [notes, reference, contentType]) item.parentElement.hidden = translate;
    syncButtons();
  }
  function options() {
    const result = {};
    for (const element of form.elements) if (element.name) result[element.name] = element.type === 'checkbox' ? element.checked : element.type === 'number' ? Number(element.value) : element.value;
    if (result.mode === 'original') { result.owned_text = ''; result.owns_text = false; }
    else { result.reference_notes = ''; result.reference_text = ''; result.content_type = ''; }
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
    for (const item of toolButtons) item.disabled = Boolean(working || !view?.current || dirty);
    for (const item of toolResults.querySelectorAll('button,input,select')) item.disabled = Boolean(working);
  }
  function updateMetrics() {
    const options = {language: form.elements.language.value, ...(view?.current?.options || view?.job?.options || {words_per_minute_min: Number(form.elements.words_per_minute_min.value), words_per_minute_max: Number(form.elements.words_per_minute_max.value)})};
    const minutes = view?.current?.report?.target_minutes ?? view?.target_minutes ?? 0;
    const measured = scriptDurationMetrics(editor.value, minutes, options);
    if (!dirty && view?.current?.report?.word_count === measured.word_count) measured.estimated_minutes = view.current.report.estimated_minutes;
    const real = !dirty && view?.narration?.duration && view.narration.version_id === view?.current?.id ? view.narration.duration : null;
    metrics.textContent = `${measured.word_count} kelime · Tahmini seslendirme: ${scriptClock(measured.estimated_minutes * 60)} dk (~${measured.spoken_rate} kelime/dk)${real ? ` · Gerçek seslendirme: ${scriptClock(real)} dk` : ''} · Hedef: ${minutes} dakika (${measured.target_word_min}–${measured.target_word_max} kelime)`;
    warnings.replaceChildren();
    if (view?.current) {
      const messages = dirty ? ['Elle düzenlenen metni onaylamadan önce tutarlılık ve gerçek bilgiler açısından inceleyin.'] : view.current.report.review_messages;
      for (const message of scriptReviewMessages(messages, measured)) warnings.append(node('li', message));
    }
  }
  function render(data, restoreForm = false) {
    const changed = view?.current?.id !== data.current?.id;
    view = data;
    if (restoreForm) {
      const saved = data.job && (active.includes(data.job.status) || ['error', 'analyzed'].includes(data.job.status)) ? data.job.options : data.current?.options || data.job?.options;
      if (saved) for (const [name, value] of Object.entries(saved)) { const element = form.elements.namedItem(name); if (element) { if (element.type === 'checkbox') element.checked = value; else element.value = value; } }
      else { form.elements.provider.value = data.default_provider; form.elements.language.value = project.language; applyLanguageRate(); }
    }
    if (!dirty && (changed || restoreForm || !editing)) editor.value = data.current?.text || data.job?.partial_text || '';
    if (changed) { editing = false; dirty = false; }
    const job = data.job;
    progress.value = job?.progress.percent || 0;
    progressText.textContent = job ? `${job.status_label} · ${phases[job.progress.phase] || 'İşlem'} · ${job.progress.percent}%${job.progress.plan ? ` · ${job.completed_sections}/${job.progress.plan.sections.length} bölüm` : ''}${job.progress.section_index ? ` · Bölüm ${job.progress.section_index}` : ''}` : 'Henüz senaryo oluşturulmadı.';
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
    feedback.textContent = job?.status === 'error' ? `${job.error_message}${job.progress.section_index ? ` Kesilen bölüm: ${job.progress.section_index}.` : ''}` : job && active.includes(job.status) ? 'İşlem sürüyor. Mevcut senaryo ve sürümler korunuyor.' : data.current ? 'Senaryo sürümünüz hazır. Metni inceleyip düzenleyebilir ve onaylayabilirsiniz.' : job?.status_label || 'Konuya uygun analiz veya senaryo oluşturma ile başlayın.';
    renderTools(); modeFields(); updateMetrics(); syncButtons(); renderFallback(data); loadUsage();
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
    if (!costConfirm(data.provider)) return;
    await mutate(async () => { await request(`${base}/${action}`, 'POST', data); dirty = false; editing = false; });
  }
  async function resumeJob() {
    const repair = ['visual','visual_scene'].includes(view.job.action) && view.job.progress.visual_repair?.status === 'awaiting_cost_confirmation';
    if (!discard() || (['generate','apply'].includes(view.job.action) && !confirmReplace())) return;
    if (repair ? !window.confirm('Aynı sağlayıcıyla bir görsel metadata düzeltmesi ek API kotası veya ücret kullanabilir. Bu ikinci çağrıyı onaylıyor musunuz?') : !costConfirm(view.job.provider)) return;
    await mutate(() => request(`${base}/jobs/${view.job.id}/resume`, 'POST', {confirm_replace_approved: view.current?.status === 'approved', ...(repair ? {visual_repair_cost_confirmed:true} : {})}));
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
