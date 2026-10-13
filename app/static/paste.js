/* “Metni yapıştır”: the owner's own narration text (AI script writing is off).
   Markers like [GÖRSEL: …] are shown coloured and never reach narration/subtitles. */
if (/^\/projects\/[^/]+\/script$/.test(window.location.pathname) && document.body.dataset.scriptGeneration !== '1') {
  const id = window.location.pathname.split('/')[2], base = `/api/projects/${id}/script`;
  const root = document.querySelector('#script-content'); root.hidden = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
  const LANG = {de: 'Almanca', en: 'İngilizce', es: 'İspanyolca', fr: 'Fransızca', tr: 'Türkçe'};
  const KNOWN = /^(G[ÖO]RSEL|HAR[İI]TA|SAYI|[ÇC][İI]ZELGE|KAR[ŞS]ILA[ŞS]TIR|L[İI]STE|ROTA|[İI]MPARATORLUK|YAKINLA[ŞS]|[İI][ŞS]ARETLE|[ÖO]NCE\W?SONRA|[İI]KON|ORAN|HANEDAN|B[İI]LG[İI])\s*:\s*\S/i;
  const plainUpper = text => text.toLocaleUpperCase('tr-TR');
  async function request(url, method = 'GET', body) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(30000), headers: {'Content-Type': 'application/json', 'X-AI-Video-Studio': 'projects'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})}); }
    catch { throw new Error('Uygulamaya ulaşılamadı. Uygulama penceresini açık tutup tekrar deneyin.'); }
    let data; try { data = await response.json(); } catch { throw new Error('Yanıt okunamadı. Sayfayı yenileyin.'); }
    if (!response.ok) { const e = new Error(data.message || 'İşlem tamamlanamadı.'); e.status = response.status; throw e; }
    return data;
  }
  const back = node('a', '← Projeye dön', 'back'); back.href = `/projects/${id}`;
  const status = node('p', 'Metin yükleniyor…', 'provider-status'); status.id = 'paste-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const panel = node('section', '', 'settings-panel'); panel.id = 'paste-panel';
  panel.append(node('h2', 'Metni yapıştır'), node('p', 'Senaryonuzu buraya yapıştırın. Fazla boşluklar, Markdown işaretleri (#, **, -, 1.) ve başlık/numara satırları otomatik temizlenir; seslendirme ve altyazı bu metni kelimesi kelimesine kullanır. İsterseniz köşeli parantezle not ekleyin — bunlar okunmaz, altyazıya da girmez: [GÖRSEL: airplane cockpit at night] o cümlede aranacak görüntü; [HARİTA: Bermuda Triangle] harita; [SAYI: %40] büyüyen sayı; [ÇİZELGE: 1945, 1962, 1991] zaman çizelgesi; [KARŞILAŞTIR: Rom | Karthago] karşılaştırma; [LİSTE: Stürme; Strömungen; Fehler] madde listesi; [ROTA: Ninive > Babil > Kudüs] haritada rota; [İMPARATORLUK: Assyrien 911-612 v. Chr.] zamanla büyüyen sınır; [YAKINLAŞ: Babil] dünyadan yere yakınlaşma; [İŞARETLE: Tapınağın sütunları] sahnenin görselinde daire/ok; [ÖNCESONRA: Antik liman | Bugünkü kıyı] iki görsel arasında perde; [İKON: 10000 asker] çoğalan ikonlar; [ORAN: %40 kıyıda yaşıyor] pasta grafik; [HANEDAN: Davud > Süleyman > Rehavam] hanedan ağacı; [BİLGİ: kısa metin] “Biliyor muydunuz?” kartı. İşaret, hemen önündeki cümleye (paragraf başındaysa sonraki cümleye) bağlanır.', 'note'));
  // Highlight editor: a coloured backdrop behind a transparent textarea.
  const editor = node('div', '', 'paste-editor');
  const backdrop = node('div', '', 'paste-backdrop'); backdrop.setAttribute('aria-hidden', 'true');
  const area = node('textarea'); area.id = 'paste-text'; area.rows = 22; area.spellcheck = true; area.setAttribute('aria-label', 'Senaryo metni');
  editor.append(backdrop, area);
  const stats = node('p', '', 'paste-stats'); stats.id = 'paste-stats';
  const warnings = node('ul', '', 'source-warnings'); warnings.id = 'paste-warnings'; warnings.hidden = true;
  const markerList = node('ul', '', 'note'); markerList.id = 'paste-markers';
  const cleaned = node('details'); cleaned.append(node('summary', 'Seslendirilecek metin (temizlenmiş hâli)')); const cleanedText = node('p', '', 'paste-clean'); cleanedText.id = 'paste-clean'; cleaned.append(cleanedText);
  const save = node('button', 'Kaydet'); save.type = 'button'; save.id = 'paste-save';
  const next = node('a', 'Sonraki adım: Seslendirme →', 'action-link'); next.href = `/projects/${id}/narration`; next.hidden = true;
  panel.append(editor, stats, warnings, markerList, cleaned, save, next);
  const versions = node('section', '', 'settings-panel'); versions.id = 'paste-versions';
  root.append(back, status, panel, versions);
  let language = 'de', timer = null, seq = 0;
  function paint() {
    backdrop.replaceChildren();
    const text = area.value, re = /\[([^\[\]\n]{0,300})\]/g; let last = 0, m;
    while ((m = re.exec(text))) {
      backdrop.append(document.createTextNode(text.slice(last, m.index)));
      backdrop.append(node('mark', m[0], (KNOWN.test(m[1].trim()) || KNOWN.test(plainUpper(m[1].trim()))) ? 'marker-ok' : 'marker-bad'));
      last = m.index + m[0].length;
    }
    backdrop.append(document.createTextNode(text.slice(last) + '\n'));
    backdrop.scrollTop = area.scrollTop;
  }
  const clock = minutes => { const s = Math.round(minutes * 60); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  function showPreview(p) {
    stats.textContent = `${p.word_count} kelime · tahmini süre ${clock(p.estimated_minutes)} dk (${LANG[p.language] || p.language} ~${Math.round(p.spoken_rate)} kelime/dk)`;
    warnings.replaceChildren(...p.warnings.map(w => node('li', '⚠ ' + w))); warnings.hidden = !p.warnings.length;
    markerList.replaceChildren(...p.markers.map(mk => node('li', `[${mk.label}: ${mk.value}] → “${mk.sentence.slice(0, 90)}${mk.sentence.length > 90 ? '…' : ''}”`)));
    cleanedText.textContent = p.text;
  }
  async function preview() {
    const mine = ++seq;
    try { const p = await request(base + '/paste/preview', 'POST', {text: area.value}); if (mine === seq) showPreview(p); }
    catch (e) { if (mine === seq) stats.textContent = e.message; }
  }
  area.addEventListener('input', () => { paint(); clearTimeout(timer); timer = setTimeout(preview, 350); });
  area.addEventListener('scroll', () => { backdrop.scrollTop = area.scrollTop; });
  async function store(confirm) {
    save.disabled = true; status.textContent = 'Kaydediliyor…';
    try { const r = await request(base + '/paste', 'POST', {text: area.value, confirm_replace_approved: confirm}); status.textContent = r.message; render(r); }
    catch (e) {
      if (e.status === 409 && !confirm && window.confirm('Bu proje için kayıtlı bir metin var. Yeni metin yeni sürüm olarak kaydedilir; eski sürüm silinmez. Mevcut seslendirme yeni metne uymayacaksa yeniden seslendirmeniz gerekir. Devam edilsin mi?')) return store(true);
      status.textContent = e.message;
    } finally { save.disabled = false; }
  }
  save.addEventListener('click', () => store(false));
  function render(view) {
    const current = view.current;
    if (current) { area.value = current.raw_text; next.hidden = current.status !== 'approved'; }
    paint(); preview();
    versions.replaceChildren(node('h2', 'Kayıtlı sürümler'));
    if (!view.versions.length) { versions.append(node('p', 'Henüz kayıtlı metin yok.', 'note')); return; }
    const list = node('ul');
    for (const v of view.versions) {
      const li = node('li', `Sürüm ${v.version} · ${new Date(v.created_at).toLocaleString('tr-TR')} · ${v.word_count} kelime · ${v.status_label}${current && v.id === current.id ? ' · (şu an kullanılan)' : ''} `);
      if (!current || v.id !== current.id) {
        const use = node('button', 'Bu sürümü kullan'); use.type = 'button';
        use.addEventListener('click', async () => {
          if (!window.confirm('Bu sürüm kullanılsın mı? Seslendirme ve sahne planı seçilen metne göre yeniden hazırlanmalıdır.')) return;
          try { await request(`${base}/versions/${v.id}/select`, 'POST', {confirm_replace_approved: true}); await request(`${base}/versions/${v.id}/approve`, 'POST', {confirm: true}); render(await request(base + '/paste')); status.textContent = `Sürüm ${v.version} kullanılıyor.`; }
          catch (e) { status.textContent = e.message; }
        });
        li.append(use);
      }
      list.append(li);
    }
    versions.append(list);
  }
  (async () => {
    try { const p = await request(`/api/projects/${id}`); language = p.language; document.querySelector('#page-title').textContent = `${p.name} · Metin`; } catch {}
    try { const view = await request(base + '/paste'); render(view); status.textContent = view.current ? 'Kayıtlı metin yüklendi. Düzenleyip Kaydet derseniz yeni sürüm olur.' : 'Metninizi yapıştırıp Kaydet deyin.'; }
    catch (e) { status.textContent = e.message; }
  })();
}
