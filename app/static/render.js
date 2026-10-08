/* Local Part 9 only. No provider request is made from this page. */
if(/^\/projects\/[^/]+\/render$/.test(location.pathname)){
  const pid=location.pathname.split('/')[2],base=`/api/projects/${pid}/render`,root=document.querySelector('#render-content');root.hidden=false;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const link=(text,href)=>{const n=el('a',text);n.href=href;return n;};
  const status=el('p','Video kaynakları kontrol ediliyor…');status.id='render-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const summary=el('section'),form=el('section'),jobs=el('section'),versions=el('section');form.className='settings-panel';
  root.append(link('← Projeye dön',`/projects/${pid}`),status,summary,form,jobs,versions);
  form.append(el('h2','Yerel video ayarları'),el('p','Video bu bilgisayarda oluşturulur. Ses, altyazı ve stok dosyaları değiştirilmez; API kredisi kullanılmaz.'));
  function field(label,type,value){const wrap=el('label',label),n=el('input');n.type=type;if(type==='checkbox')n.checked=value;else n.value=value;wrap.append(n);form.append(wrap);return n;}
  const encLabel=el('label','Encoder'),encoder=el('select');encoder.id='render-encoder';for(const [v,t] of [['auto','Otomatik — NVIDIA tercih et'],['nvenc','NVIDIA NVENC'],['cpu','CPU']]){const o=el('option',t);o.value=v;encoder.append(o);}encLabel.append(encoder);form.append(encLabel);
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
  const create=button(form,'Videoyu Oluştur',()=>action(async()=>{await request(base+'/jobs','POST',{encoder:encoder.value,subtitle_burned:subtitles.checked,music_enabled:music.checked,music_volume:Number(volume.value),music_fade_in:Number(fadeIn.value),music_fade_out:Number(fadeOut.value),music_ducking:duck.checked});}));create.id='render-create';
  const refresh=button(form,'Durumu Yenile',()=>load(true));
  async function request(url,method='GET',body=null,extra={}){
    const headers={'X-AI-Video-Studio':'projects',...extra},isFile=body instanceof File;
    if(body&&!isFile)headers['Content-Type']='application/json';
    let r;try{r=await fetch(url,{method,headers,body:body?(isFile?body:JSON.stringify(body)):undefined,cache:'no-store',signal:AbortSignal.timeout(isFile?120000:60000)});}catch{throw Error('Uygulamaya ulaşılamadı. Uygulama penceresini kontrol edip Durumu Yenile’ye basın.');}
    const data=await r.json();if(!r.ok)throw Error(data.message||'Video işlemi tamamlanamadı.');return data;
  }
  async function action(fn){if(pending)return;pending=true;updateButtons();try{await fn();status.textContent='İşlem alındı.';await load();}catch(e){status.textContent=e.message;}finally{pending=false;updateButtons();}}
  const activeJob=()=>state?.job&&['queued','preparing','rendering','validating'].includes(state.job.status);
  function updateButtons(){create.disabled=pending||!state?.ready||activeJob();upload.disabled=pending||activeJob();encoder.disabled=activeJob();subtitles.disabled=activeJob();music.disabled=activeJob();create.textContent=state?.job&&['error','cancelled'].includes(state.job.status)?'Yeniden Render Et':'Videoyu Oluştur';}
  function clock(s){return `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;}
  function render(){
    summary.replaceChildren();const s=state.summary;
    summary.append(el('p',`Seslendirme: ${state.source_ready?'Hazır':'Kontrol gerekli'} · Altyazı: ${state.source_ready?'Hazır':'Kontrol gerekli'} · Stok medya: ${state.source_ready?'Hazır':'Kontrol gerekli'}`),el('p',`FFmpeg: ${state.ffmpeg.status} · Çözünürlük: 1920×1080 · FPS: 30`));
    if(s)summary.append(el('p',`Süre: ${clock(s.duration)} · ${s.scenes} sahne · ${s.slots} medya yuvası · ${s.videos} video · ${s.images} görsel · ${s.subtitles} altyazı · ${s.overlays} vurgu yazısı`));
    if(!state.source_ready)summary.append(el('p',state.source_message));if(!state.ffmpeg.found)summary.append(el('p',state.ffmpeg.message));
    musicStatus.textContent=state.music?'Yerel müzik kaydedildi. Kullanmak için arka plan müziğini açın.':'Müzik yok. Video yalnız seslendirme ile oluşturulabilir.';
    jobs.replaceChildren();const j=state.job;
    if(j){jobs.append(el('h2',j.status_label));const p=el('progress');p.max=100;p.value=j.progress.percent;jobs.append(p,el('p',`%${j.progress.percent} · Geçen süre: ${clock(j.progress.elapsed_seconds)} · Kullanılan encoder: ${j.encoder_label}`));
      if(j.error_message)jobs.append(el('p',j.error_message));for(const w of j.progress.warnings||[])jobs.append(el('p',w));
      if(activeJob())button(jobs,'Renderı İptal Et',()=>action(()=>request(`${base}/jobs/${j.id}/cancel`,'POST')));
    }
    // Poll progress without resetting the current video player or its seek/play state.
    const key=JSON.stringify([state.active?.id,state.versions.map(v=>[v.id,v.status,v.stale,v.video_missing])]);
    if(key!==lastVersionKey){lastVersionKey=key;versions.replaceChildren();for(const v of state.versions){const card=el('section');card.className='settings-panel';const m=v.metadata;card.append(el('h2',`Video Sürümü ${v.version}${v.id===state.active?.id?' · Aktif video':''}`),el('p',v.stale?'Eski kaynaklara ait':v.status_label));
        if(v.status==='completed'&&!v.video_missing){card.append(el('p',`${clock(m.duration)} · 1920×1080 · ${v.encoder_label} · ${(m.file_size/1048576).toFixed(1)} MB · ${new Date(v.created_at).toLocaleString('tr-TR')}`));const url=`${base}/versions/${v.id}/video`,video=el('video');video.controls=true;video.preload='metadata';video.src=url;video.id=`render-video-${v.version}`;card.append(video,link('Videoyu Aç',url),el('span',' · '),link('Dosyayı İndir',url+'?download=true'));if(v.id!==state.active?.id&&!v.stale)button(card,'Aktif Video Yap',()=>action(()=>request(`${base}/versions/${v.id}/activate`,'POST')));for(const w of m.warnings||[])card.append(el('p',w));}
        if(v.video_missing)card.append(el('p','Video dosyası eksik veya değişmiş. Kaynaklar ve kayıtlar korundu.'));versions.append(card);
      }}updateButtons();
  }
  async function load(refreshTools=false){try{state=await request(base+(refreshTools?'?refresh_tools=true':''));render();status.textContent=activeJob()?'Video yerel olarak oluşturuluyor. Bu sayfayı açık tutabilirsiniz.':state.job?.status==='completed'?'Tamamlandı. Videonun başlangıcını, ortasını ve sonunu kontrol edin.':'Yerel video ayarlarını kontrol edin.';}catch(e){status.textContent=e.message;}}
  async function poll(){if(stopped)return;await load();if(!stopped)setTimeout(poll,2000);}
  window.addEventListener('pagehide',()=>{stopped=true;});poll();
}
