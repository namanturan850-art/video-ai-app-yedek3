/* Same selector in Settings and Render. Tokens never enter previews or the DOM. */
window.createMapboxStylePicker = function(host, options = {}) {
  host.classList.add('mapbox-style-picker');
  const node = (tag, text, cls) => { const n = document.createElement(tag); if(text)n.textContent=text;if(cls)n.className=cls;return n; };
  const heading=node('h3','Mapbox harita stilini seç'),status=node('p','Stiller yükleniyor…','note');
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const grid=node('div','','mapbox-style-grid');grid.setAttribute('aria-label','Mapbox harita stilleri');
  const previews=node('button','Önizlemeleri yükle','secondary');previews.type='button';
  const note=node('p','Seçim otomatik kaydedilir. Harita kaynağı Mapbox olduğunda yeni önizlemeler ve videolar bu stili kullanır. Önizlemeleri yüklemek Mapbox kullanımına sayılır.','note');
  const link=node('input'),name=node('input'),add=node('button','Studio stilini ekle','secondary');
  link.type='text';link.placeholder='mapbox://styles/kullanıcı/stil';link.maxLength=220;link.setAttribute('aria-label','Mapbox Studio Style URL');
  name.type='text';name.placeholder='Stilin adı (isteğe bağlı)';name.maxLength=80;name.setAttribute('aria-label','Özel stilin adı');
  for(const input of [link,name]){input.dataset.transient='true';input.autocomplete='off';}
  add.type='button';
  host.append(heading,status,grid,previews,note,node('h4','Mapbox Studio’daki kendi stilini ekle'),
    node('p','Studio → Share → Style URL bağlantısını yapıştırın. Stil Mapbox’ta yayımlanmış olmalı. Bu ekran statik haritalar kullanır; Studio’daki canlı 3B görünümün aynısını vaat etmez.','note'),link,name,add);
  let state=null,builtins=[],busy=false;const images=new Map();
  async function json(url,method='GET',body){
    const response=await fetch(url,{method,cache:'no-store',headers:{'Content-Type':'application/json','X-AI-Video-Studio':'settings'},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'Mapbox işlemi tamamlanamadı.');return data;
  }
  function locked(){
    if(busy)return true;
    if(options.isDirty?.()){status.textContent='Önce Mapbox bölümündeki Kaydet düğmesine basın.';return true;}
    return false;
  }
  function setBusy(value){busy=value;for(const n of host.querySelectorAll('button,input'))n.disabled=value;}
  function draw(config){
    state=config;
    if(config.styles)builtins=config.styles.filter(s=>!s.custom);
    const remaining=new Set([...builtins,...(config.custom_styles||[])].map(s=>s.uri));
    for(const [uri,url] of images){if(!remaining.has(uri)){URL.revokeObjectURL(url);images.delete(uri);}}
    const styles=[...builtins,...(config.custom_styles||[]).map(s=>({...s,custom:true}))];
    grid.replaceChildren();
    for(const s of styles){
      const card=node('div','','mapbox-style-item'),button=node('button','','mapbox-style-card');button.type='button';button.dataset.style=s.uri;
      const selected=s.uri===(config.selected_style||'');button.setAttribute('aria-pressed',String(selected));
      const image=node('img');image.alt=`${s.name} harita önizlemesi`;image.width=300;image.height=170;
      image.hidden=!images.has(s.uri);if(!image.hidden)image.src=images.get(s.uri);
      const placeholder=node('span','Önizleme yüklenmedi','mapbox-style-placeholder');placeholder.hidden=!image.hidden;
      button.append(image,placeholder,node('span',s.name));
      button.addEventListener('click',()=>save({selected_style:s.uri},'Harita stili kaydedildi.',true));
      card.append(button);
      if(s.custom){
        const remove=node('button','Stili kaldır','secondary');remove.type='button';remove.setAttribute('aria-label',`${s.name} stilini kaldır`);
        remove.addEventListener('click',()=>{const body={custom_styles:(state.custom_styles||[]).filter(x=>x.uri!==s.uri)};if(state.selected_style===s.uri)body.selected_style='';save(body,'Özel stil kaldırıldı.');});card.append(remove);
      }
      grid.append(card);
    }
    status.textContent=config.has_api_key?'Stiller hazır. Kullanılacak haritaya tıklayın.':'Stil seçebilirsiniz; haritaları almak için önce Mapbox anahtarınızı kaydedin.';
  }
  async function save(body,message,selected=false){
    if(locked())return;setBusy(true);status.textContent='Harita stili kaydediliyor…';
    try{const settings=await json('/api/settings/mapbox','PUT',body);draw(settings.mapbox);options.onSettings?.(settings);if(selected)await options.onSelected?.();status.textContent=message;}
    catch(e){status.textContent=e.message;}finally{setBusy(false);}
  }
  add.addEventListener('click',()=>{
    if(!state||locked())return;
    const uri=link.value.trim();
    if(!/^mapbox:\/\/styles\/[A-Za-z0-9_-]{1,64}\/[A-Za-z0-9_-]{1,100}$/.test(uri)){status.textContent='Studio → Share → Style URL bağlantısını girin (mapbox://styles/kullanıcı/stil).';return;}
    if([...builtins,...(state.custom_styles||[])].some(s=>s.uri===uri)){status.textContent='Bu stil zaten listede; kartına tıklayarak seçin.';return;}
    save({custom_styles:[...(state.custom_styles||[]),{uri,name:name.value.trim()||'Studio stilim'}],selected_style:uri},'Studio stili eklendi ve seçildi.',true);
  });
  previews.addEventListener('click',async()=>{
    if(!state||locked())return;if(!state.has_api_key){status.textContent='Önce Mapbox API anahtarını kaydedin.';return;}
    setBusy(true);let failed=0;const cards=[...grid.querySelectorAll('[data-style]')];
    for(let i=0;i<cards.length;i++){
      const card=cards[i],uri=card.dataset.style;if(images.has(uri))continue;
      status.textContent=`Harita önizlemesi alınıyor… ${i+1}/${cards.length}`;
      try{const r=await fetch('/api/settings/mapbox/style-preview',{method:'POST',headers:{'Content-Type':'application/json','X-AI-Video-Studio':'settings'},body:JSON.stringify({uri})});
        if(!r.ok){const d=await r.json();throw new Error(d.message||'Önizleme alınamadı.');}
        if(!(r.headers.get('content-type')||'').startsWith('image/'))throw new Error('Harita önizlemesi resim olarak alınamadı.');
        const url=URL.createObjectURL(await r.blob());images.set(uri,url);const image=card.querySelector('img');image.src=url;image.hidden=false;card.querySelector('.mapbox-style-placeholder').hidden=true;
      }catch(e){failed++;card.title=e.message;}
    }
    status.textContent=failed?`${failed} önizleme alınamadı. Anahtar izinlerini ve bağlantıyı kontrol edin; stil kartındaki açıklamaya bakın.`:'Harita önizlemeleri hazır.';setBusy(false);
  });
  async function load(){try{draw(await json('/api/settings/mapbox/styles'));}catch(e){status.textContent=e.message;}}
  load();return {draw,load};
};
