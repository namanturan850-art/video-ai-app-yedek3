const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync('app/static/program-player.js','utf8');
function setup(extra={}){
  class Video extends EventTarget {
    constructor(){super();this.currentTime=0;this.paused=true;this.readyState=4;this.playbackRate=1;this.ranges=[];}
    get buffered(){return {length:this.ranges.length,start:i=>this.ranges[i][0],end:i=>this.ranges[i][1]};}
    play(){this.paused=false;return Promise.resolve();}pause(){this.paused=true;}removeAttribute(){}load(){this.ranges=[];}
  }
  const globals={AbortController,EventTarget,Event,setTimeout,performance,URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},MediaSource:{isTypeSupported:()=>true},fetch:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(8)}),...extra};
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
  const {p,c}=setup();const finish=[];let appended=0;const run=Object.getPrototypeOf(p).pump;
  c.api=()=>new Promise(resolve=>finish.push(resolve));p.append=async()=>appended++;
  const pending=run.call(p);p.reset(8);finish.forEach(resolve=>resolve({status:'ready',start:0,duration:4,cache_hit:true}));await pending;
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
  c.api=async(url,options)=>({status:'ready',start:JSON.parse(options.body).time,duration:4,cache_hit:false});
  p.append=async meta=>{video.ranges=[[0,meta.start+meta.duration]];};
  await Object.getPrototypeOf(p).pump.call(p);
  assert.equal(p.ratios.length,3);assert.ok(p.ratios.every(n=>n<1));
});
test('invalid source pauses native clock without falling back to unsynchronized narration',async()=>{
  const {p,c,video}=setup();video.ranges=[[0,4]];p.positioned=true;p.active=true;video.currentTime=1;
  let stopped=0;c.pause=()=>stopped++;
  c.api=async()=>{throw Object.assign(Error('Kaynak 3 sn; kesiti düzeltin'),{category:'short_source'});};
  await Object.getPrototypeOf(p).pump.call(p);
  assert.ok(p.blocked);assert.equal(p.failed,false);assert.equal(video.paused,true);assert.equal(stopped,1);
  p.clock();assert.equal(c.narration.paused,true);assert.equal(c.narration.muted,true);
  p.tick();assert.equal(video.paused,true);
});
test('a proxy network timeout cannot release the narration clock into a black clip',async()=>{
  const {p,c,video}=setup();
  c.api=async()=>{throw Error('20 saniye içinde yanıt alınamadı.');};
  await Object.getPrototypeOf(p).pump.call(p);
  p.clock();p.tick();assert.equal(p.failed,false);assert.ok(p.blocked);assert.equal(video.paused,true);assert.equal(c.narration.paused,true);
});

function paused(c){c.controls.play.textContent='▶ Oynat';}
function readySegments(c,p,video){
  c.api=async(url,options)=>({status:'ready',start:JSON.parse(options.body).time,duration:4,cache_hit:true});
  p.append=async meta=>{video.ranges=[[0,meta.start+meta.duration]];};
}
test('paused monitor prepares the same runway Play needs on fast hardware',async()=>{
  const {p,video,c}=setup();paused(c);p.ratios=[.5];readySegments(c,p,video);
  await Object.getPrototypeOf(p).pump.call(p);
  assert.equal(p.next,8);
});
test('paused preparation is capped so a slow machine is not buffered for minutes',async()=>{
  const {p,video,c}=setup();paused(c);p.ratios=[3];readySegments(c,p,video);
  await Object.getPrototypeOf(p).pump.call(p);
  assert.equal(p.next,20);
});
test('the status text reports how long Play waited before the picture started',()=>{
  const {p,video,c}=setup();let shown='';p.onState=s=>{shown=s.text;};
  p.ratios=[.9];p.tick();assert.equal(p.started,false);
  video.ranges=[[0,44]];p.next=44;p.tick();
  assert.equal(p.started,true);assert.ok(p.startupSeconds>=0);
  assert.match(shown,/başlama \d+\.\d sn/);assert.match(shown,/hazırlık 0\.9× gerçek süre/);
});
test('waiting text shows buffer progress and the measured preparation speed',()=>{
  const {p,c}=setup();let shown='';p.onState=s=>{shown=s.text;};
  p.ratios=[1.8];p.tick();
  assert.match(shown,/\/ .* sn/);assert.match(shown,/hazırlık 1\.8× gerçek süre/);
  c.controls.play.textContent='▶ Oynat';p.tick();
  assert.match(shown,/duraklatıldı · .* \/ .* sn/);
});
test('Play after Pause resumes at once when the runway was prepared while paused',()=>{
  const {p,video,c}=setup();paused(c);video.ranges=[[0,8]];p.positioned=true;p.next=8;p.ratios=[.5];
  p.tick();assert.equal(video.paused,true);
  c.controls.play.textContent='❚❚ Duraklat';p.tick();
  assert.equal(p.started,true);assert.equal(video.paused,false);
});
function withHold(){
  const inserted=[];
  const document={createElement:()=>({className:'',width:0,height:0,removed:false,getContext:()=>({drawImage(){}}),remove(){this.removed=true;}})};
  const ctx=setup({document});
  ctx.video.parentNode={insertBefore:node=>inserted.push(node)};ctx.video.videoWidth=1280;ctx.video.videoHeight=720;
  return {...ctx,inserted};
}
test('a seek outside the buffer holds the last decoded frame instead of a black monitor',()=>{
  const {p,video,setTime,inserted}=withHold();video.ranges=[[0,12]];p.positioned=true;p.next=12;
  p.tick();assert.equal(video.hidden,false);
  setTime(40);p.tick();
  assert.equal(inserted.length,1);assert.equal(p.hold,inserted[0]);assert.equal(inserted[0].removed,false);
  video.ranges=[[40,52]];p.tick();
  assert.equal(inserted[0].removed,true);assert.equal(p.hold,null);assert.equal(video.hidden,false);
});
test('an in-buffer seek keeps the browser frame visible while the new picture decodes',()=>{
  const {p,video,setTime}=withHold();video.ranges=[[0,30]];p.positioned=true;p.next=30;
  p.tick();assert.equal(video.hidden,false);
  video.readyState=1;setTime(10);p.tick();
  assert.equal(p.active,false);assert.equal(video.hidden,false);
});
test('a stream that never produced a picture stays hidden and leaves no stale frame',()=>{
  const {p,video,inserted}=withHold();
  p.tick();assert.equal(video.hidden,true);assert.equal(inserted.length,0);
});
test('leaving Program mode and destroying the player release the held frame',()=>{
  const {p,video,setTime,inserted}=withHold();video.ranges=[[0,12]];p.positioned=true;p.next=12;
  p.tick();setTime(40);p.tick();assert.equal(inserted.length,1);
  p.destroy();assert.equal(inserted[0].removed,true);assert.equal(p.hold,null);
});

test('the next segment is requested while the current one is still being prepared',async()=>{
  const {p,c,video}=setup();c.data.duration=64;const requested=[],resolvers=[];
  c.api=(url,options)=>{const time=JSON.parse(options.body).time;requested.push(time);return new Promise(resolve=>resolvers.push(()=>resolve({status:'ready',start:time,duration:4,cache_hit:false})));};
  p.append=async meta=>{video.ranges=[[0,meta.start+meta.duration]];};
  const running=Object.getPrototypeOf(p).pump.call(p);await new Promise(resolve=>setTimeout(resolve,5));
  assert.deepEqual(requested.slice(0,2),[0,4]);  // two segments are in preparation at the same time
  p.reset(40);resolvers.forEach(done=>done());await running;
});
test('the measured speed is the throughput of overlapping builds, not one build time',async()=>{
  const {p,c,video}=setup();c.data.duration=16;paused(c);
  c.api=async(url,options)=>({status:'ready',start:JSON.parse(options.body).time,duration:4,cache_hit:false});
  p.append=async meta=>{video.ranges=[[0,meta.start+meta.duration]];};
  await Object.getPrototypeOf(p).pump.call(p);
  assert.ok(p.ratios.length>0&&p.ratios.every(n=>n<1));
});
