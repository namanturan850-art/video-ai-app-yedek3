const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/static/render.js'),'utf8');
class Element{
  constructor(tag,text=''){this.tag=tag;this.children=[];this.text=text;this.listeners={};}
  set textContent(value){this.text=String(value);}
  get textContent(){return this.text+this.children.map(c=>c.textContent).join('\n');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(){}
  addEventListener(type,fn){this.listeners[type]=fn;}
  set innerHTML(value){throw Error('HTML injection forbidden');}
}
async function render(diagnostic,status='error'){
  const root=new Element('main');
  const state={source_ready:true,ready:true,ffmpeg:{status:'Hazır',found:true},summary:null,music:null,versions:[],active:null,
    job:{status,status_label:status==='error'?'Hata':'Tamamlandı',encoder_label:'CPU / libx264',progress:{percent:8,elapsed_seconds:2,diagnostic}}};
  const context=vm.createContext({location:{pathname:'/projects/abc/render'},document:{querySelector:()=>root,createElement:tag=>new Element(tag)},
    window:{addEventListener(){}},File:class{},AbortSignal:{timeout(){}},fetch:async()=>({ok:true,json:async()=>state}),setTimeout(){}});
  vm.runInContext(source,context);await new Promise(resolve=>setImmediate(resolve));return root;
}
test('render page displays Turkish phase, 1-based slot and safe error code',async()=>{
  const root=await render({phase_label:'Medya işleme: Medya 5/37',safe_error_summary:'FFmpeg filtre işlemi başarısız oldu.',safe_error_code:'filter_graph_failed',media_type:'video',encoder:'h264_nvenc'});
  assert.match(root.textContent,/Render aşaması: Medya işleme: Medya 5\/37/);
  assert.match(root.textContent,/Hata türü: FFmpeg filtre işlemi başarısız oldu/);
  assert.match(root.textContent,/Tanı kodu: filter_graph_failed/);
  assert.match(root.textContent,/yalnız bu güvenli tanıyı paylaşın/);
  assert.match(root.textContent,/Medya türü: Video/);
  assert.match(root.textContent,/Encoder: NVIDIA NVENC/);
});
test('UI uses text nodes and ignores arbitrary stderr/command diagnostic fields',async()=>{
  const root=await render({phase_label:'Altyazı ön kontrolü',safe_error_summary:'Altyazı filtresi başarısız oldu.',safe_error_code:'subtitle_filter_failed',raw_stderr:'Authorization: private-key',command:'C:\\private\\ffmpeg.exe',private_url:'https://signed.invalid'});
  assert.match(root.textContent,/Altyazı filtresi başarısız oldu/);
  assert.doesNotMatch(root.textContent,/Authorization|private-key|ffmpeg.exe|signed.invalid/);
});
test('old failed jobs without diagnostic and successful jobs remain usable',async()=>{
  assert.doesNotMatch((await render(null)).textContent,/Güvenli render tanısı/);
  assert.doesNotMatch((await render({phase_label:'Old error'},'completed')).textContent,/Güvenli render tanısı/);
});
