(() => {
  const select=document.querySelector('#shell-project'); if(!select)return;
  const match=location.pathname.match(/^\/projects\/([a-f0-9]{32})/); let current=match?.[1]||'';
  const tabs=[...document.querySelectorAll('[data-shell]')],render=document.querySelector('.shell-render');
  function wire(id){const base=id?`/projects/${id}`:'/projects';tabs.find(x=>x.dataset.shell==='production').href=id?`${base}/production`:'/projects';tabs.find(x=>x.dataset.shell==='editor').href=id?`${base}/editor`:'/projects';render.href=id?`${base}/render`:'/projects';}
  function active(){const key=location.pathname.includes('/editor')?'editor':location.pathname==='/settings'||location.pathname.startsWith('/settings/')?'settings':'production';tabs.forEach(x=>x.classList.toggle('secili',x.dataset.shell===key))}
  select.addEventListener('change',()=>{current=select.value;wire(current);if(current)location.assign(`/projects/${current}/production`)});wire(current);active();
  fetch('/api/projects',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(data=>{for(const p of data.projects){const o=document.createElement('option');o.value=p.id;o.textContent=p.name;o.selected=p.id===current;select.append(o)}}).catch(()=>{select.title='Projeler yüklenemedi'});
})();
