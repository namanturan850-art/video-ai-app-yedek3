/* Optional, isolated external tool. No credential input or copy in this form. */
if (window.location.pathname==='/settings') {
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const panel=node('section');panel.id='settings-openmontage';panel.className='settings-panel';
  panel.append(node('h2','OpenMontage — Ana Montaj Motoru'),node('p','Ana motor OpenMontage’dır; Yerel Adaptif alternatif olarak seçilebilir. OpenMontage için INSTALL_OPENMONTAGE.bat dosyasına çift tıklayın. Ayrı kurulum yapılır; uygulama açılırken indirme yapılmaz.'));
  const license=node('a','Resmi OpenMontage — GNU AGPL v3');license.href='https://github.com/calesthio/OpenMontage';license.target='_blank';license.rel='noopener noreferrer';panel.append(license,node('p','Remotion kendi lisans koşullarına tabidir. OpenMontage uygulamanın senaryosunu, seslendirmesini veya zamanlamasını değiştirmez.'));
  const status=node('p','Durum kontrol ediliyor…');status.setAttribute('role','status');status.setAttribute('aria-live','polite');panel.append(status);
  const form=node('form'),inputs={};let state=null,pending=false;
  const field=(name,label,type='checkbox')=>{const l=node('label',label+' '),i=node('input');i.type=type;i.name=name;i.id='openmontage-'+name;inputs[name]=i;l.append(i);form.append(l);return i;};
  field('media_search','OpenMontage medya araması');
  field('visual_analysis','Yerel semantik kare analizi (isteğe bağlı)');form.append(node('p','Kurulum gerekli ise INSTALL_OPENMONTAGE_SEMANTIC.bat dosyasına çift tıklayın. Paketler ve model yalnız açık onayınızla indirilir; normal uygulama ortamı değişmez.'));
  field('reuse_stock_keys','Pexels/Pixabay anahtarlarımı yalnız arama işlemi sırasında OpenMontage ile kullan');
  form.append(node('p','Anahtarlar yalnız alt işlemin belleğine aktarılır; OpenMontage .env dosyasına yazılmaz. İşaretlemezseniz yalnız anahtarsız açık kaynaklar kullanılır.','note'));
  const label=node('label','Medya eşleştirme '),matching=node('select');matching.id='openmontage-matching';inputs.matching=matching;
  for(const [value,text] of [['fast','Hızlı'],['semantic','Semantik — OpenMontage (isteğe bağlı CLIP)']]){const o=node('option',text);o.value=value;matching.append(o);}label.append(matching);form.append(label);
  const advanced=node('details');advanced.append(node('summary','İleri: ayrı yerel kurulum klasörü'));const pathLabel=node('label','Klasör (varsayılan kurulum için boş bırakın) '),root=node('input');root.type='text';root.id='openmontage-root';root.autocomplete='off';root.placeholder='Varsayılan ayrı kurulum';pathLabel.append(root);advanced.append(pathLabel);form.append(advanced);
  const buttons=node('div');buttons.className='settings-actions';form.append(buttons);
  const save=node('button','Kaydet');save.type='submit';buttons.append(save);
  const reset=node('button','Varsayılan klasöre dön');reset.type='button';buttons.append(reset);
  const refresh=node('button','Durumu Yenile');refresh.type='button';buttons.append(refresh);panel.append(form);document.querySelector('#settings-content').append(panel);
  function sync(){save.disabled=reset.disabled=refresh.disabled=pending;for(const i of Object.values(inputs))i.disabled=pending;root.disabled=pending;}
  async function request(method='GET',body){const r=await fetch('/api/settings/openmontage'+(method==='GET'?'?refresh=true':''),{method,cache:'no-store',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-AI-Video-Studio':'settings'},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw new Error(data.message||'OpenMontage ayarları kaydedilemedi.');return data;}
  function display(data){state=data;status.textContent=`${data.status}${data.commit?' · Sürüm '+data.commit:''} · ${data.message}${data.media_search?' · Medya araması açık':''}${data.semantic_ready?' · CLIP hazır':' · CLIP isteğe bağlı; Hızlı kullanılabilir'}`;inputs.visual_analysis.checked=!!data.visual_analysis;inputs.media_search.checked=data.media_search;status.textContent+=` · Semantik medya analizi: ${data.semantic_status||'Kurulum gerekli'}`;inputs.reuse_stock_keys.checked=data.reuse_stock_keys;matching.value=data.matching;matching.querySelector('option[value="semantic"]').disabled=!data.semantic_ready;root.value='';root.placeholder=data.custom_path?'Özel klasör kayıtlı; değiştirmek için yeni yerel klasör girin':'Varsayılan ayrı kurulum';}
  async function operate(method,body){if(pending)return;pending=true;sync();status.textContent='Kontrol ediliyor…';try{display(await request(method,body));}catch(e){status.textContent=e instanceof TypeError||e.name==='TimeoutError'?'OpenMontage durumu alınamadı. Uygulama penceresini kontrol edip Durumu Yenile deyin.':e.message;}finally{pending=false;sync();}}
  form.addEventListener('submit',e=>{e.preventDefault();const body={visual_analysis:inputs.visual_analysis.checked,media_search:inputs.media_search.checked,reuse_stock_keys:inputs.reuse_stock_keys.checked,matching:matching.value};if(root.value.trim())body.root=root.value.trim();operate('POST',body);});
  reset.addEventListener('click',()=>operate('POST',{root:''}));refresh.addEventListener('click',()=>operate('GET'));operate('GET');
}
/* “Motor Durumu”: components, versions, missing pieces in Turkish, one-click install. */
if (window.location.pathname==='/settings') {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=node('section','','settings-panel');panel.id='settings-engine';
  const summary=node('p','Motorlar kontrol ediliyor…');summary.setAttribute('role','status');summary.setAttribute('aria-live','polite');
  const list=node('ul');list.id='engine-components';const install=node('button','Eksikleri kur (OpenMontage)');install.type='button';install.id='engine-install';install.hidden=true;
  const log=node('pre');log.id='engine-log';log.hidden=true;log.style.whiteSpace='pre-wrap';
  const refresh=node('button','Yeniden kontrol et');refresh.type='button';
  panel.append(node('h2','Motor Durumu'),summary,list,install,refresh,log);document.querySelector('#settings-content').append(panel);
  let timer=null;
  async function call(path='',body){const r=await fetch('/api/settings/openmontage/engine'+path,{method:body?'POST':'GET',cache:'no-store',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-AI-Video-Studio':'settings'},...(body?{body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw new Error(d.message||'Motor durumu alınamadı.');return d;}
  function show(d){summary.textContent=d.summary;list.replaceChildren(...d.components.map(c=>{const li=node('li');li.dataset.ok=c.ok;li.append(node('strong',`${c.ok?'✓':'✗'} ${c.name}`),` ${c.version?'('+c.version+') ':''}— ${c.message} `,node('span',`Gerekli: ${c.needed_for}`,'note'));return li;}));
    const s=d.install||{};install.hidden=!(d.can_install||s.status==='running');install.disabled=s.status==='running';install.textContent=s.status==='running'?'Kuruluyor…':'Eksikleri kur (OpenMontage)';
    log.hidden=!s.log?.length;log.textContent=(s.log||[]).join('\n');clearTimeout(timer);if(s.status==='running')timer=setTimeout(load,3000);}
  async function load(){try{show(await call());}catch(e){summary.textContent=e instanceof TypeError||e.name==='TimeoutError'?'Motor durumu alınamadı. Uygulama penceresini kontrol edip Yeniden kontrol et deyin.':e.message;}}
  install.addEventListener('click',async()=>{if(!window.confirm('OpenMontage ayrı bir klasöre kurulacak (internetten indirme yapılır, 5–20 dakika sürebilir). Mevcut projeleriniz etkilenmez. Devam edilsin mi?'))return;install.disabled=true;try{await call('/install',{confirm:true});await load();}catch(e){summary.textContent=e.message;install.disabled=false;}});
  refresh.addEventListener('click',load);load();
}
