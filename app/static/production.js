/* Existing Part 5 production editor; stock.js adds only Part 6 media slots. */
if (/^\/projects\/[^/]+\/production$/.test(window.location.pathname)) {
  const id=window.location.pathname.split('/')[2], base=`/api/projects/${id}/production`;
  const root=document.querySelector('#production-content');root.hidden=false;
  let view=null,job=null,timer=null,inFlight=false,editing=null;
  const display={stock_video:'Stok video',stock_image:'Stok görsel',ai_image:'AI görsel',motion_graphic:'Hareketli grafik',user_media:'Kullanıcı medyası',hard_cut:'Kesme',crossfade:'Yumuşak geçiş',fade:'Solma',none:'Yok',slow_zoom:'Yavaş yaklaşma',pan:'Kaydırma',ken_burns:'Görsel üzerinde yaklaşma/kaydırma',overlay:'Üst katman',emphasis_text:'Vurgu yazısı',wide:'Geniş',medium:'Orta',close:'Yakın',detail:'Detay',person:'Kişi',object:'Nesne',environment:'Ortam',movement:'Hareket',graphic:'Grafik'};
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  function button(parent,text,fn,disabled=false){const b=node('button',text);b.type='button';b.dataset.unavailable=String(disabled);b.addEventListener('click',fn);parent.append(b);return b;}
  const back=node('a','← Projeye dön');back.href=`/projects/${id}`;root.append(back);
  root.append(node('p','Onaylı senaryodan anlamlı sahneler ve kurgu önerileri hazırlayın. Stok medyayı aşağıdaki medya yuvalarına indirin. Seslendirme ve video oluşturma sonraki aşamalardadır.'));
  root.append(node('p','Yukarı/Aşağı taşı yalnızca görsel tasarımı taşır; onaylı anlatım aynı sırada kalır. Kilitli sahneler yeniden planlamada korunur.','note'));
  const status=node('p','Yükleniyor…');status.id='production-status';status.setAttribute('role','status');root.append(status);
  const provider=node('select');provider.id='production-provider';
  for(const name of ['ollama','gemini','openai']){const option=node('option',name==='ollama'?'Ollama — yerel':name==='gemini'?'Gemini':'OpenAI');option.value=name;provider.append(option);}
  const label=node('label','Planlama AI sağlayıcısı');label.htmlFor=provider.id;root.append(label,provider);
  const actions=node('div','','settings-actions');root.append(actions);
  const planButton=button(actions,'Görsel / Kurgu Planını Hazırla',generate);
  button(actions,'Kalite Kontrolünü Yenile',()=>{if(!editing)load();});
  const resume=button(actions,'Plan İşlemine Devam Et',continueJob);resume.hidden=true;
  const versions=node('select');versions.id='production-versions';const vl=node('label','Plan sürümleri');vl.htmlFor=versions.id;root.append(vl,versions);
  const summary=node('p');summary.id='production-summary';root.append(summary);
  const warnings=node('ul');warnings.id='production-warnings';root.append(node('h2','Sahne Planı Kontrolü'),warnings);
  const later=node('details');later.append(node('summary','Sonraki aşamalar için eksikler — hazırlık'));const laterWarnings=node('ul');later.append(laterWarnings);root.append(later);
  const blocks=node('div');blocks.id='visual-blocks';root.append(blocks);
  const music=node('form','','settings-panel');music.id='production-music';music.append(node('h2','Lisanslı Yerel Müzik — sonraki çalıştırma tercihleri'));
  for(const [name,text,type] of [['enabled','Müzik açık','checkbox'],['mood','Duygu / tür','text'],['local_file_label','Lisanslı müzik adı (dosya işleme daha sonra)','text'],['license_confirmed','Müziğin kullanım lisansını kontrol ettim','checkbox'],['volume','Ses seviyesi (0–1)','number'],['fade_in','Başlangıç fade (saniye)','number'],['fade_out','Bitiş fade (saniye)','number'],['ducking','Seslendirme sırasında müziği azalt','checkbox']]){
    const l=node('label',text),input=node('input');input.type=type;input.name=name;input.id=`music-${name}`;l.htmlFor=input.id;
    if(type==='number'){input.min=0;input.max=name==='volume'?1:30;input.step=.05;}music.append(l,input);
  }
  const save=node('button','Müzik Tercihlerini Kaydet');save.type='submit';music.append(save);root.append(music);
  const busy=()=>Boolean(inFlight||job&&['queued','analyzing','planning','generating','checking'].includes(job.status));
  const stamp=()=>({plan_id:view.plan.plan_id,revision:view.plan.revision});
  async function request(url,method='GET',body){
    let response;try{response=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'X-AI-Video-Studio':'projects','Content-Type':'application/json'},...(body!==undefined?{body:JSON.stringify(body)}:{})});}
    catch{throw new Error('Yerel istek tamamlanamadı. Uygulama penceresini kontrol edip yenileyin.');}
    let result;try{result=await response.json();}catch{throw new Error('Yerel yanıt okunamadı. Sayfayı yenileyip tekrar deneyin.');}
    if(!response.ok)throw new Error(result.message||'Plan işlemi tamamlanamadı.');return result;
  }
  function sync(){
    planButton.disabled=busy()||!view?.approved_script||Boolean(editing);provider.disabled=busy()||Boolean(editing);
    versions.disabled=busy()||Boolean(editing)||!view?.versions.length;save.disabled=busy()||!view?.plan||Boolean(editing);
    resume.hidden=job?.status!=='error'||!['visual','visual_scene'].includes(job.action);resume.disabled=busy()||Boolean(editing);
    for(const b of blocks.querySelectorAll('button'))b.disabled=busy()||b.dataset.unavailable==='true'||Boolean(editing&&!b.closest('form'));
  }
  async function operation(fn){if(busy())return;inFlight=true;sync();try{await fn();editing=null;await load();}catch(error){status.textContent=error.message;}finally{inFlight=false;sync();if(job&&['queued','analyzing','planning','generating','checking'].includes(job.status)){clearTimeout(timer);timer=setTimeout(load,1000);}}}
  const costConsent=()=>provider.value==='ollama'||window.confirm('Bu planlama işlemi bulut API kotası veya ücret kullanabilir. Onaylıyor musunuz?');
  async function generate(){const replaced=Boolean(view?.plan);if(replaced&&!window.confirm('Yeni plan sürümü oluşturulacak. Önceki sürüm saklanacak; aynı senaryodaki kilitli sahneler korunacak. Devam edilsin mi?'))return;if(!costConsent())return;await operation(()=>request(base+'/plan','POST',{provider:provider.value,cost_confirmed:provider.value!=='ollama',confirm_replace_plan:replaced}));}
  async function continueJob(){const repair=job.progress.visual_repair?.status==='awaiting_cost_confirmation';if(job.provider!=='ollama'&&!window.confirm(repair?'Aynı sağlayıcıyla yalnızca bir görsel metadata düzeltmesi yapılacak. Bu ikinci çağrı ek API kotası veya ücret kullanabilir. Onaylıyor musunuz?':'Devam etmek API kotası veya ücret kullanabilir. Onaylıyor musunuz?'))return;await operation(()=>request(`/api/projects/${id}/script/jobs/${job.id}/resume`,'POST',{confirm_replace_approved:false,...(repair?{visual_repair_cost_confirmed:true}:{})}));}
  function action(block,name,extra={}){return operation(()=>request(`${base}/scenes/${block.id}/actions`,'POST',{...stamp(),action:name,...extra}));}
  function sceneCard(block,index){
    const card=node('article','','settings-panel scene-card');card.dataset.sceneId=block.id;
    card.append(node('h3',`Sahne ${index+1}${block.locked?' · Kilitli':''} · ${block.start.toFixed(1)}–${block.end.toFixed(1)} sn`),node('p',`${block.timing_source==='tts'?'Gerçek anlatım zamanlaması':'Tahmini zamanlama'} · Tahmini süre: ${block.estimated_duration.toFixed(1)} sn`,'note'),node('p',block.narration,'scene-narration'),node('p',`Amaç: ${block.purpose} · Duygu: ${block.mood} · Önem: ${block.importance}`),node('p',`Görsel niyet: ${block.visual_intent}`),node('p',`Birincil sorgu (İngilizce): ${block.stock_query}`),node('p',`Alternatifler: ${block.alternative_stock_queries.join(' / ')}`),node('p',`Tür: ${display[block.media_type]} · Kompozisyon: ${display[block.composition]} · Geçiş: ${display[block.transition]} · Hareket: ${display[block.motion]}`),node('p',`Vurgu yazısı (${block.overlay_language}): ${block.overlay_text||'Yok'}`),node('p',`Özneler: ${block.entities.join(', ')||'Belirtilmedi'} · Konum: ${block.location||'Yok'} · Eylem: ${block.action||'Yok'}`),node('p',`Çekim önerisi: ${block.shot_suggestion||'Belirtilmedi'}`),node('p',`Notlar: ${block.notes||'Yok'}`));
    const controls=node('div','','settings-actions');card.append(controls);const stale=view.plan.status!=='ready',disabled=stale||block.locked;
    button(controls,'Düzenle',()=>openEditor(card,block),disabled);
    button(controls,'Bu sahneyi yeniden planla',()=>{if(costConsent())operation(()=>request(`${base}/scenes/${block.id}/regenerate`,'POST',{...stamp(),provider:provider.value,cost_confirmed:provider.value!=='ollama'}));},disabled);
    button(controls,'Sahneyi böl',()=>openSplit(card,block),disabled);
    button(controls,'Sonraki sahneyle birleştir',()=>{if(window.confirm('Anlatımlar birleştirilecek; ilk sahnenin görsel tasarımı kullanılacak. Eski plan sürümü saklanacak. Devam edilsin mi?'))action(block,'merge');},disabled||index===view.plan.blocks.length-1||view.plan.blocks[index+1]?.locked);
    button(controls,'Yukarı taşı',()=>action(block,'up'),disabled||index===0||view.plan.blocks[index-1]?.locked);
    button(controls,'Aşağı taşı',()=>action(block,'down'),disabled||index===view.plan.blocks.length-1||view.plan.blocks[index+1]?.locked);
    button(controls,block.locked?'Kilidi aç':'Kilitle',()=>action(block,block.locked?'unlock':'lock'),stale);return card;
  }
  function renderCards(){blocks.replaceChildren();for(const [index,block]of(view?.plan?.blocks||[]).entries())blocks.append(sceneCard(block,index));window.dispatchEvent(new CustomEvent('production-plan-rendered'));}
  function cancelEditor(){editing=null;renderCards();sync();}
  function openEditor(card,block){
    if(editing)return;editing=block.id;sync();const form=node('form','','scene-editor');card.append(form);
    for(const [name,text] of [['purpose','Amaç'],['mood','Duygu'],['visual_intent','Görsel niyet'],['stock_query','Birincil sorgu (İngilizce)'],['alternative_stock_queries','Bir–beş farklı alternatif sorgu (her satıra bir)'],['entities','Özneler (her satıra bir)'],['location','Konum'],['action','Eylem'],['shot_suggestion','Çekim önerisi'],['notes','Notlar'],['overlay_text','Kısa vurgu yazısı — boşsa yok'],['importance','Önem (0–100)']]){
      const l=node('label',text),input=node(['visual_intent','alternative_stock_queries','entities','notes'].includes(name)?'textarea':'input');input.name=name;input.id=`scene-${block.id}-${name}`;l.htmlFor=input.id;input.value=Array.isArray(block[name])?block[name].join('\n'):block[name];if(name==='importance'){input.type='number';input.min=0;input.max=100;input.required=true;}form.append(l,input);
    }
    for(const [name,text,choices] of [['media_type','Medya türü',['stock_video','stock_image','ai_image','motion_graphic','user_media']],['composition','Kompozisyon',['wide','medium','close','detail','person','object','environment','movement','graphic']],['transition','Geçiş',['hard_cut','crossfade','fade','none']],['motion','Hareket',['none','slow_zoom','pan','ken_burns','overlay','emphasis_text']]]){
      const l=node('label',text),select=node('select');select.name=name;select.id=`scene-${block.id}-${name}`;l.htmlFor=select.id;for(const choice of choices){const option=node('option',display[choice]);option.value=choice;select.append(option);}select.value=block[name];form.append(l,select);
    }
    const submit=node('button','Kaydet');submit.type='submit';form.append(submit);button(form,'Vazgeç',cancelEditor);
    form.addEventListener('submit',event=>{event.preventDefault();const changes={};for(const input of form.elements)if(input.name)changes[input.name]=['entities','alternative_stock_queries'].includes(input.name)?input.value.split('\n').map(x=>x.trim()).filter(Boolean):input.name==='importance'?Number(input.value):input.value;operation(()=>request(`${base}/scenes/${block.id}`,'PUT',{...stamp(),changes}));});
  }
  function openSplit(card,block){
    if(editing)return;editing=block.id;sync();const form=node('form','','scene-editor');form.append(node('p','İlk sahnenin biteceği anlamlı cümle sınırını seçin. Hiçbir kelime silinmez.'));const select=node('select');select.setAttribute('aria-label','Bölme noktası');const text=block.narration;
    let matches=[...text.matchAll(/[.!?。！？](?:["”’])?\s+/gu)];if(!matches.length){form.append(node('p','Cümle sınırı yok; anlamlı bir kelime sınırı seçin.','note'));matches=[...text.matchAll(/\s+/gu)];}
    for(const match of matches){const at=match.index+match[0].length;if(at>=text.length)continue;const option=node('option',text.slice(Math.max(0,at-70),at).trim());option.value=at;select.append(option);}
    if(!select.options.length){editing=null;status.textContent='Bu sahnede iki dolu anlatım parçası oluşturacak sınır yok.';sync();return;}
    form.append(select);const submit=node('button','Buradan böl');submit.type='submit';form.append(submit);button(form,'Vazgeç',cancelEditor);card.append(form);form.addEventListener('submit',event=>{event.preventDefault();action(block,'split',{split_at:Number(select.value)});});
  }
  async function load(){
    try{[view,job]=await Promise.all([request(base),request(`/api/projects/${id}/script`).then(x=>x.job)]);
      status.textContent=job&&['visual','visual_scene'].includes(job.action)&&['queued','analyzing','planning','generating','checking','error'].includes(job.status)?`${job.status_label} · ${job.progress.percent}% ${job.error_message||''}${job.status==='error'&&job.progress.error_category?' · Tanı: '+(job.progress.error_diagnostic||job.progress.error_category):''}`:view.state;
      warnings.replaceChildren();for(const text of view.scene_warnings)warnings.append(node('li',text));laterWarnings.replaceChildren();for(const text of view.warnings)laterWarnings.append(node('li',text));if(!view.approved_script)warnings.prepend(node('li','Önce senaryo sürümünü onaylayın.'));
      versions.replaceChildren();for(const v of view.versions){const option=node('option',`Plan Sürümü ${v.plan_version}${v.active?' · Aktif plan':''} · ${v.scene_count} sahne · ${v.status==='outdated'?'Eski plan':v.status==='approval_required'?'Onay gerekli':'Hazır'} · ${v.provider} · ${new Date(v.created_at).toLocaleString('tr-TR')}`);option.value=v.plan_id;versions.append(option);}
      if(view.plan){versions.value=view.plan.plan_id;summary.textContent=`Plan Sürümü ${view.plan.plan_version} · Aktif plan · Senaryo Sürümü ${view.plan.source_script_version||'eski'} · ${view.plan.blocks.length} sahne · ${view.plan.model||'Eski kayıt'} · ${view.coverage_complete?'Onaylı anlatım tam ve aynı sırayla kapsanıyor.':'Güncel senaryo kapsamı doğrulanamadı.'}${view.plan.status==='outdated'?' Bu plan eski senaryoya/dile ait.':''}`;for(const input of music.elements){if(!input.name)continue;if(input.type==='checkbox')input.checked=view.plan.music[input.name];else input.value=view.plan.music[input.name];}}
      else summary.textContent='Onaylı senaryodan ilk planınızı hazırlayın.';
      if(!editing)renderCards();sync();clearTimeout(timer);if(busy()&&!inFlight)timer=setTimeout(load,1000);
    }catch(error){status.textContent=error.message;}
  }
  versions.addEventListener('change',()=>{const chosen=versions.value;if(!window.confirm('Seçilen plan aktif olacak. Mevcut plan sürümü saklanacak. Devam edilsin mi?')){versions.value=view.plan.plan_id;return;}operation(()=>request(`${base}/versions/${chosen}/select`,'POST',{confirm:true}));});
  music.addEventListener('submit',event=>{event.preventDefault();const data={section_changes:view.plan.music.section_changes};for(const input of music.elements)if(input.name)data[input.name]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;operation(()=>request(base,'PUT',{music:data}));});
  window.addEventListener('pagehide',()=>clearTimeout(timer));load();
}
