/* NAMAN's real editor workspace. All writes use the existing revision APIs. */
(() => {
  const node=(tag,text='',className='')=>{const n=document.createElement(tag);n.textContent=text;n.className=className;return n;};
  const button=(text,run)=>{const b=node('button',text);b.type='button';b.onclick=run;return b;};
  const link=(text,url)=>{const a=node('a',text);a.href=url;return a;};
  const field=(label,input)=>{const n=node('label',label);n.append(input);return n;};
  const store={get(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}},set(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch{}}};
  let ctx,redrawArchive=()=>{},stopReverse=()=>{},cleanup=()=>{};
  const panels=['Özellikler','Düzenle','Motion','Metin','Ses','JSON'];
    const api={active:false,mount,refreshArchive:()=>redrawArchive(),paintWaveform,archiveError:()=>{if(!ctx)return;const retry=button('Arşivi Yeniden Dene',()=>ctx.load());ctx.library.append(retry);}};
  window.NAMANWorkspace=api;

  function mount(c){
    cleanup();ctx=c;api.active=true;
    const {root,bar,work,library,preview,inspector,timeline,layout,status,controls:k}=c;
    root.classList.add('workspace');status.setAttribute('role','status');
    status.setAttribute('aria-live','polite');
    const tools=root.querySelectorAll(':scope > details.settings-panel');
    const audioTools=[...tools].find(x=>x.querySelector('summary')?.textContent==='Ses miks ayarları');
    const manualTools=[...tools].find(x=>x.querySelector('summary')?.textContent==='Manuel AI / JSON');
    if(audioTools&&!c.data.tracks.audio.length)audioTools.append(node('p','Aktif seslendirme yok. Miks değerleri kaydedilebilir; ses üretmez. Seslendirme ekranından yerel anlatım sürümünü seçin.','note'));
    const report=node('dialog','','workspace-dialog'),reportBody=node('div','','workspace-dialog-body');
    report.append(button('Kapat',()=>report.close()),reportBody);root.append(report);
    function openReport(title,contents){reportBody.replaceChildren(node('h2',title),...contents);if(!report.open)report.showModal();}
    function showTool(title,tool){if(!tool)return;tool.open=true;openReport(title,[tool]);}

    // The inspector remains the original live edit form; tabs select its real controls.
    const inspectorFrame=node('section','','workspace-inspector'),tabBar=node('div','','workspace-tabs');
    inspector.before(inspectorFrame);inspectorFrame.append(tabBar,inspector);
    tabBar.setAttribute('role','tablist');tabBar.setAttribute('aria-label','Klip düzenleyicileri');
    let activeTab='Özellikler',selected=null;
    panels.forEach(name=>{const b=button(name,()=>selectTab(name));b.setAttribute('role','tab');b.dataset.tab=name;tabBar.append(b);});
    function selectTab(name){activeTab=name;if(name==='Ses'){showTool('Ses miks ayarları',audioTools);}applyTab();}
    const tabObserver=typeof MutationObserver==='undefined'?null:new MutationObserver(applyTab);tabObserver?.observe(inspector,{childList:true,subtree:true});
    function applyTab(){
      if(inspector.dataset.advanced==='1')return;
      tabBar.querySelectorAll('button').forEach(b=>{const on=b.dataset.tab===activeTab;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;});
      const form=inspector.querySelector('form');
      if(!form)return;
      // Preserve inputs and handlers while hiding unrelated groups, including JSON tools.
      const isMotion=!!c.getSelected()?.motion_spec;
      [...inspector.children].forEach(child=>{if(child!==form&&child.tagName!=='H2')child.hidden=false;});
      const groups=[...form.children];
      groups.forEach(child=>{
        const text=child.firstChild?.textContent||child.textContent||'';
        const json=child.querySelector?.('.naman-motion-json');
        const visual=child.classList.contains('naman-motion-visual');
        const extras=child.matches('h3,.settings-actions,.naman-json-message,.naman-json-diff,input[type=file]');
        let visible=activeTab==='Özellikler'||activeTab==='Düzenle';
        if(activeTab==='Motion')visible=visual||/Şablon|Vurgu/.test(text)||child.tagName==='BUTTON';
        if(activeTab==='JSON')visible=!!json||extras||child.tagName==='BUTTON';
        if(activeTab==='Metin')visible=c.getSelected()?.text!==undefined&&!isMotion;
        if(activeTab==='Ses')visible=false;
        if((activeTab==='Özellikler'||activeTab==='Düzenle')&&(visual||json||extras))visible=false;
        child.hidden=!visible;
      });
      let note=inspector.querySelector('.workspace-tab-note');
      if(!note){note=node('p','','workspace-tab-note');inspector.append(note);}
      const unavailable=(['Motion','JSON'].includes(activeTab)&&!isMotion)||(activeTab==='Metin'&&!c.getSelected()?.text);
      const message=activeTab==='Ses'?'Anlatım ve efekt seviyelerini Ses miks panelinde düzenleyin.':unavailable?'Bu klip için bu bölümde düzenlenebilir veri yok.':'';
      if(note.textContent!==message)note.textContent=message;
      note.hidden=!note.textContent;
    }
    tabBar.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();let i=panels.indexOf(activeTab);i=e.key==='Home'?0:e.key==='End'?panels.length-1:(i+(e.key==='ArrowRight'?1:-1)+panels.length)%panels.length;selectTab(panels[i]);tabBar.children[i].focus();};
    const selectOriginal=c.inspect;
    c.select=(track,item)=>{selected={track,item};selectOriginal(track,item);c.enhanceMotion(inspector);c.enhanceSubtitle(inspector);applyTab();};
    timeline.addEventListener('click',e=>{const clip=e.target.closest('.naman-clip');if(!clip)return;const track=clip.dataset.track,item=c.data.tracks[track]?.find(x=>x.slot_id&&x.slot_id===clip.dataset.slotId)||c.data.tracks[track]?.find(x=>x.start<=c.getTime()&&c.getTime()<x.end);if(item){selected={track,item};c.enhanceMotion(inspector);c.enhanceSubtitle(inspector);applyTab();}});

    const surface=node('div','','workspace-program-surface');
    [...preview.children].filter(n=>!n.classList.contains('naman-monitor-label')).forEach(n=>surface.append(n));
    const previewMessage=node('p','','workspace-preview-message');surface.append(previewMessage);preview.append(surface);
    const checkPreview=(time=c.getTime())=>{
      const item=c.media().find(x=>x.start<=time&&time<x.end);
      const message=!item?'Bu aralıkta hazırlanmış görüntü yok.':!item.media?'Bu yuvanın medya dosyası henüz hazır değil.':'';
      if(previewMessage.textContent!==message)previewMessage.textContent=message;
      previewMessage.hidden=!message;
    };
    api.updatePreview=checkPreview;checkPreview();
    surface.querySelectorAll('video,img').forEach(element=>element.addEventListener('error',()=>{previewMessage.textContent='Önizleme dosyası açılamadı. Medya hazırlama ekranından bu yuvanın durumunu kontrol edin.';previewMessage.hidden=false;}));

    // A dedicated source monitor makes selecting an archive item inspectable before assigning it.
    const source=node('section','','workspace-source');source.hidden=true;
    const sourceMedia=node('div','','workspace-source-media'),sourceActions=node('div','','workspace-source-actions');
    source.append(node('h3','Kaynak önizlemesi'),sourceMedia,sourceActions);library.replaceChildren();
    const libraryTabs=node('div','','workspace-tabs'),search=node('input'),provider=node('select'),items=node('div','','workspace-media-grid');
    search.type='search';search.placeholder='Medya ara…';search.setAttribute('aria-label','Medya ara');
    provider.setAttribute('aria-label','Medya kaynağı');
    const importButton=button('＋ Medya içe aktar',()=>c.upload.click());c.upload.hidden=true;
    const libraryFilters=node('div','','workspace-media-filters');libraryFilters.append(search,provider);
    let archiveTab='Arşiv',page=1,currentArchiveItem=null;const pageSize=60;
    ['Arşiv','Görseller','Ekran','Sesler','Motion'].forEach(name=>libraryTabs.append(button(name,()=>{archiveTab=name;page=1;drawArchive();})));
    const more=button('Daha fazla göster',()=>{page++;drawArchive();});
    library.append(libraryTabs,libraryFilters,importButton,c.upload,source,items,more);
    search.oninput=()=>{page=1;drawArchive();};provider.onchange=()=>{page=1;drawArchive();};
    function drawArchive(){
      const archive=c.getArchive();const previous=provider.value;
      provider.replaceChildren(new Option('Tüm kaynaklar',''),...[...new Set(archive.items.map(x=>x.provider))].map(p=>new Option(p,p)));provider.value=previous;
      [...libraryTabs.children].forEach(b=>b.classList.toggle('active',b.textContent===archiveTab));
      items.replaceChildren();
      if(archiveTab==='Motion'){
        const motions=c.media().filter(item=>item.motion_spec);
        motions.forEach(item=>{const b=button(item.label||item.motion_spec.template,()=>{const track=c.data.track_order.find(t=>c.data.tracks[t].includes(item));c.select(track,item);selectTab('Motion');c.seekTo(item.start);});b.className='workspace-motion-card';b.draggable=!!item.slot_id&&!item.locked;b.ondragstart=e=>{e.dataTransfer.setData('application/x-naman-motion-slot',item.slot_id);e.dataTransfer.effectAllowed='move';};b.append(node('small',`${c.clock(item.start)} · Mevcut proje animasyonu`));items.append(b);});
        if(!motions.length)items.append(node('p','Bu projede hazır motion kaydı yok. Görsel ve Kurgu Hazırlığı ekranından hazırlayın.','workspace-empty'));more.hidden=true;return;
      }
      const query=search.value.trim().toLocaleLowerCase('tr');
      const filtered=archive.items.filter(x=>(!provider.value||x.provider===provider.value)&&(!query||String(x.title||x.media_id).toLocaleLowerCase('tr').includes(query))&&(archiveTab==='Arşiv'||archiveTab==='Görseller'&&['video','image'].includes(x.media_type)||archiveTab==='Sesler'&&x.media_type==='audio'||archiveTab==='Ekran'&&x.provider==='screen'));
      if(!filtered.length)items.append(node('p',archiveTab==='Ekran'?'Ekran kaydı yok. Harici kaydedilen MP4 dosyasını içe aktarabilirsiniz.':'Eşleşen yerel medya yok. Medya içe aktarın veya filtreleri değiştirin.','workspace-empty'));
      filtered.slice(0,page*pageSize).forEach(item=>{
        const b=button('',()=>selectSource(item));b.className='workspace-media-card';b.draggable=item.media_type!=='audio';b.dataset.mediaId=item.media_id;b.dataset.provider=item.provider;b.title=item.title||item.media_id;
        const thumb=node('div','','workspace-media-thumb');
        if(item.media_type==='image'){const img=node('img');img.src=item.preview_url;img.alt=item.title||'Yerel görsel';img.loading='lazy';img.onerror=()=>thumb.replaceChildren(node('span','Görsel önizlenemiyor'));thumb.append(img);}
        else thumb.append(node('span',item.media_type==='audio'?'♪':'▶'),node('small',item.media_type==='audio'?'Ses dosyası':'Video · kaynakta önizle'));
        b.append(thumb,node('strong',item.title||item.media_id),node('small',`${item.provider} · ${item.duration?c.clock(item.duration):item.media_type}`));
        b.classList.toggle('selected',currentArchiveItem?.media_id===item.media_id&&currentArchiveItem?.provider===item.provider);
        b.ondragstart=e=>{c.setChosen(item);e.dataTransfer.setData('application/x-naman-media',JSON.stringify({provider:item.provider,media_id:item.media_id}));e.dataTransfer.effectAllowed='copy';};items.append(b);
      });more.hidden=filtered.length<=page*pageSize;
    }
    async function selectSource(item){
      currentArchiveItem=item;c.setChosen(item);source.hidden=false;sourceMedia.replaceChildren();sourceActions.replaceChildren();
      const media=node(item.media_type==='image'?'img':item.media_type==='audio'?'audio':'video');media.src=item.preview_url;media.controls=true;media.preload='metadata';media.alt=item.title||'Kaynak';sourceMedia.append(media);
      const start=node('input'),end=node('input');start.type=end.type='number';start.min=end.min=0;start.step=end.step=.001;start.value=item.clip_range?.start||0;end.value=item.clip_range?.end||item.duration||1;
      const save=button('Kaynak kesitini kaydet',async()=>{try{const saved=await c.api(`/api/projects/${c.id}/editor/archive/${item.provider}/${item.media_id}/range`,{method:'PUT',body:JSON.stringify({sha256:item.sha256,start:+start.value,end:+end.value,revision:item.clip_range?.revision||0})});Object.assign(item,saved);c.setChosen(item);status.textContent='Kaynak kesiti kaydedildi; sahne ve anlatım süresi değişmedi.';}catch(e){status.textContent=e.message;}});
      start.onchange=()=>{if(item.media_type!=='image')media.currentTime=+start.value;};
      sourceActions.append(field('Kaynak başlangıcı (sn)',start),field('Kaynak bitişi (sn)',end),save,button('Seçili görüntü yuvasına ata',()=>assign(item,c.getSelected())),button('Kaynağı kapat',()=>{media.pause?.();source.hidden=true;}));drawArchive();
    }
    redrawArchive=drawArchive;drawArchive();
    async function assign(item,target){
      if(!target?.slot_id||target.locked||!c.data.tracks.visuals.some(x=>x.slot_id===target.slot_id)){status.textContent='Medyayı kilitsiz bir Görüntü yuvasına bırakın. Yeni katman veya süre oluşturulmaz.';return;}
      if(!['video','image'].includes(item.media_type)){status.textContent='Bu yuvaya yalnız video veya görsel atanabilir.';return;}
      const start=item.clip_range?.start||0,end=item.clip_range?.end||item.duration||Math.max(1,target.end-target.start);
      try{await c.api(`/api/projects/${c.id}/editor/slots/${target.slot_id}/media`,{method:'PUT',body:JSON.stringify({plan_id:c.data.stock_plan_id,revision:c.data.stock_revision,provider:item.provider,media_id:item.media_id,sha256:item.sha256,start,end})});await c.load();ctx.status.textContent='Medya atandı ve revizyon kaydedildi. Geri al ile geri dönebilirsiniz.';}catch(e){status.textContent=e.message;}
    }
    timeline.addEventListener('dragover',e=>{const clip=e.target.closest('.naman-clip'),motion=e.dataTransfer.types.includes('application/x-naman-motion-slot');if(!clip||!motion&&!e.dataTransfer.types.includes('application/x-naman-media'))return;e.preventDefault();timeline.querySelectorAll('.drop-target').forEach(n=>n.classList.remove('drop-target'));if((motion?['maps','infographics','layers','emphasis'].includes(clip.dataset.track):clip.dataset.track==='visuals')&&!clip.classList.contains('locked'))clip.classList.add('drop-target');e.dataTransfer.dropEffect=clip.classList.contains('drop-target')?(motion?'move':'copy'):'none';});
    timeline.addEventListener('dragleave',e=>e.target.closest('.naman-clip')?.classList.remove('drop-target'));
    timeline.addEventListener('drop',e=>{e.preventDefault();const clip=e.target.closest('.naman-clip');timeline.querySelectorAll('.drop-target').forEach(n=>n.classList.remove('drop-target'));if(e.dataTransfer.types.includes('application/x-naman-motion-slot')){moveMotion(e.dataTransfer.getData('application/x-naman-motion-slot'),clip);return;}try{const ref=JSON.parse(e.dataTransfer.getData('application/x-naman-media')),item=c.getArchive().items.find(x=>x.media_id===ref.media_id&&x.provider===ref.provider),target=c.data.tracks.visuals.find(x=>x.slot_id===clip?.dataset.slotId);if(!item)throw Error('Arşiv öğesi bulunamadı. Arşivi yenileyin.');assign(item,target);}catch(error){status.textContent=e.dataTransfer.files.length?'Dosyayı önce Medya içe aktar ile güvenli arşive ekleyin.':error.message;}});
    async function moveMotion(slotId,clip){
      const source=c.media().find(x=>x.slot_id===slotId),target=c.media().find(x=>x.slot_id===clip?.dataset.slotId);
      const track=c.data.track_order.find(t=>c.data.tracks[t].some(x=>x.slot_id===slotId));
      if(!source?.motion_spec||!target||source.locked||target.locked||source.scene_id!==target.scene_id||track!==clip?.dataset.track){status.textContent='Motion yalnız aynı sahnenin aynı türdeki kilitsiz iz yuvaları arasında taşınabilir. Yeni katman oluşturulmaz.';return;}
      if(source.slot_id===target.slot_id){status.textContent='Animasyon zaten bu yuvada.';return;}
      const scene=c.data.scenes.find(x=>x.scene_id===source.scene_id),ordered=c.media().filter(x=>x.scene_id===source.scene_id).sort((a,b)=>a.start-b.start).map(x=>({...x})),moving=ordered.find(x=>x.slot_id===slotId);
      ordered.splice(ordered.indexOf(moving),1);ordered.splice(ordered.findIndex(x=>x.slot_id===target.slot_id),0,moving);
      let cursor=scene.start;const slots=ordered.map(item=>{const duration=item.end-item.start,start=cursor;cursor+=duration;return{slot_id:item.slot_id,start,end:cursor,source_start:item.clip_start||0,source_end:item.clip_end||((item.clip_start||0)+duration)};});
      try{await c.api(`/api/projects/${c.id}/editor/timeline`,{method:'PUT',body:JSON.stringify({plan_id:c.data.stock_plan_id,revision:c.data.stock_revision,scene_id:source.scene_id,slots})});await c.load();ctx.status.textContent='Animasyon sırası aynı sahne süresi içinde kaydedildi.';}catch(error){status.textContent=error.message;}
    }

    // Use the original control handlers; secondary tools live in an actual overflow menu.
    const edit=node('div','','workspace-control-group'),transport=node('div','','workspace-control-group workspace-transport'),view=node('div','','workspace-control-group');
    const labels={undo:'↶',redo:'↷',split:'Böl',duplicate:'Çoğalt',lock:'Kilitle',back:'−5 sn',next:'+5 sn',fb:'│◀',ff:'▶│',fullscreen:'⛶'};
    const titles={undo:'Geri al · Ctrl+Z',redo:'Yinele · Ctrl+Shift+Z',split:'İmleçte böl · Ctrl+K',duplicate:'Seçili klibi çoğalt',lock:'Klip kilidini değiştir',back:'5 saniye geri',next:'5 saniye ileri',fb:'Bir kare geri · ←',ff:'Bir kare ileri · →',play:'Oynat / Duraklat · Space',stop:'Durdur',fullscreen:'Program monitörünü tam ekran aç',fit:'Timeline’a sığdır'};
    Object.entries(titles).forEach(([key,title])=>{k[key].title=title;k[key].setAttribute('aria-label',title);if(labels[key])k[key].textContent=labels[key];});
    edit.append(k.undo,k.redo,k.split,k.duplicate,k.lock);transport.append(k.back,k.fb,k.play,k.stop,k.ff,k.next,k.time);view.append(k.fit,k.zoom,k.fullscreen);
    const extra=node('details','','workspace-overflow'),summary=node('summary','⋯');summary.setAttribute('aria-label','Diğer araçlar');extra.append(summary,field('Zaman koduna git',k.seek),button('Ses miks ayarları',()=>showTool('Ses miks ayarları',audioTools)),button('Manuel AI / JSON',()=>showTool('Manuel AI / JSON',manualTools)),c.review);bar.replaceChildren(edit,transport,view,extra);
    // Root grid owns height; details open in a modal and cannot push the timeline out of view.
    const qualityButton=button('Medya kalitesi',()=>showTool('Medya kalite raporu',c.quality));
    const selectedMedia=c.media().filter(x=>x.media),motionCount=selectedMedia.filter(x=>x.motion_spec).length,total=selectedMedia.length,percent=c.data.media_metrics?.clip_ratio??(total?Math.round(motionCount/total*100):0);
    qualityButton.textContent=`Motion klip %${percent} · hedef ≤%25`;qualityButton.className=percent>25?'workspace-warning':'workspace-quality';
    const sceneMetric=c.quality.querySelector('p');if(sceneMetric)sceneMetric.textContent=`Ana kurgu motion klip oranı: ${motionCount}/${total} (%${percent}). Durum çubuğuyla aynı ölçüm; ek katmanlar hariç.`;
    c.quality.append(node('p',`Motion içeren sahne oranı: %${c.data.media_metrics?.scene_ratio??Math.round(new Set(selectedMedia.filter(x=>x.motion_spec).map(x=>x.scene_id)).size/Math.max(1,c.data.scenes.length)*100)}${c.data.media_metrics?` · Ana kurgu motion süre oranı: %${c.data.media_metrics.duration_ratio}`:''}. Sahne ve süre oranı, klip oranından farklı ölçümlerdir.`));
    const qualityFooter=node('div','','workspace-statusbar');qualityFooter.append(qualityButton,link('Medya hazırlama / eksikleri tamamla',`/projects/${c.id}/production`),status);
    if(audioTools)audioTools.remove();if(manualTools)manualTools.remove();c.quality.remove();root.append(qualityFooter);
    const info=()=>openReport('Sekans bilgileri',[node('p',`Süre: ${c.clock(c.data.duration,true)} · ${c.data.fps} fps · ${c.data.scenes.length} sahne`),node('p',`Plan: ${c.data.plan_id} · revizyon ${c.data.revision} · medya revizyonu ${c.data.stock_revision}`),link('Çıkış ve render ayarları',`/projects/${c.id}/render`)]);
    const focusEdit=()=>{if(!c.getSelected()){status.textContent='Önce timeline üzerinde bir klip seçin.';return;}selectTab('Düzenle');inspector.querySelector('input')?.focus();};
    const save=()=>{const form=inspector.querySelector('form');if(form&&!form.closest('[hidden]')){const motionSave=[...form.querySelectorAll('button[type=button]')].find(b=>b.textContent.includes('önizleme oluştur'));if(motionSave&&['Motion','JSON'].includes(activeTab))motionSave.click();else form.requestSubmit();}else status.textContent='Uygulanan işlemler proje revizyonuna otomatik kaydedilir. Kaydedilecek açık klip formu yok.';};
    const showAudio=()=>showTool('Ses miks ayarları',audioTools),showManual=()=>{showTool('Manuel AI / JSON',manualTools);};
    const shortcuts=()=>openReport('Klavye kısayolları',[node('p','Space: oynat/duraklat · J: geri sar · K: duraklat · L: oynat · ←/→: bir kare · Ctrl+K: böl · Ctrl+S: açık klip formunu kaydet · Ctrl+Z / Ctrl+Shift+Z: geri al/yinele.'),node('p','Metin ve JSON alanlarında yazarken kısayollar devreye girmez. Sahne süresini bozan serbest silme desteklenmez.')]);

    // Panel proportions and visibility persist without changing project data.
    const settings=store.get('naman-workspace-v1',{library:280,inspector:320,timeline:.4,hidden:[]});
    const panelNodes={library,preview,inspector:inspectorFrame,timeline:layout};
    function applyLayout(){const w=innerWidth;work.style.setProperty('--library-width',`${Math.max(180,Math.min(settings.library,w*.27))}px`);work.style.setProperty('--inspector-width',`${Math.max(240,Math.min(settings.inspector,w*.28))}px`);root.style.setProperty('--timeline-share',`${Math.max(.34,Math.min(.56,settings.timeline))*100}%`);Object.entries(panelNodes).forEach(([name,n])=>n.hidden=settings.hidden.includes(name));work.classList.toggle('no-library',library.hidden);work.classList.toggle('no-inspector',inspectorFrame.hidden);work.classList.toggle('no-preview',preview.hidden);root.classList.toggle('no-timeline',layout.hidden);
      const splitters=[...work.querySelectorAll('.naman-splitter')];splitters[0].hidden=library.hidden||preview.hidden;splitters[1].hidden=inspectorFrame.hidden||preview.hidden;
      const columns=[];if(!library.hidden)columns.push(preview.hidden?'minmax(0,1fr)':'var(--library-width)');if(!splitters[0].hidden)columns.push('4px');if(!preview.hidden)columns.push('minmax(0,1fr)');if(!splitters[1].hidden)columns.push('4px');if(!inspectorFrame.hidden)columns.push(preview.hidden?'minmax(0,1fr)':'var(--inspector-width)');work.style.gridTemplateColumns=columns.join(' ');
    }
    function toggle(name){settings.hidden=settings.hidden.includes(name)?settings.hidden.filter(x=>x!==name):[...settings.hidden,name];applyLayout();store.set('naman-workspace-v1',settings);}
    function reset(){Object.assign(settings,{library:280,inspector:320,timeline:.4,hidden:[]});localStorage.removeItem('naman-editor-layout');applyLayout();store.set('naman-workspace-v1',settings);}
    work.querySelectorAll('.naman-splitter').forEach((split,index)=>{split.onpointerdown=e=>{e.preventDefault();const original=e.clientX,key=index===0?'library':'inspector',size=settings[key];const move=event=>{settings[key]=size+(event.clientX-original)*(index===0?1:-1);applyLayout();};const up=()=>{removeEventListener('pointermove',move);removeEventListener('pointerup',up);store.set('naman-workspace-v1',settings);};addEventListener('pointermove',move);addEventListener('pointerup',up);};});
    const horizontal=node('div','','workspace-row-splitter');horizontal.setAttribute('role','separator');horizontal.setAttribute('aria-label','Timeline yüksekliği');horizontal.tabIndex=0;layout.before(horizontal);horizontal.onpointerdown=e=>{e.preventDefault();const move=event=>{const bounds=root.getBoundingClientRect();settings.timeline=(bounds.bottom-event.clientY-24)/(bounds.height-80);applyLayout();};const up=()=>{removeEventListener('pointermove',move);removeEventListener('pointerup',up);store.set('naman-workspace-v1',settings);};addEventListener('pointermove',move);addEventListener('pointerup',up);};horizontal.onkeydown=e=>{if(!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();settings.timeline+=e.key==='ArrowUp'?.02:-.02;applyLayout();store.set('naman-workspace-v1',settings);};applyLayout();

    const menus=[
      ['Dosya',[['Yeni proje','/new-project'],['Proje aç / Son projeler','/projects'],['Yerel medya içe aktar',()=>c.upload.click()],['Projeyi kaydet',save],['Proje ekranına dön',`/projects/${c.id}`],['Render / Dışa aktar',`/projects/${c.id}/render`]]],
      ['Düzen',[['Geri al',()=>k.undo.click()],['Yinele',()=>k.redo.click()],['Seçili öğeyi düzenle',focusEdit],['Tercihler / Tema','/settings']]],
      ['Klip',[['İmleçte böl',()=>k.split.click()],['Çoğalt',()=>k.duplicate.click()],['Taşı / Kaynak kesitini düzenle',focusEdit],['Kilitle / Kilidi aç',()=>k.lock.click()],['Medya değiştir',()=>{settings.hidden=settings.hidden.filter(x=>x!=='library');applyLayout();search.focus();}],['Klip özellikleri',()=>selectTab('Özellikler')]]],
      ['Sekans',[['Timeline’a sığdır',()=>k.fit.click()],['Zaman koduna git',()=>{extra.open=true;k.seek.focus();}],['Sekans bilgileri',info],['Bir kare geri',()=>k.fb.click()],['Bir kare ileri',()=>k.ff.click()],['Çıkış ayarları',`/projects/${c.id}/render`]]],
      ['İşaretleyiciler',[['Kalıcı işaretleyiciler bu sürümde desteklenmiyor',null]]],
      ['Grafikler ve Başlıklar',[['Proje motion / harita öğeleri',()=>{archiveTab='Motion';drawArchive();}],['Seçili animasyon',()=>selectTab('Motion')],['Metin / Altyazı',()=>selectTab('Metin')],['Animasyon JSON',()=>selectTab('JSON')],['Manuel AI görev paketi',showManual]]],
      ['Görünüm',[['Monitörü tam ekran yap',()=>k.fullscreen.click()],['Timeline’a sığdır',()=>k.fit.click()],['Çalışma düzenini sıfırla',reset],['Tema ayarları','/settings']]],
      ['Pencere',[['Medya paneli',()=>toggle('library')],['Program monitörü',()=>toggle('preview')],['Özellikler paneli',()=>toggle('inspector')],['Timeline',()=>toggle('timeline')],['Ses araçları',showAudio],['İşlem / Kalite raporu',()=>showTool('Medya kalite raporu',c.quality)]]],
      ['Yardım',[['Klavye kısayolları',shortcuts],['NAMAN kullanımı',()=>openReport('NAMAN kullanımı',[node('p','Medyayı arşivden seçin veya kilitsiz Görüntü yuvasına sürükleyin. Klipleri timeline üzerinde seçip sağ panelde düzenleyin. Uygulanan işlemler revizyona yazılır; final MP4 için ayrıca Dışa Aktar kullanın.')])],['Sistem tanılama','/diagnostics'],['Hata / İşlem raporu',()=>openReport('İşlem durumu',[node('pre',status.textContent),button('Raporu kopyala',()=>navigator.clipboard.writeText(status.textContent))])]]]
    ];
    document.querySelector('.workspace-menubar')?.remove();
    const menubar=node('nav','','workspace-menubar');menubar.setAttribute('aria-label','Ana menü');
    menus.forEach(([title,entries])=>{
      const details=node('details'),head=node('summary',title),popup=node('div','','workspace-menu');head.setAttribute('aria-label',title+' menüsü');
      entries.forEach(([label,action])=>{const entry=typeof action==='string'?link(label,action):button(label,()=>{action?.();details.open=false;head.focus();});if(action===null){entry.disabled=true;entry.title='Bu sürümde desteklenmiyor';}popup.append(entry);});details.append(head,popup);menubar.append(details);
      details.addEventListener('toggle',()=>{if(!details.open)return;[...menubar.children].filter(d=>d!==details).forEach(d=>d.open=false);const b=popup.getBoundingClientRect();popup.style.left=b.right>innerWidth?`${Math.min(0,innerWidth-b.right-8)}px`:'0';});
    });root.before(menubar);
    const clickAway=e=>{if(!menubar.contains(e.target))menubar.querySelectorAll('details').forEach(d=>d.open=false);};document.addEventListener('click',clickAway);
    menubar.onkeydown=e=>{const d=e.target.closest('details'),summaries=[...menubar.querySelectorAll('summary')];if(e.key==='Escape'){d.open=false;d.querySelector('summary').focus();}if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const i=[...menubar.children].indexOf(d),next=menubar.children[(i+(e.key==='ArrowRight'?1:-1)+menus.length)%menus.length];d.open=false;next.open=true;next.querySelector('summary').focus();}if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();d.open=true;const targets=[...d.querySelectorAll('a,button:not(:disabled)')],i=targets.indexOf(document.activeElement);targets[(i+(e.key==='ArrowDown'?1:-1)+targets.length)%targets.length]?.focus();}};

    let reverseTimer;
    stopReverse=()=>{clearInterval(reverseTimer);reverseTimer=null;};
    const reverse=()=>{c.pause();stopReverse();reverseTimer=setInterval(()=>{if(c.getTime()<=0){stopReverse();return;}c.seekTo(c.getTime()-.1);},100);status.textContent='Geri sarılıyor · durdurmak için K';};
    const keydown=e=>{
      if(e.target.closest('input,textarea,select,[contenteditable=true]')||report.open)return;
      const ctrl=e.ctrlKey||e.metaKey,key=e.key.toLowerCase();let action;
      if(ctrl&&key==='z')action=()=>e.shiftKey?k.redo.click():k.undo.click();
      else if(ctrl&&key==='s')action=save;else if(ctrl&&key==='k')action=()=>k.split.click();
      else if(!ctrl&&e.code==='Space')action=()=>{stopReverse();k.play.click();};
      else if(!ctrl&&key==='arrowleft')action=()=>{stopReverse();k.fb.click();};else if(!ctrl&&key==='arrowright')action=()=>{stopReverse();k.ff.click();};
      else if(!ctrl&&key==='j')action=reverse;else if(!ctrl&&key==='k')action=()=>{stopReverse();c.pause();};else if(!ctrl&&key==='l')action=()=>{stopReverse();if(k.play.textContent.includes('Oynat'))k.play.click();};
      if(action){e.preventDefault();action();}
    };addEventListener('keydown',keydown);k.stop.addEventListener('click',stopReverse);k.play.addEventListener('click',stopReverse);
    report.addEventListener('click',e=>{if(e.target===report)report.close();});
    const resize=()=>applyLayout();addEventListener('resize',resize);
    cleanup=()=>{stopReverse();tabObserver?.disconnect();removeEventListener('keydown',keydown);removeEventListener('resize',resize);document.removeEventListener('click',clickAway);menubar.remove();report.close();};
    c.onDispose(cleanup);
    window.NAMANAdvanced?.mount(c);
    // Reapply real waveform when re-rendering after a saved edit.
    paintWaveform(c.data.tracks.audio[0]?.waveform||[]);
  }

  function paintWaveform(peaks){
    if(!peaks?.length||!ctx)return;
    ctx.timeline.querySelectorAll('.naman-clip[data-track=audio]').forEach(clip=>{
      clip.querySelector('canvas')?.remove();const canvas=node('canvas');canvas.width=1024;canvas.height=30;canvas.className='workspace-waveform';const paint=canvas.getContext('2d');paint.fillStyle='#70dbc0';
      peaks.forEach((p,i)=>paint.fillRect(i/peaks.length*1024,15-p*14,Math.max(1,1024/peaks.length),p*28));clip.append(canvas);
    });
  }
})();
