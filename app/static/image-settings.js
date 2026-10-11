/* Connection/configuration only; no automatic model downloads or image execution. */
if (window.location.pathname === '/settings') {
  const panel = document.createElement('form'); panel.id = 'settings-images'; panel.className = 'settings-panel';
  const fieldNames = ['engine', 'paid_usage', 'local_enabled', 'local_url', 'local_model', 'workflow', 'license_confirmed', 'gemini_model', 'openai_model', 'thumbnail_ai'];
  function node(tag, text) { const item = document.createElement(tag); if (text) item.textContent = text; return item; }
  panel.append(node('h2', 'Görsel Üretimi'), node('p', 'Ayarlar ve bağlantı testleri çalışır. Görsel çalıştırması daha sonraki aşama için hazırlandı. RTX 5070, yerel ComfyUI üzerinden kullanılabilir; model indirilmez. Cloud anahtarları mevcut Gemini/OpenAI bölümlerinden güvenle kullanılır.'));
  const status = node('p', 'Yükleniyor…'); status.id = 'image-settings-status'; status.setAttribute('role', 'status'); panel.append(status);
  function field(name, label, type, choices=[]) {
    const group = node('div'); group.className = 'setting-field'; const caption = node('label', label); caption.htmlFor = `images-${name}`;
    const input = node(type === 'select' ? 'select' : 'input'); input.id = caption.htmlFor; input.name = name;
    if (type !== 'select') input.type = type;
    else for (const [value, text] of choices) { const option = node('option', text); option.value = value; input.append(option); }
    group.append(caption, input); panel.append(group);
  }
  field('engine', 'Görsel Motoru', 'select', [['auto','Otomatik — stok önce'],['local','Yerel GPU'],['gemini','Gemini'],['openai','OpenAI'],['off','Kapalı']]);
  field('paid_usage', 'Ücretli AI kullanımı', 'select', [['off','KAPALI — Ücretli API’yi otomatik kullanma'],['ask','Ücretli kullanım öncesi sor'],['allow_fallback','Ücretli fallback’e izin ver']]);
  field('local_enabled', 'Yerel GPU sağlayıcısını etkinleştir', 'checkbox');
  field('local_url', 'Yerel ComfyUI API adresi', 'url');
  field('local_model', 'Kurulu yerel model (önce modelleri getir)', 'select', [['','Model seçin']]);
  field('workflow', 'ComfyUI workflow adı (isteğe bağlı; çalıştırma eşlemesi daha sonra)', 'text');
  field('license_confirmed', 'Seçilen yerel modelin ticari YouTube kullanım lisansını kontrol ettim', 'checkbox');
  field('resolution', 'YouTube hedef çözünürlüğü — 16:9', 'select', [['1920x1080','1920 × 1080'],['1280x720','1280 × 720'],['1024x576','1024 × 576']]);
  field('gemini_model', 'Gemini görsel modeli (API listesi; görsel yeteneğini resmi belgede kontrol edin)', 'select', [['','Model seçin']]);
  field('thumbnail_ai', 'YouTube kapağı için Gemini ile arka plan üretebilsin (isteğe bağlı; her üretim kotanızdan düşer veya ücretli olabilir)', 'checkbox');
  field('openai_model', 'OpenAI görsel modeli (hesabınızın resmi API model adı)', 'text');
  panel.append(node('p', 'Model erişimi, görsel üretme yeteneğini veya lisans uygunluğunu tek başına doğrulamaz. Bulut görsel API’leri ücret/kota kullanabilir; web aboneliği API erişimi sağlamaz.'));
  const actions = node('div'); actions.className = 'settings-actions'; panel.append(actions);
  function button(label, fn) { const item = node('button', label); item.type = 'button'; item.addEventListener('click', fn); actions.append(item); }
  let busy = false, dirty = false;
  function controls(value) { busy = value; for (const item of panel.querySelectorAll('input,select,button')) item.disabled = value; }
  function models(name, values, selected) { const select = panel.elements[name]; select.replaceChildren(); const empty = node('option','Model seçin'); empty.value=''; select.append(empty); for (const value of values) { const option=node('option', value); option.value=value; select.append(option); } select.value=values.includes(selected)?selected:''; }
  function show(data) {
    models('local_model',data.local_models,data.local_model); models('gemini_model',data.gemini_models,data.gemini_model);
    for (const name of fieldNames) { const item=panel.elements[name]; if (item.type==='checkbox') item.checked=data[name]; else item.value=data[name]; }
    panel.elements.resolution.value=`${data.width}x${data.height}`; dirty=false;
    status.textContent=`${data.status} · ${data.message}`;
  }
  async function load() { controls(true); try { show((await settingsRequest('/api/settings')).images); } catch(error) {status.textContent=error.message;} finally {controls(false);} }
  async function save() {
    const payload={}; for (const name of fieldNames) { const item=panel.elements[name]; payload[name]=item.type==='checkbox'?item.checked:item.value; }
    [payload.width,payload.height]=panel.elements.resolution.value.split('x').map(Number);
    if(payload.paid_usage==='allow_fallback' && !window.confirm('Gelecekte stok/yerel görsel yetmezse ücretli bulut fallback kullanımına izin veriyorsunuz. Devam edilsin mi?')) return;
    controls(true); try {show((await settingsRequest('/api/settings/images','PUT',payload)).images); status.textContent='Görsel tercihleri kaydedildi. Çalıştırma daha sonra.';} catch(error){status.textContent=error.message;} finally{controls(false);}
  }
  async function operation(provider, kind) {
    if(dirty){status.textContent='Önce Kaydet deyin; bağlantı ve keşif kayıtlı ayarları kullanır.';return;}
    controls(true); status.textContent='Bağlantı kontrol ediliyor…';
    try {const result=await settingsRequest(`/api/settings/images/${provider}/${kind}`,'POST'); if(result.images) show(result.images); else status.textContent=`${result.result.status} · ${result.result.message}`;} catch(error){status.textContent=error.message;} finally{controls(false);}
  }
  button('Kaydet',save); button('Temizle',async()=>{if(!window.confirm('Yalnızca görsel tercihleri temizlensin mi? Gemini/OpenAI anahtarları korunur.'))return; controls(true);try{show((await settingsRequest('/api/settings/images','DELETE')).images);}catch(error){status.textContent=error.message;}finally{controls(false);}});
  button('Yerel Modelleri Getir',()=>operation('local','models')); button('Yerel Bağlantıyı Test Et',()=>operation('local','test'));
  button('Gemini Görsel Modellerini Getir',()=>operation('gemini','models')); button('Gemini Görsel Bağlantısını Test Et',()=>operation('gemini','test'));
  button('OpenAI Görsel Bağlantısını Test Et',()=>operation('openai','test'));
  panel.addEventListener('input',()=>{dirty=true;}); panel.addEventListener('submit',event=>{event.preventDefault();if(!busy)save();});
  document.querySelector('#settings-sections').append(panel); load();
}
