const {test}=require('node:test');const assert=require('node:assert/strict');
const {timestamp,parse,current}=require('../../app/static/subtitles-timing.js');
test('SRT/editor time format round trip, including hour and carry',()=>{
  for(const seconds of [0,.001,4.12,59.999,60,193.001,3600.25,86399.999])assert.equal(parse(timestamp(seconds)),seconds);
  assert.equal(timestamp(59.9999),'00:01:00,000');
});
test('invalid time formats reject safely',()=>{
  for(const bad of ['-1','NaN','00:00:60,000','00:61:00,000','0:0:0','00:00:04','<script>','Infinity'])assert.throws(()=>parse(bad));
});
test('local currentTime follows next cue and gaps; exact endpoint exclusive',()=>{
  const cues=[{start:0,end:2,text:'first'},{start:2,end:4,text:'second'},{start:5,end:6,text:'third'}];
  for(const [time,index] of [[0,0],[1.99,0],[2,1],[4,-1],[5,2],[6,-1]])assert.equal(current(cues,time),index);
});
