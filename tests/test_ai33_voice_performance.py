"""DOM work is bounded by new options, not every previously loaded voice."""
from pathlib import Path
import shutil
import subprocess

import pytest


CASES={
    'first_30':"updateAI33VoiceOptions(select,voices(1), '',null);assert.equal(created,31);assert.equal(select.options.length,31);",
    'append_reuses_nodes':"updateAI33VoiceOptions(select,voices(1),'',null);const first=select.options[1];const before=created;updateAI33VoiceOptions(select,[...voices(1),...voices(2)],'',null);assert.equal(created-before,30);assert.equal(select.options[1],first);assert.equal(select.options.length,61);",
    'duplicates':"updateAI33VoiceOptions(select,[...voices(1),...voices(1)],'',null);assert.equal(select.options.length,31);",
    'refresh_reuses_all':"updateAI33VoiceOptions(select,voices(1),'edge_1_1',null);const first=select.options[1];updateAI33VoiceOptions(select,voices(1),'edge_1_1',null);assert.equal(created,31);assert.equal(select.options[1],first);assert.equal(select.value,'edge_1_1');",
    'saved_voice_not_lost':"updateAI33VoiceOptions(select,voices(2),'edge_1_1',{display_name:'Saved'});assert.equal(select.value,'edge_1_1');assert(select.options.some(o=>o.textContent==='Saved (seçili ses)'));",
    'provider_replaces_visible':"updateAI33VoiceOptions(select,voices(1),'',null);updateAI33VoiceOptions(select,voices(1,'minimax'),'',null);assert.equal(select.options.length,31);assert(select.options.slice(1).every(o=>o.value.startsWith('minimax_')));",
    'all_sequential_and_yields':"let running=0,max=0,yielded=false;const b=createAI33VoiceBrowser(async q=>{max=Math.max(max,++running);await new Promise(r=>setTimeout(r,1));running--;return {voices:voices(q.page).map(v=>({...v,provider:'edge'}))};});b.reset('edge');setTimeout(()=>{yielded=true},0);await b.all();assert.equal(max,1);assert.equal(b.state.voices.length,300);assert(yielded);",
    'provider_reset_cancels_all':"let calls=0;const b=createAI33VoiceBrowser(async q=>{calls++;return {voices:voices(1).map(v=>({...v,provider:'edge'}))};});b.reset('edge');await assert.rejects(b.all(()=>b.reset('minimax')));assert.equal(calls,1);assert.equal(b.state.voices.length,0);",
}


@pytest.mark.parametrize('case',CASES)
def test_incremental_voice_browser_dom_work(case):
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed for browser state tests.')
    path=Path(__file__).resolve().parents[1]/'app/static/settings-ai33-browser.js'
    script="""
      const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
      let created=0;
      class Option { constructor(){this.value='';this.textContent='';this.parent=null;}remove(){this.parent.options=this.parent.options.filter(o=>o!==this);}}
      const select={options:[],value:'',append(batch){for(const option of batch.options){option.parent=this;this.options.push(option)}}};
      global.document={createElement(tag){assert.equal(tag,'option');created++;return new Option()},createDocumentFragment(){return {options:[],append(o){this.options.push(o)}}}};
      vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
      const voices=(page,provider='edge')=>Array.from({length:30},(_,i)=>({voice_id:`${provider}_${page}_${i}`,display_name:`Voice ${page} ${i}`}));
      (async()=>{
    """+CASES[case]+"\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});"
    result=subprocess.run([node,'-e',script,str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
