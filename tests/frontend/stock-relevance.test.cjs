const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/stock.js'),'utf8');
class Element{
 constructor(tag,text=''){this.tag=tag;this.children=[];this.text=text;this.listeners={};this.style={};this.dataset={};}
 set textContent(value){this.text=String(value);}get textContent(){return this.text+this.children.map(c=>c.textContent).join('\n');}
 append(...children){for(const c of children){c.parent=this;this.children.push(c);}}replaceChildren(...children){this.children=[];this.append(...children);}
 insertBefore(child,before){child.parent=this;this.children.splice(this.children.indexOf(before),0,child);}
 setAttribute(){}addEventListener(type,fn){this.listeners[type]=fn;}
 set innerHTML(value){throw Error('HTML injection forbidden');}
 get lastChild(){return this.children.at(-1);}remove(){this.parent.children=this.parent.children.filter(c=>c!==this);}
 find(predicate){return predicate(this)?this:this.children.map(c=>c.find(predicate)).find(Boolean);}
 walk(){return [this,...this.children.flatMap(c=>c.walk())];}
 querySelectorAll(selector){return this.walk().filter(c=>selector==='[data-scene-id]'?c.dataset.sceneId:selector==='.stock-scene'?c.className==='stock-scene':false);}
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function harness({confirm=true,busy=false,selected=true,locked=false}={}){
 const root=new Element('main'),blocks=new Element('div'),card=new Element('article');card.dataset.sceneId='scene';blocks.append(card);root.append(blocks);
 const calls=[],confirmations=[];
 const media={provider:'pixabay',media_type:'image',media_id:'map',width:1920,height:1080,page_url:'https://pixabay.com/photos/map/',description:'Bermuda Triangle map',provider_query:'Bermuda Triangle map',query_used:'Bermuda Triangle map',search_tier:1,relevance_score:90,relevance_label:'Çok ilgili',local_path:'stock/map.jpg'};
 const state={plan_id:'plan',revision:7,selection_version:2,providers:{pexels:false,pixabay:true},warnings:[],search_options:{video_duration_tolerance_seconds:1.25},
  job:busy?{id:'job',status:'running',progress:{percent:20,message:'Aranıyor',search_diagnostics:[]}}:null,
  media_mix:{total_slots:1,selected_videos:0,selected_images:selected?1:0,unresolved_slots:selected?0:1,video_ratio_percent:selected?0:null},
  slots:[{slot_id:'slot',scene_id:'scene',order:1,estimated_start:0,estimated_end:5,duration:5,status:selected?'complete':'ai_needed',status_label:selected?'Tamamlandı':'Uygun stok medya bulunamadı',subject_anchor:'Bermuda Triangle',visual_goal:'ocean map',search_query:'Bermuda Triangle',preferred_type:'stock_video',locked,selected_media:selected?media:null,candidates:[media],warnings:[]}]};
 const fetch=async(url,opts)=>{calls.push({url,method:opts.method,body:opts.body});return {ok:true,json:async()=>state};};
 vm.runInContext(source,vm.createContext({document:{querySelector:s=>s==='#production-content'?root:blocks,createElement:tag=>new Element(tag)},window:{location:{pathname:'/projects/abc/production'},addEventListener(){},confirm:text=>{confirmations.push(text);return confirm;}},AbortSignal:{timeout(){}},fetch,setTimeout(){},clearTimeout(){}}));
 await settle();return {root,calls,confirmations,find:id=>root.find(n=>n.id===id),button:text=>root.find(n=>n.tag==='button'&&n.textContent===text)};
}
test('opening existing stock state never starts a search',async()=>{
 const {calls,find}=await harness();assert.equal(calls.length,1);assert.equal(calls[0].method,'GET');assert.equal(find('stock-complete').disabled,false);
});
test('Medyayı Tamamla requires confirmation and explains what is protected and that Claude is paid',async()=>{
 const {calls,find,confirmations}=await harness({confirm:false});find('stock-complete').listeners.click();await settle();assert.equal(calls.length,1);
 assert.match(confirmations[0],/Kilitli ve onaylı seçimler korunur/);assert.match(confirmations[0],/eski dosyalar silinmez/);assert.match(confirmations[0],/Gemini ücretsiz kotası/);
});
test('confirmed Medyayı Tamamla posts the single action and current revision only',async()=>{
 const {calls,find}=await harness();find('stock-complete').listeners.click();await settle();
 const post=calls.find(c=>c.method==='POST');assert.match(post.url,/\/stock\/jobs$/);
 assert.deepEqual(JSON.parse(post.body),{plan_id:'plan',revision:7,action:'complete_media'});
});
test('one media button, diagnostics download, stage and source details visible',async()=>{
 const {root,find}=await harness();
 const buttons=root.walk().filter(n=>n.tag==='button').map(n=>n.textContent);
 assert.ok(!buttons.includes('Alakaya Göre Medyayı Yeniden Ara')&&!buttons.includes('Medyayı Otomatik Bul')&&!buttons.includes('Eksik Medyaları Akıllı Tamamla'));
 assert.equal(find('stock-diagnostics').href,'/api/projects/abc/production/stock/diagnostics');
 assert.match(root.textContent,/Aşama: Yapay zekâ onayı bekliyor/);assert.match(root.textContent,/Ana konu: Bermuda Triangle/);assert.match(root.textContent,/Çok ilgili/);assert.match(root.textContent,/Sorgu: Bermuda Triangle map/);assert.match(root.textContent,/Medya seçim sürümü 2/);assert.doesNotMatch(root.textContent,/güven oranı|görsel olarak doğrulandı/i);
});
test('active job disables the button',async()=>{
 const {find}=await harness({busy:true});assert.equal(find('stock-complete').disabled,true);
});
test('empty slot is explained, manual choice stays possible and locks are respected',async()=>{
 const {root,button}=await harness({selected:false});assert.match(root.textContent,/Boş — Medyayı Tamamla deyin/);assert.equal(button('Değiştir').disabled,false);assert.equal(button('Yeniden seçtir').disabled,false);
 const locked=await harness({locked:true});assert.equal(locked.button('Değiştir').disabled,true);assert.equal(locked.button('Yeniden seçtir').disabled,true);
});
