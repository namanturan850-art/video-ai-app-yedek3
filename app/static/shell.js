(() => {
  const select=document.querySelector('#shell-project'); if(!select)return;
  const match=location.pathname.match(/^\/projects\/([a-f0-9]{32})/); let current=match?.[1]||'';
  const tabs=[...document.querySelectorAll('[data-shell]')],render=document.querySelector('.shell-render');
  const importing=document.createElement('a'),exporting=document.createElement('a');
  importing.textContent='İçe Aktar';importing.dataset.shell='import';
  exporting.textContent='Dışa Aktar';exporting.dataset.shell='export';
  const nav=document.querySelector('#shell-tabs');nav.prepend(importing);nav.append(exporting);
  tabs.push(importing,exporting);
  function wire(id){const base=id?`/projects/${id}`:'/projects';tabs.find(x=>x.dataset.shell==='production').href=id?`${base}/production`:'/projects';tabs.find(x=>x.dataset.shell==='editor').href=id?`${base}/editor`:'/projects';render.href=id?`${base}/render`:'/projects';importing.href=id?`${base}/editor#import`:'/projects';exporting.href=render.href;}
  function active(){const key=location.pathname.includes('/editor')?'editor':location.pathname==='/settings'||location.pathname.startsWith('/settings/')?'settings':'production';tabs.forEach(x=>x.classList.toggle('secili',x.dataset.shell===key))}
  select.addEventListener('change',()=>{current=select.value;wire(current);if(current)location.assign(`/projects/${current}/${location.pathname.endsWith('/editor')?'editor':'production'}`)});wire(current);active();
  if(location.pathname.endsWith('/render')){tabs.forEach(x=>x.classList.toggle('secili',x.dataset.shell==='export'));}
  if(location.pathname.endsWith('/editor'))importing.addEventListener('click',event=>{event.preventDefault();document.querySelector('.naman-library input[type=file]')?.click();});
  fetch('/api/projects',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(data=>{for(const p of data.projects){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;o.selected=p.id===current;select.append(o)}if(location.pathname==='/')home(data.projects);}).catch(()=>{select.title='Projeler yüklenemedi';if(location.pathname==='/')home([],true);});
  function home(projects,failed=false){
    const root=document.querySelector('#dashboard');if(!root)return;
    document.body.classList.add('naman-home-page');
    const make=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
    const a=(text,url)=>{const n=make('a',text);n.href=url;return n;};
    const sidebar=make('aside','','home-sidebar'),content=make('section','','home-content');
    sidebar.append(a('＋ Yeni Proje','/new-project'),a('▣ Proje Aç','/projects'),a('◷ Son Projeler','#recent-projects'),a('⚙ Ayarlar','/settings'));
    const title=make('div','','home-title');title.append(make('p','NAMAN · YEREL VİDEO STÜDYOSU','eyebrow'),make('h1','Bir sonraki hikâyenize başlayın.'),make('p','Metninizi, medyanızı ve kurgunuzu aynı çalışma alanında yönetin.'));
    const actions=make('div','','home-actions');actions.append(a('＋ Yeni proje oluştur','/new-project'),a('Kayıtlı proje aç','/projects'));
    const list=make('div','','home-project-list');list.id='recent-projects';
    content.append(title,actions,make('h2','Son güncellenen projeler'),list);
    const dates=new Intl.DateTimeFormat('tr-TR',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Istanbul'});
    [...projects].sort((a,b)=>String(b.updated_at||'').localeCompare(String(a.updated_at||''))).slice(0,12).forEach(project=>{
      const row=a('',`/projects/${project.id}`);row.className='home-project';
      const date=project.updated_at?dates.format(new Date(project.updated_at)):'';
      row.append(make('span','▤','home-project-icon'),make('strong',project.name),make('small',`${project.status_label||project.status||''}${date?' · '+date:''}`),make('span','Aç →'));list.append(row);
    });
    if(!projects.length)list.append(make('p',failed?'Projeler yüklenemedi. Proje Aç ekranından yeniden deneyin.':'Henüz kayıtlı proje yok. Yeni Proje ile başlayın.','home-empty'));
    root.replaceChildren(sidebar,content);
  }
})();
