const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('app/static/editor.js','utf8');
const code=source.slice(source.indexOf('async function api('),source.indexOf('  const clamp='));
function request(fetch){const context={fetch,AbortController,setTimeout,clearTimeout,headers:{}};vm.runInNewContext(code+';globalThis.request=api;',context);return context.request;}
test('cancelled seek aborts its pending request immediately',async()=>{
  const controller=new AbortController();
  const api=request((url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true})));
  const pending=api('/local',{signal:controller.signal});controller.abort();
  await assert.rejects(pending,error=>error.name==='AbortError');
});
test('preview scheduling receives a typed busy error instead of an opaque failure',async()=>{
  const api=request(async()=>({ok:false,status:503,headers:{get:()=> 'application/json'},json:async()=>({message:'Önizleme hazırlanıyor',category:'preview_busy'})}));
  await assert.rejects(api('/local'),error=>error.status===503&&error.category==='preview_busy');
});
