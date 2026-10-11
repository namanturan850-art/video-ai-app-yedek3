/* Channels + “Tarzım” kit: list, edit, wizard (Gemini by default), live preview, sound effects. */
if (window.location.pathname === '/channels') {
  const root = document.querySelector('#channels-content'); root.hidden = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
  const status = node('p', 'Kanallar yükleniyor…', 'provider-status'); status.id = 'channels-status'; status.setAttribute('role', 'status');
  const list = node('div', '', 'channel-list'); list.id = 'channel-list';
  const add = node('button', '＋ Yeni kanal'); add.type = 'button'; add.id = 'channel-add';
  const editor = node('section', '', 'settings-panel'); editor.id = 'channel-editor'; editor.hidden = true;
  root.append(status, add, list, editor);
  let data = null, current = null, voices = [], draft = null, playing = null, pendingWizard = null;
  const LANGS = [['de', 'Almanca'], ['es', 'İspanyolca'], ['en', 'İngilizce'], ['fr', 'Fransızca'], ['tr', 'Türkçe']];
  const EASE = {smooth: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, snappy: t => 1 - Math.pow(1 - t, 3),
    bounce: t => { const n = 7.5625, d = 2.75; if (t < 1 / d) return n * t * t; if (t < 2 / d) return n * (t -= 1.5 / d) * t + .75; if (t < 2.5 / d) return n * (t -= 2.25 / d) * t + .9375; return n * (t -= 2.625 / d) * t + .984375; }, linear: t => t};
  async function request(url, method = 'GET', body, headers = {}) {
    let response;
    try { response = await fetch(url, {method, cache: 'no-store', signal: AbortSignal.timeout(60000), headers: {'X-AI-Video-Studio': 'projects', ...(body instanceof Blob ? {} : {'Content-Type': 'application/json'}), ...headers}, ...(body === undefined ? {} : {body: body instanceof Blob ? body : JSON.stringify(body)})}); }
    catch { throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini açık tutup tekrar deneyin.'); }
    let json; try { json = await response.json(); } catch { throw new Error('Yanıt okunamadı. Sayfayı yenileyin.'); }
    if (!response.ok) throw new Error(json.message || 'İşlem tamamlanamadı.');
    return json;
  }
  function field(parent, label, control, id) { const g = node('div', '', 'setting-field'); const l = node('label', label); l.htmlFor = id; control.id = id; g.append(l, control); parent.append(g); return control; }
  function select(options, value) { const s = node('select'); for (const [k, v] of options) { const o = node('option', v); o.value = k; s.append(o); } s.value = value; return s; }
  function input(type, value) { const i = node('input'); i.type = type; i.value = value ?? ''; return i; }
  const family = id => (data.options.fonts.find(f => f.id === id) || {family: 'Arial'}).family;

  function renderList() {
    list.replaceChildren();
    for (const c of data.channels) {
      const card = node('article', '', 'channel-card' + (current && current.id === c.id ? ' active' : '')); card.dataset.channelId = c.id;
      const sw = node('div'); for (const k of ['background', 'primary', 'accent']) { const s = node('span', '', 'swatch'); s.style.background = c.style.palette[k]; sw.append(s); }
      card.append(node('h3', c.name + (c.is_default ? ' · Varsayılan' : '')), node('p', `${LANGS.find(l => l[0] === c.language)?.[1] || c.language} · ${c.target_duration_minutes} dk · ${c.project_count} proje`), sw);
      card.addEventListener('click', () => open(c)); list.append(card);
    }
  }

  function open(channel) {
    current = channel; draft = JSON.parse(JSON.stringify(channel.style)); renderList(); editor.hidden = false; editor.replaceChildren();
    editor.append(node('h2', channel.id ? `Kanal: ${channel.name}` : 'Yeni kanal'));
    const info = node('div', '', 'kit-grid'); editor.append(info);
    const name = field(info, 'Kanal adı', input('text', channel.name), 'channel-name'); name.maxLength = 80;
    const language = field(info, 'Dil', select(LANGS, channel.language || 'de'), 'channel-language');
    const duration = field(info, 'Hedef video süresi (dakika)', input('number', channel.target_duration_minutes || 5), 'channel-duration'); duration.min = 1; duration.max = 180; duration.step = .5;
    const niche = field(editor, 'Konu / niş açıklaması', node('textarea'), 'channel-niche'); niche.rows = 2; niche.maxLength = 600; niche.value = channel.niche || '';
    const voice = field(info, 'Varsayılan ses (AI33)', select([['', 'Ayarlardaki varsayılan'], ...voices.map(v => [`${v.provider}|${v.voice_id}|${v.display_name || ''}`, `${v.display_name || v.voice_id} · ${v.provider}`])],
      channel.voice_id ? `${channel.voice_provider}|${channel.voice_id}|${channel.voice_name || ''}` : ''), 'channel-voice');
    if (channel.voice_id && voice.value === '') { const o = node('option', `${channel.voice_name || channel.voice_id} · ${channel.voice_provider}`); o.value = `${channel.voice_provider}|${channel.voice_id}|${channel.voice_name || ''}`; voice.append(o); voice.value = o.value; }
    const speed = field(info, 'Konuşma hızı (0,5–1,5)', input('number', channel.voice_speed || 1), 'channel-speed'); speed.min = .5; speed.max = 1.5; speed.step = .05;

    // ---- Tarzım ----
    editor.append(node('h3', 'Tarzım kiti'));
    // A real button (not a collapsible line): it visibly opens the questions,
    // scrolls to them and puts the cursor in the first one.
    const openWizard = node('button', '✨ Tarzımı oluştur'); openWizard.type = 'button'; openWizard.id = 'style-wizard-open';
    editor.append(openWizard, node('p', 'Birkaç soru sorulur; yapay zekâ renk, font ve hareket önerir, siz düzenleyip kaydedersiniz.', 'note'));
    const wizard = node('section', '', 'settings-panel wizard-panel'); wizard.id = 'style-wizard'; wizard.hidden = true;
    wizard.append(node('h4', 'Tarzımı oluştur — 3 kısa soru'));
    const wz = node('div', '', 'kit-grid'); wizard.append(wz);
    const topic = field(wz, 'Kanal ne anlatıyor?', input('text', channel.niche || ''), 'wizard-topic');
    const audience = field(wz, 'İzleyici kim?', input('text', ''), 'wizard-audience');
    const feeling = field(wz, 'Nasıl bir his?', select(data.options.feelings.map(f => [f, f[0].toUpperCase() + f.slice(1)]), draft.feeling || 'ciddi'), 'wizard-feeling');
    const notes = field(wz, 'Ek not (isteğe bağlı)', input('text', ''), 'wizard-notes');
    const ask = node('button', 'Öneri al'); ask.type = 'button'; ask.id = 'wizard-run'; const why = node('p', '', 'wizard-result'); why.id = 'wizard-reason'; why.setAttribute('role', 'status'); why.hidden = true;
    wizard.append(ask, why); editor.append(wizard);
    const tell = text => { why.hidden = false; why.textContent = text; };
    openWizard.addEventListener('click', () => { wizard.hidden = !wizard.hidden; openWizard.textContent = wizard.hidden ? '✨ Tarzımı oluştur' : '✕ Soruları kapat';
      if (!wizard.hidden) { wizard.scrollIntoView({behavior: 'smooth', block: 'start'}); topic.focus({preventScroll: true}); } });
    const kit = node('div', '', 'kit-grid'); editor.append(kit);
    const colors = {};
    for (const [k, label] of [['background', 'Arka plan'], ['primary', 'Ana renk'], ['accent', 'Vurgu rengi'], ['text', 'Yazı rengi']]) colors[k] = field(kit, label, input('color', draft.palette[k]), 'kit-' + k);
    const fonts = data.options.fonts.map(f => [f.id, f.label]);
    const heading = field(kit, 'Başlık fontu', select(fonts, draft.heading_font), 'kit-heading');
    const body = field(kit, 'Metin fontu', select(fonts, draft.body_font), 'kit-body');
    const motion = field(kit, 'Animasyon süresi (sn)', input('number', draft.motion_duration), 'kit-motion'); motion.min = .2; motion.max = 2; motion.step = .1;
    const easing = field(kit, 'Yumuşama eğrisi', select(data.options.easings.map(e => [e.id, e.label]), draft.easing), 'kit-easing');
    editor.append(node('h4', 'Ses efektleri'));
    const sfx = node('div', '', 'kit-grid'); editor.append(sfx); const sfxSel = {};
    for (const s of data.options.sfx) {
      const box = node('div', '', 'setting-field'); const l = node('label', s.label); box.append(l);
      const sel = select([['default:' + s.id, 'Uygulamayla gelen'], ['none', 'Kapalı'], ...(draft.sfx[s.id].startsWith('upload:') ? [[draft.sfx[s.id], 'Yüklediğim dosya']] : [])], draft.sfx[s.id]); sel.id = 'kit-sfx-' + s.id; sfxSel[s.id] = sel;
      const play = node('button', '▶'); play.type = 'button'; play.title = 'Dinle';
      play.addEventListener('click', () => { const src = sel.value === 'none' ? null : sel.value.startsWith('default:') ? s.default_url : `/api/channels/${channel.id}/sfx/${s.id}`; if (src) { playing?.pause(); playing = new Audio(src); playing.volume = Number(vol.value) * 2; playing.play().catch(() => {}); } });
      const up = node('input'); up.type = 'file'; up.accept = '.wav,.mp3,.ogg,audio/*'; up.id = 'kit-upload-' + s.id; up.disabled = !channel.id;
      up.addEventListener('change', async () => { const file = up.files[0]; if (!file) return; try { const saved = await request(`/api/channels/${channel.id}/sfx/${s.id}`, 'POST', file, {'X-File-Name': file.name}); await load(saved.id); status.textContent = `${s.label} sesi yüklendi.`; } catch (e) { status.textContent = e.message; } });
      box.append(sel, play, up); sfx.append(box);
    }
    const vol = field(sfx, 'Efekt ses düzeyi (seslendirmenin altında)', input('range', draft.sfx_volume), 'kit-sfx-volume'); vol.min = 0; vol.max = .5; vol.step = .01;
    editor.append(node('h4', 'Altyazı stili'));
    const sub = node('div', '', 'kit-grid'); editor.append(sub);
    const sFont = field(sub, 'Altyazı fontu', select(fonts, draft.subtitle.font), 'kit-sub-font');
    const sColor = field(sub, 'Altyazı rengi', input('color', draft.subtitle.color), 'kit-sub-color');
    const sOutline = field(sub, 'Kenar rengi', input('color', draft.subtitle.outline), 'kit-sub-outline');
    const sPos = field(sub, 'Konum', select([['bottom', 'Altta'], ['middle', 'Ortada'], ['top', 'Üstte']], draft.subtitle.position), 'kit-sub-position');
    const sSize = field(sub, 'Boyut', input('number', draft.subtitle.size), 'kit-sub-size'); sSize.min = 32; sSize.max = 96;

    // ---- live preview ----
    const preview = node('div', '', 'kit-preview'); preview.id = 'kit-preview';
    const pTitle = node('div', 'Örnek Başlık', 'kit-title'), pBar = node('div', '', 'kit-bar'), pNum = node('div', '0', 'kit-number'),
      pBody = node('div', 'Kanalınızın renkleri, fontları ve hareket ritmi burada görünür.', 'kit-body'), pSub = node('div', 'Örnek altyazı satırı', 'kit-sub');
    preview.append(pTitle, pBar, pNum, pBody, pSub);
    const replay = node('button', '▶ Örnek animasyonu oynat'); replay.type = 'button'; replay.id = 'kit-play';
    editor.append(node('h4', 'Canlı önizleme'), preview, replay);
    const avatar = node('details', '', 'settings-panel'); avatar.append(node('summary', 'Avatar (yer ayrıldı — henüz üretilmiyor)'), node('p', 'İleride kurguda köşede bir avatar penceresi gösterilebilecek. Şimdilik yalnızca not alabilirsiniz.', 'note'));
    const aNote = field(avatar, 'Avatar notu', input('text', channel.avatar?.note || ''), 'channel-avatar-note'); aNote.maxLength = 300; editor.append(avatar);
    const actions = node('div', '', 'settings-actions'); const save = node('button', 'Kaydet'); save.type = 'button'; save.id = 'channel-save';
    const del = node('button', 'Kanalı sil'); del.type = 'button'; del.hidden = !channel.id || channel.is_default; actions.append(save, del); editor.append(actions);

    function collect() {
      draft.palette = Object.fromEntries(Object.entries(colors).map(([k, el]) => [k, el.value.toUpperCase()]));
      Object.assign(draft, {heading_font: heading.value, body_font: body.value, motion_duration: Number(motion.value), easing: easing.value, sfx_volume: Number(vol.value)});
      draft.sfx = Object.fromEntries(Object.entries(sfxSel).map(([k, el]) => [k, el.value]));
      draft.subtitle = {font: sFont.value, color: sColor.value.toUpperCase(), outline: sOutline.value.toUpperCase(), position: sPos.value, size: Number(sSize.value)};
      return draft;
    }
    function paint() {
      const k = collect(), p = k.palette;
      preview.style.background = p.background; pTitle.style.color = p.primary; pTitle.style.fontFamily = `'${family(k.heading_font)}',sans-serif`;
      pBar.style.background = p.accent; pNum.style.color = p.accent; pNum.style.fontFamily = `'${family(k.heading_font)}',sans-serif`;
      pBody.style.color = p.text; pBody.style.fontFamily = `'${family(k.body_font)}',sans-serif`;
      Object.assign(pSub.style, {color: k.subtitle.color, fontFamily: `'${family(k.subtitle.font)}',sans-serif`, fontSize: `${k.subtitle.size / 1080 * 100 * .9}cqh`,
        textShadow: `0 0 3px ${k.subtitle.outline},0 0 3px ${k.subtitle.outline}`, top: k.subtitle.position === 'top' ? '6%' : k.subtitle.position === 'middle' ? '46%' : 'auto', bottom: k.subtitle.position === 'bottom' ? '6%' : 'auto'});
      preview.style.containerType = 'size';
    }
    function animate() {
      const k = collect(), ease = EASE[k.easing] || EASE.smooth, total = k.motion_duration * 1000, start = performance.now();
      if (k.sfx.rise !== 'none') sfx.querySelector('#kit-sfx-rise')?.parentElement.querySelector('button')?.click();
      const step = now => { const t = Math.min(1, (now - start) / total), e = ease(t);
        pBar.style.width = `${40 * e}%`; pTitle.style.transform = `translateY(${(1 - e) * 30}px)`; pTitle.style.opacity = Math.min(1, e * 1.2);
        pNum.textContent = `${Math.round(1945 * e)}`; if (t < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    }
    editor.querySelectorAll('input,select').forEach(el => el.addEventListener('input', paint));
    replay.addEventListener('click', animate);
    ask.addEventListener('click', async () => {
      const answers = {topic: topic.value, audience: audience.value, feeling: feeling.value, notes: notes.value};
      if (!channel.id) {  // new channel: save it first, then continue automatically
        if (!name.value.trim()) { tell('Önce yukarıdaki “Kanal adı” kutusuna bir ad yazın; kanal otomatik kaydedilip öneri hazırlanır.'); name.focus(); return; }
        pendingWizard = answers; save.click(); return;
      }
      ask.disabled = true; tell('Öneri hazırlanıyor… (yapay zekâ ile 10–30 saniye sürebilir)');
      try {
        const r = await request(`/api/channels/${channel.id}/style/suggest`, 'POST', answers);
        const s = r.style; for (const k in colors) colors[k].value = s.palette[k]; heading.value = s.heading_font; body.value = s.body_font; motion.value = s.motion_duration; easing.value = s.easing;
        sFont.value = s.subtitle.font; sPos.value = s.subtitle.position; draft.feeling = s.feeling;
        tell(`✓ ${r.source === 'preset' ? 'Hazır öneri' : 'Yapay zekâ önerisi'} uygulandı: ${r.reason} Aşağıdaki renkler, fontlar ve önizleme güncellendi. Beğendiyseniz en alttaki “Kaydet” düğmesine basın.`);
        status.textContent = 'Tarzım önerisi hazır — önizlemeye bakıp Kaydet deyin.';
        paint(); preview.scrollIntoView({behavior: 'smooth', block: 'center'}); preview.classList.add('kit-flash'); setTimeout(() => preview.classList.remove('kit-flash'), 1600); animate();
      } catch (e) { tell(e.message); } finally { ask.disabled = false; }
    });
    save.addEventListener('click', async () => {
      const [vp, vid, vname] = voice.value ? voice.value.split('|') : ['', '', ''];
      const payload = {name: name.value, language: language.value, niche: niche.value, target_duration_minutes: Number(duration.value), voice_provider: vp, voice_id: vid, voice_name: vname, voice_speed: Number(speed.value), style: collect()};
      try {
        const saved = channel.id ? await request(`/api/channels/${channel.id}`, 'PUT', {...payload, avatar: {note: aNote.value}}) : await request('/api/channels', 'POST', payload);
        await load(saved.id); status.textContent = `“${saved.name}” kaydedildi.`;
      } catch (e) { status.textContent = e.message; }
    });
    del.addEventListener('click', async () => { if (!window.confirm('Bu kanal silinsin mi? Bağlı proje varsa silinmez.')) return; try { await request(`/api/channels/${channel.id}`, 'DELETE'); editor.hidden = true; await load(); } catch (e) { status.textContent = e.message; } });
    paint();
    if (pendingWizard && channel.id) { const a = pendingWizard; pendingWizard = null; wizard.hidden = false; openWizard.textContent = '✕ Soruları kapat';
      topic.value = a.topic; audience.value = a.audience; feeling.value = a.feeling; notes.value = a.notes; ask.click(); }
  }

  add.addEventListener('click', () => open({name: '', language: 'de', target_duration_minutes: 5, niche: '', voice_speed: 1, style: JSON.parse(JSON.stringify(data.channels[0].style)), avatar: {}}));
  async function load(select) {
    try {
      data = await request('/api/channels');
      try { const s = await request('/api/settings'); voices = s.ai33?.voices || []; } catch { voices = []; }
      status.textContent = `${data.channels.length} kanal · Öneriler: ${data.engine === 'claude' ? 'Claude (ücretli)' : data.engine === 'gemini' ? 'Gemini (ücretsiz kota)' : 'hazır şablonlar (yapay zekâ ayarlı değil)'}`;
      renderList();
      const target = data.channels.find(c => c.id === (select || current?.id));
      if (target) open(target);
    } catch (e) { status.textContent = e.message; }
  }
  load();
}
