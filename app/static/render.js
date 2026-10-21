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
  const engineLabel=el('label','Montaj Motoru'),montageEngine=el('select');montageEngine.id='render-engine';for(const [v,t] of [['openmontage','OpenMontage — Ana Motor'],['native','Yerel Adaptif — FFmpeg / NVIDIA']]){const o=el('option',t);o.value=v;montageEngine.append(o);}montageEngine.value='openmontage';engineLabel.append(montageEngine);const engineStatus=el('p');engineStatus.id='render-engine-status';form.append(engineLabel,engineStatus);let engineTouched=false;montageEngine.addEventListener('change',()=>{engineTouched=true;load();});
  const styleLabel=el('label','Kurgu Stili'),editingStyle=el('select');editingStyle.id='render-editing-style';
  for(const [value,text] of [['adaptive','Uyarlanabilir YouTube (önerilen)'],['basic','Temel'],['balanced','Dengeli YouTube'],['dynamic','Dinamik YouTube']]){const option=el('option',text);option.value=value;editingStyle.append(option);}
  const subtitleProfiles={adaptive:'Kalın YouTube altyazısı',basic:'Klasik altyazı',balanced:'Kalın YouTube altyazısı',dynamic:'Kalın büyük YouTube altyazısı'};
  const subtitleProfile=el('p',subtitleProfiles.balanced);subtitleProfile.id='render-subtitle-profile';
  editingStyle.value='adaptive';styleLabel.append(editingStyle);form.append(styleLabel,subtitleProfile);
  editingStyle.addEventListener('change',()=>{subtitleProfile.textContent=subtitleProfiles[editingStyle.value];if(!subtitleModeChosen)subtitles.value='full';return load();});
  const subtitles=el('select');subtitles.id='render-subtitles';const subtitleLabel=el('label','Altyazı Gösterimi');for(const [value,text] of [['full','Tam altyazı'],['emphasis','Sadece önemli vurgular'],['none','Altyazı yok']]){const o=el('option',text);o.value=value;subtitles.append(o);}subtitles.value='full';subtitleLabel.append(subtitles);form.append(subtitleLabel);let subtitleModeChosen=false;subtitles.addEventListener('change',()=>{subtitleModeChosen=true;if(state?.editorial&&state.editorial.editing_mode!=='legacy')return action(async()=>{const settings=await request(`/api/projects/${pid}/editor/editorial`);await request(`/api/projects/${pid}/editor/editorial`,'PUT',{...settings,preferences:{...settings.preferences,subtitle_display:subtitles.value}});});return load();});
  let variationSeed='';try{variationSeed=localStorage.getItem(`render-variation-${pid}`)||'';}catch{}
  // One-click look (colours, fonts, motion rhythm) for motion graphics, text graphics and subtitles.
  const lookLabel=el('label','Video görünümü (renk, yazı tipi, animasyon ritmi)'),look=el('select');look.id='render-look';lookLabel.append(look);const lookNote=el('p','');lookNote.className='note';form.append(lookLabel,lookNote);
  // Loaded once, after the first video-state request (see poll below).
  // Harita stili (kanal ayarı) and the word highlight in subtitles.
  const mapLabel=el('label','Harita stili (kanal ayarı)'),mapStyle=el('select');mapStyle.id='render-map-style';mapLabel.append(mapStyle);
  const wordLabel=el('label',''),wordBox=el('input');wordBox.type='checkbox';wordBox.id='render-word-highlight';wordLabel.append(wordBox,document.createTextNode(' Altyazıda okunan kelimeyi renkli kutuyla vurgula'));
  const mapNote=el('p','');mapNote.className='note';mapNote.id='render-map-note';mapNote.hidden=true;
  form.append(mapLabel,mapNote,wordLabel);
  const saveLook=async body=>{lookNote.textContent='Görünüm kaydediliyor…';try{const r=await fetch(`/api/projects/${pid}/look`,{method:'PUT',cache:'no-store',headers:{'Content-Type':'application/json','X-AI-Video-Studio':'projects'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.message||'Görünüm kaydedilemedi.');mapStyle.value=d.map_style;wordBox.checked=d.word_highlight;lookNote.textContent='✓ Kaydedildi. Yeni grafikler ve bir sonraki video bu ayarla oluşur.';}catch(e){lookNote.textContent=e.message;}};
  const stylePanel=el('details');stylePanel.id='render-mapbox-styles';
  stylePanel.append(el('summary','Mapbox harita görünümünü seç / Studio stili ekle'));
  const styleHost=el('section');stylePanel.append(styleHost);form.append(stylePanel);let mapboxPicker=null;
  stylePanel.addEventListener('toggle',()=>{if(stylePanel.open&&!mapboxPicker)mapboxPicker=window.createMapboxStylePicker(styleHost,{onSelected:async()=>{
    const r=await fetch(`/api/projects/${pid}/look`,{method:'PUT',cache:'no-store',headers:{'Content-Type':'application/json','X-AI-Video-Studio':'projects'},body:JSON.stringify({map_style:'satellite'})});
    const data=await r.json();if(!r.ok)throw new Error(data.message||'Stil kaydedildi; Mapbox harita kaynağı seçilemedi.');mapStyle.value='satellite';lookNote.textContent='✓ Mapbox stili seçildi. Yeni grafikler ve bir sonraki video bu ayarı kullanır.';
  }});});
  mapStyle.addEventListener('change',()=>saveLook({map_style:mapStyle.value}));wordBox.addEventListener('change',()=>saveLook({word_highlight:wordBox.checked}));
  const loadLook=()=>fetch(`/api/projects/${pid}/look`,{cache:'no-store'}).then(r=>r.json()).then(d=>{look.replaceChildren(...[['','Varsayılan (sade)'],...d.looks.map(l=>[l.id,l.label])].map(([v,t])=>{const o=el('option',t);o.value=v;return o;}));look.value=d.look||'';
    mapStyle.replaceChildren(...(d.map_styles||[]).map(m=>{const o=el('option',m.label+(m.disabled&&m.note?' — '+m.note:''));o.value=m.id;o.disabled=!!m.disabled;return o;}));mapStyle.value=d.map_style||'dark';
    const blocked=(d.map_styles||[]).find(m=>m.disabled&&m.note);mapNote.textContent=blocked?`ℹ ${blocked.label}: ${blocked.note}`:'';mapNote.hidden=!blocked;wordBox.checked=!!d.word_highlight;}).catch(()=>{});let lookLoaded=false;
  look.addEventListener('change',async()=>{if(!look.value)return;lookNote.textContent='Görünüm kaydediliyor…';try{const r=await fetch(`/api/projects/${pid}/look`,{method:'PUT',cache:'no-store',headers:{'Content-Type':'application/json','X-AI-Video-Studio':'projects'},body:JSON.stringify({look:look.value})});const d=await r.json();if(!r.ok)throw new Error(d.message||'Görünüm kaydedilemedi.');lookNote.textContent='✓ Görünüm kaydedildi. Yeni motion grafikler ve bir sonraki video bu görünümle oluşur.';}catch(e){lookNote.textContent=e.message;}});
  // Background music under the narration: always visible, not hidden in a fold.
  const musicDetails=el('section');musicDetails.id='render-music';musicDetails.className='music-panel';musicDetails.append(el('h3','🎵 Arka plan müziği (konuşmanın altında çalar)'),el('p','Kendi müzik dosyanızı ekleyin (MP3, WAV, M4A, OGG, FLAC). Konuşma sırasında müzik otomatik kısılır, başta yavaşça açılır, sonda yavaşça kapanır.'));form.append(musicDetails);
  const music=field('Bu videoda arka plan müziği kullan','checkbox',false,musicDetails);music.id='render-music-enabled';const file=field('1) Müzik dosyasını seçin (en fazla 100 MB)','file','',musicDetails);file.accept='.mp3,.wav,.m4a,.ogg,.flac';file.id='render-music-file';
  const license=field('2) Bu müziği kullanma hakkına sahibim (telifsiz veya lisanslı).','checkbox',false,musicDetails);license.id='render-music-license';
  const volume=field('Müzik seviyesi (0–0,30)','number',.12,musicDetails);volume.min=0;volume.max=.3;volume.step=.01;
  const fadeIn=field('Müzik başlangıç geçişi (saniye)','number',2,musicDetails),fadeOut=field('Müzik bitiş geçişi (saniye)','number',3,musicDetails);for(const n of [fadeIn,fadeOut]){n.min=0;n.max=30;n.step=.1;}
  const duck=field('Konuşma sırasında müziği kıs','checkbox',true,musicDetails),musicStatus=el('p');musicStatus.id='render-music-status';musicDetails.append(musicStatus);let musicTouched=false;music.addEventListener('change',()=>{musicTouched=true;});
  let state=null,pending=false,lastVersionKey='',stopped=false;
  const button=(parent,text,fn)=>{const n=el('button',text);n.type='button';n.addEventListener('click',fn);parent.append(n);return n;};
  const upload=button(musicDetails,'3) Müziği Ekle',async()=>{
    if(!file.files[0]||!license.checked){status.textContent='Müzik dosyasını seçin ve kullanma hakkınızı onaylayın.';return;}
    const f=file.files[0];if(f.size>100000000){status.textContent='Müzik dosyası 100 MB sınırını aşıyor.';return;}
    await action(async()=>{await request(base+'/music','POST',f,{'X-Music-Format':f.name.split('.').pop().toLowerCase(),'X-Music-License':'confirmed'});file.value='';music.checked=true;});
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
  function updateButtons(){create.disabled=pending||!state?.ready||activeJob();upload.disabled=pending||activeJob();encoder.disabled=activeJob();montageEngine.disabled=pending||activeJob()||!!(state?.editorial&&state.editorial.editing_mode!=='legacy');editingStyle.disabled=montageEngine.disabled;subtitles.disabled=pending||activeJob();variation.disabled=pending||activeJob();music.disabled=activeJob()||!!state?.timeline_music;create.textContent=state?.job&&['error','cancelled'].includes(state.job.status)?'Yeniden Render Et':'Videoyu Oluştur';}
  function clock(s){return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
  function remaining(p){ // rough estimate from real progress (Remotion frames fill 40-90 %)
    if(!(p.percent>=45&&p.percent<95&&p.elapsed_seconds>20))return '';
    return ` · Kalan: yaklaşık ${clock(Math.round(p.elapsed_seconds*(100-p.percent)/p.percent))}`;
  }
  const motionLabels={none:'Yok',push_in:'Yakınlaşma',push_out:'Uzaklaşma',pan_left:'Sola kayma',pan_right:'Sağa kayma',pan_up:'Yukarı kayma',pan_down:'Aşağı kayma',subtle_reframe:'Hafif kadraj değişimi'};
  const transitionLabels={hard_cut:'Temiz kesme',none:'Yok',crossfade:'Yumuşak geçiş',fade:'Koyu geçiş',fade_dark:'Koyu geçiş',dip_black:'Kısa kararma'};
  const styleLabels={adaptive:'Uyarlanabilir YouTube',basic:'Temel',balanced:'Dengeli YouTube',dynamic:'Dinamik YouTube'};
  const layoutLabels={full_broll:'Tam B-roll',split_media_text:'Medya ve metin',fact_card:'Bilgi kartı',big_number:'Büyük sayı',timeline_card:'Zaman çizelgesi',dual_media:'İki medya',minimal_title:'Kısa başlık',quote_emphasis:'Kısa vurgu',location_card:'Konum kartı'};
  function editCounts(parent,count,label){if(!count)return;parent.append(el('p',`${label}: Hareket efektleri: ${count.motion_effects} · Sahne geçişleri: ${count.scene_transitions} · Vurgu yazıları: ${count.emphasis_texts} · Klip içi değişimler: ${count.internal_edits}`));if(count.layouts)parent.append(el('p',Object.entries(count.layouts).map(([k,v])=>`${layoutLabels[k]}: ${v}`).join(' · ')),el('p',`Görsel düzen hataları: ${count.layout_failures||0} · B-roll: ${clock(count.broll_seconds||0)} · Grafik: ${clock(count.graphic_seconds||0)}`));}
  let planKey='';
  function showEditPlan(){const plan=state.smart_edit_plan,key=plan?.fingerprint||'';if(planKey===key)return;planKey=key;editSummary.replaceChildren();if(!plan)return;
    editSummary.append(el('h2',`Kurgu stili: ${plan.style_label}${plan.estimated?' · Tahmini plan':''}`),el('p','Yerel ve aynı kaynaklarda aynı plan. API kredisi kullanılmaz; yeni stok dosyası indirilmez.'));
    if(plan.edit_profile_label)editSummary.append(el('p',`Kurgu ritmi (sahne duygularından seçildi): ${plan.edit_profile_label}`));
    if(plan.edit_variation_seed)editSummary.append(el('p',`Kurgu Varyasyonu: ${variationSeed||'Varsayılan'}`));editCounts(editSummary,plan.summary,'Planlanan kurgu');const details=el('details');details.append(el('summary','Kurgu Planını Gör'));
    const table=el('table'),thead=el('thead'),head=el('tr');for(const text of ['Zaman','Sahne','Düzen','Medya','Efekt','Geçiş','Metin'])head.append(el('th',text));thead.append(head);table.append(thead);
    const body=el('tbody');let sceneOrder=0,lastScene='';for(const item of plan.slots){if(lastScene!==item.scene_id){sceneOrder++;lastScene=item.scene_id;}
      for(const segment of item.segments){const row=el('tr'),texts=plan.emphasis.filter(e=>e.slot_id===item.slot_id&&e.start>=segment.start&&e.start<segment.end).map(e=>e.text).join(' · ');
        const transition=segment===item.segments[item.segments.length-1]?item.transition_out:'hard_cut';
        for(const text of [`${clock(segment.start)}–${clock(segment.end)}`,String(sceneOrder),item.layout_label||'Tam B-roll',item.media_type==='image'?'Görsel':'Video',motionLabels[segment.motion_effect]||'Mevcut hareket',transitionLabels[transition]||'Temiz kesme',(item.texts||[]).join(' · ')||texts||'—'])row.append(el('td',text));body.append(row);}}
    table.append(body);const wrapper=el('div');wrapper.style.overflowX='auto';wrapper.append(table);details.append(wrapper);editSummary.append(details);
  }
  function render(){
    if(state.editorial&&state.editorial.editing_mode!=='legacy'){montageEngine.value='native';montageEngine.disabled=true;editingStyle.value='basic';editingStyle.disabled=true;subtitles.value=state.editorial.subtitle_display;wordBox.checked=state.editorial.word_highlight;wordBox.disabled=true;engineStatus.textContent='Manuel Kurgu / Kullanıcı Düzenlemeleri — otomatik dekor ve montaj yok.';if(state.timeline_music){music.checked=false;music.disabled=true;musicDetails.title='Müzik Kurgu timeline’ındaki kliplerden yönetiliyor; buradaki eski global müzik kullanılmaz.';}}

    // OpenMontage is optional: without it the local engine is chosen, so “Videoyu Oluştur” is never blocked by a default.
    if(!engineTouched&&montageEngine.value==='openmontage'&&state.openmontage&&!state.openmontage.ready&&!activeJob()){engineTouched=true;montageEngine.value='native';blockers.replaceChildren(el('p','Video kaynakları kontrol ediliyor…'));load();return;}
    showEditPlan();blockers.replaceChildren();engineStatus.textContent=state.editorial?.editing_mode!=='legacy'?'Manuel Kurgu — kayıtlı timeline, yerel FFmpeg':`OpenMontage: ${state.openmontage?.status||'Kurulu değil'}${state.openmontage?.ready?'':' — video Yerel Adaptif motorla oluşturulur.'}`;if(!state.ready||activeJob()){blockers.append(el('h3','Video henüz oluşturulamıyor.'));const reasons=state.readiness?.blockers||[];for(const b of reasons){blockers.append(el('p',b.message));const screen=b.screen;if(screen&&screen!=='render')blockers.append(link(screen==='production'?'Eksik Medyaları Akıllı Tamamla — Medya ekranına git':screen==='settings'?'Ayarlar ekranına git':'İlgili ekranı aç',screen==='settings'?'/settings':`/projects/${pid}/${screen}${screen==='production'?'#stock-short-clips':''}`));}if(!reasons.length)blockers.append(el('p',activeJob()?'Başka render işlemi devam ediyor.':state.source_message||state.ffmpeg.message||'Video kaynakları kontrol ediliyor…'));if(state.readiness?.unresolved_stock_slots)blockers.append(el('p',`Eksik medya: ${state.readiness.unresolved_stock_slots}`));}blockers.hidden=!!state.ready&&!activeJob();
    summary.replaceChildren();const s=state.summary;const recovery=state.recovery;if(recovery){summary.append(el('p',`Medya: ${recovery.selected_stock_assets||0}/${recovery.raw_stock_slots||0} ham alan dolu`),el('p',`Akıllı kurgu: ${recovery.render_ready?'Tamamlandı':'Eksikler var'} · Etkili zaman çizelgesi: ${recovery.effective_covered_duration||0} saniye kapsandı · Eksik süre: ${recovery.effective_uncovered_duration||0} sn`));if(recovery.continued_seconds)summary.append(el('p',`${recovery.continued_seconds} sn, komşu çekimin kesintisiz devamıyla kapatıldı.`));if(recovery.message)summary.append(el('p',recovery.message));}
    summary.append(el('p',`Seslendirme: ${(state.readiness?.narration_ready??state.source_ready)?'Hazır':'Kontrol gerekli'} · Altyazı: ${(state.readiness?.subtitles_ready??state.source_ready)?'Hazır':'Kontrol gerekli'} · Stok medya: ${(state.readiness?.stock_ready??state.source_ready)?'Hazır':'Kontrol gerekli'}`),el('p',`FFmpeg: ${state.ffmpeg.status} · Çözünürlük: 1920×1080 · FPS: 30`));
    const qualityWarnings=state.readiness?.quality_warnings||[];
    if(qualityWarnings.length)summary.append(el('p',`${qualityWarnings.length} mevcut medya yatay HD standardının altında. Seçimleriniz korundu; isterseniz Medya ekranında kontrol edin.`),link('Medya seçimlerini kontrol et',`/projects/${pid}/production#stock-short-clips`));
    if(s)summary.append(el('p',`Süre: ${clock(s.duration)} · ${s.scenes} sahne · ${s.slots} medya yuvası · ${s.videos} video · ${s.images} görsel · ${s.subtitles} altyazı · ${s.overlays} mevcut sahne vurgusu`));
    if(!state.source_ready)summary.append(el('p',state.source_message));if(!state.ffmpeg.found)summary.append(el('p',state.ffmpeg.message));
    if(state.music&&!musicTouched&&!state.timeline_music)music.checked=true;  // an added track is used unless the owner turns it off
    musicStatus.textContent=state.music?(music.checked?'✓ Müzik eklendi ve bu videoda kullanılacak (konuşmada otomatik kısılır).':'Müzik eklendi ama şu an kapalı. Kullanmak için “Bu videoda arka plan müziği kullan” kutusunu işaretleyin.'):'Henüz müzik yok. Video yalnız seslendirme ile oluşturulur; isterseniz yukarıdan müzik ekleyin.';
    jobs.replaceChildren();const j=state.job;
    if(j){jobs.append(el('h2',j.status_label));const p=el('progress');p.max=100;p.value=j.progress.percent;jobs.append(p,el('p',`%${j.progress.percent} · Geçen süre: ${clock(j.progress.elapsed_seconds)}${remaining(j.progress)} · Kullanılan encoder: ${j.encoder_label}`));
      if(j.error_message)jobs.append(el('p',j.error_message));for(const w of j.progress.warnings||[])jobs.append(el('p',w));
      const d=j.progress.diagnostic;if(j.status==='error'&&d){const panel=el('section');panel.id='render-safe-diagnostic';panel.setAttribute('aria-live','polite');
        panel.append(el('h3','Güvenli render tanısı'),el('p',`Render aşaması: ${d.phase_label}`),el('p',`Hata türü: ${d.safe_error_summary}`),el('p',`Tanı kodu: ${d.safe_error_code}`));
        if(d.media_type)panel.append(el('p',`Medya türü: ${d.media_type==='video'?'Video':'Görsel'}`));
        if(d.encoder)panel.append(el('p',`Encoder: ${d.encoder==='h264_nvenc'?'NVIDIA NVENC':'CPU / libx264'}`));
        panel.append(el('p','Hata devam ederse yalnız bu güvenli tanıyı paylaşın. Önceki video ve kaynaklar korundu.'));jobs.append(panel);
      }
      if(activeJob())button(jobs,'Renderı İptal Et',()=>action(()=>request(`${base}/jobs/${j.id}/cancel`,'POST')));
      if(['error','cancelled'].includes(j.status)){
        jobs.append(el('p','Güvenli yeniden başlatma kaynak/plan kimliğini doğrular, aynı ayarlarla yeni sürüm üretir ve hazır medya/animasyon önbelleğini kullanır. Kaldığı kareden devam etmez.','note'));
        button(jobs,'Aynı ayarlarla güvenli yeniden başlat',()=>{if(confirm('Kaynaklar doğrulanıp aynı yerel ayarlarla yeni render sürümü başlatılsın mı?'))return action(()=>request(`${base}/jobs/${j.id}/restart`,'POST',{confirmed:true}));});
      }
    }
    // Poll progress without resetting the current video player or its seek/play state.
    const key=JSON.stringify([state.active?.id,state.versions.map(v=>[v.id,v.status,v.stale,v.video_missing])]);
    if(key!==lastVersionKey){lastVersionKey=key;versions.replaceChildren();for(const v of state.versions){const card=el('section');card.className='settings-panel';const m=v.metadata;card.append(el('h2',`Video Sürümü ${v.version}${v.id===state.active?.id?' · Aktif video':''}`),el('p',v.stale?'Eski kaynaklara ait':v.status_label));
        card.append(el('p',`Montaj Motoru: ${(m.montage_engine||m.options?.montage_engine)==='openmontage'?'OpenMontage':'Yerel Adaptif'}`));const rt=m.render_timing;if(rt&&rt.total_seconds)card.append(el('p',`Render süresi: ${clock(Math.round(rt.total_seconds))}${rt.remotion_seconds?` (Remotion ${clock(Math.round(rt.remotion_seconds))} · FFmpeg ${clock(Math.round(rt.ffmpeg_seconds))})`:''}${rt.parallel_pieces>1?` · ${rt.parallel_pieces} parça paralel`:''}`));if(m.editing_style)card.append(el('p',`Kurgu stili: ${styleLabels[m.editing_style]||'Temel'}`));editCounts(card,m.smart_edit_summary,'Planlanan kurgu');editCounts(card,m.smart_edit_applied_summary,'Uygulanan kurgu');
        if(v.status==='completed'&&!v.video_missing){card.append(el('p',`${clock(m.duration)} · 1920×1080 · ${v.encoder_label} · ${(m.file_size/1048576).toFixed(1)} MB · ${new Date(v.created_at).toLocaleString('tr-TR')}`));const url=`${base}/versions/${v.id}/video`,video=el('video');video.controls=true;video.preload='metadata';video.src=url;video.id=`render-video-${v.version}`;card.append(video,link('Videoyu Aç',url),el('span',' · '),link('Dosyayı İndir',url+'?download=true'));if(v.id!==state.active?.id&&!v.stale)button(card,'Aktif Video Yap',()=>action(()=>request(`${base}/versions/${v.id}/activate`,'POST')));for(const w of m.warnings||[])card.append(el('p',w));}
        if(v.video_missing)card.append(el('p','Video dosyası eksik veya değişmiş. Kaynaklar ve kayıtlar korundu.'));versions.append(card);
      }}updateButtons();
  }
  async function load(refreshTools=false){try{const selectedEngine=montageEngine.value,chosen=editingStyle.value,selectedSeed=variationSeed,selectedMode=subtitles.value;const loaded=await request(`${base}?montage_engine=${montageEngine.value}&editing_style=${encodeURIComponent(chosen)}${variationSeed?'&edit_variation_seed='+encodeURIComponent(variationSeed):''}&subtitle_display=${subtitles.value}${refreshTools?'&refresh_tools=true':''}`);if(selectedEngine!==montageEngine.value||chosen!==editingStyle.value||selectedSeed!==variationSeed||selectedMode!==subtitles.value)return;state=loaded;render();status.textContent=activeJob()?'Video yerel olarak oluşturuluyor. Bu sayfayı açık tutabilirsiniz.':state.job?.status==='completed'?'Tamamlandı. Videonun başlangıcını, ortasını ve sonunu kontrol edin.':'Yerel video ayarlarını kontrol edin.';}catch(e){status.textContent=e.message;}}
  updateButtons();blockers.append(el('p','Video kaynakları kontrol ediliyor…'));
  async function poll(){if(stopped)return;await load();if(!lookLoaded){lookLoaded=true;loadLook();}if(!stopped)setTimeout(poll,2000);}
  window.addEventListener('pagehide',()=>{stopped=true;});poll();
}
