const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync('app/static/program-player.js','utf8');
function setup(){
  class Video extends EventTarget {
    constructor(){super();this.currentTime=0;this.paused=true;this.readyState=4;this.playbackRate=1;this.ranges=[];}
    get buffered(){return {length:this.ranges.length,start:i=>this.ranges[i][0],end:i=>this.ranges[i][1]};}
    play(){this.paused=false;return Promise.resolve();}pause(){this.paused=true;}removeAttribute(){}load(){this.ranges=[];}
  }
  const globals={AbortController,EventTarget,Event,setTimeout,performance,URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},MediaSource:{isTypeSupported:()=>true},fetch:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(8)})};
  vm.runInNewContext(code,globals);
  const video=new Video();let time=0,revision=0,rate=1;
  const c={id:'project',root:{dataset:{}},controls:{play:{textContent:'❚❚ Duraklat'}},data:{duration:64},narration:{paused:false,pause(){this.paused=true;}},getTime:()=>time,getPlaybackRate:()=>rate,api:async()=>{throw Error('unexpected API');}};
  const p=new globals.NAMANProgramPlayer({video,c,getRevision:()=>revision,getMode:()=> 'program',quality:{value:'auto'},onState:()=>{}});
  p.reset(0);p.pump=async()=>{};
  return {p,video,c,globals,setTime:t=>time=t,setRevision:()=>revision++,setRate:r=>rate=r};
}
test('cold playback holds narration and transport until measured runway is ready',()=>{
  const {p,video,c}=setup();video.ranges=[[0,4]];p.positioned=true;p.next=4;p.ratios=[2,2];
  p.tick();assert.equal(video.paused,true);assert.equal(p.clock(),0);assert.equal(c.narration.paused,true);assert.equal(c.narration.muted,true);
  video.ranges=[[0,44]];p.next=44;p.tick();assert.equal(video.paused,false);
  video.currentTime=1.25;assert.equal(p.clock(),1.25);
});
test('paused seek and playback speed apply to the same native decoder',()=>{
  const {p,video,c,setTime,setRate}=setup();video.ranges=[[0,12]];p.positioned=true;p.next=12;p.lastClock=1;c.controls.play.textContent='▶ Oynat';setTime(5);
  p.tick();assert.equal(video.currentTime,5);assert.equal(video.paused,true);
  setRate(2);p.tick();assert.equal(video.playbackRate,2);
});
test('new editor revision cancels old generation and releases its buffered media',()=>{
  const {p,video,setRevision}=setup();video.ranges=[[0,12]];p.positioned=true;p.next=12;
  const generation=p.generation,signal=p.abort.signal;setRevision();p.tick();
  assert.equal(signal.aborted,true);assert.equal(p.generation,generation+1);assert.equal(p.active,false);assert.equal(video.buffered.length,0);
});
test('late response after seek cannot append an old generation',async()=>{
  const {p,c}=setup();let finish,appended=0;const run=Object.getPrototypeOf(p).pump;
  c.api=()=>new Promise(resolve=>finish=resolve);p.append=async()=>appended++;
  const pending=run.call(p);p.reset(8);finish({status:'ready',start:0,duration:4,cache_hit:true});await pending;
  assert.equal(appended,0);assert.equal(p.next,8);
});
test('forward preparation never evicts frames that have not played',async()=>{
  const {p,video,c}=setup();const removed=[];
  class Buffer extends EventTarget {
    get buffered(){return {length:1,start:()=>0,end:()=>60};}
    appendBuffer(){queueMicrotask(()=>this.dispatchEvent(new Event('updateend')));}
    remove(a,b){removed.push([a,b]);queueMicrotask(()=>this.dispatchEvent(new Event('updateend')));}
  }
  p.source={readyState:'open'};p.sourceBuffer=new Buffer();p.mime='test';c.api=async()=>({mime:'test',url:'/local',origin:0});
  await p.append({start:32,duration:4,stream_info_url:'/local'},p.generation);assert.deepEqual(removed,[]);
  video.currentTime=40;await p.append({start:40,duration:4,stream_info_url:'/local'},p.generation);assert.deepEqual(removed,[[0,32]]);
});
test('normal pause interruption does not demote continuous playback',async()=>{
  const {p,video}=setup();video.ranges=[[0,12]];p.positioned=true;p.next=12;
  video.play=()=>{const error=Error('interrupted');error.name='AbortError';return Promise.reject(error);};
  p.tick();await Promise.resolve();assert.equal(p.failed,false);
});
test('busy decoder queue retries without losing continuous playback',async()=>{
  const {p,c}=setup();const run=Object.getPrototypeOf(p).pump;
  c.api=async()=>{throw Object.assign(Error('busy'),{category:'preview_busy',status:503});};
  await run.call(p);assert.equal(p.failed,false);assert.ok(p.retryAt>0);assert.equal(p.next,0);
});
test('saving an audio mix invalidates buffered sound even without a timeline revision',()=>{
  const {p,c,video}=setup();p.getRevision=()=>p.constructor.revision(0,c);p.reset(0);
  video.ranges=[[0,12]];p.positioned=true;p.next=12;const signal=p.abort.signal;
  c.data.audio_settings={narration_volume:.5};p.tick();
  assert.equal(signal.aborted,true);assert.equal(p.active,false);assert.equal(video.buffered.length,0);
});
test('underrun waits for actual forward buffer instead of counting already played segments',()=>{
  const {p,video,c,setTime}=setup();c.data.duration=240;
  p.positioned=true;p.next=100;p.started=true;p.ratios=[2];
  video.currentTime=99.9;video.ranges=[[92,100]];video.paused=false;
  setTime(99.9);p.lastClock=99.9;video.dispatchEvent(new Event('waiting'));
  p.tick();assert.equal(video.paused,true);assert.equal(p.started,false);
  video.ranges=[[92,160]];p.next=160;p.tick();assert.equal(video.paused,false);
});
test('recovery near the end requires only the remaining duration',()=>{
  const {p,video,c,setTime}=setup();c.data.duration=240;
  p.positioned=true;p.next=240;p.ratios=[4];video.currentTime=236;video.ranges=[[228,240]];
  setTime(236);p.lastClock=236;
  assert.equal(p.warmup(),4);p.tick();assert.equal(video.paused,false);
});
test('a discontinuous buffer is never counted as contiguous runway',()=>{
  const {p,video}=setup();p.positioned=true;p.next=64;p.ratios=[2];
  video.ranges=[[0,4],[8,64]];p.tick();assert.equal(video.paused,true);
});
test('long sessions retain only the preparation measurements used by the scheduler',async()=>{
  const {p,c,video}=setup();c.data.duration=20;p.ratios=[1,2,3];
  c.api=async()=>({status:'ready',start:p.next,duration:4,cache_hit:false});
  p.append=async meta=>{video.ranges=[[0,meta.start+meta.duration]];};
  await Object.getPrototypeOf(p).pump.call(p);
  assert.equal(p.ratios.length,3);assert.ok(p.ratios.every(n=>n<1));
});
