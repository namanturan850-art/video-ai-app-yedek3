const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/render.js'),'utf8');
class Element{
 constructor(tag,text=''){this.tag=tag;this.children=[];this.text=text;this.listeners={};this.style={};}
 set textContent(value){this.text=String(value);}get textContent(){return this.text+this.children.map(c=>c.textContent).join('\n');}
 append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
 setAttribute(){}addEventListener(type,fn){this.listeners[type]=fn;}
 set innerHTML(value){throw Error('HTML injection forbidden');}
 find(predicate){return predicate(this)?this:this.children.map(c=>c.find(predicate)).find(Boolean);}
}
const counts={motion_effects:27,scene_transitions:8,emphasis_texts:7,internal_edits:11,slots:37,scenes:24};
const plan=style=>({editing_style:style,style_label:{basic:'Temel',balanced:'Dengeli YouTube',dynamic:'Dinamik YouTube'}[style],fingerprint:style,
 summary:style==='basic'?{...counts,motion_effects:0,scene_transitions:0,emphasis_texts:0,internal_edits:0}:counts,
 slots:[{slot_id:'a',scene_id:'s',transition_out:'crossfade',segments:[{start:0,end:4,motion_effect:'push_in'}]}],
 emphasis:[{slot_id:'a',start:0,text:'Im Jahr 2026'}],raw_filter:'private-filter-never-show'});
async function harness({job=null,versions=[]}={}){
 const root=new Element('main'),calls=[];
 const fetch=async(url,opts)=>{calls.push({url,method:opts.method,body:opts.body});const style=new URL(url,'http://local').searchParams.get('editing_style')||'balanced';
  return {ok:true,json:async()=>({ready:true,source_ready:true,summary:null,ffmpeg:{found:true,status:'Hazır'},smart_edit_plan:plan(style),music:null,job,versions,active:versions[0]||null})};};
 vm.runInContext(source,vm.createContext({location:{pathname:'/projects/abc/render'},document:{querySelector:()=>root,createElement:tag=>new Element(tag)},window:{addEventListener(){}},File:class{},AbortSignal:{timeout(){}},fetch,setTimeout(){}}));
 await new Promise(resolve=>setImmediate(resolve));return {root,calls,find:id=>root.find(n=>n.id===id)};
}
test('balanced is default and nonzero local editing plan appears before render',async()=>{
 const {root,calls,find}=await harness();assert.equal(find('render-editing-style').value,'balanced');assert.match(calls[0].url,/editing_style=balanced/);
 assert.match(root.textContent,/Hareket efektleri: 27/);assert.match(root.textContent,/Sahne geçişleri: 8/);assert.match(root.textContent,/Vurgu yazıları: 7/);assert.match(root.textContent,/Klip içi değişimler: 11/);
 assert.match(root.textContent,/Kurgu Planını Gör/);assert.match(root.textContent,/Im Jahr 2026/);assert.doesNotMatch(root.textContent,/private-filter/);
});
test('changing style recalculates plan using only local GET',async()=>{
 const {root,calls,find}=await harness();const select=find('render-editing-style');select.value='basic';await select.listeners.change();
 assert.match(calls.at(-1).url,/editing_style=basic/);assert.equal(calls.at(-1).method,'GET');assert.match(root.textContent,/Kurgu stili: Temel/);assert.match(root.textContent,/Hareket efektleri: 0/);
});
test('create sends chosen style and manual refresh retains style',async()=>{
 const {root,calls,find}=await harness();find('render-editing-style').value='dynamic';await find('render-create').listeners.click();
 const posted=calls.find(c=>c.method==='POST');assert.equal(JSON.parse(posted.body).editing_style,'dynamic');
 await root.find(n=>n.tag==='button'&&n.textContent==='Durumu Yenile').listeners.click();assert.match(calls.at(-1).url,/editing_style=dynamic&refresh_tools=true/);
});
test('finished version distinguishes planned and actually applied effects',async()=>{
 const version={id:'v1',version:1,status:'completed',status_label:'Tamamlandı',encoder_label:'NVIDIA NVENC',created_at:'2026-10-09T00:00:00Z',metadata:{duration:193,file_size:1024,editing_style:'balanced',smart_edit_summary:counts,smart_edit_applied_summary:{...counts,motion_effects:26,emphasis_texts:6}}};
 const {root}=await harness({versions:[version]});assert.match(root.textContent,/Planlanan kurgu: Hareket efektleri: 27/);assert.match(root.textContent,/Uygulanan kurgu: Hareket efektleri: 26/);assert.match(root.textContent,/Vurgu yazıları: 6/);
});
test('busy job disables editing style and existing diagnostic remains visible',async()=>{
 const {find}=await harness({job:{status:'rendering',status_label:'Render ediliyor',encoder_label:'NVIDIA NVENC',progress:{percent:30,elapsed_seconds:10}}});assert.equal(find('render-editing-style').disabled,true);
});
