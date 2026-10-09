/* Local Part 9 / 9.5 only. No provider request is made from this page. */
if(/^\/projects\/[^/]+\/render$/.test(location.pathname)){
  const pid=location.pathname.split('/')[2],base=`/api/projects/${pid}/render`,root=document.querySelector('#render-content');root.hidden=false;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const link=(text,href)=>{const n=el('a',text);n.href=href;return n;};
  const status=el('p','Video kaynakları kontrol ediliyor…');status.id='render-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const summary=el('section'),editSummary=el('section'),form=el('section'),jobs=el('section'),versions=el('section');form.className='settings-panel';
  root.append(link('← Projeye dön',`/projects/${pid}`),status,summary,form,editSummary,jobs,versions);
  form.append(el('h2','Yerel video ayarları'),el('p','Video bu bilgisayarda oluşturulur. Ses, altyazı ve stok dosyaları değiştirilmez; API kredisi kullanılmaz.'));
  function field(label,type,value){const wrap=el('label',label),n=el('input');n.type=type;if(type==='checkbox')n.checked=value;else n.value=value;wrap.append(n);form.append(wrap);return n;}
  const encLabel=el('label','Encoder'),encoder=el('select');encoder.id='render-encoder';for(const [v,t] of [['auto','Otomatik — NVIDIA tercih et'],['nvenc','NVIDIA NVENC'],['cpu','CPU']]){const o=el('option',t);o.value=v;encoder.append(o);}encLabel.append(encoder);form.append(encLabel);
  const styleLabel=el('label','Kurgu Stili'),editingStyle=el('select');editingStyle.id='render-editing-style';
  for(const [value,text] of [['basic','Temel'],['balanced','Dengeli YouTube'],['dynamic','Dinamik YouTube']]){const option=el('option',text);option.value=value;editingStyle.append(option);}
  editingStyle.value='balanced';styleLabel.append(editingStyle);form.append(styleLabel);editingStyle.addEventListener('change',()=>load());
  const subtitles=field('Altyazıları Videoya Yaz','checkbox',true);subtitles.id='render-subtitles';
  const music=field('Arka plan müziği açık','checkbox',false),file=field('Arka plan müziği ekle (en fazla 100 MB)','file','');file.accept='.mp3,.wav,.m4a,.ogg,.flac';
  const license=field('Bu müziği kullanma hakkına sahibim.','checkbox',false);
  const volume=field('Müzik seviyesi (0–0,30)','number',.12);volume.min=0;volume.max=.3;volume.step=.01;
  const fadeIn=field('Müzik başlangıç geçişi (saniye)','number',2),fadeOut=field('Müzik bitiş geçişi (saniye)','number',3);for(const n of [fadeIn,fadeOut]){n.min=0;n.max=30;n.step=.1;}
  const duck=field('Konuşma sırasında müziği kıs','checkbox',true),musicStatus=el('p');form.append(musicStatus);
  let state=null,pending=false,lastVersionKey='',stopped=false;
  const button=(parent,text,fn)=>{const n=el('button',text);n.type='button';n.addEventListener('click',fn);parent.append(n);return n;};
  const upload=button(form,'Müziği Kaydet',async()=>{
    if(!file.files[0]||!license.checked){status.textContent='Müzik dosyasını seçin ve kullanma hakkınızı onaylayın.';return;}
    const f=file.files[0];if(f.size>100000000){status.textContent='Müzik dosyası 100 MB sınırını aşıyor.';return;}
    await action(async()=>{await request(base+'/music','POST',f,{'X-Music-Format':f.name.split('.').pop().toLowerCase(),'X-Music-License':'confirmed'});file.value='';});
  });
  const create=button(form,'Videoyu Oluştur',()=>action(async()=>{await request(base+'/jobs','POST',{encoder:encoder.value,editing_style:editingStyle.value,subtitle_burned:subtitles.checked,music_enabled:music.checked,music_volume:Number(volume.value),music_fade_in:Number(fadeIn.value),music_fade_out:Number(fadeOut.value),music_ducking:duck.checked});}));create.id='render-create';
  const refresh=button(form,'Durumu Yenile',()=>load(true));
  async function request(url,method='GET',body=null,extra={}){
    const headers={'X-AI-Video-Studio':'projects',...extra},isFile=body instanceof File;
    if(body&&!isFile)headers['Content-Type']='application/json';
    let r;try{r=await fetch(url,{method,headers,body:body?(isFile?body:JSON.stringify(body)):undefined,cache:'no-store',signal:AbortSignal.timeout(isFile?120000:60000)});}catch{throw Error('Uygulamaya ulaşılamadı. Uygulama penceresini kontrol edip Durumu Yenile’ye basın.');}
    const data=await r.json();if(!r.ok)throw Error(data.message||'Video işlemi tamamlanamadı.');return data;
  }
  async function action(fn){if(pending)return;pending=true;updateButtons();try{await fn();status.textContent='İşlem alındı.';await load();}catch(e){status.textContent=e.message;}finally{pending=false;updateButtons();}}
  const activeJob=()=>state?.job&&['queued','preparing','rendering','validating'].includes(state.job.status);
  function updateButtons(){create.disabled=pending||!state?.ready||activeJob();upload.disabled=pending||activeJob();encoder.disabled=activeJob();editingStyle.disabled=pending||activeJob();subtitles.disabled=activeJob();music.disabled=activeJob();create.textContent=state?.job&&['error','cancelled'].includes(state.job.status)?'Yeniden Render Et':'Videoyu Oluştur';}
  function clock(s){return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
  const motionLabels={none:'Yok',push_in:'Yakınlaşma',push_out:'Uzaklaşma',pan_left:'Sola kayma',pan_right:'Sağa kayma',pan_up:'Yukarı kayma',pan_down:'Aşağı kayma',subtle_reframe:'Hafif kadraj değişimi'};
  const transitionLabels={hard_cut:'Temiz kesme',none:'Yok',crossfade:'Yumuşak geçiş',fade:'Koyu geçiş',fade_dark:'Koyu geçiş',dip_black:'Kısa kararma'};
  const styleLabels={basic:'Temel',balanced:'Dengeli YouTube',dynamic:'Dinamik YouTube'};
  function editCounts(parent,count,label){if(!count)return;parent.append(el('p',`${label}: Hareket efektleri: ${count.motion_effects} · Sahne geçişleri: ${count.scene_transitions} · Vurgu yazıları: ${count.emphasis_texts} · Klip içi değişimler: ${count.internal_edits}`));}
  let planKey='';
  function showEditPlan(){const plan=state.smart_edit_plan,key=plan?.fingerprint||'';if(planKey===key)return;planKey=key;editSummary.replaceChildren();if(!plan)return;
    editSummary.append(el('h2',`Kurgu stili: ${plan.style_label}`),el('p','Yerel ve aynı kaynaklarda aynı plan. API kredisi kullanılmaz; yeni stok dosyası indirilmez.'));
    editCounts(editSummary,plan.summary,'Planlanan kurgu');const details=el('details');details.append(el('summary','Kurgu Planını Gör'));
    const table=el('table'),thead=el('thead'),head=el('tr');for(const text of ['Zaman','Sahne','Efekt','Geçiş','Vurgu'])head.append(el('th',text));thead.append(head);table.append(thead);
    const body=el('tbody');let sceneOrder=0,lastScene='';for(const item of plan.slots){if(lastScene!==item.scene_id){sceneOrder++;lastScene=item.scene_id;}
      for(const segment of item.segments){const row=el('tr'),texts=plan.emphasis.filter(e=>e.slot_id===item.slot_id&&e.start>=segment.start&&e.start<segment.end).map(e=>e.text).join(' · ');
        const transition=segment===item.segments[item.segments.length-1]?item.transition_out:'hard_cut';
        for(const text of [`${clock(segment.start)}–${clock(segment.end)}`,String(sceneOrder),motionLabels[segment.motion_effect]||'Mevcut hareket',transitionLabels[transition]||'Temiz kesme',texts||'—'])row.append(el('td',text));body.append(row);}}
    table.append(body);const wrapper=el('div');wrapper.style.overflowX='auto';wrapper.append(table);details.append(wrapper);editSummary.append(details);
  }
  function render(){showEditPlan();
    summary.replaceChildren();const s=state.summary;
    summary.append(el('p',`Seslendirme: ${state.source_ready?'Hazır':'Kontrol gerekli'} · Altyazı: ${state.source_ready?'Hazır':'Kontrol gerekli'} · Stok medya: ${state.source_ready?'Hazır':'Kontrol gerekli'}`),el('p',`FFmpeg: ${state.ffmpeg.status} · Çözünürlük: 1920×1080 · FPS: 30`));
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
        if(m.editing_style)card.append(el('p',`Kurgu stili: ${styleLabels[m.editing_style]||'Temel'}`));editCounts(card,m.smart_edit_summary,'Planlanan kurgu');editCounts(card,m.smart_edit_applied_summary,'Uygulanan kurgu');
        if(v.status==='completed'&&!v.video_missing){card.append(el('p',`${clock(m.duration)} · 1920×1080 · ${v.encoder_label} · ${(m.file_size/1048576).toFixed(1)} MB · ${new Date(v.created_at).toLocaleString('tr-TR')}`));const url=`${base}/versions/${v.id}/video`,video=el('video');video.controls=true;video.preload='metadata';video.src=url;video.id=`render-video-${v.version}`;card.append(video,link('Videoyu Aç',url),el('span',' · '),link('Dosyayı İndir',url+'?download=true'));if(v.id!==state.active?.id&&!v.stale)button(card,'Aktif Video Yap',()=>action(()=>request(`${base}/versions/${v.id}/activate`,'POST')));for(const w of m.warnings||[])card.append(el('p',w));}
        if(v.video_missing)card.append(el('p','Video dosyası eksik veya değişmiş. Kaynaklar ve kayıtlar korundu.'));versions.append(card);
      }}updateButtons();
  }
  async function load(refreshTools=false){try{const chosen=editingStyle.value;const loaded=await request(`${base}?editing_style=${encodeURIComponent(chosen)}${refreshTools?'&refresh_tools=true':''}`);if(chosen!==editingStyle.value)return;state=loaded;render();status.textContent=activeJob()?'Video yerel olarak oluşturuluyor. Bu sayfayı açık tutabilirsiniz.':state.job?.status==='completed'?'Tamamlandı. Videonun başlangıcını, ortasını ve sonunu kontrol edin.':'Yerel video ayarlarını kontrol edin.';}catch(e){status.textContent=e.message;}}
  async function poll(){if(stopped)return;await load();if(!stopped)setTimeout(poll,2000);}
  window.addEventListener('pagehide',()=>{stopped=true;});poll();
}
