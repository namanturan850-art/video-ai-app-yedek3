/* Pure local playback/editor helpers, also exercised by Node regression tests. */
(function(root){
  function timestamp(seconds){
    const ms=Math.round(seconds*1000),h=Math.floor(ms/3600000),m=Math.floor(ms%3600000/60000),s=Math.floor(ms%60000/1000);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;
  }
  function parse(value){
    const match=/^(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})$/.exec(value.trim());
    if(!match)throw new Error('Zamanı 00:00:04,120 biçiminde yazın.');
    return Number(match[1])*3600+Number(match[2])*60+Number(match[3])+Number(match[4])/1000;
  }
  function current(cues,time){return cues.findIndex(c=>time>=c.start&&time<c.end);}
  const api={timestamp,parse,current};root.SubtitleTiming=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
