/* Local Part 9 / 9.5 only. No provider request is made from this page. */
if(/^\/projects\/[^/]+\/render$/.test(location.pathname)){
  const pid=location.pathname.split('/')[2],base=`/api/projects/${pid}/render`,root=document.querySelector('#render-content');root.hidden=false;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const link=(text,href)=>{const n=el('a',text);n.href=href;return n;};
  const status=el('p','Video kaynakları kontrol ediliyor…');status.id='render-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const summary=el('section'),editSummary=el('section'),form=el('section'),jobs=el('section'),versions=el('section');form.className='settings-panel';
  root.append(link('← Projeye dön',`/projects/${pid}`),status,summary,form,editSummary,jobs,versions);
  form.append(el('h2','Yerel video ayarları'),el('p','Video bu bilgisayarda oluşturulur. Ses, altyazı ve stok dosyaları değiştirilmez; API kredisi kullanılmaz.'));
  function field(label,type,value,parent=form){const wrap=el('label',label),n=el('input');n.type=type;if(type==='checkbox')n.checked=value;else n.value=value;wrap.append(n);parent.append(wrap);return n;}
  const encLabel=el('label','Encoder'),encoder=el('select');encoder.id='render-encoder';for(const [v,t] of [['auto','Otomatik — NVIDIA tercih et'],['nvenc','NVIDIA NVENC'],['cpu','CPU']]){const o=el('option',t);o.value=v;encoder.append(o);}encoder.value='auto';encLabel.append(encoder);form.append(encLabel);
  const engineLabel=el('label','Montaj Motoru'),montageEngine=el('select');montageEngine.id='render-engine';for(const [v,t] of [['openmontage','OpenMontage — Ana Motor'],['native','Yerel Adaptif — FFmpeg / NVIDIA']]){const o=el('option',t);o.value=v;montageEngine.append(o);}montageEngine.value='openmontage';engineLabel.append(montageEngine);const engineStatus=el('p');engineStatus.id='render-engine-status';form.append(engineLabel,engineStatus);montageEngine.addEventListener('change',()=>load());
  const styleLabel=el('label','Kurgu Stili'),editingStyle=el('select');editingStyle.id='render-editing-style';
  for(const [value,text] of [['adaptive','Uyarlanabilir YouTube (önerilen)'],['basic','Temel'],['balanced','Dengeli YouTube'],['dynamic','Dinamik YouTube']]){const option=el('option',text);option.value=value;editingStyle.append(option);}
  const subtitleProfiles={adaptive:'Kalın YouTube altyazısı',basic:'Klasik altyazı',balanced:'Kalın YouTube altyazısı',dynamic:'Kalın büyük YouTube altyazısı'};
  const subtitleProfile=el('p',subtitleProfiles.balanced);subtitleProfile.id='render-subtitle-profile';
  editingStyle.value='adaptive';styleLabel.append(editingStyle);form.append(styleLabel,subtitleProfile);
  editingStyle.addEventListener('change',()=>{subtitleProfile.textContent=subtitleProfiles[editingStyle.value];if(!subtitleModeChosen)subtitles.value=editingStyle.value==='adaptive'?'emphasis':'full';return load();});
  const subtitles=el('select');subtitles.id='render-subtitles';const subtitleLabel=el('label','Altyazı Gösterimi');for(const [value,text] of [['full','Tam altyazı'],['emphasis','Sadece önemli vurgular'],['none','Altyazı yok']]){const o=el('option',text);o.value=value;subtitles.append(o);}subtitles.value='emphasis';subtitleLabel.append(subtitles);form.append(subtitleLabel);let subtitleModeChosen=false;subtitles.addEventListener('change',()=>{subtitleModeChosen=true;return load();});
  let variationSeed='';try{variationSeed=localStorage.getItem(`render-variation-${pid}`)||'';}catch{}
  const music=field('Arka plan müziği açık','checkbox',false),musicDetails=el('details');musicDetails.append(el('summary','Müzik dosyası ve ayrıntıları'));form.append(musicDetails);const file=field('Arka plan müziği ekle (en fazla 100 MB)','file','',musicDetails);file.accept='.mp3,.wav,.m4a,.ogg,.flac';
  const license=field('Bu müziği kullanma hakkına sahibim.','checkbox',false,musicDetails);
  const volume=field('Müzik seviyesi (0–0,30)','number',.12,musicDetails);volume.min=0;volume.max=.3;volume.step=.01;
  const fadeIn=field('Müzik başlangıç geçişi (saniye)','number',2,musicDetails),fadeOut=field('Müzik bitiş geçişi (saniye)','number',3,musicDetails);for(const n of [fadeIn,fadeOut]){n.min=0;n.max=30;n.step=.1;}
  const duck=field('Konuşma sırasında müziği kıs','checkbox',true,musicDetails),musicStatus=el('p');form.append(musicStatus);
  let state=null,pending=false,lastVersionKey='',stopped=false;
  const button=(parent,text,fn)=>{const n=el('button',text);n.type='button';n.addEventListener('click',fn);parent.append(n);return n;};
  const upload=button(musicDetails,'Müziği Kaydet',async()=>{
    if(!file.files[0]||!license.checked){status.textContent='Müzik dosyasını seçin ve kullanma hakkınızı onaylayın.';return;}
    const f=file.files[0];if(f.size>100000000){status.textContent='Müzik dosyası 100 MB sınırını aşıyor.';return;}
    await action(async()=>{await request(base+'/music','POST',f,{'X-Music-Format':f.name.split('.').pop().toLowerCase(),'X-Music-License':'confirmed'});file.value='';});
  });
  const variationNote=el('p');variationNote.id='render-variation-feedback';form.append(variationNote);
  const variation=button(form,'Yeni Kurgu Varyasyonu',async()=>{variationSeed=String(Number(variationSeed||0)+1);try{localStorage.setItem(`render-variation-${pid}`,variationSeed);}catch{}await load();const missing=state?.ready?0:state?.readiness?.unresolved_stock_slots||0;variationNote.textContent=missing?`Kurgu varyasyonu hazırlandı ancak ${missing} medya alanı tamamlanmadan render başlatılamaz.`:state?.ready?'Yeni kurgu varyasyonu hazırlandı. API veya TTS çağrısı yapılmadı.':'Varyasyon seçildi. Render için aşağıdaki eksikleri tamamlayın.';});variation.id='render-variation';
  const blockers=el('section');blockers.id='render-blockers';blockers.setAttribute('role','status');form.append(blockers);
  const create=button(form,'Videoyu Oluştur',()=>action(async()=>{await request(base+'/jobs','POST',{encoder:encoder.value,montage_engine:montageEngine.value,editing_style:editingStyle.value,edit_variation_seed:variationSeed||null,subtitle_display:subtitles.value,subtitle_burned:subtitles.value==='full',music_enabled:music.checked,music_volume:Number(volume.value),music_fade_in:Number(fadeIn.value),music_fade_out:Number(fadeOut.value),music_ducking:duck.checked});}));create.id='render-create';
  const refresh=button(form,'Durumu Yenile',()=>load(true));
  async function request(url,method='GET',body=null,extra={}){
    const headers={'X-AI-Video-Studio':'projects',...extra},isFile=body instanceof File;
    if(body&&!isFile)headers['Content-Type']='application/json';
    let r;try{r=await fetch(url,{method,headers,body:body?(isFile?body:JSON.stringify(body)):undefined,cache:'no-store',signal:AbortSignal.timeout(isFile?120000:60000)});}catch{throw Error('Uygulamaya ulaşılamadı. Uygulama penceresini kontrol edip Durumu Yenile’ye basın.');}
    const data=await r.json();if(!r.ok)throw Error(data.message||'Video işlemi tamamlanamadı.');return data;
  }
  async function action(fn){if(pending)return;pending=true;updateButtons();try{await fn();status.textContent='İşlem alındı.';await load();}catch(e){status.textContent=e.message;}finally{pending=false;updateButtons();}}
  const activeJob=()=>!!(state?.job&&['queued','preparing','rendering','validating'].includes(state.job.status));
  function updateButtons(){create.disabled=pending||!state?.ready||activeJob();upload.disabled=pending||activeJob();encoder.disabled=activeJob();montageEngine.disabled=pending||activeJob();editingStyle.disabled=pending||activeJob();subtitles.disabled=pending||activeJob();variation.disabled=pending||activeJob();music.disabled=activeJob();create.textContent=state?.job&&['error','cancelled'].includes(state.job.status)?'Yeniden Render Et':'Videoyu Oluştur';}
  function clock(s){return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
  const motionLabels={none:'Yok',push_in:'Yakınlaşma',push_out:'Uzaklaşma',pan_left:'Sola kayma',pan_right:'Sağa kayma',pan_up:'Yukarı kayma',pan_down:'Aşağı kayma',subtle_reframe:'Hafif kadraj değişimi'};
  const transitionLabels={hard_cut:'Temiz kesme',none:'Yok',crossfade:'Yumuşak geçiş',fade:'Koyu geçiş',fade_dark:'Koyu geçiş',dip_black:'Kısa kararma'};
  const styleLabels={adaptive:'Uyarlanabilir YouTube',basic:'Temel',balanced:'Dengeli YouTube',dynamic:'Dinamik YouTube'};
  const layoutLabels={full_broll:'Tam B-roll',split_media_text:'Medya ve metin',fact_card:'Bilgi kartı',big_number:'Büyük sayı',timeline_card:'Zaman çizelgesi',dual_media:'İki medya',minimal_title:'Kısa başlık',quote_emphasis:'Kısa vurgu',location_card:'Konum kartı'};
  function editCounts(parent,count,label){if(!count)return;parent.append(el('p',`${label}: Hareket efektleri: ${count.motion_effects} · Sahne geçişleri: ${count.scene_transitions} · Vurgu yazıları: ${count.emphasis_texts} · Klip içi değişimler: ${count.internal_edits}`));if(count.layouts)parent.append(el('p',Object.entries(count.layouts).map(([k,v])=>`${layoutLabels[k]}: ${v}`).join(' · ')),el('p',`Görsel düzen hataları: ${count.layout_failures||0} · B-roll: ${clock(count.broll_seconds||0)} · Grafik: ${clock(count.graphic_seconds||0)}`));}
  let planKey='';
  function showEditPlan(){const plan=state.smart_edit_plan,key=plan?.fingerprint||'';if(planKey===key)return;planKey=key;editSummary.replaceChildren();if(!plan)return;
    editSummary.append(el('h2',`Kurgu stili: ${plan.style_label}${plan.estimated?' · Tahmini plan':''}`),el('p','Yerel ve aynı kaynaklarda aynı plan. API kredisi kullanılmaz; yeni stok dosyası indirilmez.'));
    if(plan.edit_variation_seed)editSummary.append(el('p',`Kurgu Varyasyonu: ${variationSeed||'Varsayılan'}`));editCounts(editSummary,plan.summary,'Planlanan kurgu');const details=el('details');details.append(el('summary','Kurgu Planını Gör'));
    const table=el('table'),thead=el('thead'),head=el('tr');for(const text of ['Zaman','Sahne','Düzen','Medya','Efekt','Geçiş','Metin'])head.append(el('th',text));thead.append(head);table.append(thead);
    const body=el('tbody');let sceneOrder=0,lastScene='';for(const item of plan.slots){if(lastScene!==item.scene_id){sceneOrder++;lastScene=item.scene_id;}
      for(const segment of item.segments){const row=el('tr'),texts=plan.emphasis.filter(e=>e.slot_id===item.slot_id&&e.start>=segment.start&&e.start<segment.end).map(e=>e.text).join(' · ');
        const transition=segment===item.segments[item.segments.length-1]?item.transition_out:'hard_cut';
        for(const text of [`${clock(segment.start)}–${clock(segment.end)}`,String(sceneOrder),item.layout_label||'Tam B-roll',item.media_type==='image'?'Görsel':'Video',motionLabels[segment.motion_effect]||'Mevcut hareket',transitionLabels[transition]||'Temiz kesme',(item.texts||[]).join(' · ')||texts||'—'])row.append(el('td',text));body.append(row);}}
    table.append(body);const wrapper=el('div');wrapper.style.overflowX='auto';wrapper.append(table);details.append(wrapper);editSummary.append(details);
  }
  function render(){showEditPlan();blockers.replaceChildren();engineStatus.textContent=`OpenMontage: ${state.openmontage?.status||'Kurulu değil'}${state.openmontage?.commit?' · '+state.openmontage.commit:''}`;if(!state.ready||activeJob()){blockers.append(el('h3','Video henüz oluşturulamıyor.'));const reasons=state.readiness?.blockers||[];for(const b of reasons){blockers.append(el('p',b.message));const screen=b.screen;if(screen&&screen!=='render')blockers.append(link(screen==='production'?'Eksik Medyaları Akıllı Tamamla — Medya ekranına git':screen==='settings'?'Ayarlar ekranına git':'İlgili ekranı aç',screen==='settings'?'/settings':`/projects/${pid}/${screen}${screen==='production'?'#stock-short-clips':''}`));}if(!reasons.length)blockers.append(el('p',activeJob()?'Başka render işlemi devam ediyor.':state.source_message||state.ffmpeg.message||'Video kaynakları kontrol ediliyor…'));if(state.readiness?.unresolved_stock_slots)blockers.append(el('p',`Eksik medya: ${state.readiness.unresolved_stock_slots}`));}blockers.hidden=!!state.ready&&!activeJob();
    summary.replaceChildren();const s=state.summary;const recovery=state.recovery;if(recovery){summary.append(el('p',`Medya: ${recovery.selected_stock_assets||0}/${recovery.raw_stock_slots||0} ham alan dolu`),el('p',`Akıllı kurgu: ${recovery.render_ready?'Tamamlandı':'Eksikler var'} · Etkili zaman çizelgesi: ${recovery.effective_covered_duration||0} saniye kapsandı · Eksik süre: ${recovery.effective_uncovered_duration||0} sn`));if(recovery.message)summary.append(el('p',recovery.message));}
    summary.append(el('p',`Seslendirme: ${(state.readiness?.narration_ready??state.source_ready)?'Hazır':'Kontrol gerekli'} · Altyazı: ${(state.readiness?.subtitles_ready??state.source_ready)?'Hazır':'Kontrol gerekli'} · Stok medya: ${(state.readiness?.stock_ready??state.source_ready)?'Hazır':'Kontrol gerekli'}`),el('p',`FFmpeg: ${state.ffmpeg.status} · Çözünürlük: 1920×1080 · FPS: 30`));
    if(s)summary.append(el('p',`Süre: ${clock(s.duration)} · ${s.scenes} sahne · ${s.slots} medya yuvası · ${s.videos} video · ${s.images} görsel · ${s.subtitles} altyazı · ${s.overlays} mevcut sahne vurgusu`));
    if(!state.source_ready)summary.append(el('p',state.source_message));if(!state.ffmpeg.found)summary.append(el('p',state.ffmpeg.message));
    musicStatus.textContent=state.music?'Yerel müzik kaydedildi. Kullanmak için arka plan müziğini açın.':'Müzik yok. Video yalnız seslendirme ile oluşturulabilir.';
    jobs.replaceChildren();const j=state.job;
    if(j){jobs.append(el('h2',j.status_label));const p=el('progress');p.max=100;p.value=j.progress.percent;jobs.append(p,el('p',`%${j.progress.percent} · Geçen süre: ${clock(j.progress.elapsed_seconds)} · Kullanılan encoder: ${j.encoder_label}`));
      if(j.error_message)jobs.append(el('p',j.error_message));for(const w of j.progress.warnings||[])jobs.append(el('p',w));
      const d=j.progress.diagnostic;if(j.status==='error'&&d){const panel=el('section');panel.id='render-safe-diagnostic';panel.setAttribute('aria-live','polite');
        panel.append(el('h3','Güvenli render tanısı'),el('p',`Render aşaması: ${d.phase_label}`),el('p',`Hata türü: ${d.safe_error_summary}`),el('p',`Tanı kodu: ${d.safe_error_code}`));
        if(d.media_type)panel.append(el('p',`Medya türü: ${d.media_type==='video'?'Video':'Görsel'}`));
        if(d.encoder)panel.append(el('p',`Encoder: ${d.encoder==='h264_nvenc'?'NVIDIA NVENC':'CPU / libx264'}`));
        panel.append(el('p','Hata devam ederse yalnız bu güvenli tanıyı paylaşın. Önceki video ve kaynaklar korundu.'));jobs.append(panel);
      }
      if(activeJob())button(jobs,'Renderı İptal Et',()=>action(()=>request(`${base}/jobs/${j.id}/cancel`,'POST')));
    }
    // Poll progress without resetting the current video player or its seek/play state.
    const key=JSON.stringify([state.active?.id,state.versions.map(v=>[v.id,v.status,v.stale,v.video_missing])]);
    if(key!==lastVersionKey){lastVersionKey=key;versions.replaceChildren();for(const v of state.versions){const card=el('section');card.className='settings-panel';const m=v.metadata;card.append(el('h2',`Video Sürümü ${v.version}${v.id===state.active?.id?' · Aktif video':''}`),el('p',v.stale?'Eski kaynaklara ait':v.status_label));
        card.append(el('p',`Montaj Motoru: ${(m.montage_engine||m.options?.montage_engine)==='openmontage'?'OpenMontage':'Yerel Adaptif'}`));if(m.editing_style)card.append(el('p',`Kurgu stili: ${styleLabels[m.editing_style]||'Temel'}`));editCounts(card,m.smart_edit_summary,'Planlanan kurgu');editCounts(card,m.smart_edit_applied_summary,'Uygulanan kurgu');
        if(v.status==='completed'&&!v.video_missing){card.append(el('p',`${clock(m.duration)} · 1920×1080 · ${v.encoder_label} · ${(m.file_size/1048576).toFixed(1)} MB · ${new Date(v.created_at).toLocaleString('tr-TR')}`));const url=`${base}/versions/${v.id}/video`,video=el('video');video.controls=true;video.preload='metadata';video.src=url;video.id=`render-video-${v.version}`;card.append(video,link('Videoyu Aç',url),el('span',' · '),link('Dosyayı İndir',url+'?download=true'));if(v.id!==state.active?.id&&!v.stale)button(card,'Aktif Video Yap',()=>action(()=>request(`${base}/versions/${v.id}/activate`,'POST')));for(const w of m.warnings||[])card.append(el('p',w));}
        if(v.video_missing)card.append(el('p','Video dosyası eksik veya değişmiş. Kaynaklar ve kayıtlar korundu.'));versions.append(card);
      }}updateButtons();
  }
  async function load(refreshTools=false){try{const selectedEngine=montageEngine.value,chosen=editingStyle.value,selectedSeed=variationSeed,selectedMode=subtitles.value;const loaded=await request(`${base}?montage_engine=${montageEngine.value}&editing_style=${encodeURIComponent(chosen)}${variationSeed?'&edit_variation_seed='+encodeURIComponent(variationSeed):''}&subtitle_display=${subtitles.value}${refreshTools?'&refresh_tools=true':''}`);if(selectedEngine!==montageEngine.value||chosen!==editingStyle.value||selectedSeed!==variationSeed||selectedMode!==subtitles.value)return;state=loaded;render();status.textContent=activeJob()?'Video yerel olarak oluşturuluyor. Bu sayfayı açık tutabilirsiniz.':state.job?.status==='completed'?'Tamamlandı. Videonun başlangıcını, ortasını ve sonunu kontrol edin.':'Yerel video ayarlarını kontrol edin.';}catch(e){status.textContent=e.message;}}
  updateButtons();blockers.append(el('p','Video kaynakları kontrol ediliyor…'));
  async function poll(){if(stopped)return;await load();if(!stopped)setTimeout(poll,2000);}
  window.addEventListener('pagehide',()=>{stopped=true;});poll();
}
