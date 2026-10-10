/* Part 6: background requests never keep a browser connection open for downloads. */
if (/^\/projects\/[^/]+\/production$/.test(window.location.pathname)) {
  const project=window.location.pathname.split('/')[2],base=`/api/projects/${project}/production/stock`;
  const root=document.querySelector('#production-content'),blocks=document.querySelector('#visual-blocks');
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  const section=node('section','','settings-panel stock-controls');section.id='stock-controls';
  section.append(node('h2','Stok Medya — video ve görsel seçimi'),node('p','Alaka konu ve metadata ile değerlendirilir. Ayarlar’da açıkça etkinleştirilmiş yerel CLIP modeli varsa gerçek video kareleri de incelenir; bu tarihsel gerçeklik doğrulaması değildir. Önce ilgili video aranır, bulunamazsa ilgili görsel denenir. Yeterli ilgili video varsa hedef yaklaşık %80–95 videodur; ilgisiz medya oran için seçilmez. Seslendirme ve altyazılar değiştirilmez.'));
  const message=node('p','Güncel sahne planı kontrol ediliyor…');message.setAttribute('role','status');
  const controls=node('div','','settings-actions'),warningList=node('ul');section.append(message,controls,warningList);root.insertBefore(section,blocks);
  const recovery=node('section');recovery.id='stock-recovery-report';section.append(recovery);const mix=node('p'),recent=node('details');recent.append(node('summary','Son arama tanısı'));section.append(mix,recent);
  let state=null,pending=false,timer=null,loading=false,candidateSlot=null,previewSlot=null;
  const active=()=>pending||['queued','running'].includes(state?.job?.status);
  function button(parent,text,fn,disabled=false){const b=node('button',text);b.type='button';b.disabled=disabled;b.addEventListener('click',fn);parent.append(b);return b;}
  const auto=button(controls,'Medyayı Otomatik Bul',()=>start('auto'));
  const missing=button(controls,'Eksik Medyaları Tamamla',()=>start('missing'));
  const relevance=button(controls,'Alakaya Göre Medyayı Yeniden Ara',()=>{
    if(window.confirm('Kilitli medyalar korunacak. Diğer yuvalar konuya uygunluk sırasıyla yeniden aranacak. Önceki seçimler ve indirilen dosyalar saklanır; seslendirme ve altyazılar değişmez. Devam edilsin mi?'))start('relevance_research');
  });relevance.id='stock-relevance-research';
  const short=button(controls,'Eksik Medyaları Akıllı Tamamla',()=>{if(window.confirm('Geçerli seçimler ve kilitli aralıklar korunur. Yalnız eksikler için yeni konu sorguları/sayfalar denenir; gerekirse aynı sahne içinde zaman çizelgesi toparlanır. Seslendirme, altyazılar ve eski dosyalar değişmez. Devam edilsin mi?'))start('smart_recovery');});short.id='stock-short-clips';
  const bulk=button(controls,'Uygun görselleri videoyla değiştir',()=>{if(window.confirm('Video tercihli, kilitsiz görsel yuvalarında video aranacak. Mevcut görseller yalnız video başarıyla indirildiğinde değiştirilecek. Devam edilsin mi?'))start('replace_images');});
  const toleranceLabel=node('label','Kısa video toleransı (sn) '),tolerance=node('select');
  for(const value of [0,.5,1,1.25,1.5]){const option=node('option',String(value).replace('.',','));option.value=String(value);tolerance.append(option);}tolerance.value='1.25';toleranceLabel.append(tolerance);controls.append(toleranceLabel);
  const resume=button(controls,'Devam Et',()=>operate(()=>request(`${base}/jobs/${state.job.id}/resume`,'POST',stamp())));resume.hidden=true;
  button(controls,'Medya Durumunu Yenile',load);
  const stamp=()=>({plan_id:state.plan_id,revision:state.revision});
  async function request(url,method='GET',body){
    let response;
    try{response=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'X-AI-Video-Studio':'projects','Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
    catch{throw new Error('Yerel medya isteği tamamlanamadı. Uygulama penceresini kontrol edip Medya Durumunu Yenile deyin.');}
    let result;try{result=await response.json();}catch{throw new Error('Medya yanıtı okunamadı. Sayfayı yenileyin.');}
    if(!response.ok){const error=new Error(result.message||'Medya işlemi tamamlanamadı.');error.category=result.category;throw error;}
    return result;
  }
  function sync(){auto.disabled=active()||!state;missing.disabled=active()||!state;relevance.disabled=active()||!state;short.disabled=active()||!state;resume.hidden=state?.job?.status!=='error';resume.disabled=active();tolerance.disabled=active()||!state;bulk.disabled=active()||!state?.slots.some(s=>!s.locked&&s.preferred_type==='stock_video'&&s.selected_media?.media_type==='image');}
  async function operate(fn){if(active())return;pending=true;sync();try{await fn();await load();}catch(error){message.textContent=error.message;}finally{pending=false;render();}}
  function start(action){return operate(()=>request(base+'/jobs','POST',{...stamp(),action,video_duration_tolerance_seconds:Number(tolerance.value)}));}
  function slotJob(slot,action,extra={}){return operate(()=>request(`${base}/slots/${slot.slot_id}/jobs`,'POST',{...stamp(),action,video_duration_tolerance_seconds:Number(tolerance.value),...extra}));}
  function slotAction(slot,action){return operate(()=>request(`${base}/slots/${slot.slot_id}/actions`,'POST',{...stamp(),action}));}
  function candidateID(m){return `${m.provider}:${m.media_type}:${m.media_id}`;}
  async function select(slot,media){
    const duplicate=state.slots.some(s=>s.slot_id!==slot.slot_id&&s.selected_media?.provider===media.provider&&s.selected_media?.media_id===media.media_id&&s.selected_media?.media_type===media.media_type);
    if(duplicate&&!window.confirm('Bu medya başka yuvada kullanılıyor. Aynı dosyanın tekrar kullanımını onaylıyor musunuz?'))return;
    candidateSlot=null;await slotJob(slot,'select',{candidate_id:candidateID(media),allow_duplicate:duplicate});
  }
  function thumbnail(media){
    if(!media.preview_url)return node('p','Küçük önizleme yok; indirdikten sonra Önizle düğmesini kullanın.','note');
    const img=node('img');img.className='stock-thumbnail';img.alt=`${media.provider} ${media.media_type==='video'?'video':'görsel'} önizlemesi`;
    img.src=media.preview_url;img.loading='lazy';img.referrerPolicy='no-referrer';return img;
  }
  function mediaInfo(media){return `${media.provider==='pexels'?'Pexels':media.provider==='openmontage'?'OpenMontage':'Pixabay'} · ${media.media_type==='video'?'Video':'Görsel'} · ${media.width}×${media.height}${media.width>media.height?' · Yatay'+(Math.abs(media.width/media.height-16/9)<.06?' · 16:9':''):' · Dikey/kare'}`;}
  function sourceInfo(media){
    const info=node('details');info.append(node('summary','Kaynak Bilgisi'),node('p',`${media.provider} · Medya ID: ${media.media_id} · Oluşturan: ${media.creator_name||'Belirtilmedi'}`));
    if(media.relevance_label)info.append(node('p',`Alaka: ${media.relevance_label} · Arama kademesi: ${media.search_tier||'—'} · Sorgu: ${media.query_used}`));
    if(media.provider_query)info.append(node('p',`Sağlayıcı sorgusu: ${media.provider_query}`));
    const link=node('a','Sağlayıcıdaki kaynak sayfası');link.href=media.page_url;link.target='_blank';link.rel='noopener noreferrer';info.append(link);
    if(media.downloaded_at)info.append(node('p',`İndirildi: ${new Date(media.downloaded_at).toLocaleString('tr-TR')} · Yerel dosya: ${media.local_path}`));
    info.append(node('p','Kullanım koşullarını kaynak sayfasından kontrol edin. İndirme, lisans incelemesi yerine geçmez.','note'));return info;
  }
  function candidateBrowser(slot){
    const browser=node('div','','stock-candidates');browser.append(node('h5','Alternatif medya adayları'));
    if(!slot.candidates.length)browser.append(node('p','Henüz aday yok. Yeniden Ara düğmesine basın.'));
    for(const media of slot.candidates){const card=node('article','','stock-candidate');card.append(thumbnail(media),node('p',mediaInfo(media)),node('p',`Arama: ${media.query_used}`),node('p',`Alaka: ${media.relevance_label||'Henüz değerlendirilmedi'}`),sourceInfo(media));button(card,'Bu Medyayı Seç',()=>select(slot,media),active()||slot.locked);browser.append(card);}
    button(browser,'Adayları Kapat',()=>{candidateSlot=null;render();});return browser;
  }
  function slotCard(slot){
    const card=node('article','','stock-slot');card.dataset.slotId=slot.slot_id;
    card.append(node('h4',`Medya ${slot.order}${slot.locked?' · Kilitli':''} · ${slot.estimated_start.toFixed(1)}–${slot.estimated_end.toFixed(1)} sn`),node('p',`${slot.status_label} · ${slot.duration.toFixed(1)} sn`),node('p',`Görsel amaç: ${slot.visual_goal}`),node('p',`Arama: ${slot.search_query}`));
    const media=slot.selected_media;
    card.append(node('p',`Tekrar durumu: ${slot.repeat_status||'Benzersiz'}`));
    if(slot.subject_anchor)card.append(node('p',`Ana konu: ${slot.subject_anchor}`));
    if(media)card.append(thumbnail(media),node('p',mediaInfo(media)),sourceInfo(media));
    if(media)card.append(node('p',`Kaynak süre: ${slot.source_duration??media.duration??'—'} sn · Kullanılan: ${slot.used_duration??slot.duration} sn${slot.trim_needed?' · Yerel kesme uygulanacak':''}${slot.portrait_warning?' · Dikey/kare kaynak: çerçeveli kullanım veya manuel kontrol gerekli':''}`));
    if(media?.relevance_label)card.append(node('p',`Alaka: ${media.relevance_label} · Arama kademesi: ${media.search_tier||'—'}`));
    for(const reason of slot.missing_reason_messages||[])card.append(node('p',reason));if(slot.visual_check)card.append(node('p',`Yerel kare analizi: ${{match:'Görsel bağlam uyumlu',mismatch:'Görsel özne uyumsuz',uncertain:'Elle kontrol gerekli',not_available:'Kurulum gerekli; yalnız metadata',error:'Hata; doğrulama yapılmadı'}[slot.visual_check.verdict]||'Kontrol gerekli'}`));if(media?.source_metadata?.footage_role)card.append(node('p',`Görüntü niteliği: ${{direct_factual:'Doğrudan doğrulanmış kayıt',contextual_broll:'Bağlamsal B-roll; tarihsel gerçeklik kanıtı değildir',illustrative:'Temsili görüntü'}[media.source_metadata.footage_role]||'Elle kontrol gerekli'}`));if(slot.message)card.append(node('p',slot.message));for(const warning of slot.warnings)card.append(node('p',warning,'note'));
    if(slot.coverage_warning)card.append(node('p',slot.coverage_warning,'note'));
    if(slot.search_diagnostics?.length){const diag=node('details');diag.append(node('summary','Arama Tanısı'));for(const d of slot.search_diagnostics)diag.append(node('p',`${d.query} · ${d.summary}`));card.append(diag);}
    const buttons=node('div','','settings-actions');card.append(buttons);
    button(buttons,'Önizle',()=>{previewSlot=previewSlot===slot.slot_id?null:slot.slot_id;render();},!media);
    button(buttons,'Değiştir',()=>{candidateSlot=candidateSlot===slot.slot_id?null:slot.slot_id;render();},active()||slot.locked);
    button(buttons,'Yeniden Ara',()=>{candidateSlot=slot.slot_id;slotJob(slot,'search');},active()||slot.locked);
    if(media?.media_type==='image')button(buttons,'Video ile değiştirmeyi dene',()=>{candidateSlot=slot.slot_id;slotJob(slot,'search_videos');},active()||slot.locked);
    button(buttons,slot.locked?'Kilidi Aç':'Kilitle',()=>slotAction(slot,slot.locked?'unlock':'lock'),active()||(!slot.locked&&(!media||slot.status!=='complete')));
    button(buttons,'Kaldır',()=>{if(window.confirm('Medya bu yuvadan kaldırılacak. İndirilen dosya proje önbelleğinde korunacak. Devam edilsin mi?'))slotAction(slot,'remove');},active()||slot.locked||!media);
    if(previewSlot===slot.slot_id&&media){
      const preview=node(media.media_type==='video'?'video':'img');preview.className='stock-preview';preview.src=`${base}/slots/${slot.slot_id}/preview`;
      if(media.media_type==='video'){preview.controls=true;preview.preload='metadata';}else preview.alt='Seçilen yerel görsel';card.append(preview);
    }
    if(candidateSlot===slot.slot_id)card.append(candidateBrowser(slot));return card;
  }
  function render(){
    for(const old of blocks.querySelectorAll('.stock-scene'))old.remove();
    for(const sceneCard of blocks.querySelectorAll('[data-scene-id]')){
      const slots=state?.slots.filter(s=>s.scene_id===sceneCard.dataset.sceneId)||[];if(!slots.length)continue;
      const media=node('section','','stock-scene');media.append(node('h3',`Medya Yuvaları · ${slots.length} görsel çekim`));for(const slot of slots)media.append(slotCard(slot));sceneCard.append(media);
    }
    recovery.replaceChildren();const diag=state?.missing_media_diagnostics;if(diag){recovery.append(node('p',`${diag.raw_stock_slots} medya alanı · ${diag.selected_stock_assets} tamamlandı · ${diag.unresolved_raw_slots} eksik`));for(const d of diag.reasons||[])recovery.append(node('p',`${d.count} alan: ${d.message}`));}const recovered=state?.recovery_report;if(recovered)recovery.append(node('p',`Akıllı kurgu: ${recovered.render_ready?'Tamamlandı':'Eksikler var'} · ${recovered.effective_covered_duration} saniye kapsandı · Eksik süre: ${recovered.effective_uncovered_duration} sn · ${recovered.effective_render_segments} etkili bölüm`));const counts=state?.media_mix;mix.textContent=counts?`${counts.total_slots} medya yuvası · Video: ${counts.selected_videos} · Görsel: ${counts.selected_images} · ${counts.unresolved_slots} eksik${Number.isFinite(counts.video_ratio_percent)?' · Video oranı: '+counts.video_ratio_percent+'%':''}${Number.isFinite(counts.average_used_duration)?' · Ortalama çekim: '+counts.average_used_duration+' sn · En uzun: '+counts.maximum_used_duration+' sn · Benzersiz medya: '+counts.unique_media_count:''}${state.selection_version?' · Medya seçim sürümü '+state.selection_version:''}`:'';
    while(recent.children.length>1)recent.lastChild.remove();for(const d of state?.job?.progress?.search_diagnostics||[])recent.append(node('p',`${d.query} · ${d.summary}`));recent.hidden=recent.children.length===1;
    warningList.replaceChildren();for(const text of state?.warnings||[])warningList.append(node('li',text));sync();
  }
  async function load(){
    if(loading)return;loading=true;
    try{state=await request(base);if(state.search_options)tolerance.value=String(state.search_options.video_duration_tolerance_seconds);const job=state.job;
      message.textContent=job?.status==='error'?`${job.error_message} · Tanı: ${job.progress.category}`:job&&['queued','running'].includes(job.status)?`${job.progress.percent}% · ${job.progress.message}`:`${state.slots.filter(s=>s.status==='complete').length}/${state.slots.length} medya tamamlandı. ${!state.providers.pexels&&!state.providers.pixabay&&!state.providers.openmontage?'Ayarlar → Pexels/Pixabay anahtarını kaydedin veya isteğe bağlı OpenMontage medya aramasını açın.':'Seçimleri önizleyip anlatıma uygunluğu kontrol edin.'}`;
      render();
    }catch(error){state=null;message.textContent=error.message;render();}
    finally{loading=false;clearTimeout(timer);if(['queued','running'].includes(state?.job?.status))timer=setTimeout(load,1200);}
  }
  window.addEventListener('production-plan-rendered',load);
  window.addEventListener('pagehide',()=>clearTimeout(timer));load();
}
