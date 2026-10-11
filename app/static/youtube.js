/* YouTube preparation: titles, description and tags (copy). No upload, no thumbnail. */
if (/^\/projects\/[^/]+\/youtube$/.test(window.location.pathname)) {
  const pid = window.location.pathname.split('/')[2], api = `/api/projects/${pid}/youtube`;
  const root = document.querySelector('#youtube-content'); root.hidden = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
  const back = node('a', '← Projeye dön', 'back'); back.href = `/projects/${pid}`;
  const status = node('p', 'YouTube bilgileri yükleniyor…', 'provider-status'); status.id = 'youtube-status'; status.setAttribute('role', 'status');
  const textPanel = node('section', '', 'settings-panel'); textPanel.id = 'youtube-text';
  root.append(back, status, node('p', 'Bu sayfa yalnızca hazırlık yapar; YouTube’a otomatik yükleme yapılmaz. Metinleri kopyalayıp YouTube Studio’ya yapıştırın.', 'note'), textPanel);
  let view = null;
  async function request(url, method = 'GET', body) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(180000), headers: {'X-AI-Video-Studio': 'projects', 'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})}); }
    catch { throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini açık tutup tekrar deneyin.'); }
    let json; try { json = await response.json(); } catch { throw new Error('Yanıt okunamadı. Sayfayı yenileyin.'); }
    if (!response.ok) throw new Error(json.message || 'İşlem tamamlanamadı.');
    return json;
  }
  // YouTube's own count: commas count, a tag with a space is quoted (+2).
  const tagsLength = tags => tags.reduce((n, t) => n + t.length + (t.includes(' ') ? 2 : 0), 0) + Math.max(0, tags.length - 1);
  const splitTags = value => value.split(',').map(t => t.replace(/#/g, '').trim()).filter(Boolean);
  function copyButton(label, get) {
    const b = node('button', label); b.type = 'button'; b.className = 'youtube-copy';
    b.addEventListener('click', async () => { try { await navigator.clipboard.writeText(get()); b.textContent = '✓ Kopyalandı'; } catch { const t = node('textarea'); t.value = get(); document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); b.textContent = '✓ Kopyalandı'; } setTimeout(() => { b.textContent = label; }, 1800); });
    return b;
  }
  function render() {
    const p = view.package, limits = view.limits;
    textPanel.replaceChildren(node('h2', 'Başlık, açıklama ve etiketler'));
    const gen = node('button', p.titles?.length ? 'Yeniden öner' : 'Önerileri oluştur'); gen.type = 'button'; gen.id = 'youtube-generate';
    textPanel.append(node('p', `Motor: ${view.engine_label || 'ayarlı değil (Ayarlar → Gemini)'}. Metinler videonun dilinde yazılır, ardından yapay zekâ anlam ve dil hatasına karşı bir kez daha kontrol eder.`, 'note'), gen);
    gen.addEventListener('click', async () => { gen.disabled = true; status.textContent = 'Öneriler hazırlanıyor ve dil kontrolü yapılıyor…'; try { view = await request(api + '/text', 'POST'); status.textContent = 'Öneriler hazır.'; render(); } catch (e) { status.textContent = e.message; } finally { gen.disabled = false; } });
    if (!p.titles?.length) return;
    const proof = p.proofread || {};
    const badge = node('p', view.ready ? '✓ Yayına hazır: dil kontrolü yapıldı.' : proof.stale ? '⚠ Değişiklik yaptınız: yayına hazır olması için “Dil kontrolünü yap” deyin.' : '⚠ Dil kontrolü henüz yapılmadı.', view.ready ? 'youtube-ready' : 'youtube-warning');
    badge.id = 'youtube-ready';
    textPanel.append(badge);
    if (proof.issues?.length) { const ul = node('ul', '', 'note'); ul.id = 'youtube-issues'; for (const t of proof.issues) ul.append(node('li', 'Düzeltildi: ' + t)); textPanel.append(ul); }
    textPanel.append(node('h3', 'Başlık (5 öneri — birini seçin veya düzenleyin)'));
    const list = node('div'); list.id = 'youtube-titles';
    const title = node('input'); title.type = 'text'; title.maxLength = limits.title; title.value = p.chosen_title || ''; title.id = 'youtube-title';
    const count = node('span', '', 'note'); count.id = 'youtube-title-count';
    const sync = () => { count.textContent = ` ${title.value.length}/${limits.title}`; count.style.color = title.value.length > limits.title ? '#9b2727' : ''; };
    for (const t of p.titles) { const label = node('label', '', 'youtube-title-option'); const r = node('input'); r.type = 'radio'; r.name = 'yt-title'; r.checked = t.text === p.chosen_title;
      r.addEventListener('change', () => { title.value = t.text; sync(); }); label.append(r, ` ${t.text} (${t.length}/${limits.title})`); list.append(label, node('br')); }
    title.addEventListener('input', sync); sync();
    textPanel.append(list, title, count, copyButton('Başlığı kopyala', () => title.value));
    textPanel.append(node('h3', 'Açıklama'));
    const desc = node('textarea'); desc.id = 'youtube-description'; desc.rows = 14; desc.maxLength = 5000; desc.value = p.description || '';
    textPanel.append(desc, copyButton('Açıklamayı kopyala', () => desc.value));
    textPanel.append(node('h3', 'Etiketler (virgülle ayrılır, # kullanılmaz)'));
    const tags = node('textarea'); tags.id = 'youtube-tags'; tags.rows = 3; tags.value = (p.tags || []).join(', ');
    const tagCount = node('span', '', 'note'); tagCount.id = 'youtube-tags-count';
    const syncTags = () => { const n = tagsLength(splitTags(tags.value)); tagCount.textContent = ` ${n}/${limits.tags}${n > limits.tags ? ' — kaydedince sondaki en zayıf etiketler çıkarılır' : ''}${tags.value.includes('#') ? ' — # işaretleri kaldırılacak' : ''}`; tagCount.style.color = n > limits.tags ? '#9b2727' : ''; };
    tags.addEventListener('input', syncTags); syncTags();
    textPanel.append(tags, tagCount, copyButton('Etiketleri kopyala', () => splitTags(tags.value).join(', ')));
    const save = node('button', 'Değişiklikleri kaydet'); save.type = 'button'; save.id = 'youtube-save';
    save.addEventListener('click', async () => { try { const r = await request(api, 'PUT', {chosen_title: title.value, description: desc.value, tags: splitTags(tags.value)}); view = r; status.textContent = ['Kaydedildi.', ...(r.notes || [])].join(' '); render(); } catch (e) { status.textContent = e.message; } });
    const check = node('button', 'Dil kontrolünü yap'); check.type = 'button'; check.id = 'youtube-check';
    check.addEventListener('click', async () => { check.disabled = true; status.textContent = 'Yapay zekâ başlık, açıklama ve etiketleri kontrol ediyor…'; try { view = await request(api + '/check', 'POST'); status.textContent = 'Dil kontrolü tamamlandı.'; render(); } catch (e) { status.textContent = e.message; } finally { check.disabled = false; } });
    textPanel.append(node('br'), save, check, copyButton('Hepsini kopyala', () => `${title.value}\n\n${desc.value}\n\n${splitTags(tags.value).join(', ')}`));
  }
  async function load() { try { view = await request(api); status.textContent = view.package.titles?.length ? 'Kayıtlı öneriler yüklendi.' : 'Önerileri oluşturmak için düğmeye basın.'; render(); } catch (e) { status.textContent = e.message; } }
  load();
}
