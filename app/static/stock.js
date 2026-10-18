/* Part 6: background requests never keep a browser connection open for downloads. */
if (/^\/projects\/[^/]+\/production$/.test(window.location.pathname)) {
  const project=window.location.pathname.split('/')[2],base=`/api/projects/${project}/production/stock`;
  const root=document.querySelector('#production-content'),blocks=document.querySelector('#visual-blocks');
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  // Contextual = scene concepts matched (e.g. ship+ocean), not footage of the named event itself.
  const relevanceText=media=>media.relevance_basis==='contextual'?`${media.relevance_label} (bağlamsal görüntü — olayın kendisi değil)`:media.relevance_basis==='visual'?`${media.relevance_label} (görsel kontrol)`:media.relevance_label;
  const section=node('section','','settings-panel stock-controls');section.id='stock-controls';
  const modeText=node('p');
  section.append(node('h2','Stok Medya — kaynak hazırlama'),modeText);
  const message=node('p','Güncel sahne planı kontrol ediliyor…');message.setAttribute('role','status');
  const controls=node('div','','settings-actions'),warningList=node('ul');section.append(message,controls,warningList);root.insertBefore(section,blocks);
  const recovery=node('section');recovery.id='stock-recovery-report';const recoveryDrawer=node('details');recoveryDrawer.id='stock-recovery-drawer';recoveryDrawer.append(node('summary','Eksik medya tanısı'),recovery);section.append(recoveryDrawer);const mix=node('details'),recent=node('details');recent.append(node('summary','Son arama tanısı'));section.append(mix,recent);
  const performanceLine=node('p','','note');performanceLine.id='stock-performance';section.insertBefore(performanceLine,controls);
  let state=null,pending=false,timer=null,loading=false,previewSlot=null;
  const active=()=>pending||['queued','running'].includes(state?.job?.status);
  function button(parent,text,fn,disabled=false){const b=node('button',text);b.type='button';b.disabled=disabled;b.addEventListener('click',fn);parent.append(b);return b;}
  const complete=button(controls,'Medyayı Tamamla',()=>{if(window.confirm(`Boş ve kontrol edilmemiş yuvalar doldurulacak. Kilitli ve onaylı seçimler korunur, eski dosyalar silinmez.${state?.ai_engine==='claude'?' Claude görsel kontrolü açıksa çağrılar ücretlidir.':''} Devam edilsin mi?`))start('complete_media');},true);complete.id='stock-complete';
  const recheck=button(controls,'Yapay zekâyla yeniden kontrol et',()=>{if(window.confirm('Yapay zekâ onayı olmadan (yerel kelime eşleşmesiyle) seçilen yuvalara Gemini yeniden bakacak; uymayanlar değiştirilir. Devam edilsin mi?'))start('complete_media');});recheck.id='stock-recheck';recheck.hidden=true;
  const download=node('a','Tanılama dosyası indir');download.href=`${base}/diagnostics`;download.id='stock-diagnostics';download.setAttribute('download','');
  controls.append(download);
  const diagnosticStatus=node('p','','note');diagnosticStatus.id='stock-diagnostics-status';diagnosticStatus.setAttribute('role','status');section.append(diagnosticStatus);
  const copyFallback=node('textarea');copyFallback.id='stock-diagnostics-text';copyFallback.hidden=true;copyFallback.readOnly=true;copyFallback.rows=8;copyFallback.setAttribute('aria-label','Tanılama metni — seçip kopyalayın');section.append(copyFallback);
  const manualMode=()=>state?.editorial_preferences?.editing_mode!=='legacy';
  const fallbackText=()=>manualMode()?'Uygun stok bulunamazsa yuva boş bırakılır. Otomatik grafik eklenmez.':'Legacy otomatik mod: uygun stok bulunamazsa anlatımdan motion grafik hazırlanabilir.';
  async function diagnosticText(){return JSON.stringify(await request(`${base}/diagnostics`),null,2);}
  download.addEventListener('click',async event=>{event.preventDefault();diagnosticStatus.textContent='Tanılama hazırlanıyor…';
    try{const filename=`NAMAN-medya-tani-${new Date().toISOString().slice(0,10)}.json`;
      if(typeof window.showSaveFilePicker==='function'){
        let handle;try{handle=await window.showSaveFilePicker({suggestedName:filename,types:[{description:'JSON tanılama',accept:{'application/json':['.json']}}]});}catch(error){if(error.name==='AbortError'){diagnosticStatus.textContent='Kaydetme iptal edildi. Tanıyı Kopyala seçeneğini kullanabilirsiniz.';return;}throw error;}
        const text=await diagnosticText(),writable=await handle.createWritable();await writable.write(text);await writable.close();diagnosticStatus.textContent=`Kaydedildi: ${handle.name} — seçtiğiniz klasör.`;
      }else{
        const text=await diagnosticText(),url=URL.createObjectURL(new Blob([text],{type:'application/json'})),a=node('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
        diagnosticStatus.textContent='İndirme tarayıcıya iletildi. Masaüstünde Farklı Kaydet penceresinden konum seçin; tarayıcıda İndirilenler bölümünü kontrol edin. Kaydetme tamamlanmadıysa Tanıyı Kopyala seçeneğini kullanın.';
      }
    }catch(error){diagnosticStatus.textContent='Tanılama kaydedilemedi: '+error.message+' Tanıyı Kopyala seçeneğini deneyin.';}
  });
  button(controls,'Tanıyı Kopyala',async()=>{let text;try{text=await diagnosticText();
    if(!globalThis.navigator?.clipboard?.writeText)throw new Error('Panoya erişim yok.');
    await navigator.clipboard.writeText(text);copyFallback.hidden=true;diagnosticStatus.textContent='Tanılama panoya kopyalandı. Seçtiğiniz metin dosyasına yapıştırabilirsiniz.';
  }catch(error){try{copyFallback.value=text||await diagnosticText();copyFallback.hidden=false;copyFallback.focus();copyFallback.select();diagnosticStatus.textContent='Otomatik kopyalama yapılamadı. Aşağıdaki seçili tanı metnini Ctrl+C ile kopyalayın.';}catch(readError){diagnosticStatus.textContent='Tanılama okunamadı: '+readError.message;}}}).id='stock-diagnostics-copy';
  const summaryLine=node('p','','provider-status');summaryLine.id='stock-summary';section.insertBefore(summaryLine,controls);
  const clipNote=node('p','','note stock-clip-warning');clipNote.id='stock-clip-warning';clipNote.hidden=true;section.insertBefore(clipNote,controls);
  const translateNote=node('p','','note stock-translate');translateNote.id='stock-translate';translateNote.hidden=true;
  const settingNote=node('p','','note stock-setting');settingNote.id='stock-setting';settingNote.hidden=true;section.insertBefore(settingNote,controls);section.insertBefore(translateNote,controls);
  // Kontrol edilmesi gerekenler: low CLIP score, tags only, close to a period/place problem.
  const reviewBox=node('section','','stock-review');reviewBox.id='stock-review';reviewBox.hidden=true;section.insertBefore(reviewBox,summaryLine);
  const stamp=()=>({plan_id:state.plan_id,revision:state.revision});
  async function request(url,method='GET',body){
    let response;
    try{response=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'X-AI-Video-Studio':'projects','Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
    catch{throw new Error('Yerel medya isteği tamamlanamadı. Uygulama penceresini kontrol edip Ekranı Yenile deyin.');}
    let result;try{result=await response.json();}catch{throw new Error('Medya yanıtı okunamadı. Sayfayı yenileyin.');}
    if(!response.ok){const error=new Error(result.message||'Medya işlemi tamamlanamadı.');error.category=result.category;throw error;}
    return result;
  }
  function sync(){complete.disabled=active()||!state;const unchecked=state?.media_summary?.unchecked||0;recheck.hidden=manualMode()||!unchecked||state?.job?.progress?.local_mode==='off';recheck.textContent=`Yapay zekâyla yeniden kontrol et (${unchecked} yuva)`;recheck.disabled=active()||!state;}
  async function operate(fn){if(active()||!state)return;pending=true;sync();try{await fn();await load();}catch(error){message.textContent=error.message;}finally{pending=false;render();}}
  function start(action){return operate(()=>request(base+'/jobs','POST',{...stamp(),action}));}
  function slotJob(slot,action,extra={}){return operate(()=>request(`${base}/slots/${slot.slot_id}/jobs`,'POST',{...stamp(),action,...extra}));}
  function slotAction(slot,action){return operate(()=>request(`${base}/slots/${slot.slot_id}/actions`,'POST',{...stamp(),action}));}
  function thumbnail(media){
    if(!media.preview_url)return node('p','Küçük önizleme yok; indirdikten sonra Önizle düğmesini kullanın.','note');
    const img=node('img');img.className='stock-thumbnail';img.alt=`${media.provider} ${media.media_type==='video'?'video':'görsel'} önizlemesi`;
    img.src=media.preview_url;img.loading='lazy';img.referrerPolicy='no-referrer';return img;
  }
  const TEMPLATE_LABELS={stat:'Büyüyen sayı',map:'Harita + işaret',quote:'Başlık / alıntı',timeline:'Zaman çizelgesi',compare:'Karşılaştırma',list:'Madde listesi',
    route:'Rota (haritada)',empire:'İmparatorluk sınırı',zoom:'Yakınlaşma (dünya → yer)',mark:'Görselde işaretle',beforeafter:'Önce / sonra',icons:'İkonlarla sayı',ratio:'Oran (pasta)',dynasty:'Hanedan ağacı',fact:'Biliyor muydunuz?'};
  // The nine marker infographics are edited as marker text (same writing as in the pasted text).
  const MOMENT_LABELS={intro:'Açılış (başlık + kanal adı)',outro:'Kapanış (abone ol + zil)',endscreen:'YouTube bitiş ekranı'};
  const MARKER_HELP={route:'Yerler, “>” ile: Ninive > Babil > Kudüs',empire:'Ad ve yıllar; isterseniz “|” sonra başkent ve sınır yerleri: Assyrien 911-612 v. Chr. | Ninive, Memphis, Susa',zoom:'Bir yer adı: Babil',
    mark:'Görselde gösterilecek şeyin kısa açıklaması',beforeafter:'İki şey, “|” ile: Antik liman | Bugünkü kıyı',icons:'Sayı ve nesne: 10000 asker',ratio:'Yüzde ve etiket: %40 nüfus kıyıda yaşıyor',
    dynasty:'Kuşaklar “>” ile, kardeşler “,” ile: Davud > Süleyman > Rehavam, Yeroboam',fact:'Kısa bir bilgi cümlesi'};
  function motionForm(slot){
    const spec=slot.selected_media?.source_metadata?.motion||{template:'quote',data:{text:''},emphasis:''};
    const form=node('form','','settings-panel stock-motion-form');form.noValidate=true;
    const row=(label,el)=>{const g=node('div','','setting-field');const l=node('label',label);g.append(l,el);form.append(g);return el;};
    const sel=row('Şablon',node('select'));for(const [k,v] of Object.entries(TEMPLATE_LABELS)){const o=node('option',v);o.value=k;sel.append(o);}sel.value=spec.template;
    const fields=node('div');form.append(fields);const emphasis=row('Vurgu kelimesi (seslendirmede söylendiği an)',node('input'));emphasis.value=spec.emphasis||'';
    // Same names as app/motion/layouts.py NAMES; “Otomatik” lets the app vary it (never the same twice in a row).
    const layoutSel=row('Yerleşim',node('select'));
    function layouts(){const t=sel.value,kind=['map','route','empire','zoom'].includes(t)?'map':['mark','beforeafter'].includes(t)?'picture':'card';
      const names={card:['Orta','Panel','Yan şerit'],map:['Konu ortada','Konu solda','Konu sağda'],picture:['Etiket üstte','Etiket altta','Etiket yanda']}[kind];
      layoutSel.replaceChildren();const auto=node('option','Otomatik');auto.value='';layoutSel.append(auto);
      names.forEach((n,i)=>{const o=node('option',n);o.value=String(i);layoutSel.append(o);});
      layoutSel.value=t===spec.template&&slot.motion_layout_owner?String(spec.layout||0):'';}
    const d=spec.data||{};let inputs={};
    const lines=list=>list.map(e=>typeof e==='string'?e:[e.date??e.label,e.label??e.value].filter(x=>x!==undefined).join(' | ')).join('\n');
    function draw(){fields.replaceChildren();inputs={};const t=sel.value;
      const add=(key,label,value,area)=>{const el=node(area?'textarea':'input');el.value=value??'';if(area)el.rows=4;const g=node('div','','setting-field');const l=node('label',label);g.append(l,el);fields.append(g);inputs[key]=el;};
      if(t==='stat'){add('value','Sayı (anlatımda geçmeli)',d.value);add('label','Açıklama',d.label);}
      if(t==='map'){add('place','Yer adı (anlatımda geçmeli)',d.place);add('lat','Enlem',d.lat);add('lon','Boylam',d.lon);add('label','Etiket',d.label);}
      if(t==='quote')add('text','Metin (anlatımdan birebir)',d.text,true);
      if(t==='timeline')add('events','Her satıra: tarih | açıklama (2–5 satır)',d.events?d.events.map(e=>`${e.date} | ${e.label}`).join('\n'):'',true);
      if(t==='compare'){add('title','Başlık',d.title);add('items','Her satıra: ad | değer (değer isteğe bağlı)',d.items?d.items.map(e=>`${e.label} | ${e.value||''}`).join('\n'):'',true);}
      if(t==='list'){add('title','Başlık',d.title);add('items','Her satıra bir madde (2–4)',d.items?d.items.join('\n'):'',true);}
      if(MARKER_HELP[t]){add('source',`İşaret metni — ${MARKER_HELP[t]}`,spec.template===t?(d.source||''):'',true);
        if(t==='mark'){add('fx','Odak noktası yatay (0 = sol, 1 = sağ)',spec.template===t?d.fx??.5:.5);add('fy','Odak noktası dikey (0 = üst, 1 = alt)',spec.template===t?d.fy??.5:.5);}}}
    sel.addEventListener('change',()=>{draw();layouts();});draw();layouts();
    const save=node('button','Motion metnini kaydet ve yeniden çiz');save.type='submit';form.append(save,node('p','Sayı, tarih, yer ve alıntılar bu sahnenin anlatımında geçmelidir; uydurma bilgi kabul edilmez. İşaret şablonlarında yerler uygulamanın çevrimdışı yer listesinden bulunur; bulunamayan yer için uyarı gösterilir.','note'));
    form.addEventListener('submit',event=>{event.preventDefault();const t=sel.value,v=k=>inputs[k]?.value.trim()||'';const rows=k=>v(k).split('\n').map(x=>x.split('|').map(y=>y.trim())).filter(x=>x[0]);
      const layout=layoutSel.value===''?{}:{layout:Number(layoutSel.value)};
      if(MARKER_HELP[t]){slotJob(slot,'motion_edit',{motion:{template:t,data:{source:v('source'),...(t==='mark'?{fx:Number(v('fx')||.5),fy:Number(v('fy')||.5)}:{})},emphasis:emphasis.value.trim(),...layout}});return;}
      const data=t==='stat'?{value:v('value'),label:v('label')}:t==='map'?{place:v('place'),lat:Number(v('lat')),lon:Number(v('lon')),label:v('label')}:t==='quote'?{text:v('text')}
        :t==='timeline'?{events:rows('events').map(x=>({date:x[0],label:x[1]||''}))}:t==='compare'?{title:v('title'),items:rows('items').map(x=>({label:x[0],value:x[1]||''}))}:{title:v('title'),items:rows('items').map(x=>x[0])};
      slotJob(slot,'motion_edit',{motion:{template:t,data,emphasis:emphasis.value.trim(),...layout}});});
    return form;
  }
  function mediaInfo(media){if(media.provider==='generated'&&media.media_type==='video')return `Motion grafik · ${TEMPLATE_LABELS[media.source_metadata?.motion?.template]||MOMENT_LABELS[media.source_metadata?.motion?.template]||''}${media.source_metadata?.layout_label?' · '+media.source_metadata.layout_label:''} · 1920×1080 · ${media.source_metadata?.engine==='openmontage'?'OpenMontage':'yerel çizim'}`;if(media.provider==='generated')return `Üretilmiş kart · ${{map:'Konum',number:'Sayı',quote:'Alıntı',title:'Başlık'}[media.source_metadata?.card_kind]||'Başlık'} · 1920×1080`;return `${{pexels:'Pexels',openmontage:'OpenMontage',wikimedia:'Wikimedia Commons'}[media.provider]||'Pixabay'} · ${media.media_type==='video'?'Video':'Görsel'} · ${media.width}×${media.height}${media.width>media.height?' · Yatay'+(Math.abs(media.width/media.height-16/9)<.06?' · 16:9':''):' · Dikey/kare'}`;}
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
    card.append(node('h4',`Medya ${slot.display_order||slot.order}${slot.locked?' · Kilitli':''} · ${slot.estimated_start.toFixed(1)}–${slot.estimated_end.toFixed(1)} sn`));
    const stage=slot.director?.stage_label||(slot.locked&&media?'Kilitli (sizin seçiminiz)':media?(slot.ai_review?.approved?'Yapay zekâ onayladı':slot.local_review?.method==='clip'?'CLIP onayladı — kaynak hazır':slot.local_review?.method==='words'?'Yalnız etiket/kelimeyle seçildi — önizleyin':'Kaynak hazır — Yapay zekâ onayı bekliyor'):'Boş — Medyayı Tamamla deyin');
    const stageLine=node('p',`Aşama: ${stage}`,'provider-status');stageLine.className+=' stock-stage';card.append(stageLine);
    if(Number.isFinite(score)){const rel=node('p',`Alaka puanı: ${score}/10${score<9?' — önce buna bakın':''} · ${slot.ai_review.reason||''}`,'stock-relevance');if(slot.ai_review.model)rel.append(node('small',` · ${slot.ai_review.model.replace(/^gemini-/,'')} ile seçildi`,'stock-model'));card.append(rel);}
    const clip=slot.local_review?.clip;
    if(media&&media.provider!=='generated'&&clip&&!slot.ai_review?.approved){const line=node('p',`Yerel görüntü modeli (CLIP): ${clip.score}/10 · ${{match:'kareler cümleyle eşleşti',uncertain:'kararsız — etiketlerle de kontrol edildi',mismatch:'uyumsuz'}[clip.verdict]||''}`,'stock-relevance stock-clip');card.append(line);}
    if(media&&media.provider!=='generated'&&!slot.ai_review?.approved&&!slot.continuation_of&&slot.local_review?.method!=='clip')card.append(node('p','⚠ Görüntüsü bir modelle kontrol edilmedi — etiket/kelime eşleşmesiyle seçildi. Önizleyip bakın.','stock-unchecked'));
    if(slot.sentence)card.append(node('p',`Cümle: ${slot.sentence}`,'stock-sentence'));
    if(slot.sentence_tr&&slot.sentence_tr!==slot.sentence)card.append(node('p',`Türkçesi: ${slot.sentence_tr}`,'stock-sentence-tr'));
    if(slot.visual_note)card.append(node('p',`[GÖRSEL] notu: ${slot.visual_note_tr||slot.visual_note}`,'stock-visual-note'));
    if(slot.message)card.append(node('p',`Neden: ${slot.message}`));
    if(media&&!(media.provider==='generated'&&media.media_type==='video'))card.append(thumbnail(media));
    const top=node('div','','settings-actions');card.append(top);
    button(top,'Yeniden seçtir',()=>{
      const own=media&&media.provider!=='generated';
      const reason=own?window.prompt('Bu medya neden uymadı? (isteğe bağlı — örn. “modern bina var”, “konu dışı”). Bu medya bu projede bir daha önerilmez.',''):'';
      if(reason===null)return;
      if(own||window.confirm('Bu yuva için yeni kaynak alternatifleri aranır. '+fallbackText()+' Devam edilsin mi?'))slotJob(slot,'reselect',own?{reason:reason.trim().slice(0,200)}:{});
    },active()||slot.locked).className='stock-reselect';
    const isMotion=media?.provider==='generated'&&media?.media_type==='video';
    if(isMotion)button(top,'Stok videoyla değiştir',()=>slotJob(slot,'to_stock'),active()||slot.locked).className='stock-to-stock';
    else button(top,'Motion’a çevir',()=>slotJob(slot,'to_motion'),active()||slot.locked).className='stock-to-motion';
    if(isMotion&&media.source_metadata?.suggested&&!slot.locked){const tip=node('p','💡 Bu infografiği uygulama cümledeki sayı/tarih/yer bilgisinden önerdi. Uygunsa onaylayın; değilse metnini düzenleyin veya stok videoyla değiştirin.','stock-suggested');card.append(tip);
      button(top,'Öneriyi onayla',()=>slotAction(slot,'lock'),active()).className='stock-approve-suggestion';}
    if(isMotion){const preview=node('video');preview.className='stock-preview';preview.src=`${base}/slots/${slot.slot_id}/preview`;preview.controls=true;preview.preload='metadata';preview.muted=true;card.append(preview);
      const edit=node('details');edit.append(node('summary','Motion metnini düzenle'),motionForm(slot));card.append(edit);}
    const more=node('details','','stock-slot-details');more.append(node('summary','Ayrıntılar'));card.append(more);
    const keep=card;card=more;
    card.append(node('p',`${slot.status_label} · ${slot.duration.toFixed(1)} sn`),node('p',`Görsel amaç: ${slot.visual_goal}`),node('p',`Planlanan arama: ${slot.search_query}`));
    for(const step of slot.director?.steps||[]){card.append(node('p',`${step.label||(step.stage==='sources_only'?'Kaynak hazırlama':'Medya hazırlama')}: ${step.queries?.length?'“'+step.queries.join('”, “')+'” · ':''}${{chosen:'seçildi',no_approved_candidate:'onaylanan aday yok',ai_unavailable:'Yapay zekâya ulaşılamadı',kept:'korundu',kept_no_better_option:'daha iyisi yok, korundu'}[step.result]||(step.result==='missing'?'Uygun stok video veya görsel bulunamadı. Otomatik kurgu grafiği oluşturulmadı.':'İşlem kaydı; ayrıntılar için arama tanısına bakın.')}`));
      for(const j of step.judged||[])card.append(node('p',`· ${j.provider} ${j.media_type==='video'?'video':'görsel'} ${j.media_id} — ${j.clip_approved?'CLIP onaylı':j.local?'Yerel metadata':'AI'} ${j.score}/10 ${j.approved?'✓':'✗'} ${j.reason}`,'note'));}
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
  function renderReview(){
    reviewBox.replaceChildren();const slots=state?.slots||[];reviewBox.hidden=!slots.length;if(!slots.length)return;
    reviewBox.append(node('h3','Kontrol edilmesi gerekenler'));
    if(!slots.some(s=>Array.isArray(s.review_flags))){reviewBox.append(node('p','Liste Medyayı Tamamla bittikten sonra görünür.','note'));return;}
    const list=slots.filter(s=>(s.review_flags||[]).length);
    if(!list.length){reviewBox.append(node('p','Kontrol gerekmiyor.','stock-review-none'));return;}
    for(const slot of list){
      const item=node('article','','stock-review-item');item.dataset.slotId=slot.slot_id;
      item.append(node('h4',`Medya ${slot.display_order||slot.order} · ${slot.estimated_start.toFixed(1)}–${slot.estimated_end.toFixed(1)} sn`));
      for(const flag of slot.review_flags)item.append(node('p','⚠ '+flag,'stock-review-flag'));
      const sentence=slot.sentence_tr||slot.sentence;if(sentence)item.append(node('p',`Cümle: ${sentence}`,'stock-sentence-tr'));
      if(slot.selected_media)item.append(thumbnail(slot.selected_media));
      const actions=node('div','','settings-actions');item.append(actions);
      button(actions,'Yeniden seç',()=>slotJob(slot,'reselect',{}),active()||slot.locked).className='stock-review-reselect';
      reviewBox.append(item);
    }
  }
  function render(){
    renderReview();
    for(const old of blocks.querySelectorAll('.stock-scene'))old.remove();
    for(const sceneCard of blocks.querySelectorAll('[data-scene-id]')){
      const slots=state?.slots.filter(s=>s.scene_id===sceneCard.dataset.sceneId)||[];if(!slots.length)continue;
      const media=node('section','','stock-scene');media.append(node('h3',`Medya Yuvaları · ${slots.length} görsel çekim`));for(const slot of slots)media.append(slotCard(slot));sceneCard.append(media);
    }
    summaryLine.textContent=state?.media_summary?.text||'';
    translateNote.replaceChildren();const tnote=state?.translation_note;translateNote.hidden=!tnote;
    if(tnote){translateNote.append(node('span','Türkçe çeviri: '+tnote+' '));if(!tnote.endsWith('…'))button(translateNote,'Çeviriyi yeniden dene',()=>operate(()=>request(base+'/translate','POST',{})),active()).id='stock-retranslate';else setTimeout(load,3000);}
    const perf=state?.job?.progress||{},timings=perf.timings||{},search=perf.search_metrics||{};
    const labels={search:'Arama',clip:'CLIP (judging içinde)',judging:'Judging',download_validation:'İndirme + kontrol',motion:'Motion'};
    performanceLine.hidden=!Object.keys(timings).length;
    performanceLine.textContent=[`Geçen aktif süre: ${perf.performance?.active_wall_seconds??0} sn`,...Object.entries(labels).map(([k,label])=>`${label}: ${timings[k]?.seconds??0} sn / ${timings[k]?.calls??0} işlem`),`Benzersiz sorgu: ${search.unique_queries??0}`,`Sağlayıcı araması (başarılı): ${perf.provider_searches??0}`,`Arama önbelleği: ${perf.cached_search_reads??0}`,`Önizleme önbelleği: ${perf.preview_cache_hits??0}`,`Karar önbelleği: ${perf.ai_cached??0}`,`CLIP kare vektörü önbelleği: ${perf.clip_metrics?.image_vector_hits??0}`,`CLIP metin vektörü önbelleği: ${perf.clip_metrics?.text_vector_hits??0}`,`Kalite önbelleği: ${perf.quality_cache_hits??0}`,`Motion önbelleği: ${perf.motion_cache_hits??0}`,`API hataları: ${Object.values(perf.api_errors||{}).reduce((a,b)=>a+b,0)}`,`Kalan yuva: ${state?.slots.filter(s=>s.status!=='complete').length??0}`,'Aşama süreleri toplanmaz; CLIP judging içinde, aramalar paralel olabilir.'].join(' · ');
    const clipWarning=state?.job?.progress?.clip_warning;clipNote.hidden=!clipWarning;clipNote.textContent=clipWarning?'ℹ '+clipWarning:'';
    const where=state?.job?.progress?.setting,dropped=state?.job?.progress?.setting_rejected||{},redo=state?.job?.progress?.setting_reselected||0;settingNote.hidden=!where?.label;
    settingNote.textContent=where?.label?`Dönem ve yer: ${where.label} · bu döneme/yere uymayan görüntüler elenir${dropped.anachronism?` · dönemle çelişen ${dropped.anachronism}`:''}${dropped.place?` · yanlış coğrafya ${dropped.place} tekil aday (bu işte; eksik yuva sayısı değildir)}`:''}${dropped.style?` · karikatür/3D ${dropped.style}`:''}${redo?` · önceki ${redo} seçim yenilendi`:''}`:'';
    modeText.textContent='Yerel arşiv → ilgili stok video → ilgili stok görsel aranır. CLIP veya yalnız metadata kontrolünün kapsamı her seçimde gösterilir. '+fallbackText();
    recovery.replaceChildren();const diag=state?.missing_media_diagnostics;if(diag?.unresolved_raw_slots){for(const d of diag.reasons||[])recovery.append(node('p',`${d.count} eksik yuva: ${d.message}`));}
    for(const slot of state?.slots||[])if(!slot.selected_media&&slot.status!=='complete'){
      const detail=node('details','','stock-missing-diagnostic');detail.append(node('summary',`Eksik yuva ${slot.display_order||slot.order} · ${slot.estimated_start.toFixed(1)}–${slot.estimated_end.toFixed(1)} sn`));
      const panel=node('div','','stock-diagnostic-scroll');detail.append(panel);
      panel.append(node('p',`Anlatım: ${slot.sentence||'Cümle kaydı yok'}`),node('p',`Görsel amaç: ${slot.visual_goal||'Belirtilmedi'}`),node('p',`Ana konu: ${slot.visual_subject?.subject||slot.subject_anchor||'Belirlenemedi'}`));
      for(const reason of slot.missing_reason_messages||[])panel.append(node('p',reason));
      const attempts=slot.search_attempts?.length?slot.search_attempts:slot.director?.searches||[];
      if(attempts.length>100)panel.append(node('p',`Son 100/${attempts.length} arama kaydı gösteriliyor. Tam kayıt için Tanılama dosyası indir seçeneğini kullanın.`));
      for(const s of attempts.slice(-100))panel.append(node('p',`${s.at||''} · ${s.provider} · ${s.media_type==='image'?'Görsel':'Video'} · “${s.query}” · sayfa ${s.page||1} · sonuç ${s.results??'—'}${s.cached?' · önbellek':''}${s.skipped?' · '+(s.skipped==='budget'?'arama bütçesi':'önceki başarısız deneme'):''}${s.error?' · '+(s.error_text||s.error):''}`,'note'));
      if(slot.search_attempts?.length)for(const s of slot.director?.searches||[])if(s.skipped)panel.append(node('p',`${s.provider} · “${s.query||'sağlayıcı durumu'}” · ${{previous_failure:'Önceki başarısız deneme bu geçişte tekrarlanmadı',budget:'Güvenli arama bütçesi; bu alternatif henüz denenmedi',provider_unavailable:'Bu işte önceki sağlayıcı hatası nedeniyle atlandı'}[s.skipped]||'Arama atlandı'}${s.error_text?' · '+s.error_text:''}`,'note'));
      for(const [reason,count] of Object.entries(slot.director?.rejected||{}))panel.append(node('p',`Eleme: ${{setting_conflict:'Dönem/coğrafya uyumsuz',visual_subject_conflict:'Görsel konu çelişkisi',used_elsewhere:'Daha önce kullanıldı',duration:'Süre yetersiz',resolution:'Çözünürlük yetersiz',orientation:'Çerçeve oranı uyumsuz',ai_rejected_before:'Uygunluk kontrolünde elendi',owner_rejected:'Kullanıcı reddetti',watermark_or_logo:'Logo/filigran',must_not_show:'İstenmeyen içerik',modern_in_history:'Tarihle çelişen modern içerik'}[reason]||'Diğer kayıt ('+reason+')'} · ${count} aday geçişi`));
      for(const j of slot.director?.judged||[])panel.append(node('p',`${j.media} · ${j.clip?'CLIP '+j.clip.score+'/10':'CLIP uygulanmadı'} · ${j.approved?'uygun':'elenmiş'} · ${j.reason||'Neden kaydı yok'}`));
      panel.append(node('p','Alternatif: kendi medyanızı Arşiv üzerinden atayabilir veya bu bölüm için manuel infografik hazırlayabilirsiniz. Otomatik eklenmez.'));
      button(panel,'Yalnız yeni alternatifleri ara',()=>slotJob(slot,'reselect'),active()||slot.locked);recovery.append(detail);
    }
    const counts=state?.media_mix;mix.replaceChildren();if(counts){mix.append(node('summary','Ayrıntılı sayılar'),node('p',`Yapay zekâ isteği: son işte ${state.ai_requests?.last_job??0}, bu projede toplam ${state.ai_requests?.total??0}${state.ai_requests?.cached?` (önbellekten ${state.ai_requests.cached} karar)`:''} · Stok video oranı %${counts.video_ratio_percent} · Motion grafik oranı %${counts.motion_ratio_percent??0} · Ortalama çekim ${counts.average_used_duration} sn · En uzun ${counts.maximum_used_duration} sn · Farklı medya ${counts.unique_media_count}${state.selection_version?' · Seçim sürümü '+state.selection_version:''}`,'note'));}mix.hidden=!counts;
    while(recent.children.length>1)recent.lastChild.remove();for(const d of state?.job?.progress?.search_diagnostics||[])recent.append(node('p',`${d.query} · ${d.summary}`));recent.hidden=recent.children.length===1;
    warningList.replaceChildren();for(const text of state?.warnings||[])warningList.append(node('li',text));sync();
  }
  async function load(){
    if(loading)return;loading=true;
    try{state=await request(base);const job=state.job;
      message.textContent=job?.status==='error'?`⚠ ${job.error_message}`:job&&['queued','running'].includes(job.status)?`${job.progress.percent}% · ${job.progress.message}`:`${state.slots.filter(s=>s.status==='complete').length}/${state.slots.length} medya tamamlandı. ${!state.providers.pixabay&&!state.providers.wikimedia&&!state.providers.openmontage?'Ayarlar → Pixabay anahtarını kaydedin.':'Seçimleri önizleyip anlatıma uygunluğu kontrol edin.'}${job?.status==='completed'&&job.progress?.local_reason&&state.media_summary?.unchecked&&job.progress.local_mode!=='off'?' ⚠ '+job.progress.local_reason:''}${job?.progress?.gemini_503_diagnosis?' ℹ '+job.progress.gemini_503_diagnosis:''}${job?.progress?.marker_warnings?.length?' ⚠ Çizilemeyen/eksik işaretler: '+job.progress.marker_warnings.join(' · '):''}`;
      render();
    }catch(error){state=null;message.textContent=error.message;render();}
    finally{loading=false;clearTimeout(timer);if(['queued','running'].includes(state?.job?.status))timer=setTimeout(load,1200);}
  }
  window.addEventListener('production-plan-rendered',load);
  window.addEventListener('pagehide',()=>clearTimeout(timer));load();
}
