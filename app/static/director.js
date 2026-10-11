/* Claude director panel on the script page: purpose → script → approval → edit plan. */
if (/^\/projects\/[^/]+\/script$/.test(window.location.pathname)) {
  const id = window.location.pathname.split('/')[2];
  const api = `/api/projects/${id}/director`;
  const root = document.querySelector('#script-content');
  const names = {gemini: 'Gemini', ollama: 'Ollama', openai: 'OpenAI'};
  const fields = [['audience', 'Hedef kitle'], ['main_message', 'Ana mesaj'], ['tone', 'Ton'], ['hook', 'Açılış kancası'],
    ['viewer_promise', 'İzleyiciye vaat'], ['content_type', 'İçerik türü'], ['summary', 'Özet']];
  const order = ['purpose', 'script', 'approve', 'plan', 'done'];
  let timer = null, data = null;
  function node(tag, text, className) { const item = document.createElement(tag); if (text) item.textContent = text; if (className) item.className = className; return item; }
  async function request(url, method = 'GET', body) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(15000), headers: {'Content-Type': 'application/json', 'X-AI-Video-Studio': 'projects'}, ...(body !== undefined ? {body: JSON.stringify(body)} : {})}); }
    catch { throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini açık tutup sayfayı yenileyin; yönetmen arka planda sürüyor olabilir.'); }
    let json; try { json = await response.json(); } catch { throw new Error('Yerel yanıt okunamadı. Sayfayı yeniden açın.'); }
    if (!response.ok) throw new Error(json.message || 'Yönetmen işlemi tamamlanamadı. Tekrar deneyin.');
    return json;
  }
  const panel = node('section', '', 'settings-panel'); panel.id = 'director-panel';
  panel.append(node('h2', 'Claude Yönetmen'), node('p', 'Yalnızca konu, dil ve hedef süre yeterli. Claude sırayla videonun amacını belirler, senaryoyu yazar, kurgu planını (sahneler, görsel türü, arama sözcükleri, “mutlaka göster / gösterme” notları) çıkarır.', 'note'));
  const status = node('p', '', 'provider-status'); status.id = 'director-status'; status.setAttribute('role', 'status');
  const steps = node('ol'); steps.id = 'director-steps';
  const autoLabel = node('label', ' Senaryoyu otomatik onayla (kapatırsanız senaryoyu okuyup siz onaylarsınız)');
  const auto = node('input'); auto.type = 'checkbox'; auto.id = 'director-auto-approve'; auto.checked = true; autoLabel.prepend(auto);
  const actions = node('div', '', 'settings-actions');
  const run = node('button', 'Yönetmeni Başlat'); run.type = 'button'; run.id = 'director-run'; actions.append(run);
  const backups = node('div', '', 'settings-actions'); backups.id = 'director-backups'; backups.hidden = true;
  const purpose = node('details', '', 'settings-panel'); purpose.id = 'director-purpose';
  purpose.append(node('summary', 'Videonun amacı (düzenlenebilir)'));
  const purposeForm = node('form'); purposeForm.noValidate = true; purpose.append(purposeForm);
  for (const [name, label] of fields) {
    const group = node('div', '', 'setting-field'); const caption = node('label', label); caption.htmlFor = `director-${name}`;
    const control = node(name === 'summary' ? 'textarea' : 'input'); control.id = `director-${name}`; control.name = name;
    if (name === 'summary') control.rows = 3; else control.type = 'text';
    group.append(caption, control); purposeForm.append(group);
  }
  const savePurpose = node('button', 'Amacı Kaydet'); savePurpose.type = 'button'; purposeForm.append(savePurpose);
  purposeForm.append(node('p', 'Amacı değiştirip kaydederseniz, senaryo bir sonraki çalıştırmada bu özete göre yazılır.', 'note'));
  panel.append(status, steps, autoLabel, actions, backups, purpose);
  root.prepend(panel);
  const back = root.querySelector('a.back'); if (back) back.after(panel);

  function render(view) {
    data = view; const state = view.state || {status: 'idle'};
    const busy = ['queued', 'running'].includes(state.status);
    status.textContent = state.status === 'idle' ? (view.options.claude_ready ? 'Hazır. Yönetmeni Başlat deyin.' : 'Önce Ayarlar → Claude bölümünde API anahtarını kaydedin.')
      : `${state.message || ''}`;
    steps.replaceChildren();
    const current = order.indexOf(state.step);
    for (const key of order.slice(0, 4)) {
      const index = order.indexOf(key);
      const mark = state.status === 'done' || index < current ? '✓' : index === current ? (state.status === 'error' ? '✗' : state.status === 'waiting' ? '…' : '⏳') : '·';
      steps.append(node('li', `${mark} ${view.steps[key]}`));
    }
    run.textContent = state.status === 'error' || state.status === 'waiting' ? 'Yönetmeni Devam Ettir' : state.status === 'done' ? 'Yönetmeni Yeniden Çalıştır' : 'Yönetmeni Başlat';
    run.disabled = busy || !view.options.claude_ready && !(state.provider && state.provider !== 'claude');
    savePurpose.disabled = busy;
    if (view.purpose) for (const [name] of fields) { const control = purposeForm.elements.namedItem(name); if (document.activeElement !== control) control.value = view.purpose[name] || ''; }
    purpose.hidden = !view.purpose;
    backups.replaceChildren();
    const offer = state.status === 'error' && state.offer_backup ? view.options.backup_providers : [];
    backups.hidden = !offer.length;
    if (offer.length) backups.append(node('p', 'Claude bu adımı tamamlayamadı. İsterseniz yedek motorla devam edebilirsiniz (kendiliğinden geçilmez):'));
    for (const name of offer) {
      const b = node('button', `${names[name]} ile devam et`); b.type = 'button';
      b.addEventListener('click', () => {
        if (window.confirm(`Claude yerine ${names[name]} kullanılsın mı? ${name === 'ollama' ? 'Yerel çalışır.' : 'API kotası veya ücret kullanabilir.'}`)) start(name);
      });
      backups.append(b);
    }
    clearTimeout(timer);
    if (busy) timer = setTimeout(load, 2000);
  }
  async function load() {
    try { render(await request(api)); } catch (error) { status.textContent = error.message; }
  }
  async function start(provider = 'claude') {
    const state = data?.state || {};
    const resuming = ['error', 'waiting'].includes(state.status);
    if (provider !== 'ollama' && !window.confirm('Yönetmen Claude API’sini kullanır ve ücretlidir (3 dakikalık video için tahmini birkaç kuruş–1 dolar arası; kesin tutar bu sayfada gösterilir). Devam edilsin mi?')) return;
    let replace = false;
    if (!resuming && document.querySelector('#script-versions option')) {
      if (!window.confirm('Bu projede senaryo var. Yönetmen yeni bir sürüm yazar; eski sürümler silinmez. Devam edilsin mi?')) return;
      replace = true;
    }
    run.disabled = true;
    try {
      await request(`${api}/run`, 'POST', {cost_confirmed: true, auto_approve: auto.checked, confirm_replace: replace, provider});
      await load();
    } catch (error) { status.textContent = error.message; run.disabled = false; }
  }
  run.addEventListener('click', () => start(data?.state?.provider && data.state.status !== 'done' && data.state.provider !== 'claude' ? data.state.provider : 'claude'));
  savePurpose.addEventListener('click', async () => {
    const body = {}; for (const [name] of fields) body[name] = purposeForm.elements.namedItem(name).value;
    try { const r = await request(`${api}/purpose`, 'PUT', body); status.textContent = r.message; await load(); }
    catch (error) { status.textContent = error.message; }
  });
  load();
}
