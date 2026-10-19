/* Bounded proxy scheduling and one continuous, muxed Program decoder. */
(() => {
  class ProgramPlayer {
    static revision(revision,c){return JSON.stringify([revision,c.data.audio_settings,c.data.subtitle_version_id,c.data.stock_revision]);}
    constructor({video,c,getRevision,getMode,quality,onState}) {
      Object.assign(this,{video,c,getRevision,getMode,quality,onState});
      this.generation=0;this.failed=false;this.active=false;this.disposed=false;
      this.ratios=[];this.lastClock=null;this.revision=-1;this.chosen='';
      this.abort=new AbortController();
      this.waiting=()=>{if(this.started&&this.ahead()<.25&&!video.ended){this.started=false;video.pause();}};
      video.addEventListener('waiting',this.waiting);
      this.error=()=>this.fail('Tarayıcı kesintisiz videoyu çözemedi.');video.addEventListener('error',this.error);
      this.frame=(now)=>{if(this.active&&!video.paused){if(this.fpsAt){this.fpsCount++;if(now-this.fpsAt>=1000){this.fps=this.fpsCount*1000/(now-this.fpsAt);this.fpsAt=now;this.fpsCount=0;}}else{this.fpsAt=now;this.fpsCount=0;}}else this.fpsAt=0;if(!this.disposed&&!this.failed)this.frameId=video.requestVideoFrameCallback?.(this.frame);};
      this.frameId=video.requestVideoFrameCallback?.(this.frame);
    }
    get running(){return this.c.controls.play.textContent.includes('Duraklat')&&this.getMode()!=='source';}
    get enabled(){return this.getMode()!=='source'&&this.quality.value!=='frames';}
    ahead(){const r=this.video.buffered,t=this.video.currentTime;for(let i=0;i<r.length;i++)if(r.start(i)<=t+.04&&t<r.end(i)+.01)return r.end(i)-t;return 0;}
    contains(t){const r=this.video.buffered;for(let i=0;i<r.length;i++)if(r.start(i)<=t+.001&&t<r.end(i)-.001)return true;return false;}
    warmup(){
      // Recovery must be based on the current playhead, not the first segment.
      // Played/evicted media cannot provide runway after a decoder underrun.
      const remaining=Math.max(0,this.c.data.duration-(this.positioned?this.video.currentTime:this.seekTime));
      const ratio=Math.max(1,...this.ratios.slice(-3))*(this.c.getPlaybackRate?.()||1);
      // If preparation is slower than playback, build a measured runway first.
      // Never pretend a cold decoder is playing while the narration runs ahead.
      return Math.min(remaining,Math.min(60,Math.max(8,remaining*(1-1/ratio)+8)));
    }
    reset(time){
      this.abort.abort();this.abort=new AbortController();this.generation++;
      this.sourceBuffer=null;this.source=null;this.positioned=false;this.started=false;this.active=false;
      this.video.pause();this.video.removeAttribute('src');this.video.load();
      if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);this.objectUrl=null;
      this.anchor=Math.floor(time/4)*4;this.next=this.anchor;this.lastClock=time;this.seekTime=time;
      this.blocked='';this.retryAt=0;this.retryMessage='';this.revision=this.getRevision();this.chosen=this.quality.value;this.ratios=[];this.fpsAt=0;
    }
    fail(message){if(this.disposed||this.failed)return;this.failed=true;this.active=false;this.abort.abort();this.video.pause();this.video.removeAttribute('src');this.video.load();if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);this.onState({active:false,text:message+' Standart parça önizlemesi kullanılacak.'});}
    clock(){
      if(!this.enabled){this.video.pause();this.active=false;delete this.c.root.dataset.programClock;return undefined;}
      this.c.root.dataset.programClock='1';this.c.narration?.pause();if(this.c.narration)this.c.narration.muted=true;
      const requested=this.c.getTime();
      if(this.lastClock!==null&&Math.abs(requested-this.lastClock)>1/600){
        if(this.contains(requested)){this.video.currentTime=requested;this.seekTime=requested;}
        else this.reset(requested);
      }
      const result=this.active&&this.positioned?this.video.currentTime:requested;
      this.lastClock=result;return Math.min(result,this.c.data.duration);
    }
    async append(meta,generation){
      const info=await this.c.api(meta.stream_info_url,{signal:this.abort.signal});
      if(generation!==this.generation||this.disposed)return;
      if(!MediaSource.isTypeSupported(info.mime))throw Object.assign(Error('Bu tarayıcı proxy codec’ini desteklemiyor.'),{category:'proxy_fallback'});
      if(!this.source){
        const source=new MediaSource();this.source=source;
        const opened=new Promise((resolve,reject)=>{source.addEventListener('sourceopen',resolve,{once:true});this.abort.signal.addEventListener('abort',()=>reject(Error('cancelled')),{once:true});});
        this.objectUrl=URL.createObjectURL(source);this.video.src=this.objectUrl;await opened;
        if(generation!==this.generation)return;
        this.sourceBuffer=source.addSourceBuffer(info.mime);this.mime=info.mime;
      }
      if(info.mime!==this.mime)throw Object.assign(Error('Parçaların codec profilleri eşleşmiyor.'),{category:'proxy_fallback'});
      const response=await fetch(info.url,{signal:this.abort.signal});if(!response.ok)throw Error('Önizleme parçası alınamadı.');
      const bytes=await response.arrayBuffer();if(generation!==this.generation)return;
      const buffer=this.sourceBuffer,signal=this.abort.signal;
      const update=(action)=>new Promise((resolve,reject)=>{
        const done=()=>{clear();resolve();},error=()=>{clear();reject(Object.assign(Error('Video tamponu eklenemedi.'),{category:'proxy_fallback'}));},cancel=()=>{clear();reject(Error('cancelled'));};
        const clear=()=>{buffer.removeEventListener('updateend',done);buffer.removeEventListener('error',error);signal.removeEventListener('abort',cancel);};
        buffer.addEventListener('updateend',done,{once:true});buffer.addEventListener('error',error,{once:true});signal.addEventListener('abort',cancel,{once:true});
        try{action();}catch(e){clear();reject(e);}
      });
      buffer.timestampOffset=meta.start-info.origin;
      buffer.appendWindowStart=meta.start;buffer.appendWindowEnd=meta.start+meta.duration+.0001;
      await update(()=>buffer.appendBuffer(bytes));if(generation!==this.generation)return;
      if(this.source.readyState==='open'){this.source.duration=this.c.data.duration;if(meta.start+meta.duration>=this.c.data.duration-.001)this.source.endOfStream();}
      // Keep a bounded back buffer while permitting ordinary short backward seeks.
      const cutoff=this.video.currentTime-8;
      if(cutoff>0&&buffer.buffered.length&&buffer.buffered.start(0)<cutoff)await update(()=>buffer.remove(0,cutoff));
    }
    async pump(){
      if(this.pumping||this.failed||this.disposed||!this.enabled||performance.now()<(this.retryAt||0))return;
      this.pumping=true;const generation=this.generation;
      try{
        while(generation===this.generation&&!this.disposed&&this.enabled){
          const desired=this.c.getTime(),limit=this.running?Math.min(this.c.data.duration,desired+Math.max(12,this.warmup())):Math.min(this.c.data.duration,desired+4);
          if(this.next>=limit-.001)break;
          const time=this.next,started=performance.now();
          let meta=await this.c.api(`/api/projects/${this.c.id}/editor/advanced/program-proxy`,{method:'POST',body:JSON.stringify({time,quality:this.chosen}),signal:this.abort.signal});
          const fresh=!meta.cache_hit;
          while(meta.status!=='ready'&&generation===this.generation&&!this.disposed){
            await new Promise(resolve=>setTimeout(resolve,120));if(generation!==this.generation||this.disposed)break;
            meta=await this.c.api(meta.status_url,{signal:this.abort.signal});
          }
          if(generation!==this.generation||this.disposed)return;
          await this.append(meta,generation);if(generation!==this.generation)return;
          if(fresh){this.ratios.push((performance.now()-started)/1000/meta.duration);this.ratios=this.ratios.slice(-3);}
          this.next=meta.start+meta.duration;
        }
      }catch(e){if(generation===this.generation&&!this.disposed){if(e.category==='preview_busy'){this.retryAt=performance.now()+500;this.retryMessage='Önceki önizleme işi tamamlanıyor';}else if(e.category==='proxy_fallback'){this.fail(e.message);}else{this.blocked=e.category?e.message:'Önizleme alınamadı; ses ve görüntü bekletildi. Bağlantıyı kontrol edip kaliteyi yeniden seçin.';this.video.pause();this.started=false;this.c.pause?.();}}}
      finally{this.pumping=false;}
    }
    tick(){
      if(this.failed||this.disposed)return;
      if(!this.enabled){this.video.pause();this.active=false;this.onState({active:false,text:'Örnek kare / kaynak önizlemesi'});return;}
      const desired=this.c.getTime();
      if(this.revision!==this.getRevision()||this.chosen!==this.quality.value)this.reset(desired);
      else if(this.lastClock!==null&&Math.abs(desired-this.lastClock)>1/600){if(this.contains(desired)){this.video.currentTime=desired;this.seekTime=desired;this.lastClock=desired;}else this.reset(desired);}
      if(this.blocked){this.video.pause();this.onState({active:this.active,text:this.blocked});return;}
      this.video.playbackRate=this.c.getPlaybackRate?.()||1;
      this.pump();
      if(!this.positioned&&this.video.readyState>=1&&this.contains(this.seekTime)){this.video.currentTime=this.seekTime;this.positioned=true;}
      this.active=this.positioned&&this.video.readyState>=2;
      const available=this.ahead(),goal=this.warmup();
      if(this.running){
        if(!this.started&&available>=goal-.04&&this.active)this.started=true;
        if(this.started&&this.active&&this.video.paused&&!this.video.ended){this.video.playbackRate=this.c.getPlaybackRate?.()||1;const generation=this.generation;this.video.play().catch(e=>{if(e.name==='AbortError'||generation!==this.generation||!this.running)return;this.fail('Oynat düğmesine yeniden basın: '+e.message);});}
      }else{this.video.pause();this.started=false;if(this.positioned&&Math.abs(this.video.currentTime-desired)>.001)this.video.currentTime=desired;}
      this.video.hidden=!this.active;
      const text=!this.active&&!this.running?'Önizleme hazırlanıyor · duraklatıldı':this.running&&!this.started?`Önizleme hazırlanıyor · ${Math.min(available,goal).toFixed(1)} / ${goal.toFixed(1)} sn · duraklatılabilir`:
        `Kesintisiz proxy · ${this.video.videoWidth||0}×${this.video.videoHeight||0} · ${this.video.paused?'duraklatıldı':this.fps?this.fps.toFixed(1)+' fps':'30 fps hedefi'}`;
      this.onState({active:this.active,text});
    }
    destroy(){this.disposed=true;this.abort.abort();this.generation++;this.video.pause();this.video.removeEventListener('waiting',this.waiting);this.video.removeEventListener('error',this.error);if(this.frameId)this.video.cancelVideoFrameCallback?.(this.frameId);if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);}
  }
  globalThis.NAMANProgramPlayer=ProgramPlayer;
})();
