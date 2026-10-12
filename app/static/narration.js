/* Part 7 local UI. Paid work always requires explicit confirmation. */
if (/^\/projects\/[^/]+\/narration$/.test(window.location.pathname)) {
  const pid=window.location.pathname.split('/')[2],base=`/api/projects/${pid}/narration`;
  const root=document.querySelector('#narration-content');root.hidden=false;
  const languageName=code=>({de:'Almanca',es:'İspanyolca',en:'İngilizce',fr:'Fransızca',tr:'Türkçe'}[code]||code);
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const back=node('a','← Projeye dön');back.href=`/projects/${pid}`;root.append(back);
  const intro=node('p','Bu aşama yalnız seslendirme oluşturur. Sahne planı ve stok dosyaları değişmez. Altyazı ve video render yapılmaz.');
  const status=node('p','Seslendirme bilgileri yükleniyor…');status.setAttribute('role','status');
  const diagnostic=node('pre');diagnostic.id='narration-diagnostic';
  const source=node('p'),docs=node('p'),controls=node('div');controls.className='settings-actions';
  const form=node('div');form.className='settings-panel';
  function field(label,control){const wrapper=node('div');wrapper.className='setting-field';const title=node('label',label);title.append(control);wrapper.append(title);form.append(wrapper);return control;}
  const provider=field('Ses sağlayıcısı',node('select'));
  for(const [value,label] of [['elevenlabs','ElevenLabs'],['minimax','MiniMax'],['clone','Mevcut klon sesler'],['edge','Microsoft Edge'],['vbee','Vbee'],['fishaudio','Fish Audio']]){const o=node('option',label);o.value=value;provider.append(o);}
  const voice=field('Ses',node('select')),speed=field('Hız (0,5–1,5)',node('input'));speed.type='number';speed.min='.5';speed.max='1.5';speed.step='.05';speed.value='1';
  const settings=node('a','Ses seçmek için Ayarlar → AI33 / OpenSpeaker');settings.href='/settings';form.append(settings);
  const versions=node('section');versions.id='narration-versions';root.append(intro,status,diagnostic,source,docs,form,controls,versions);
  let state=null,pending=false,timer=null,loading=false,initialized=false;
  function button(parent,text,fn){const b=node('button',text);b.type='button';b.addEventListener('click',fn);parent.append(b);return b;}
  const RUNNING=['queued','running','verifying'];
  const active=()=>pending||RUNNING.includes(state?.job?.status);
  async function request(url,method='GET',body){
    let response;
    try{response=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(15000),headers:{'X-AI-Video-Studio':'projects','Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
    catch{throw new Error('Seslendirme ekranına ulaşılamadı. Uygulama penceresini kontrol edip Yenile deyin.');}
    let result;try{result=await response.json();}catch{throw new Error('Seslendirme yanıtı okunamadı. Sayfayı yenileyip tekrar deneyin.');}if(!response.ok)throw new Error(result.message||'Seslendirme işlemi tamamlanamadı.');return result;
  }
  async function operate(fn){if(active())return;pending=true;sync();try{await fn();await load();}catch(error){status.textContent=error.message;}finally{pending=false;sync();}}
  function generate(kind='narration',regenerate=false,force=false){
    if(!state?.approved_script)return;
    const warning=force?'Aynı metin ve sesle yakın zamanda oluşturulmuş bir AI33 görevi var. YENİ bir görev oluşturulacak ve tekrar kredi harcanacak. Emin misiniz?':kind==='preview'?'Bu işlem AI33 kredisi kullanabilir. Devam edilsin mi?':regenerate?'Yeni bir AI33 görevi oluşturulacak ve ek kredi kullanabilir. Mevcut seslendirme korunacak. Devam edilsin mi?':'AI33/OpenSpeaker seslendirmesi kredi kullanabilir. Devam edilsin mi?';
    if(!window.confirm(warning))return;
    return operate(()=>request(base+'/jobs','POST',{source_script_version_id:state.approved_script.id,voice_provider:provider.value,voice_id:voice.value,speed:Number(speed.value),kind,cost_confirmed:true,regenerate_confirmed:regenerate,force_new_task:force}));
  }
  const AUDIO_FORMATS={mp3:'mp3',wav:'wav',flac:'flac',ogg:'ogg',m4a:'m4a'};
  async function upload(version,file){
    const format=AUDIO_FORMATS[(file?.name||'').split('.').pop().toLowerCase()];
    if(!format){status.textContent='Desteklenen ses biçimleri: MP3, WAV, FLAC, OGG, M4A.';return;}
    if(!window.confirm(`“${file.name}” dosyası Sürüm ${version.version} için ses olarak kaydedilsin mi? Kredi harcanmaz.`))return;
    return operate(async()=>{
      let response;
      try{response=await fetch(`${base}/versions/${version.id}/upload`,{method:'POST',cache:'no-store',headers:{'X-AI-Video-Studio':'projects','X-Audio-Format':format,'Content-Type':'application/octet-stream'},body:file});}
      catch{throw new Error('Ses dosyası yüklenemedi. Uygulama penceresini kontrol edip tekrar deneyin.');}
      let result;try{result=await response.json();}catch{throw new Error('Yükleme yanıtı okunamadı.');}
      if(!response.ok)throw new Error(result.message||'Ses dosyası yüklenemedi.');
    });
  }
  const create=button(controls,'Seslendirmeyi Oluştur',()=>generate()),sample=button(controls,'Kısa TTS Testi (kredi kullanır)',()=>generate('preview'));sample.className='secondary';
  const regenerate=button(controls,'Yeniden Oluştur',()=>generate('narration',true));
  const resume=button(controls,'Devam Et',()=>operate(()=>request(`${base}/jobs/${state.job.id}/resume`,'POST',{})));
  const forceNew=button(controls,'Yeni görev oluştur (kredi harcanır)',()=>generate('narration',true,true));forceNew.className='secondary';
  button(controls,'Yenile',load);
  function voiceChoices(){
    const selected=voice.value;voice.replaceChildren();const empty=node('option','Ayarlar ekranından sesleri getirin');empty.value='';voice.append(empty);
    for(const v of state?.settings.voices||[])if(v.provider===provider.value){const o=node('option',`${v.display_name||v.voice_id}${v.language?' · '+v.language:''}${v.gender?' · '+v.gender:''}`);o.value=v.voice_id;voice.append(o);}
    voice.value=selected&&Array.from(voice.options).some(o=>o.value===selected)?selected:provider.value===state?.settings.voice_provider?state.settings.voice_id:'';
    sync();
  }
  provider.addEventListener('change',voiceChoices);voice.addEventListener('change',sync);speed.addEventListener('input',sync);
  function sync(){
    const chosen=state?.settings.voices.find(v=>v.provider===provider.value&&v.voice_id===voice.value),rate=Number(speed.value);
    const usable=state?.settings.contract_ready&&state.settings.has_api_key&&state.approved_script&&chosen&&/^(elevenlabs|minimax|clone|edge|kokoro|vbee|fishaudio)_\S+$/.test(voice.value)&&Number.isFinite(rate)&&rate>=.5&&rate<=1.5;
    create.disabled=sample.disabled=regenerate.disabled=active()||!usable;
    create.hidden=!!state?.versions.some(v=>v.kind==='narration');regenerate.hidden=!create.hidden;
    resume.hidden=state?.job?.status!=='error'||state?.job?.progress.category==='recent_duplicate';resume.disabled=active();
    forceNew.hidden=!(state?.job?.status==='error'&&state.job.progress.category==='recent_duplicate');forceNew.disabled=active()||!usable;
    provider.disabled=voice.disabled=speed.disabled=active()||!state;
  }
  function render(){
    source.textContent=state?.approved_script?`Onaylı senaryo: Sürüm ${state.approved_script.version} · Dil: ${languageName(state.approved_script.language)} · ${state.approved_script.character_count} karakter`:'Önce senaryo sürümünü onaylayın.';
    docs.textContent=state?.settings.documentation_message||'';
    versions.replaceChildren();versions.append(node('h2','Seslendirme sürümleri'));
    for(const v of state?.versions||[]){
      const m=v.metadata,card=node('article');card.className='settings-panel';
      card.append(node('h3',`${v.kind==='preview'?'Kısa TTS Testi':'Seslendirme'} Sürümü ${v.version}${state.active?.id===v.id?' · Aktif seslendirme':''}`),node('p',`${m.provider} · ${m.voice_provider} · ${m.voice_name||m.voice_id} · Hız: ${m.speed}`),node('p',`Dil: ${languageName(m.target_language)} · ${m.character_count} karakter · ${new Date(v.created_at).toLocaleString('tr-TR')}`),node('p',`Kaynak senaryo: ${m.source_script_version?'Sürüm '+m.source_script_version:v.source_script_version_id}`));
      card.append(node('p',`Durum: ${{queued:'Görev oluşturuluyor',running:'Görev bekleniyor',verifying:'Doğrulanıyor (AI33 görev geçmişinde aranıyor)',completed:'Tamamlandı',error:'Hata'}[m.status]||'Bekliyor'}`));
      card.append(node('p',m.task_id?`AI33 görevi: ${m.task_id}${m.recovered_from_history?' (görev geçmişinden kurtarıldı)':''}${m.reused_existing_task?' (mevcut görev kullanıldı, yeni kredi harcanmadı)':''}`:m.audio_source==='manual_upload'?'AI33 görevi: bağlanmadı (ses elle yüklendi)':m.creation_attempted?'AI33 görevi: istek gönderildi, kimlik henüz doğrulanmadı':'AI33 görevi: henüz gönderilmedi'));
      if(m.audio_source==='manual_upload')card.append(node('p','Ses dosyası elle yüklendi.'));
      if(v.stale)card.append(node('p','Eski senaryo sürümüne ait'));
      if(!m.audio)card.append(node('p','Ses dosyası henüz hazır değil.'));
      if((!m.audio||v.audio_missing)&&!RUNNING.includes(m.status)){
        const tools=node('div');tools.className='settings-actions';
        if(m.status==='error'&&(m.task_id||m.creation_attempted)){const rescue=button(tools,'AI33’ten kurtar',()=>operate(()=>request(`${base}/versions/${v.id}/recover`,'POST',{})));rescue.disabled=active();rescue.title='AI33 görev geçmişinde bu sürümün görevini bulur ve sesi indirir. Yeni kredi harcanmaz.';}
        const picker=node('input');picker.type='file';picker.accept='.mp3,.wav,.flac,.ogg,.m4a,audio/*';picker.hidden=true;
        picker.addEventListener('change',()=>{const file=picker.files?.[0];picker.value='';if(file)upload(v,file);});
        const manual=button(tools,'Sesi elle yükle',()=>picker.click());manual.className='secondary';manual.disabled=active();manual.title='AI33 panelinden indirdiğiniz ses dosyasını bu sürüme bağlar.';
        tools.append(picker);card.append(tools);
      }
      if(v.audio_missing)card.append(node('p','Yerel ses dosyası eksik; görev kimliği korundu.'));
      if(m.audio&&!v.audio_missing){
        card.append(node('p',m.audio.duration===null?'Ses süresi daha sonra hesaplanacak.':`Gerçek ses süresi: ${m.audio.duration.toFixed(1)} saniye`));
        const audio=node('audio');audio.controls=true;audio.preload='metadata';audio.src=`${base}/versions/${v.id}/audio`;card.append(audio);
        const open=node('a','Ses Dosyasını Aç');open.href=audio.src;open.target='_blank';open.rel='noopener';card.append(open);
        if(v.kind==='narration'&&state.active?.id!==v.id){const activate=button(card,'Aktif Seslendirme Olarak Seç',()=>{if(window.confirm('Bu seslendirme sürümü aktif seçilsin mi?'))operate(()=>request(`${base}/versions/${v.id}/activate`,'POST',{confirm:true}));});activate.disabled=active();}
      }
      versions.append(card);
    }
    sync();
  }
  async function load(){
    if(loading)return;loading=true;
    try{state=await request(base);if(!initialized){provider.value=state.settings.voice_provider;speed.value=String(state.settings.speed);initialized=true;}voiceChoices();
      const job=state.job;status.textContent=job?job.status==='error'?`⚠ ${job.error_message}`:job.progress.message:'Seslendirme bilgileri hazır.';
      diagnostic.textContent=job?.progress?.diagnostic?JSON.stringify(job.progress.diagnostic,null,2):'';
      render();
    }catch(error){status.textContent=error.message;}finally{loading=false;clearTimeout(timer);if(RUNNING.includes(state?.job?.status))timer=setTimeout(load,1200);}
  }
  window.addEventListener('pagehide',()=>clearTimeout(timer));load();
}
