/* Part 6: background requests never keep a browser connection open for downloads. */
if (/^\/projects\/[^/]+\/production$/.test(window.location.pathname)) {
  const project=window.location.pathname.split('/')[2],base=`/api/projects/${project}/production/stock`;
  const root=document.querySelector('#production-content'),blocks=document.querySelector('#visual-blocks');
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  // Contextual = scene concepts matched (e.g. ship+ocean), not footage of the named event itself.
  const relevanceText=media=>media.relevance_basis==='contextual'?`${media.relevance_label} (bağlamsal görüntü — olayın kendisi değil)`:media.relevance_basis==='visual'?`${media.relevance_label} (görsel kontrol)`:media.relevance_label;
  const section=node('section','','settings-panel stock-controls');section.id='stock-controls';
  section.append(node('h2','Stok Medya — yapay zekâ seçer, her yuva dolar'),node('p','Medyayı Tamamla: her boş yuva için sırayla (1) planlanan sorguyla stok video, (2) yapay zekânın yazdığı yeni sorgularla video, (3) stok görsel + hafif kamera hareketi, (4) daha geniş konu medyası denenir — her aday, yapay zekâ (varsayılan: Gemini, ücretsiz kota) önizleme karelerine bakıp onaylamadan kullanılmaz. Hiçbiri uymazsa yuva anlatımdan bir motion grafik olur. Metinde [HARİTA], [SAYI], [ÇİZELGE], [KARŞILAŞTIR] veya [LİSTE] işareti olan sahneler doğrudan infografik olur. Yapay zekâ kotası dolarsa iş durur, tamamlanan yuvalar korunur; Medyayı Tamamla’ya tekrar basınca kaldığı yerden devam eder. Seslendirme ve altyazılar değişmez.'));
  const message=node('p','Güncel sahne planı kontrol ediliyor…');message.setAttribute('role','status');
  const controls=node('div','','settings-actions'),warningList=node('ul');section.append(message,controls,warningList);root.insertBefore(section,blocks);
  const recovery=node('section');recovery.id='stock-recovery-report';section.append(recovery);const mix=node('details'),recent=node('details');recent.append(node('summary','Son arama tanısı'));section.append(mix,recent);
  let state=null,pending=false,timer=null,loading=false,previewSlot=null;
  const active=()=>pending||['queued','running'].includes(state?.job?.status);
  function button(parent,text,fn,disabled=false){const b=node('button',text);b.type='button';b.disabled=disabled;b.addEventListener('click',fn);parent.append(b);return b;}
  const complete=button(controls,'Medyayı Tamamla',()=>{if(window.confirm(`Boş ve yapay zekâ onayı olmayan yuvalar doldurulacak. Kilitli ve onaylı seçimler korunur, eski dosyalar silinmez.${state?.ai_engine==='claude'?' Claude çağrıları ücretlidir.':' Gemini ücretsiz kotası kullanılır; hız sınırında kısa beklemeler olabilir.'} Devam edilsin mi?`))start('complete_media');},true);complete.id='stock-complete';
  const download=node('a','Tanılama dosyası indir');download.href=`${base}/diagnostics`;download.id='stock-diagnostics';download.setAttribute('download','');
  controls.append(download);
  const summaryLine=node('p','','provider-status');summaryLine.id='stock-summary';section.insertBefore(summaryLine,controls);
  const stamp=()=>({plan_id:state.plan_id,revision:state.revision});
  async function request(url,method='GET',body){
    let response;
    try{response=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'X-AI-Video-Studio':'projects','Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
    catch{throw new Error('Yerel medya isteği tamamlanamadı. Uygulama penceresini kontrol edip Ekranı Yenile deyin.');}
    let result;try{result=await response.json();}catch{throw new Error('Medya yanıtı okunamadı. Sayfayı yenileyin.');}
    if(!response.ok){const error=new Error(result.message||'Medya işlemi tamamlanamadı.');error.category=result.category;throw error;}
    return result;
  }
  function sync(){complete.disabled=active()||!state;}
  async function operate(fn){if(active()||!state)return;pending=true;sync();try{await fn();await load();}catch(error){message.textContent=error.message;}finally{pending=false;render();}}
  function start(action){return operate(()=>request(base+'/jobs','POST',{...stamp(),action}));}
  function slotJob(slot,action,extra={}){return operate(()=>request(`${base}/slots/${slot.slot_id}/jobs`,'POST',{...stamp(),action,...extra}));}
  function slotAction(slot,action){return operate(()=>request(`${base}/slots/${slot.slot_id}/actions`,'POST',{...stamp(),action}));}
  function thumbnail(media){
    if(!media.preview_url)return node('p','Küçük önizleme yok; indirdikten sonra Önizle düğmesini kullanın.','note');
    const img=node('img');img.className='stock-thumbnail';img.alt=`${media.provider} ${media.media_type==='video'?'video':'görsel'} önizlemesi`;
    img.src=media.preview_url;img.loading='lazy';img.referrerPolicy='no-referrer';return img;
  }
  const TEMPLATE_LABELS={stat:'Büyüyen sayı',map:'Harita + işaret',quote:'Başlık / alıntı',timeline:'Zaman çizelgesi',compare:'Karşılaştırma',list:'Madde listesi'};
  function motionForm(slot){
    const spec=slot.selected_media?.source_metadata?.motion||{template:'quote',data:{text:''},emphasis:''};
    const form=node('form','','settings-panel stock-motion-form');form.noValidate=true;
    const row=(label,el)=>{const g=node('div','','setting-field');const l=node('label',label);g.append(l,el);form.append(g);return el;};
    const sel=row('Şablon',node('select'));for(const [k,v] of Object.entries(TEMPLATE_LABELS)){const o=node('option',v);o.value=k;sel.append(o);}sel.value=spec.template;
    const fields=node('div');form.append(fields);const emphasis=row('Vurgu kelimesi (seslendirmede söylendiği an)',node('input'));emphasis.value=spec.emphasis||'';
    const d=spec.data||{};let inputs={};
    const lines=list=>list.map(e=>typeof e==='string'?e:[e.date??e.label,e.label??e.value].filter(x=>x!==undefined).join(' | ')).join('\n');
    function draw(){fields.replaceChildren();inputs={};const t=sel.value;
      const add=(key,label,value,area)=>{const el=node(area?'textarea':'input');el.value=value??'';if(area)el.rows=4;const g=node('div','','setting-field');const l=node('label',label);g.append(l,el);fields.append(g);inputs[key]=el;};
      if(t==='stat'){add('value','Sayı (anlatımda geçmeli)',d.value);add('label','Açıklama',d.label);}
      if(t==='map'){add('place','Yer adı (anlatımda geçmeli)',d.place);add('lat','Enlem',d.lat);add('lon','Boylam',d.lon);add('label','Etiket',d.label);}
      if(t==='quote')add('text','Metin (anlatımdan birebir)',d.text,true);
      if(t==='timeline')add('events','Her satıra: tarih | açıklama (2–5 satır)',d.events?d.events.map(e=>`${e.date} | ${e.label}`).join('\n'):'',true);
      if(t==='compare'){add('title','Başlık',d.title);add('items','Her satıra: ad | değer (değer isteğe bağlı)',d.items?d.items.map(e=>`${e.label} | ${e.value||''}`).join('\n'):'',true);}
      if(t==='list'){add('title','Başlık',d.title);add('items','Her satıra bir madde (2–4)',d.items?d.items.join('\n'):'',true);}}
    sel.addEventListener('change',draw);draw();
    const save=node('button','Motion metnini kaydet ve yeniden çiz');save.type='submit';form.append(save,node('p','Sayı, tarih, yer ve alıntılar bu sahnenin anlatımında geçmelidir; uydurma bilgi kabul edilmez.','note'));
    form.addEventListener('submit',event=>{event.preventDefault();const t=sel.value,v=k=>inputs[k]?.value.trim()||'';const rows=k=>v(k).split('\n').map(x=>x.split('|').map(y=>y.trim())).filter(x=>x[0]);
      const data=t==='stat'?{value:v('value'),label:v('label')}:t==='map'?{place:v('place'),lat:Number(v('lat')),lon:Number(v('lon')),label:v('label')}:t==='quote'?{text:v('text')}
        :t==='timeline'?{events:rows('events').map(x=>({date:x[0],label:x[1]||''}))}:t==='compare'?{title:v('title'),items:rows('items').map(x=>({label:x[0],value:x[1]||''}))}:{title:v('title'),items:rows('items').map(x=>x[0])};
      slotJob(slot,'motion_edit',{motion:{template:t,data,emphasis:emphasis.value.trim()}});});
    return form;
  }
  function mediaInfo(media){if(media.provider==='generated'&&media.media_type==='video')return `Motion grafik · ${TEMPLATE_LABELS[media.source_metadata?.motion?.template]||''} · 1920×1080 · ${media.source_metadata?.engine==='openmontage'?'OpenMontage':'yerel çizim'}`;if(media.provider==='generated')return `Üretilmiş kart · ${{map:'Konum',number:'Sayı',quote:'Alıntı',title:'Başlık'}[media.source_metadata?.card_kind]||'Başlık'} · 1920×1080`;return `${{pexels:'Pexels',openmontage:'OpenMontage',wikimedia:'Wikimedia Commons'}[media.provider]||'Pixabay'} · ${media.media_type==='video'?'Video':'Görsel'} · ${media.width}×${media.height}${media.width>media.height?' · Yatay'+(Math.abs(media.width/media.height-16/9)<.06?' · 16:9':''):' · Dikey/kare'}`;}
  function sourceInfo(media){
    if(media.provider==='generated'){const info=node('details');info.append(node('summary','Kaynak Bilgisi'),node('p',`Uygulama tarafından üretildi. Yazı anlatımdan alındı: “${media.source_metadata?.card_text||''}”`));return info;}
    const info=node('details');info.append(node('summary','Kaynak Bilgisi'),node('p',`${media.provider} · Medya ID: ${media.media_id} · Oluşturan: ${media.creator_name||'Belirtilmedi'}`));if(media.source_metadata?.license)info.append(node('p',`Lisans: ${media.source_metadata.license} · Yazar: ${media.source_metadata.author||media.creator_name||'Belirtilmedi'} · YouTube açıklamasına kaynak olarak eklenir.`));
    if(media.relevance_label)info.append(node('p',`Alaka: ${relevanceText(media)} · Arama kademesi: ${media.search_tier||'—'} · Sorgu: ${media.query_used}`));
    if(media.provider_query)info.append(node('p',`Sağlayıcı sorgusu: ${media.provider_query}`));
    const link=node('a','Sağlayıcıdaki kaynak sayfası');link.href=media.page_url;link.target='_blank';link.rel='noopener noreferrer';info.append(link);
    if(media.downloaded_at)info.append(node('p',`İndirildi: ${new Date(media.downloaded_at).toLocaleString('tr-TR')} · Yerel dosya: ${media.local_path}`));
    info.append(node('p','Kullanım koşullarını kaynak sayfasından kontrol edin. İndirme, lisans incelemesi yerine geçmez.','note'));return info;
  }
  function slotCard(slot){
    let card=node('article','','stock-slot');card.dataset.slotId=slot.slot_id;
    const media=slot.selected_media;
    const score=media&&media.provider!=='generated'?slot.ai_review?.score:null;
    if(Number.isFinite(score)&&score<9)card.classList.add('stock-slot-check');  // 7–8: worth a look first
    card.append(node('h4',`Medya ${slot.order}${slot.locked?' · Kilitli':''} · ${slot.estimated_start.toFixed(1)}–${slot.estimated_end.toFixed(1)} sn`));
    const stage=slot.director?.stage_label||(slot.locked&&media?'Kilitli (sizin seçiminiz)':media?(slot.ai_review?.approved?'Yapay zekâ onayladı':'Yapay zekâ onayı bekliyor — Medyayı Tamamla deyin'):'Boş — Medyayı Tamamla deyin');
    const stageLine=node('p',`Aşama: ${stage}`,'provider-status');stageLine.className+=' stock-stage';card.append(stageLine);
    if(Number.isFinite(score)){const rel=node('p',`Alaka puanı: ${score}/10${score<9?' — önce buna bakın':''} · ${slot.ai_review.reason||''}`,'stock-relevance');if(slot.ai_review.model)rel.append(node('small',` · ${slot.ai_review.model.replace(/^gemini-/,'')} ile seçildi`,'stock-model'));card.append(rel);}
    if(slot.message)card.append(node('p',`Neden: ${slot.message}`));
    if(media&&!(media.provider==='generated'&&media.media_type==='video'))card.append(thumbnail(media));
    const top=node('div','','settings-actions');card.append(top);
    button(top,'Yeniden seçtir',()=>{
      const own=media&&media.provider!=='generated';
      const reason=own?window.prompt('Bu medya neden uymadı? (isteğe bağlı — örn. “modern bina var”, “konu dışı”). Bu medya bu projede bir daha önerilmez.',''):'';
      if(reason===null)return;
      if(own||window.confirm('Bu yuva için yapay zekâ yeniden aday arar ve seçer. Uygun stok bulunamazsa motion grafik üretilir; yuva boş kalmaz. Devam edilsin mi?'))slotJob(slot,'reselect',own?{reason:reason.trim().slice(0,200)}:{});
    },active()||slot.locked).className='stock-reselect';
    const isMotion=media?.provider==='generated'&&media?.media_type==='video';
    if(isMotion)button(top,'Stok videoyla değiştir',()=>slotJob(slot,'to_stock'),active()||slot.locked).className='stock-to-stock';
    else button(top,'Motion’a çevir',()=>slotJob(slot,'to_motion'),active()||slot.locked).className='stock-to-motion';
    if(isMotion){const preview=node('video');preview.className='stock-preview';preview.src=`${base}/slots/${slot.slot_id}/preview`;preview.controls=true;preview.preload='metadata';preview.muted=true;card.append(preview);
      const edit=node('details');edit.append(node('summary','Motion metnini düzenle'),motionForm(slot));card.append(edit);}
    const more=node('details','','stock-slot-details');more.append(node('summary','Ayrıntılar'));card.append(more);
    const keep=card;card=more;
    card.append(node('p',`${slot.status_label} · ${slot.duration.toFixed(1)} sn`),node('p',`Görsel amaç: ${slot.visual_goal}`),node('p',`Planlanan arama: ${slot.search_query}`));
    for(const step of slot.director?.steps||[]){card.append(node('p',`${step.label}: ${step.queries?.length?'“'+step.queries.join('”, “')+'” · ':''}${{chosen:'seçildi',no_approved_candidate:'onaylanan aday yok',ai_unavailable:'Yapay zekâya ulaşılamadı',kept:'korundu',kept_no_better_option:'daha iyisi yok, korundu'}[step.result]||step.result||''}`));
      for(const j of step.judged||[])card.append(node('p',`· ${j.provider} ${j.media_type==='video'?'video':'görsel'} ${j.media_id} — AI ${j.score}/10 ${j.approved?'✓':'✗'} ${j.reason}`,'note'));}
    for(const s of (slot.director?.searches||[]).filter(s=>s.error))card.append(node('p',`${s.provider} “${s.query}”: ${s.error_text}`,'note'));
    card.append(node('p',`Tekrar durumu: ${slot.repeat_status||'Benzersiz'}`));
    if(slot.subject_anchor)card.append(node('p',`Ana konu: ${slot.subject_anchor}`));
    if(media)card.append(node('p',mediaInfo(media)),sourceInfo(media));
    if(media)card.append(node('p',`Kaynak süre: ${slot.source_duration??media.duration??'—'} sn · Kullanılan: ${slot.used_duration??slot.duration} sn${slot.trim_needed?' · Yerel kesme uygulanacak':''}${slot.portrait_warning?' · Dikey/kare kaynak: çerçeveli kullanım veya manuel kontrol gerekli':''}`));
    if(media?.relevance_label)card.append(node('p',`Alaka: ${relevanceText(media)} · Arama kademesi: ${media.search_tier||'—'}`));
    for(const reason of slot.missing_reason_messages||[])card.append(node('p',reason));if(slot.visual_check)card.append(node('p',`Yerel kare analizi: ${{match:'Görsel bağlam uyumlu',mismatch:'Görsel özne uyumsuz',uncertain:'Elle kontrol gerekli',not_available:'Kurulum gerekli; yalnız metadata',error:'Hata; doğrulama yapılmadı'}[slot.visual_check.verdict]||'Kontrol gerekli'}`));if(media?.source_metadata?.footage_role)card.append(node('p',`Görüntü niteliği: ${{direct_factual:'Doğrudan doğrulanmış kayıt',contextual_broll:'Bağlamsal B-roll; tarihsel gerçeklik kanıtı değildir',illustrative:'Temsili görüntü'}[media.source_metadata.footage_role]||'Elle kontrol gerekli'}`));if(slot.message)card.append(node('p',slot.message));for(const warning of slot.warnings)card.append(node('p',warning,'note'));
    if(slot.coverage_warning)card.append(node('p',slot.coverage_warning,'note'));
    if(slot.search_diagnostics?.length){const diag=node('details');diag.append(node('summary','Arama Tanısı'));for(const d of slot.search_diagnostics)diag.append(node('p',`${d.query} · ${d.summary}`));card.append(diag);}
    const buttons=node('div','','settings-actions');card.append(buttons);
    button(buttons,'Önizle',()=>{previewSlot=previewSlot===slot.slot_id?null:slot.slot_id;render();},!media);
    button(buttons,slot.locked?'Kilidi Aç':'Kilitle',()=>slotAction(slot,slot.locked?'unlock':'lock'),active()||(!slot.locked&&(!media||slot.status!=='complete')));
    button(buttons,'Kaldır',()=>{if(window.confirm('Medya bu yuvadan kaldırılacak. İndirilen dosya proje önbelleğinde korunacak. Devam edilsin mi?'))slotAction(slot,'remove');},active()||slot.locked||!media);
    if(previewSlot===slot.slot_id&&media){
      const preview=node(media.media_type==='video'?'video':'img');preview.className='stock-preview';preview.src=`${base}/slots/${slot.slot_id}/preview`;
      if(media.media_type==='video'){preview.controls=true;preview.preload='metadata';}else preview.alt='Seçilen yerel görsel';card.append(preview);
    }
    return keep;
  }
  function render(){
    for(const old of blocks.querySelectorAll('.stock-scene'))old.remove();
    for(const sceneCard of blocks.querySelectorAll('[data-scene-id]')){
      const slots=state?.slots.filter(s=>s.scene_id===sceneCard.dataset.sceneId)||[];if(!slots.length)continue;
      const media=node('section','','stock-scene');media.append(node('h3',`Medya Yuvaları · ${slots.length} görsel çekim`));for(const slot of slots)media.append(slotCard(slot));sceneCard.append(media);
    }
    summaryLine.textContent=state?.media_summary?.text||'';
    recovery.replaceChildren();const diag=state?.missing_media_diagnostics;if(diag?.unresolved_raw_slots){for(const d of diag.reasons||[])recovery.append(node('p',`${d.count} eksik yuva: ${d.message}`));}
    const counts=state?.media_mix;mix.replaceChildren();if(counts){mix.append(node('summary','Ayrıntılı sayılar'),node('p',`Stok video oranı %${counts.video_ratio_percent} · Motion grafik oranı %${counts.motion_ratio_percent??0} · Ortalama çekim ${counts.average_used_duration} sn · En uzun ${counts.maximum_used_duration} sn · Farklı medya ${counts.unique_media_count}${state.selection_version?' · Seçim sürümü '+state.selection_version:''}`,'note'));}mix.hidden=!counts;
    while(recent.children.length>1)recent.lastChild.remove();for(const d of state?.job?.progress?.search_diagnostics||[])recent.append(node('p',`${d.query} · ${d.summary}`));recent.hidden=recent.children.length===1;
    warningList.replaceChildren();for(const text of state?.warnings||[])warningList.append(node('li',text));sync();
  }
  async function load(){
    if(loading)return;loading=true;
    try{state=await request(base);const job=state.job;
      message.textContent=job?.status==='error'?`⚠ ${job.error_message}`:job&&['queued','running'].includes(job.status)?`${job.progress.percent}% · ${job.progress.message}`:`${state.slots.filter(s=>s.status==='complete').length}/${state.slots.length} medya tamamlandı. ${!state.providers.pixabay&&!state.providers.wikimedia&&!state.providers.openmontage?'Ayarlar → Pixabay anahtarını kaydedin.':'Seçimleri önizleyip anlatıma uygunluğu kontrol edin.'}`;
      render();
    }catch(error){state=null;message.textContent=error.message;render();}
    finally{loading=false;clearTimeout(timer);if(['queued','running'].includes(state?.job?.status))timer=setTimeout(load,1200);}
  }
  window.addEventListener('production-plan-rendered',load);
  window.addEventListener('pagehide',()=>clearTimeout(timer));load();
}
