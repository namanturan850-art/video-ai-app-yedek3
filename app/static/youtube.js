/* YouTube preparation: titles, description, tags (copy) and thumbnail. No upload. */
if (/^\/projects\/[^/]+\/youtube$/.test(window.location.pathname)) {
  const pid = window.location.pathname.split('/')[2], api = `/api/projects/${pid}/youtube`;
  const root = document.querySelector('#youtube-content'); root.hidden = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
  const back = node('a', '← Projeye dön', 'back'); back.href = `/projects/${pid}`;
  const status = node('p', 'YouTube bilgileri yükleniyor…', 'provider-status'); status.id = 'youtube-status'; status.setAttribute('role', 'status');
  const textPanel = node('section', '', 'settings-panel'); textPanel.id = 'youtube-text';
  const thumbPanel = node('section', '', 'settings-panel'); thumbPanel.id = 'youtube-thumb';
  root.append(back, status, node('p', 'Bu sayfa yalnızca hazırlık yapar; YouTube’a otomatik yükleme yapılmaz. Metinleri kopyalayıp YouTube Studio’ya yapıştırın.', 'note'), textPanel, thumbPanel);
  let view = null;
  async function request(url, method = 'GET', body) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(180000), headers: {'X-AI-Video-Studio': 'projects', 'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})}); }
    catch { throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini açık tutup tekrar deneyin.'); }
    let json; try { json = await response.json(); } catch { throw new Error('Yanıt okunamadı. Sayfayı yenileyin.'); }
    if (!response.ok) throw new Error(json.message || 'İşlem tamamlanamadı.');
    return json;
  }
  function copyButton(label, get) {
    const b = node('button', label); b.type = 'button'; b.className = 'youtube-copy';
    b.addEventListener('click', async () => { try { await navigator.clipboard.writeText(get()); b.textContent = '✓ Kopyalandı'; } catch { const t = node('textarea'); t.value = get(); document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); b.textContent = '✓ Kopyalandı'; } setTimeout(() => { b.textContent = label; }, 1800); });
    return b;
  }
  function renderText() {
    const p = view.package; textPanel.replaceChildren(node('h2', 'Başlık, açıklama ve etiketler'));
    const gen = node('button', p.titles ? 'Yeniden öner' : 'Önerileri oluştur'); gen.type = 'button'; gen.id = 'youtube-generate';
    textPanel.append(node('p', `Motor: ${view.engine_label || 'ayarlı değil (Ayarlar → Gemini)'}. Metinler videonun dilinde yazılır.`, 'note'), gen);
    gen.addEventListener('click', async () => { gen.disabled = true; status.textContent = 'Öneriler hazırlanıyor…'; try { view.package = await request(api + '/text', 'POST'); status.textContent = 'Öneriler hazır.'; render(); } catch (e) { status.textContent = e.message; } finally { gen.disabled = false; } });
    if (!p.titles) return;
    textPanel.append(node('h3', 'Başlık (5 öneri — birini seçin veya düzenleyin)'));
    const list = node('div'); list.id = 'youtube-titles';
    const title = node('input'); title.type = 'text'; title.maxLength = 100; title.value = p.chosen_title || ''; title.id = 'youtube-title';
    const count = node('span', '', 'note');
    const sync = () => { count.textContent = ` ${title.value.length} karakter${title.value.length < 55 || title.value.length > 72 ? ' · önerilen 60–70' : ''}`; };
    for (const t of p.titles) { const label = node('label', '', 'youtube-title-option'); const r = node('input'); r.type = 'radio'; r.name = 'yt-title'; r.checked = t.text === p.chosen_title;
      r.addEventListener('change', () => { title.value = t.text; sync(); }); label.append(r, ` ${t.text} (${t.length})`); list.append(label, node('br')); }
    title.addEventListener('input', sync); sync();
    textPanel.append(list, title, count, copyButton('Başlığı kopyala', () => title.value));
    textPanel.append(node('h3', 'Açıklama'));
    const desc = node('textarea'); desc.id = 'youtube-description'; desc.rows = 14; desc.maxLength = 5000; desc.value = p.description || '';
    textPanel.append(desc, copyButton('Açıklamayı kopyala', () => desc.value));
    textPanel.append(node('h3', 'Etiketler'));
    const tags = node('textarea'); tags.id = 'youtube-tags'; tags.rows = 2; tags.value = (p.tags || []).join(', ');
    textPanel.append(tags, copyButton('Etiketleri kopyala', () => tags.value));
    const save = node('button', 'Değişiklikleri kaydet'); save.type = 'button'; save.id = 'youtube-save';
    save.addEventListener('click', async () => { try { view.package = await request(api, 'PUT', {chosen_title: title.value, description: desc.value, tags: tags.value.split(',').map(t => t.trim()).filter(Boolean)}); status.textContent = 'Kaydedildi.'; } catch (e) { status.textContent = e.message; } });
    textPanel.append(node('br'), save, copyButton('Hepsini kopyala', () => `${title.value}\n\n${desc.value}\n\n${tags.value}`));
  }
  function renderThumb() {
    const p = view.package; thumbPanel.replaceChildren(node('h2', 'Kapak (1280×720)'));
    if (!view.video_ready) thumbPanel.append(node('p', 'Video henüz oluşturulmadı; kareler seçilen medyadan önerilir. En iyi sonuç için önce videoyu oluşturun.', 'note'));
    const find = node('button', 'Etkileyici kareleri öner'); find.type = 'button'; find.id = 'youtube-frames'; thumbPanel.append(find);
    if (view.ai_background.enabled) {
      const ai = node('button', 'Gemini ile arka plan üret (kota/ücret)'); ai.type = 'button'; thumbPanel.append(ai, node('p', view.ai_background.note, 'note'));
      ai.addEventListener('click', async () => { if (!window.confirm(view.ai_background.note + ' Devam edilsin mi?')) return; try { p.frames = (await request(api + '/ai-background', 'POST', {cost_confirmed: true})).frames; render(); } catch (e) { status.textContent = e.message; } });
    }
    find.addEventListener('click', async () => { find.disabled = true; status.textContent = 'Kareler inceleniyor…'; try { p.frames = (await request(api + '/frames', 'POST')).frames; status.textContent = `${p.frames.length} kare önerildi.`; render(); } catch (e) { status.textContent = e.message; } finally { find.disabled = false; } });
    if (!p.frames?.length) return;
    const grid = node('div', '', 'kit-grid'); grid.id = 'youtube-frame-grid';
    let chosen = p.thumbnail_frame || p.frames[0].id;
    for (const f of p.frames) { const card = node('label', '', 'channel-card' + (f.id === chosen ? ' active' : '')); const img = node('img'); img.src = f.url + `?v=${Date.now()}`; img.alt = 'Kare'; img.style.width = '100%';
      const r = node('input'); r.type = 'radio'; r.name = 'yt-frame'; r.value = f.id; r.checked = f.id === chosen; r.addEventListener('change', () => { chosen = f.id; grid.querySelectorAll('.channel-card').forEach(c => c.classList.remove('active')); card.classList.add('active'); });
      card.append(r, img, node('span', f.ai ? ' Gemini arka planı' : ` ${f.time ?? ''} sn`, 'note')); grid.append(card); }
    thumbPanel.append(grid);
    const label = node('label', 'Kapak yazısı (2–4 kelime, başlığı tekrar etmesin)'); const text = node('input'); text.id = 'youtube-thumb-text'; text.maxLength = 40;
    text.value = p.thumbnail_text || (p.thumbnail_texts || [])[0] || ''; label.htmlFor = text.id;
    const ideas = node('div'); for (const t of p.thumbnail_texts || []) { const b = node('button', t); b.type = 'button'; b.addEventListener('click', () => { text.value = t; }); ideas.append(b); }
    const make = node('button', '3 yerleşim oluştur'); make.type = 'button'; make.id = 'youtube-make';
    thumbPanel.append(label, text, ideas, make);
    make.addEventListener('click', async () => { try { const r = await request(api + '/thumbnails', 'POST', {frame: chosen, text: text.value}); Object.assign(p, {thumbnails: r.thumbnails, thumbnail_warning: r.warning, thumbnail_text: text.value, thumbnail_frame: chosen}); render(); } catch (e) { status.textContent = e.message; } });
    if (p.thumbnail_warning) thumbPanel.append(node('p', p.thumbnail_warning, 'note'));
    if (p.thumbnails?.length) {
      const out = node('div', '', 'kit-grid'); out.id = 'youtube-thumbnails';
      for (const t of p.thumbnails) {
        const box = node('div', '', 'channel-card'); const big = node('img'); big.src = t.url; big.alt = t.label; big.style.width = '100%';
        const phone = node('div', '', 'note'); phone.textContent = 'Telefonda:'; const small = node('img'); small.src = t.url; small.alt = 'Küçük önizleme'; small.style.width = '168px'; small.style.borderRadius = '6px';
        const dl = node('a', 'PNG indir'); dl.href = t.url + '?download=true'; dl.className = 'action-link'; dl.setAttribute('download', '');
        box.append(node('h4', t.label), big, phone, small, node('br'), dl); out.append(box);
      }
      thumbPanel.append(out);
    }
  }
  function render() { renderText(); renderThumb(); }
  async function load() { try { view = await request(api); status.textContent = view.package.titles ? 'Kayıtlı öneriler yüklendi.' : 'Önerileri oluşturmak için düğmeye basın.'; render(); } catch (e) { status.textContent = e.message; } }
  load();
}
