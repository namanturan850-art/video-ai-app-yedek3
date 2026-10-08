/* Credentials live only in blank password inputs until explicitly saved. */
if (window.location.pathname === '/settings') {
  const root = document.querySelector('#settings-content');
  const sections = document.querySelector('#settings-sections');
  const pageStatus = document.querySelector('#settings-status');
  const reload = document.querySelector('#settings-reload');
  root.hidden = false;
  const definitions = [
    {id: 'general', title: 'Genel', description: 'Varsayılan içerik dilini seçin. İçerik üretimi sonraki aşamalarda eklenecek.', fields: [{name: 'content_language', label: 'Varsayılan içerik dili', type: 'select'}]},
    {id: 'ollama', title: 'Ollama', description: 'İsteğe bağlı yerel senaryo hizmeti. Ollama kullanmayacaksanız model adını boş bırakın. Testten önce ayarları kaydedin.', fields: [{name: 'base_url', label: 'Yerel adres (Base URL)', type: 'url'}, {name: 'model', label: 'Bilgisayarınızda kurulu modelin adı', type: 'text'}], test: true},
    {id: 'openai', title: 'OpenAI (isteğe bağlı)', description: 'Etkinleştir seçimini açın, anahtarınızı ve Chat Completions modelini Kaydet deyin. Bağlantı testi resmi API’den model erişimini kontrol eder; metin üretmez. Üretim kota/bakiye kontrolü ayrıca yapılır.', fields: [{name: 'enabled', label: 'Etkinleştir', type: 'checkbox'}, {name: 'model', label: 'Model adı', type: 'text'}], secret: true, test: true},
    {id: 'gemini', title: 'Gemini (isteğe bağlı)', description: 'Google Gemini Developer API anahtarınızı kaydedin. Gemini Plus / Google AI Pro web aboneliği API erişimi yerine geçmez. Kullanmak zorunda değilsiniz.', fields: [{name: 'model', label: 'Model (API listesinden seçin)', type: 'select'}], secret: true, test: true},
    {id: 'pexels', title: 'Pexels', description: 'Resmî Pexels API ile video ve fotoğraf arayın. Anahtarı önce Kaydet deyin, ardından Bağlantıyı Test Et düğmesine basın.', fields: [], secret: true, test: true},
    {id: 'pixabay', title: 'Pixabay', description: 'Resmî Pixabay API ile video ve görsel arayın. Anahtarı önce Kaydet deyin, ardından Bağlantıyı Test Et düğmesine basın.', fields: [], secret: true, test: true},
    {id:'ai33',title:'AI33 / OpenSpeaker',description:'Anahtarınızı Kaydet, ardından Bağlantıyı Test Et. Ses sağlayıcısını kaydedip Sesleri Getir deyin. Bağlantı testi ücretli ses üretmez.',fields:[{name:'voice_provider',label:'Ses sağlayıcısı',type:'select',choices:[['elevenlabs','ElevenLabs'],['minimax','MiniMax'],['clone','Mevcut klon sesler'],['edge','Microsoft Edge'],['vbee','Vbee'],['fishaudio','Fish Audio']]},{name:'voice_id',label:'Ses',type:'select',choices:[['','Önce Sesleri Getir düğmesine basın']]},{name:'speed',label:'Hız (0,5–1,5)',type:'number'},{name:'base_url',label:'Eski kayıtlı Base URL (uyumluluk için korunur)',type:'url',advanced:true},{name:'model',label:'Eski model alanı (kullanılmaz)',type:'text',advanced:true}],secret:true,test:true}
  ];
  const forms = new Map();
  let loaded = false;
  let ttsVoices=[];
  const ttsBrowser=createAI33VoiceBrowser(body=>request('/api/settings/ai33/voices','POST',body));
  // Provider preview requests must not send the local Settings page as referrer.
  const previewReferrer=document.createElement('meta');previewReferrer.name='referrer';previewReferrer.content='no-referrer';document.head.append(previewReferrer);

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function addField(form, provider, field) {
    const wrapper = element('div', '', 'setting-field');
    const id = `${provider}-${field.name}`;
    const label = element('label', field.label);
    label.htmlFor = id;
    const input = document.createElement(field.type === 'select' ? 'select' : 'input');
    input.id = id;
    input.name = field.name;
    if (field.type !== 'select') input.type = field.type;
    if (field.type === 'select') {
      for (const [value, title] of (field.choices || (provider === 'gemini' ? [['', 'Önce Modelleri Getir düğmesine basın']] : [['de', 'Almanca'], ['es', 'İspanyolca'], ['en', 'İngilizce'], ['fr', 'Fransızca'], ['tr', 'Türkçe']]))) {
        const option = element('option', title);
        option.value = value;
        input.append(option);
      }
    } else if (field.type !== 'checkbox') {
      input.maxLength = field.name === 'api_key' ? 4096 : field.type === 'url' ? 500 : 150;
      input.autocomplete = field.name === 'api_key' ? 'new-password' : 'off';
      input.spellcheck = false;
    }
    if(provider==='ai33'&&field.type==='number'){input.min='.5';input.max='1.5';input.step='.05';}
    if(field.advanced)input.readOnly=true;
    wrapper.append(label, input);
    if(field.advanced){let advanced=form.querySelector('[data-role=advanced]');if(!advanced){advanced=element('details');advanced.dataset.role='advanced';advanced.append(element('summary','Gelişmiş / önceki kayıtlar'),element('p','Doğrulanmış API adresi https://api.ai33.pro kullanılır. Önceki adres ve model kayıtları korunur; kayıtlı adres ağ hedefi olarak kullanılmaz.','note'));form.append(advanced);}advanced.append(wrapper);}else form.append(wrapper);
  }
  for (const definition of definitions) {
    const form = element('form', '', 'settings-panel');
    form.id = `settings-${definition.id}`;
    form.autocomplete = 'off';
    form.append(element('h2', definition.title), element('p', definition.description, 'note'));
    const status = element('p', 'Yükleniyor…', 'provider-status');
    status.dataset.role = 'provider-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    form.append(status);
    for (const field of definition.fields) addField(form, definition.id, field);
    if (definition.secret) {
      addField(form, definition.id, {name: 'api_key', label: 'API anahtarı', type: 'password'});
      const keyInfo = element('p', '', 'note');
      keyInfo.dataset.role = 'key-info';
      form.append(keyInfo, element('p', 'Boş bırakırsanız kayıtlı anahtar korunur. Değiştirmek için yeni anahtarı girin. Temizle bu bölümdeki anahtarı ve ayarları siler.', 'note'));
    }
    const actions = element('div', '', 'settings-actions');
    const save = element('button', 'Kaydet');
    save.type = 'submit';
    const clear = element('button', 'Temizle', 'secondary');
    clear.type = 'button';
    clear.addEventListener('click', () => {
      if (window.confirm(`${definition.title} bölümündeki kayıtlı bilgiler silinsin mi?`)) {
        perform(definition, 'DELETE');
      }
    });
    actions.append(save, clear);
    if (definition.id !== 'general') {
      const test = element('button', 'Bağlantıyı Test Et', 'secondary');
      test.type = 'button';
      test.dataset.role = 'test';
      test.disabled = !definition.test;
      test.addEventListener('click', () => {
        if (form.dataset.dirty === 'true') {
          status.textContent = 'Önce Kaydet düğmesine basın; test kayıtlı bilgileri kullanır.';
        } else perform(definition, 'POST');
      });
      actions.append(test);
    }
    if (definition.id === 'gemini') {
      const models = element('button', 'Modelleri Getir', 'secondary'); models.type = 'button';
      models.addEventListener('click', async () => {
        if (form.dataset.dirty === 'true') { status.textContent = 'Önce Kaydet düğmesine basın; model listesi kayıtlı anahtarı kullanır.'; return; }
        setBusy(form, true, definition); status.textContent = 'Gemini modelleri alınıyor…';
        try {
          const result = await request('/api/settings/gemini/models', 'POST');
          showSettings(result.settings);
          const data = result.settings.gemini;
          status.textContent = data.model && !data.model_verified ? `Hata · ${data.message}` : 'Model listesi hazır. Model alanından seçip Kaydet düğmesine basın.';
        } catch (error) { status.textContent = `Hata · ${error.message}`; }
        finally { setBusy(form, false, definition); }
      });
      actions.append(models);
      form.append(element('p', 'Önce anahtarı Kaydet, sonra Modelleri Getir. Listeden model seçip tekrar Kaydet. Bağlantı testi senaryo üretmez; internet durumuna göre 60 saniyeye kadar sürebilir.', 'note'));
    }
    if(definition.id==='ai33'){
      const browserArea=element('section','','setting-field');browserArea.append(element('h3','Ses listesi'));
      const searchLabel=element('label','Ses adına göre ara');searchLabel.htmlFor='ai33-voice-search';
      const voiceSearch=element('input');voiceSearch.id='ai33-voice-search';voiceSearch.type='search';voiceSearch.placeholder='Ses adı (isteğe bağlı)';voiceSearch.maxLength=200;voiceSearch.dataset.transient='true';
      const pages=element('div','','settings-actions');
      const indicator=element('p','Sayfa 1 · Henüz ses alınmadı.','note');indicator.dataset.role='voice-page';indicator.setAttribute('aria-live','polite');
      const voices=element('button','Sesleri Getir');voices.type='button';
      const previous=element('button','Önceki Sayfa','secondary');previous.type='button';previous.dataset.role='voice-previous';
      const next=element('button','Sonraki Sayfa','secondary');next.type='button';next.dataset.role='voice-next';
      const more=element('button','Daha Fazla Ses Yükle','secondary');more.type='button';more.dataset.role='voice-more';
      const all=element('button','Tüm Sesleri Getir','secondary');all.type='button';
      async function fetchVoices(mode){
        if(form.dataset.dirty==='true'){status.textContent='Önce Kaydet düğmesine basın; ses listesi kayıtlı anahtarı kullanır.';return;}
        const provider=form.elements.namedItem('voice_provider').value,search=voiceSearch.value.trim();
        if(ttsBrowser.state.provider!==provider||ttsBrowser.state.search!==search)ttsBrowser.reset(provider,search);
        setBusy(form,true,definition);status.textContent='AI33 sesleri alınıyor…';
        try{
          const display=result=>{showSettings(result.settings);refreshTTSBrowser();status.textContent=`Sayfa ${ttsBrowser.state.page} alındı · ${ttsBrowser.state.voices.length} ses listede.`;};
          if(mode==='all')await ttsBrowser.all(display);
          else {const page=mode==='previous'?Math.max(1,ttsBrowser.state.page-1):mode==='next'||mode==='more'?ttsBrowser.state.page+1:1;display(await ttsBrowser.page(page,mode==='more'));}
          status.textContent=ttsBrowser.state.voices.length?'Ses listesi hazır. Listeden ses seçip Kaydet deyin.':'Bu sayfada ses bulunamadı. Önceki sayfaya dönün veya aramayı değiştirin.';
        }
        catch(error){status.textContent=`Hata · ${error.message}`;const diag=form.querySelector('[data-role=tts-diagnostic]');diag.textContent=error.diagnostic?JSON.stringify(error.diagnostic,null,2):'';}
        finally{setBusy(form,false,definition);}
      }
      voices.addEventListener('click',()=>fetchVoices('first'));previous.addEventListener('click',()=>fetchVoices('previous'));
      next.addEventListener('click',()=>fetchVoices('next'));more.addEventListener('click',()=>fetchVoices('more'));all.addEventListener('click',()=>fetchVoices('all'));
      voiceSearch.addEventListener('input',()=>{ttsBrowser.reset(form.elements.namedItem('voice_provider').value,voiceSearch.value.trim());refreshTTSBrowser();});
      pages.append(previous,next,more,all);browserArea.append(searchLabel,voiceSearch,voices,indicator,pages,element('p','Her sayfada en fazla 30 ses. Tüm Sesleri Getir en fazla 10 sayfa / 300 ses yükler; boş sayfada durur. Sağlayıcı ve arama değişince sayfa 1’e dönülür.','note'));
      form.insertBefore(browserArea,form.elements.namedItem('voice_id').closest('.setting-field'));
      const taskArea=element('section','','setting-field');taskArea.append(element('h3','Mevcut Görevi İncele'));
      const taskLabel=element('label','Task ID');taskLabel.htmlFor='ai33-task-id';
      const taskID=element('input');taskID.id='ai33-task-id';taskID.type='text';taskID.maxLength=150;taskID.autocomplete='off';taskID.spellcheck=false;taskID.dataset.transient='true';
      const inspect=element('button','Görevi İncele');inspect.type='button';
      async function inspectExisting(historyOnly){
        if(form.dataset.dirty==='true'){status.textContent='Önce Kaydet deyin; tanılama kayıtlı anahtarı kullanır.';return;}
        const id=taskID.value.trim();
        if(!historyOnly&&!/^[A-Za-z0-9_-]{1,150}$/.test(id)){status.textContent='Geçerli bir Task ID girin. Yalnız harf, rakam, tire ve alt çizgi kullanılabilir (en fazla 150 karakter).';return;}
        setBusy(form,true,definition);status.textContent='Mevcut görev salt okunur inceleniyor…';
        try{const result=await request(historyOnly?'/api/settings/ai33/tasks/diagnose':'/api/settings/ai33/task/diagnose','POST',historyOnly?{}:{task_id:id});form.querySelector('[data-role=tts-diagnostic]').textContent=JSON.stringify(result.diagnostic,null,2);status.textContent=result.message;}
        catch(error){status.textContent=`Hata · ${error.message}`;form.querySelector('[data-role=tts-diagnostic]').textContent=error.diagnostic?JSON.stringify(error.diagnostic,null,2):'';}
        finally{setBusy(form,false,definition);}
      }
      inspect.addEventListener('click',()=>inspectExisting(false));
      const history=element('button','Görev Geçmişini İncele');history.type='button';
      history.addEventListener('click',()=>inspectExisting(true));const taskActions=element('div','','settings-actions');taskActions.append(inspect,history);taskArea.append(taskLabel,taskID,taskActions,element('p','AI33 sitesinde zaten oluşturduğunuz görevin kimliğini yapıştırın. Yalnız GET ile incelenir; yeni ücretli görev oluşturulmaz. Sonuçta sadece alan adları/türleri ve güvenli durum/tür değerleri gösterilir.','note'));
      const listen=element('button','Önizlemeyi Dinle');listen.type='button';listen.dataset.role='voice-preview';listen.hidden=true;
      const audio=element('audio');audio.controls=true;audio.preload='none';audio.crossOrigin='anonymous';audio.hidden=true;audio.dataset.role='voice-audio';
      const previewStatus=element('p','','note');previewStatus.dataset.role='voice-preview-status';
      listen.addEventListener('click',async()=>{
        const selected=selectedVoice();if(!selected?.preview_url)return;
        audio.src=selected.preview_url;audio.hidden=false;
        previewStatus.textContent='Sağlayıcının hazır örnek sesi. Yeni TTS görevi oluşturulmaz.';
        try{await audio.play();}catch{previewStatus.textContent='Örnek ses açılamadı. Sağlayıcının önizleme adresi erişilebilir olmayabilir; tekrar deneyin.';}
      });
      audio.addEventListener('error',()=>{previewStatus.textContent='Örnek ses açılamadı. Sağlayıcının önizleme adresi erişilebilir olmayabilir; tekrar deneyin.';});
      const info=element('details');info.dataset.role='voice-info';info.append(element('summary','Seçilen sesin bilgileri'));const infoBody=element('div');infoBody.dataset.role='voice-info-body';info.append(infoBody);
      form.append(listen,audio,previewStatus,info);
      form.elements.namedItem('voice_id').addEventListener('change',showSelectedVoice);
      form.elements.namedItem('voice_provider').addEventListener('change',()=>{ttsVoices=[];voiceSearch.value='';ttsBrowser.reset(form.elements.namedItem('voice_provider').value);populateTTSVoices('');showSelectedVoice();refreshTTSBrowser();});
      const docs=element('p','','note');docs.dataset.role='tts-documentation';form.append(docs);
      const credit=element('p','','note');credit.dataset.role='tts-credits';form.append(credit);
      const diag=element('pre');diag.dataset.role='tts-diagnostic';taskArea.append(diag);form.append(taskArea);
    }
    form.append(actions);
    if (definition.test === false) form.append(element('p', definition.id === 'ai33' ? 'AI33 API belgeleri gerekli' : definition.id === 'openai' ? 'Bu ekranda ayrı bağlantı testi yoktur. Senaryo ekranında üretim deneyebilirsiniz.' : 'API belgeleri gerekli. Bağlantı testi bu aşamada kullanılamaz.', 'note'));
    form.addEventListener('input', event => { if(!event.target.dataset.transient)form.dataset.dirty = 'true'; });
    form.addEventListener('submit', event => { event.preventDefault(); perform(definition, 'PUT'); });
    forms.set(definition.id, form);
    sections.append(form);
  }
  const ffmpeg = element('section', '', 'settings-panel');
  ffmpeg.id = 'settings-ffmpeg';
  ffmpeg.append(element('h2', 'FFmpeg'), element('p', 'Otomatik algılanır. Ayarları kullanmak için kurmanız gerekmez.', 'note'));
  const ffmpegStatus = element('p', 'Kontrol ediliyor…', 'provider-status');
  ffmpegStatus.setAttribute('role', 'status');
  ffmpegStatus.setAttribute('aria-live', 'polite');
  const ffmpegPath = element('p', '', 'executable-path');
  const ffmpegButton = element('button', 'Bağlantıyı Test Et');
  ffmpegButton.type = 'button';
  ffmpegButton.addEventListener('click', async () => {
    ffmpegButton.disabled = true;
    ffmpegStatus.textContent = 'FFmpeg kontrol ediliyor…';
    try {
      const result = await request('/api/settings/ffmpeg/test', 'POST');
      showSettings(result.settings);
      ffmpegStatus.textContent = `${result.result.status} · ${result.result.message}`;
    } catch (error) { ffmpegStatus.textContent = error.message; }
    finally { ffmpegButton.disabled = false; }
  });
  ffmpeg.append(ffmpegStatus, ffmpegPath, ffmpegButton);
  const youtube = element('section', '', 'settings-panel');
  youtube.id = 'settings-youtube';
  youtube.append(element('h2', 'YouTube'), element('p', 'Daha sonra', 'provider-status'), element('p', 'YouTube bağlantısı ve yükleme sonraki aşamalarda ele alınacak.', 'note'));
  sections.append(ffmpeg, youtube);

  function setBusy(form, busy, definition) {
    form.dataset.busy=String(busy);
    for (const control of form.querySelectorAll('input, select, button')) {
      control.disabled = busy || (control.dataset.role === 'test' && !definition.test) ||
        (definition.id === 'gemini' && control.name === 'model' && control.options.length === 1);
    }
    if(definition.id==='ai33')refreshTTSBrowser();
  }
  function refreshTTSBrowser(){
    const form=forms.get('ai33');if(!form)return;
    const state=ttsBrowser.state,busy=form.dataset.busy==='true';
    form.querySelector('[data-role=voice-page]').textContent=`Sayfa ${state.page} · ${state.initialized?`${state.voices.length} ses listede${state.exhausted?' · Liste sonu / 10 sayfa sınırı':''}`:'Sesleri Getir ile başlayın.'}`;
    form.querySelector('[data-role=voice-previous]').disabled=busy||state.page<=1;
    for(const role of ['voice-next','voice-more'])form.querySelector(`[data-role=${role}]`).disabled=busy||!state.initialized||state.exhausted;
  }
  function selectedVoice(){const form=forms.get('ai33');return ttsVoices.find(v=>v.provider===form.elements.namedItem('voice_provider').value&&v.voice_id===form.elements.namedItem('voice_id').value);}
  function populateTTSVoices(selected){
    const form=forms.get('ai33'),choices=form.elements.namedItem('voice_id');choices.replaceChildren();
    const empty=element('option','Sesleri Getir ile listeden bir ses seçin');empty.value='';choices.append(empty);
    const visible=ttsBrowser.state.initialized?ttsBrowser.state.voices:ttsVoices;
    for(const voice of visible.filter(v=>v.provider===form.elements.namedItem('voice_provider').value)){const opt=element('option',voice.display_name||voice.voice_id);opt.value=voice.voice_id;choices.append(opt);}
    if(selected&&!Array.from(choices.options).some(o=>o.value===selected)){const saved=ttsVoices.find(v=>v.provider===form.elements.namedItem('voice_provider').value&&v.voice_id===selected);const legacy=element('option',saved?`${saved.display_name} (seçili ses)`:'Önceki kayıtlı ses (henüz doğrulanmadı)');legacy.value=selected;choices.append(legacy);}
    choices.value=selected||'';
  }
  function showSelectedVoice(){
    const form=forms.get('ai33'),voice=selectedVoice(),audio=form.querySelector('[data-role=voice-audio]');
    if(audio.dataset.voice!==voice?.voice_id){audio.pause();audio.removeAttribute('src');audio.hidden=true;audio.dataset.voice=voice?.voice_id||'';form.querySelector('[data-role=voice-preview-status]').textContent='';}
    form.querySelector('[data-role=voice-preview]').hidden=!voice?.preview_url;
    const info=form.querySelector('[data-role=voice-info-body]');info.replaceChildren();
    if(voice){for(const [field,label] of [['description','Açıklama'],['language','Dil'],['locale','Bölge'],['gender','Cinsiyet'],['age','Yaş'],['accent','Aksan'],['category','Kategori'],['use_cases','Kullanım alanları'],['descriptives','Tanımlamalar'],['tags','Etiketler'],['languages','Diller']]){
      const value=voice[field];if(value&&(!Array.isArray(value)||value.length))info.append(element('p',`${label}: ${Array.isArray(value)?value.map(v=>typeof v==='string'?v:JSON.stringify(v)).join(', '):value}`));
    }}form.querySelector('[data-role=voice-info]').hidden=!voice;
  }
  function showSettings(settings, resetSection = null) {
    for (const definition of definitions) {
      const form = forms.get(definition.id);
      const data = settings[definition.id];
      const reset = !loaded || resetSection === definition.id;
      const previousVoice=definition.id==='ai33'?form.elements.namedItem('voice_id').value:'';
      if (definition.id === 'gemini') showGeminiModels(data.models, reset ? data.model : form.elements.namedItem('model').value);
      if (reset) {
        for (const field of definition.fields) {
          const input = form.elements.namedItem(field.name);
          if (field.type === 'checkbox') input.checked = data[field.name];
          else input.value = data[field.name] || '';
        }
        if (definition.secret) form.elements.namedItem('api_key').value = '';
        form.dataset.dirty = 'false';
      }
      if(definition.id==='ai33'){if(!loaded||(reset&&ttsBrowser.state.provider!==data.voice_provider))ttsBrowser.reset(data.voice_provider);ttsVoices=data.voices||[];populateTTSVoices(reset?data.voice_id:previousVoice);showSelectedVoice();refreshTTSBrowser();form.querySelector('[data-role=tts-documentation]').textContent=data.documentation_message||'';if(reset)form.querySelector('[data-role=tts-diagnostic]').textContent='';}
      form.querySelector('[data-role="provider-status"]').textContent = definition.id === 'general' ? 'Tercihler hazır.' : `${data.status} · ${data.message}`;
      if (definition.secret) form.querySelector('[data-role="key-info"]').textContent = data.has_api_key ? `Kayıtlı anahtar: ${data.masked_api_key}` : 'Henüz anahtar kaydedilmedi.';
    }
    ffmpegStatus.textContent = settings.ffmpeg.message;
    ffmpegPath.textContent = settings.ffmpeg.executable_path ? `Algılanan dosya: ${settings.ffmpeg.executable_path}` : '';
    loaded = true;
  }
  function showGeminiModels(models, selected) {
    const choices = forms.get('gemini').elements.namedItem('model'); choices.replaceChildren();
    const empty = element('option', models.length ? 'Bir model seçin' : 'Önce Modelleri Getir düğmesine basın'); empty.value = ''; choices.append(empty);
    for (const model of models) { const option = element('option', model); option.value = model; choices.append(option); }
    choices.value = models.includes(selected) ? selected : '';
  }
  async function request(url, method = 'GET', body) {
    return settingsRequest(url, method, body);
  }
  async function perform(definition, method) {
    const form = forms.get(definition.id);
    const status = form.querySelector('[data-role="provider-status"]');
    let body;
    if (method === 'PUT') {
      body = {};
      for (const field of definition.fields) {
        const input = form.elements.namedItem(field.name);
        body[field.name] = field.type === 'checkbox' ? input.checked : field.type==='number'?Number(input.value):input.value;
      }
      if (definition.secret && form.elements.namedItem('api_key').value) body.api_key = form.elements.namedItem('api_key').value;
      if (definition.id === 'gemini' && body.api_key) body.model = ''; // Save a new key before discovering its models.
    }
    setBusy(form, true, definition);
    status.textContent = method === 'POST' ? 'Bağlantı kontrol ediliyor…' : 'Bilgiler kaydediliyor…';
    try {
      const result = await request(`/api/settings/${definition.id}${method === 'POST' ? '/test' : ''}`, method, body);
      if(definition.id==='ai33'&&(method==='DELETE'||body?.api_key))ttsBrowser.reset((result.settings||result).ai33.voice_provider);
      showSettings(result.settings || result, method === 'POST' ? null : definition.id);
      if (method === 'POST') {status.textContent = `${result.result.status} · ${result.result.message}`;if(definition.id==='ai33')form.querySelector('[data-role=tts-credits]').textContent=result.result.credits_message||'';}
      pageStatus.textContent = method === 'POST' ? 'Bağlantı kontrolü tamamlandı.' : method === 'DELETE' ? 'Bu bölümdeki kayıtlı bilgiler temizlendi.' : 'Ayarlar kaydedildi. Anahtarlar yalnızca bu bilgisayarda saklanır.';
    } catch (error) { status.textContent = `Hata · ${error.message}`; }
    finally { setBusy(form, false, definition); }
  }
  async function load() {
    reload.disabled = true;
    for (const definition of definitions) setBusy(forms.get(definition.id), true, definition);
    pageStatus.textContent = 'Ayarlar yükleniyor…';
    try {
      const data = await request('/api/settings');
      loaded = false;
      showSettings(data);
      pageStatus.textContent = 'Ayarlar hazır. Kullanmak istemediğiniz hizmetleri boş bırakabilirsiniz.';
      for (const definition of definitions) setBusy(forms.get(definition.id), false, definition);
    } catch (error) { pageStatus.textContent = error.message; }
    finally { reload.disabled = false; }
  }
  reload.addEventListener('click', () => {
    if ([...forms.values()].some(form => form.dataset.dirty === 'true') && !window.confirm('Kaydedilmemiş değişiklikler kaldırılıp kayıtlı ayarlar yüklensin mi?')) return;
    load();
  });
  load();
}
