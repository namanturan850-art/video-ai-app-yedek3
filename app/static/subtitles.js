/* Part 8: local audio, deterministic subtitles, immutable saved edits. */
if(/^\/projects\/[^/]+\/subtitles$/.test(window.location.pathname)){
  const pid=window.location.pathname.split('/')[2],base=`/api/projects/${pid}/subtitles`;
  const root=document.querySelector('#subtitles-content');root.hidden=false;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const link=(text,href)=>{const n=node('a',text);n.href=href;return n;};
  const status=node('p','Altyazı bilgileri yükleniyor…');status.id='subtitles-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const summary=node('div'),actions=node('div');actions.className='settings-actions';
  const preview=node('section');preview.className='settings-panel';
  const audio=node('audio');audio.id='subtitle-audio';audio.controls=true;audio.preload='metadata';
  const caption=node('p','Ses oynarken geçerli altyazı burada görünür.');caption.id='subtitle-preview';caption.className='subtitle-preview';
  const versionList=node('section'),editor=node('section');editor.id='subtitle-editor';
  root.append(link('← Projeye dön',`/projects/${pid}`),status,summary,actions,preview,versionList,editor);
  preview.append(node('h2','Yerel ses ve altyazı önizlemesi'),audio,caption);
  let state=null,pending=false,draft=[],rows=[],activeCue=-1,dirty=false;
  const button=(parent,text,fn)=>{const b=node('button',text);b.type='button';b.addEventListener('click',fn);parent.append(b);return b;};
  async function request(url,method='GET',body){
    let r;try{r=await fetch(url,{method,cache:'no-store',signal:AbortSignal.timeout(60000),headers:{'Content-Type':'application/json','X-AI-Video-Studio':'projects'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
    catch{throw new Error('Yerel işlem yanıt vermedi. Uygulama penceresini açık tutup sayfayı yenileyin; sürümleriniz korunur.');}
    let result;try{result=await r.json();}catch{throw new Error('Altyazı yanıtı okunamadı. Sayfayı yeniden açın.');}
    if(!r.ok)throw new Error(result.message||'Altyazı işlemi tamamlanamadı.');return result;
  }
  function sync(){
    create.disabled=pending||!state?.can_generate;save.disabled=pending||!state?.active||state.active.stale;
    refresh.disabled=pending;duration.disabled=pending||!state?.narration;
    for(const element of editor.querySelectorAll('input,textarea'))element.disabled=pending||state?.active?.stale;
    for(const element of versionList.querySelectorAll('button'))element.disabled=pending;
  }
  async function operate(fn){
    if(pending)return;pending=true;sync();status.textContent='Yerel altyazı işlemi yapılıyor…';
    try{await fn();state=await request(base);render();status.textContent=state.message;}
    catch(error){status.textContent=error.message;}
    finally{pending=false;sync();}
  }
  function discard(){return !dirty||window.confirm('Kaydedilmemiş altyazı değişiklikleri var. Bu değişikliklerden vazgeçilsin mi?');}
  const create=button(actions,'Altyazıları Oluştur',()=>{
    if(!discard())return;const regenerate=!!state?.versions.length;
    if(regenerate&&!window.confirm('Yeni bir altyazı sürümü oluşturulacak. Mevcut sürüm korunacak.'))return;
    operate(()=>request(base+'/versions','POST',{regenerate_confirmed:regenerate}));
  });
  const duration=button(actions,'Ses Süresini Ölç',()=>{if(discard())operate(()=>request(base+'/duration','POST',{}));});
  const refresh=button(actions,'Yenile',()=>{if(discard())load();});
  const save=button(actions,'Değişiklikleri Kaydet',()=>operate(async()=>{
    const cues=rows.map(row=>({start:SubtitleTiming.parse(row.start.value),end:SubtitleTiming.parse(row.end.value),text:row.text.value}));
    await request(`${base}/versions/${state.active.id}/edit`,'POST',{cues});
  }));
  button(preview,'Önceki Altyazı',()=>{if(draft.length)audio.currentTime=draft[Math.max(0,(activeCue<0?0:activeCue)-1)].start;});
  button(preview,'Sonraki Altyazı',()=>{if(draft.length)audio.currentTime=draft[Math.min(draft.length-1,(activeCue<0?-1:activeCue)+1)].start;});
  function follow(){
    const index=SubtitleTiming.current(draft,audio.currentTime);
    if(index!==activeCue){if(rows[activeCue])rows[activeCue].card.classList.remove('current-cue');if(rows[index])rows[index].card.classList.add('current-cue');activeCue=index;}
    caption.textContent=index>=0?draft[index].text:'Bu anda altyazı yok.';
  }
  audio.addEventListener('timeupdate',follow);audio.addEventListener('seeked',follow);
  function updateDraft(index){
    dirty=true;const row=rows[index];
    try{draft[index]={...draft[index],start:SubtitleTiming.parse(row.start.value),end:SubtitleTiming.parse(row.end.value),text:row.text.value};follow();}
    catch{status.textContent='Zamanı 00:00:04,120 biçiminde yazın. Kaydetmeden önce kontrol edin.';}
  }
  function render(){
    dirty=false;summary.replaceChildren();versionList.replaceChildren();editor.replaceChildren();rows=[];activeCue=-1;
    const voice=state.narration,m=voice?.metadata,a=m?.audio,lang={de:'Almanca',es:'İspanyolca',en:'İngilizce',fr:'Fransızca',tr:'Türkçe'};
    summary.append(node('p',voice?`Aktif seslendirme: ${m.voice_name||m.voice_id} · Dil: ${lang[m.target_language]||m.target_language}`:'Aktif tamamlanmış seslendirme bulunamadı.'),node('p',`Ses süresi: ${a?.duration?`${Math.floor(a.duration/60)}:${String(Math.round(a.duration)%60).padStart(2,'0')}`:'Ölçülemedi'}`),node('p',`Kaynak senaryo: ${m?.source_script_version?'Sürüm '+m.source_script_version:'—'}`),node('p','Zamanlama: Ses süresine göre yaklaşık zamanlama'),node('p','Kelime zamanları kesin değildir. Başlangıç, orta ve son bölümü dinleyerek gerektiğinde zamanları düzeltin. Bu işlem yereldir ve API kredisi kullanmaz.'));
    const audioUrl=voice&&!voice.audio_missing&&(!state.active||!state.active.stale)?`/api/projects/${pid}/narration/versions/${voice.id}/audio`:null;
    if(audioUrl&&audio.getAttribute('src')!==audioUrl)audio.src=audioUrl;
    if(!audioUrl)audio.removeAttribute('src');preview.hidden=!audioUrl;
    create.textContent=state.versions.length?'Altyazıları Yeniden Oluştur':'Altyazıları Oluştur';
    versionList.append(node('h2','Altyazı sürümleri'));
    for(const v of state.versions){
      const card=node('article');card.className='settings-panel';card.append(node('h3',`Altyazı Sürümü ${v.version}${state.active?.id===v.id?' · Aktif altyazı':''}`),node('p',new Date(v.created_at).toLocaleString('tr-TR')));
      if(v.stale)card.append(node('p',v.stale_message));
      if(!v.metadata.text_matches_narration)card.append(node('p','Altyazı metni seslendirme metninden farklı.'));
      const links=node('div');links.className='settings-actions';
      for(const ext of ['srt','vtt']){const open=link(`${ext.toUpperCase()} Dosyasını Aç`,`${base}/versions/${v.id}/files/${ext}`);open.target='_blank';open.rel='noopener';links.append(open);}
      card.append(links);
      if(state.active?.id!==v.id)button(card,'Aktif Altyazı Olarak Seç',()=>{if(discard()&&window.confirm('Bu altyazı sürümü aktif seçilsin mi?'))operate(()=>request(`${base}/versions/${v.id}/activate`,'POST',{confirm:true}));});
      versionList.append(card);
    }
    draft=(state.active?.cues||[]).map(c=>({...c}));
    if(state.active){
      editor.append(node('h2',`Altyazı Sürümü ${state.active.version} · Düzenleme`),node('p','Kaydetmek yeni bir sürüm oluşturur; önceki sürüm korunur. Zaman biçimi: 00:00:04,120.'));
      if(state.active.stale)editor.append(node('p','Bu sürüm eski seslendirmeye veya senaryoya ait. Eşleşen güncel seslendirmeyi seçin ya da altyazıları yeniden oluşturun.'));
      for(const [index,cue] of draft.entries()){
        const card=node('article');card.className='subtitle-cue settings-panel';card.dataset.index=String(index);card.append(node('h3',`#${index+1}`));
        const row={card};
        for(const [key,label] of [['start','Başlangıç'],['end','Bitiş'],['text','Metin']]){
          const group=node('label',label),input=node(key==='text'?'textarea':'input');input.setAttribute('aria-label',`${index+1}. altyazı ${label}`);
          input.value=key==='text'?cue.text:SubtitleTiming.timestamp(cue[key]);if(key==='text')input.rows=2;
          else{input.type='text';input.placeholder='00:00:04,120';}
          row[key]=input;input.addEventListener('input',()=>updateDraft(index));group.append(input);card.append(group);
        }
        rows.push(row);editor.append(card);
      }
    }
    follow();sync();
  }
  async function load(){
    if(pending)return;pending=true;sync();status.textContent='Yerel ses süresi ve altyazılar kontrol ediliyor…';
    try{state=await request(base);render();status.textContent=state.message;}catch(error){status.textContent=error.message;}
    finally{pending=false;sync();}
  }
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  load();
}
