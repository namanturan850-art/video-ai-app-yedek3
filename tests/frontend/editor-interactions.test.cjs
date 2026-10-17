const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/editor.js'),'utf8');

class Element{
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.style={setProperty(){}};this.dataset={};this.className='';this.classList={add(){},remove(){}};this.currentTime=0;this.paused=true;this.scrollLeft=0;this.offsetWidth=100;}
  set textContent(v){this.text=String(v);this.children=[]} get textContent(){return this.text||''}
  append(...nodes){this.children.push(...nodes)} replaceChildren(...nodes){this.children=nodes}
  remove(){this.removed=true}
  setAttribute(){} addEventListener(type,fn){this.listeners[type]=fn} getBoundingClientRect(){return{left:0,width:1200}}
  querySelectorAll(selector){const out=[];const walk=n=>{if(n.className&&selector.slice(1).split('.').every(x=>n.className.split(' ').includes(x)))out.push(n);(n.children||[]).forEach(walk)};this.children.forEach(walk);return out}
  pause(){this.paused=true} play(){this.paused=false;return Promise.resolve()}
}
const find=(root,cls)=>root.querySelectorAll('.'+cls)[0];
async function page(){
  const root=new Element('main'),created=[],requests=[];
  const state={duration:60,fps:30,plan_id:'p',revision:1,stock_plan_id:'p',stock_revision:1,warnings:[],scenes:[{scene_id:'s',start:0,end:60,locked:false}],track_order:['emphasis','layers','maps','infographics','visuals','audio','subtitles'],tracks:{emphasis:[],layers:[],maps:[],infographics:[],visuals:[{scene_id:'s',slot_id:'v1',start:0,end:30,clip_start:0,label:'Video 1',preview_url:'/preview1',media:{media_type:'video'}},{scene_id:'s',slot_id:'v2',start:30,end:60,clip_start:2,label:'Video 2',preview_url:'/preview2',media:{media_type:'video'}}],audio:[{start:0,end:60,url:'/audio'}],subtitles:[{start:20,end:30,text:'Yirmi üç saniye'}]}};
  const pointer={};
  const context=vm.createContext({location:{pathname:'/projects/abc/editor'},document:{querySelector:()=>root,createElement:t=>{const e=new Element(t);created.push(e);return e}},fetch:async(url,options={})=>{requests.push({url,options});return{ok:true,json:async()=>url.endsWith('/archive')?{items:[]}:state}},confirm:()=>true,requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout,clearTimeout,addEventListener:(t,f)=>pointer[t]=f,removeEventListener:(t)=>delete pointer[t],console});
  vm.runInContext(source,context);await new Promise(r=>setImmediate(r));return{root,created,pointer,requests};
}
test('ruler click and playhead scrubbing seek real audio and video to 23 seconds',async()=>{
  const {root,created,pointer}=await page(),ruler=find(root,'naman-ruler'),head=find(root,'naman-playhead'),audio=created.find(x=>x.tag==='audio'),video=created.find(x=>x.tag==='video');
  ruler.onpointerdown({clientX:276,preventDefault(){}});assert.equal(audio.currentTime,23);assert.equal(video.currentTime,23);assert.match(root.textContent+find(root,'naman-time').textContent,/00:23\.000/);
  head.onpointerdown({clientX:120,preventDefault(){}});pointer.pointermove({clientX:300});pointer.pointerup({clientX:300});assert.equal(audio.currentTime,25);assert.equal(video.currentTime,25);
});
test('right trim handle changes adjacent boundary and persists the revision',async()=>{
  const {root,pointer,requests}=await page(),clips=root.querySelectorAll('.naman-clip'),right=clips[0].children.find(x=>x.className.includes('right'));
  right.onpointerdown({clientX:360,preventDefault(){},stopPropagation(){}});pointer.pointermove({clientX:372});pointer.pointerup();await new Promise(r=>setImmediate(r));
  const request=requests.find(x=>x.url.endsWith('/editor/timeline'));assert.ok(request);const body=JSON.parse(request.options.body);
  assert.equal(body.slots[0].end,31);assert.equal(body.slots[1].start,31);assert.equal(body.revision,1);
});
