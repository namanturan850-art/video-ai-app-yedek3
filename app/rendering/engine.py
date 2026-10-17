"""Bounded per-slot commands + small transition pieces + one concat/final pass.

Crossfade handles occupy the start of the next slot; they add no time and never
subtract master-clock frames. All temporary inputs use internally fixed names.
"""
from pathlib import Path
import os
from threading import Lock,RLock
import time
from app.rendering.models import RenderError
from app.rendering.diagnostics import diagnostic
from app.rendering.tools import select_encoder
from app.rendering.files import write
from app.rendering import ass,probe,smart_graph
from app.rendering.parallel import run_parallel
# Scene-change looks (FFmpeg xfade names); anything else falls back to fade.
XFADE_STYLES=('fade','zoomin','smoothleft','smoothright','circleopen','wipeleft')


def default_workers(encoder):
    """NVENC does the heavy lifting on the GPU (a few sessions in parallel); libx264 shares the CPU.
    AVS_RENDER_WORKERS (1-8) overrides this."""
    chosen=os.environ.get('AVS_RENDER_WORKERS','')
    if chosen.isdigit() and 1<=int(chosen)<=8:return int(chosen)
    cpus=os.cpu_count() or 2
    return max(1,min(3,cpus//2)) if encoder=='h264_nvenc' else max(1,min(3,cpus//4))


class FFmpegRenderProvider:
    def __init__(self,tools,runner,progress=lambda *a:None,log=lambda *a:None,workers=None):
        self.tools,self.runner,self.progress,self.log=tools,runner,progress,log
        self.warnings=[];self.counter=0;self.lock=RLock();self.workers=workers;self.timing={}

    def command(self):return [self.tools['ffmpeg'],'-hide_banner','-loglevel','error','-nostdin','-y','-filter_threads','1','-filter_complex_threads','1','-progress','pipe:1','-nostats']

    def codec(self,encoder):
        if encoder=='h264_nvenc':return ['-c:v','h264_nvenc','-preset','p5','-cq','20','-b:v','0','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r','30']
        return ['-c:v','libx264','-preset','medium','-crf','20','-threads','4','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r','30']

    def graph(self,folder,text):
        with self.lock:self.counter+=1;name=f'filter-{self.counter}.txt'
        write(folder/name,text);return ['-/filter_complex',name]

    def render(self,plan):
        requested=plan['options']['encoder'];encoder=select_encoder(requested,self.tools)
        try:return self.attempt(plan,encoder)
        except RenderError as error:
            if error.category!='nvenc_failed' or requested!='auto' or 'libx264' not in self.tools['encoders']:raise
            self.warnings.append('NVIDIA NVENC başlatılamadı; aynı render görevi bir kez CPU / libx264 ile yeniden deneniyor.')
            self.log('nvenc_initialization_failed_cpu_retry')
            # Same job/version, no recursive fallback and no retry for other failures.
            return self.attempt(plan,'libx264')

    def pieces_in_parallel(self,encoder,count):
        """How many slot encodes run at once (1 = one after another, e.g. test runners without spawn())."""
        if not hasattr(self.runner,'spawn'):return 1
        return max(1,min(self.workers or default_workers(encoder),count))

    def decorative(self,code,**context):
        phase={'adaptive_layout_failed':'adaptive_layout','smart_motion_failed':'smart_motion','smart_transition_failed':'smart_transition','emphasis_render_failed':'emphasis_render'}[code]
        safe=diagnostic(code,phase=phase,**context)
        getattr(self.runner,'diagnostic_callback',lambda value:None)(safe)
        self.log(code)

    def attempt(self,plan,encoder):
        folder=plan['temporary'];timeline=plan['timeline'];duration=timeline['duration'];slots=timeline['slots'];opts=plan['options']
        opts=dict(opts)
        edit=plan.get('smart_edit_plan');style=edit['editing_style'] if edit else 'basic';smart=style!='basic' and edit is not None
        mode=opts.get('subtitle_display') or 'full'  # full subtitles (every sentence, bottom centre) unless the owner chose otherwise
        opts['subtitle_burned']=mode=='full'
        edits={item['slot_id']:item for item in edit['slots']} if edit else {}
        advanced=plan.get('advanced_document') or {}
        custom_transitions={item['slot_id']:item for item in advanced.get('transitions',[])}
        custom_adjustments={item['slot_id']:item for item in advanced.get('adjustments',[])}
        emphasis=list(edit['emphasis']) if smart else None
        applied={'motion_effects':0,'scene_transitions':0,'emphasis_texts':0,'internal_edits':0};transitions=set()
        if style=='adaptive':
            from app.rendering import adaptive
            applied.update(adaptive_texts=0,layouts={name:0 for name in adaptive.LAYOUTS},layout_failures=0,graphic_seconds=0.)
        self.progress('preparing',2,encoder,self.warnings)
        if opts['subtitle_burned'] and 'ass' not in self.tools['filters']:
            raise RenderError('subtitle_invalid','Bu FFmpeg sürümü altyazı yazmayı desteklemiyor. Altyazı seçimini kapatın veya libass destekli FFmpeg kullanın.',diagnostic=diagnostic('subtitle_filter_failed',phase='subtitle_preflight',encoder=encoder))
        kit=plan.get('style_kit') or {};sub_style=kit.get('subtitle')
        fontsdir='';graphic_style=None
        from app.channels import FONTS
        if kit.get('palette'):
            # Emphasis texts drawn as graphics in the look's colours and heading font.
            graphic_style={**{k:kit['palette'][k] for k in ('background','accent','primary')},'font':FONTS[kit.get('heading_font','arial')][0]}
        for font in {f for f in ((sub_style or {}).get('font'),kit.get('heading_font') if graphic_style else None) if f and f!='arial'}:
            # Bundled OFL font next to the ASS file; libass reads it via fontsdir.
            import shutil
            (folder/'fonts').mkdir(exist_ok=True)
            shutil.copyfile(Path(__file__).resolve().parent.parent/'static'/'fonts'/FONTS[font][1],folder/'fonts'/FONTS[font][1])
            fontsdir=':fontsdir=fonts'
        assf=lambda name:f'ass=filename={name}{fontsdir}'
        timed=[{**s,**next(m for m in timeline['editing_scenes'] if m['scene_id']==s['scene_id'])} for s in timeline['scenes']]
        for scene,original in zip(timed,timeline['scenes']):scene.update(start=original['start'],end=original['end'])
        replaced_texts=[(s['start'],s['end'],s.get('overlay_text')) for s in timed if s['scene_id']+':overlay_text' in advanced.get('suppressed_layers',[])]
        for scene in timed:
            if scene['scene_id'] in advanced.get('suppressed_scenes',[]) or scene['scene_id']+':overlay_text' in advanced.get('suppressed_layers',[]):scene['overlay_text']=''
        if emphasis and advanced.get('suppressed_scenes'):
            hidden=[s for s in timed if s['scene_id'] in advanced['suppressed_scenes']]
            emphasis=[item for item in emphasis if not any(s['start']<=item.get('start',-1)<s['end'] for s in hidden)]
        if emphasis and replaced_texts:
            emphasis=[item for item in emphasis if not any(a<=item.get('start',-1)<b and item.get('text')==text for a,b,text in replaced_texts)]
        try:content,warnings,has_text=ass.create(plan['handoff']['subtitles'],timed,duration,subtitles=opts['subtitle_burned'],overlays=mode!='none' and 'ass' in self.tools['filters'],editing_style=style,subtitle_style=sub_style,graphic_style=graphic_style,emphasis=emphasis)
        except RenderError as error:
            raise RenderError(error.category,str(error),diagnostic=diagnostic('subtitle_filter_failed',phase='subtitle_preflight',encoder=encoder)) from None
        self.warnings+=warnings;caption_name=None
        if has_text:
            self.counter+=1;caption_name=f'captions-{self.counter}.ass';write(folder/caption_name,content)
            # One local frame checks libass/file syntax before any expensive slot encode.
            args=self.command()+['-f','lavfi','-i','color=s=1920x1080:r=30:d=0.04','-vf',assf(caption_name),'-frames:v','1','-an','-f','null','-']
            try:self.runner.run(args,folder,phase='subtitle_preflight')
            except RenderError as error:
                if not smart or not emphasis or error.category!='render_failed':raise
                self.decorative('emphasis_render_failed',encoder=encoder)
                self.warnings.append('Vurgu yazısı ön kontrolü başarısız; yalnız mevcut altyazılar kullanılıyor.')
                emphasis=[]
                content,_,has_text=ass.create(plan['handoff']['subtitles'],timed,duration,subtitles=opts['subtitle_burned'],overlays=mode!='none',editing_style=style,subtitle_style=sub_style,graphic_style=graphic_style,emphasis=[])
                self.counter+=1;caption_name=f'captions-{self.counter}.ass';write(folder/caption_name,content)
                args[args.index('-vf')+1]=assf(caption_name)
                if has_text:self.runner.run(args,folder,phase='subtitle_preflight')
        incoming=[0]*len(slots);outgoing=[0]*len(slots);fades=[0.]*len(slots)
        for i,slot in enumerate(slots[:-1]):
            # Same scene: hard cut, except a motion graphic sliding in/out.
            custom=custom_transitions.get(slot['slot_id'])
            if slot['scene_id']==slots[i+1]['scene_id'] and not custom and not (smart and edits[slot['slot_id']].get('transition_style') in ('smoothleft','smoothright')):continue
            transition=edits[slot['slot_id']]['transition_out'] if smart else slot['editing']['transition']
            if custom:transition={'cut':'hard_cut','cross_dissolve':'crossfade','dip_black':'dip_black','wipe':'crossfade'}[custom['kind']]
            if transition=='crossfade':
                desired=round(edits[slot['slot_id']]['transition_duration']*30) if smart else 10
                if custom:desired=round(custom['duration']*30)
                frames=min(desired,slot['frames']//4,slots[i+1]['frames']//4)
                if frames>=2 and 'xfade' in self.tools['filters']:outgoing[i]=incoming[i+1]=frames
                else:self.warnings.append('Kısa veya desteklenmeyen sahne geçişi temiz kesmeye dönüştürüldü.')
            elif transition in ('fade','fade_dark','dip_black'):
                if 'fade' in self.tools['filters'] and min(slot['frames'],slots[i+1]['frames'])>=4:
                    fades[i]=custom['duration']/2 if custom else edits[slot['slot_id']]['transition_duration']/2 if smart else .15;transitions.add(i)
                else:self.warnings.append('Desteklenmeyen kısa fade geçişi temiz kesmeye dönüştürüldü.')
        done=[0.]*len(slots);gate=Lock()
        def report(i,frames):
            with gate:
                done[i]=max(done[i],frames);total=sum(done)
            self.progress('rendering',min(70,8+62*total/timeline['frames']),encoder,self.warnings)
        def bump(key,amount=1):
            with self.lock:applied[key]+=amount

        def slot_job(i,slot,runner):
            count=slot['frames'];total=count+outgoing[i];length=total/30
            media=plan['media'][slot['slot_id']];args=self.command()
            speed=custom_adjustments.get(slot['slot_id'],{}).get('transform',{}).get('speed',1)
            context={'slot_index':i,'slot_id':slot['slot_id'],'slot_count':len(slots),'media_type':media['type'],'encoder':encoder}
            actual=probe.stock(self.tools['ffprobe'],media['path'],media['type'],**{k:v for k,v in context.items() if k!='media_type'})
            if actual is None:
                # ffprobe remains optional: verify actual decoding when unavailable.
                runner.run(self.command()+['-i',str(media['path']),'-map','0:v:0','-frames:v','1','-an','-f','null','-'],folder,phase='input_preflight',**context)
                self.warnings.append('ffprobe bulunamadı; stok medya dekodu kontrol edildi ancak kaynak boyutu ve süresi ön kontrolde ölçülemedi.')
            if media['type']=='video':
                source_duration=actual['stock_duration'] if actual else media.get('duration') or 0
                planned=edits.get(slot['slot_id'],{})
                seek=min(max(0,planned.get('source_in',media.get('segment_start',max(0,(source_duration-length*speed)/2)))),max(0,source_duration-length*speed))
                if slot['slot_id'] in custom_adjustments:
                    seek=max(0,media.get('segment_start',0.))
                # The final source-audio mixer must use the identical decoded cut.
                media['segment_start']=seek
                # Legacy short assets remain playable; newly acquired normal
                # B-roll has strict coverage and is never sped up or looped.
                loop=['-stream_loop','-1'] if source_duration<count/30-.04 else []
                decode_length=length*speed+.1 if not loop else length*speed
                args+=loop+['-ss',f'{seek:.6f}','-t',f'{decode_length:.6f}','-i',str(media['path'])]
            else:args+=['-loop','1','-framerate','30','-t',f'{length:.6f}','-i',str(media['path'])]
            normalize='scale=1920:1080:force_original_aspect_ratio=increase:out_range=tv,crop=1920:1080,setsar=1,fps=30,format=yuv420p'
            # A 25fps seek near EOF can otherwise yield one fewer 30fps frame.
            # Prefetch where possible; this bounded EOF pad supplies only frame
            # alignment/transition handles, never fills an undersized new clip.
            if media['type']=='video' and not loop:normalize+=f',tpad=stop_mode=clone:stop_duration={outgoing[i]/30+.1:.6f}'
            portrait=bool(actual and next((s['width']<=s['height'] for s in actual.get('streams',[]) if s.get('codec_type')=='video'),False))
            if portrait or edits.get(slot['slot_id'],{}).get('fit')=='contain':
                # Portrait/square source in a 16:9 video: sharp centre over a
                # blurred, darkened full-frame copy of itself (no black bars).
                normalize=('split=2[bgsrc][fgsrc];[bgsrc]scale=1920:1080:force_original_aspect_ratio=increase:out_range=tv,crop=1920:1080,gblur=sigma=28,eq=brightness=-0.12[bg];'
                           '[fgsrc]scale=1920:1080:force_original_aspect_ratio=decrease:out_range=tv[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p')
                # overlay ends one frame early at EOF; clone the last frame so
                # frame-exact trims below still get every frame.
                normalize+=f',tpad=stop_mode=clone:stop_duration={(outgoing[i]/30 if media["type"]=="video" and not loop else 0)+.1:.6f}'
            if speed!=1:normalize=f'setpts=(PTS-STARTPTS)/{speed},'+normalize
            motion=slot['editing']['motion']
            if not smart and media['type']=='image' and motion in ('slow_zoom','ken_burns','pan'):
                if 'zoompan' not in self.tools['filters']:self.warnings.append('Görsel hareketi desteklenmiyor; durağan görsel kullanıldı.')
                else:
                    if motion=='pan':z='1.04';x=f'(iw-iw/zoom)*min(on/{max(total-1,1)},1)'
                    else:z=f'min(1.05,1+on*0.05/{max(total-1,1)})';x='iw/2-iw/zoom/2'
                    normalize+=f",scale=3840:2160,zoompan=z='{z}':x='{x}':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30"
            normalize+=',setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,settb=1/30,setpts=PTS-STARTPTS'
            parts=[('core',incoming[i],count)]
            if incoming[i]:parts.append(('head',0,incoming[i]))
            if outgoing[i]:parts.append(('tail',count,total))
            smart_slot=edits.get(slot['slot_id']) if smart else None
            decorate=True
            if smart_slot and any(x['motion_effect']!='none' for x in smart_slot['segments']) and 'perspective' not in self.tools['filters']:
                decorate=False;self.decorative('smart_motion_failed',**context)
                self.warnings.append('Akıllı kamera hareketi bu FFmpeg sürümünde desteklenmiyor; normal kadraj kullanıldı.')
            layout_graph=None
            if style=='adaptive' and smart_slot and smart_slot.get('layout')!='full_broll' and decorate:
                if 'ass' not in self.tools['filters']:
                    bump('layout_failures');self.warnings.append('Görsel düzen desteklenmiyor; B-roll korunuyor.')
                else:
                    secondary=smart_slot.get('secondary_slot_id')
                    if secondary:
                        second=plan['media'].get(secondary)
                        if second:
                            args+=(['-stream_loop','-1'] if second['type']=='video' else ['-loop','1','-framerate','30'])+['-t',f'{length:.6f}','-i',str(second['path'])]
                    name=f'layout-{i}.ass';write(folder/name,adaptive.captions(smart_slot,edit['theme'],graphic_style))
                    layout_graph=adaptive.graph(smart_slot,edit['theme'],name,graphic_style,fontsdir)
            graph=smart_graph.slot_graph(normalize,parts,i,incoming,outgoing,fades,smart_slot,emphasis or (),decorate=decorate,layout_graph=layout_graph)
            graph_index=len(args)
            args+=self.graph(folder,graph.rstrip(';\n'))
            for name,start,end in parts:args+=['-map',f'[{name}]','-an',*self.codec(encoder),'-frames:v',str(end-start),f'{name}-{i}.mp4']
            report(i,0)
            callback=lambda seconds:report(i,min(count,seconds*30))
            try:runner.run(args,folder,callback,phase='slot_render',**context)
            except RenderError as error:
                has_motion=smart_slot and any(x['motion_effect']!='none' for x in smart_slot['segments'])
                if media.get('was_graphic'):raise
                if not smart or not decorate or error.category!='render_failed' or not (has_motion or layout_graph or fades[i] or (i and fades[i-1])):raise
                self.decorative('adaptive_layout_failed' if layout_graph else 'smart_motion_failed' if has_motion else 'smart_transition_failed',**context)
                self.warnings.append('Bir dekoratif klip efekti uygulanamadı; aynı medya ve süre normal kadrajla korundu.')
                if layout_graph:bump('layout_failures')
                decorate=False
                graph=smart_graph.slot_graph(normalize,parts,i,incoming,outgoing,fades,decorate=False)
                retry=args[:graph_index]+self.graph(folder,graph)+args[graph_index+2:]
                runner.run(retry,folder,callback,phase='slot_render',**context)
            if smart_slot and decorate:
                bump('motion_effects',int(any(x['motion_effect']!='none' for x in smart_slot['segments'])))
                bump('internal_edits',len(smart_slot['segments'])-1)
            elif not smart and media['type']=='image' and motion in ('slow_zoom','ken_burns','pan') and 'zoompan' in self.tools['filters']:bump('motion_effects')
            if not decorate:
                for boundary in (i-1,i):
                    if boundary>=0:
                        with self.lock:transitions.discard(boundary);fades[boundary]=0.
            if style=='adaptive':
                actual_layout=smart_slot['layout'] if layout_graph and decorate else 'full_broll'
                with self.lock:applied['layouts'][actual_layout]+=1
                if actual_layout!='full_broll':
                    bump('adaptive_texts',len(smart_slot['texts']))
                    bump('graphic_seconds',smart_slot['layout_window']['end']-smart_slot['layout_window']['start'])
            report(i,count)
        slot_started=time.monotonic()
        workers=self.pieces_in_parallel(encoder,len(slots))
        run_parallel(len(slots),lambda i,runner:slot_job(i,slots[i],runner),workers,self.runner)
        self.timing={'slot_seconds':round(time.monotonic()-slot_started,1),'parallel_pieces':workers}
        assembly=[]
        for i,slot in enumerate(slots):
            if incoming[i]:
                d=incoming[i]/30;transition=f'transition-{i}.mp4'
                args=self.command()+['-i',f'tail-{i-1}.mp4','-i',f'head-{i}.mp4']
                # N frames occur at 0 .. (N-1)/30. Reach the second clip on the
                # final handle frame, not one frame after the handle ends.
                blend=(incoming[i]-1)/30 if smart or slots[i-1]['slot_id'] in custom_transitions else d
                xstyle=edits[slots[i-1]['slot_id']].get('transition_style','fade') if smart else 'fade'
                if custom_transitions.get(slots[i-1]['slot_id'],{}).get('kind')=='wipe':xstyle='wipeleft'
                if xstyle not in XFADE_STYLES:xstyle='fade'
                graph=f'[0:v]settb=1/30,setpts=N/(30*TB),fps=30[a];[1:v]settb=1/30,setpts=N/(30*TB),fps=30[b];[a][b]xfade=transition={xstyle}:duration={blend:.6f}:offset=0,format=yuv420p,settb=1/30,setpts=N/(30*TB),fps=30[v]'
                args+=self.graph(folder,graph)+['-map','[v]','-an',*self.codec(encoder),'-frames:v',str(incoming[i]),transition]
                try:
                    self.runner.run(args,folder,encoder=encoder,phase='crossfade',slot_index=i,slot_id=slot['slot_id'],slot_count=len(slots),media_type=plan['media'][slot['slot_id']]['type']);assembly.append(transition);transitions.add(i-1)
                except RenderError as error:
                    if error.category!='render_failed':raise
                    if smart:self.decorative('smart_transition_failed',encoder=encoder,slot_index=i,slot_id=slot['slot_id'],slot_count=len(slots))
                    self.warnings.append('Bir crossfade uygulanamadı; aynı süre korunarak temiz kesme kullanıldı.')
                    assembly.append(f'head-{i}.mp4')
            assembly.append(f'core-{i}.mp4')
        concat='ffconcat version 1.0\n'+''.join(f"file '{name}'\n" for name in assembly)
        self.counter+=1;manifest=f'assembly-{self.counter}.ffconcat';write(folder/manifest,concat)
        if 'ass' not in self.tools['filters'] and any(s.get('overlay_text') for s in timed):self.warnings.append('Vurgu yazıları desteklenmiyor; atlandı.')
        args=self.command()+['-f','concat','-safe','1','-i',manifest,'-i',str(plan['audio'])]
        vf='[0:v]null'
        if has_text:
            vf+=','+assf(caption_name)
        mix=plan.get('audio_settings') or {}
        narration_volume=min(2.,max(0.,float(mix.get('narration_volume',1.))))
        narration_fade_in=min(duration/2,max(0.,float(mix.get('narration_fade_in',0.))))
        narration_fade_out=min(duration/2,max(0.,float(mix.get('narration_fade_out',0.))))
        graph=vf+'[v];\n'+f'[1:a]aresample=48000,apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,volume={narration_volume:.6f}'
        if narration_fade_in:graph+=f',afade=t=in:st=0:d={narration_fade_in:.6f}'
        if narration_fade_out:graph+=f',afade=t=out:st={duration-narration_fade_out:.6f}:d={narration_fade_out:.6f}'
        graph+='[nar]'
        if opts['music_enabled']:
            args+=['-stream_loop','-1','-i',str(plan['music'])]
            fi=min(opts['music_fade_in'],duration/2);fo=min(opts['music_fade_out'],duration/2)
            graph+=f';\n[2:a]aresample=48000,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,volume={opts["music_volume"]:.6f}'
            if fi:graph+=f',afade=t=in:st=0:d={fi:.6f}'
            if fo:graph+=f',afade=t=out:st={duration-fo:.6f}:d={fo:.6f}'
            graph+='[music];\n'
            if opts['music_ducking'] and 'sidechaincompress' in self.tools['filters']:
                graph+='[nar]asplit[voice][side];[music][side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250[duck];[voice][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98:level=false[a]'
            else:
                if opts['music_ducking']:self.warnings.append('Ducking desteklenmiyor; düşük ses seviyeli müzik karışımı kullanıldı.')
                graph+='[nar][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98:level=false[a]'
        else:graph+=';\n[nar]anull[a]'
        events=[cut_aligned(e,slots,incoming) for e in (plan.get('sfx') or {}).get('events',[])]
        events=[e for e in events if 0<=e['t']<duration]
        if events:
            # Kit sound effects at the motion emphasis moments: added UNDER the
            # narration at a low, fixed level. Master the narration/music first:
            # loudnorm after this mix would amplify effects during silent speech.
            graph=master(graph,self.tools['filters'])
            graph=graph[::-1].replace(']a[',']0a[',1)[::-1]
            first=len([a for a in args if a=='-i'])
            for k,e in enumerate(events):
                volume=min(.5,max(0.,float(e.get('level',plan['sfx'].get('volume',.18)))))
                args+=['-i',e['path']];delay=int(round(e['t']*1000))
                graph+=f';\n[{first+k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={volume:.3f},adelay={delay}|{delay}[fx{k}]'
            graph+=';\n'+''.join(f'[fx{k}]' for k in range(len(events)))+(f'amix=inputs={len(events)}:duration=longest:normalize=0' if len(events)>1 else 'anull')+'[fxall]'
            graph+=';\n[a0]aformat=channel_layouts=stereo[a1];[a1][fxall]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98:level=false[a]'
            applied['sound_effects']=len(events)
        else:
            graph=master(graph,self.tools['filters'])
        if advanced:
            from app.editor.compositor import compile_graph
            assets={**plan['media'],**dict(plan.get('advanced_assets') or {})}
            for clip in advanced.get('clips',[]):
                if clip['visible'] and clip['kind']=='motion':
                    from app.motion.clips import render_clip
                    path,_,_=render_clip(plan['advanced_stock'],{**clip['motion'],'local_only':True},plan.get('style_kit') or {},clip['end']-clip['start'],0,prefer_openmontage=False,cancelled=self.runner.event.is_set if hasattr(self.runner,'event') else None)
                    assets[clip['id']]={'path':path,'type':'video','has_audio':False}
            prefix,video_label,extra_audio=compile_graph(args,advanced,assets,folder=folder,duration=duration,adjustment_slots=plan.get('advanced_slots'))
            if prefix:graph=prefix+';\n'+graph.replace('[0:v]null',f'[{video_label}]null',1)
            if extra_audio:
                graph=graph.replace('[a]','[adv_master]',1)
                graph+=';\n[adv_master]'+''.join(f'[{a}]' for a in extra_audio)+f'amix=inputs={len(extra_audio)+1}:duration=first:normalize=0,alimiter=limit=0.84:level=false[a]'
        args+=self.graph(folder,graph)+['-map','[v]','-map','[a]',*self.codec(encoder),'-frames:v',str(timeline['frames']),
            '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{duration:.6f}','-movflags','+faststart','output.mp4']
        final_started=time.monotonic();self.progress('rendering',75,encoder,self.warnings)
        callback=lambda seconds:self.progress('rendering',min(95,75+20*seconds/duration),encoder,self.warnings)
        try:self.runner.run(args,folder,callback,encoder=encoder,phase='final_assembly')
        except RenderError as error:
            if not smart or not emphasis or not has_text or error.category!='render_failed':raise
            self.decorative('emphasis_render_failed',encoder=encoder)
            self.warnings.append('Son birleştirmede vurgu yazısı atlandı; mevcut altyazı/ses zamanları korundu.')
            emphasis=[]
            content,_,subtitles_remain=ass.create(plan['handoff']['subtitles'],timed,duration,subtitles=opts['subtitle_burned'],overlays=mode!='none',editing_style=style,subtitle_style=sub_style,graphic_style=graphic_style,emphasis=[])
            previous_caption=caption_name
            self.counter+=1;caption_name=f'captions-{self.counter}.ass';write(folder/caption_name,content)
            graph=graph.replace(assf(previous_caption),assf(caption_name))
            if not subtitles_remain:
                # The ASS file remains a valid empty track; removing only its node
                # keeps the audio graph and all master timestamps unchanged.
                graph=graph.replace(','+assf(caption_name),'')
            graph_index=args.index('-/filter_complex');args[graph_index:graph_index+2]=self.graph(folder,graph)
            self.runner.run(args,folder,callback,encoder=encoder,phase='final_assembly')
        self.timing['final_seconds']=round(time.monotonic()-final_started,1)
        self.progress('validating',96,encoder,self.warnings)
        output=folder/'output.mp4'
        try:validated=probe.validate(self.tools['ffprobe'],output,duration)
        except RenderError as error:
            raise RenderError(error.category,str(error),diagnostic=diagnostic('output_validation_failed',phase='output_validation',encoder=encoder)) from None
        if validated is None:
            # Without ffprobe verify both streams actually decode and the measured end.
            cmd=self.command()+['-i','output.mp4','-map','0:v:0','-map','0:a:0','-f','null','-']
            end=self.runner.run(cmd,folder,phase='output_decode_validation',encoder=encoder)
            if abs(end-duration)>.04:raise RenderError('output_invalid','Video süresi yerel dekod kontrolünde eşleşmedi.',diagnostic=diagnostic('output_validation_failed',phase='output_decode_validation',encoder=encoder))
            validated={'duration':duration,'width':1920,'height':1080,'fps':30,'video_codec':'h264','audio_codec':'aac','validation_method':'ffmpeg_decode_configured_format'}
            self.warnings.append('ffprobe bulunamadı; akışlar ve süre FFmpeg dekoduyla kontrol edildi. Biçim alanları render ayarlarından alınmıştır.')
        applied['scene_transitions']=len(transitions)
        if advanced:
            validated['advanced_editor']={'schema_version':advanced['schema_version'],'clips':len(advanced['clips']),
                'adjustments':len(advanced['adjustments']),'transitions':len(advanced['transitions']),
                'keyframes':sum(len(x['keyframes']) for x in advanced['clips']+advanced['adjustments'])}
        applied['emphasis_texts']=len(emphasis or ()) if smart and 'ass' in self.tools['filters'] else len(edit['emphasis']) if edit and 'ass' in self.tools['filters'] else sum(bool(x.get('overlay_text')) for x in timed) if mode!='none' and 'ass' in self.tools['filters'] else 0
        if style=='adaptive':
            applied['emphasis_texts']=applied['adaptive_texts'];applied['graphic_seconds']=round(applied['graphic_seconds'],3)
            applied['broll_seconds']=round(duration-applied['graphic_seconds'],3)
        validated.update(subtitle_display=mode,edit_variation_seed=edit.get('edit_variation_seed') if edit else None,editing_style=style,smart_edit_applied_summary=applied,encoder_used=encoder,render_timing={**self.timing,'engine':'ffmpeg','slots':len(slots)},subtitle_burned=opts['subtitle_burned'],music_enabled=opts['music_enabled'],warnings=list(dict.fromkeys(self.warnings)))
        return {'path':output,'metadata':validated}


def cut_aligned(event,slots,incoming):
    """A transition whoosh moved so its loudest moment is the visible cut of the
    rendered timeline: the slot's end, plus half of the crossfade really used."""
    if event.get('sound')!='whoosh' or not event.get('slot_id'):return event
    i=next((k for k,s in enumerate(slots) if s['slot_id']==event['slot_id']),None)
    if i is None:return event
    blend=incoming[i+1]/30 if i+1<len(slots) else 0.
    return {**event,'t':round(max(0.,slots[i]['end_frame']/30+blend/2-float(event.get('peak') or 0)),3)}


# Every render: about -14 LUFS, true peak at most -1 dBTP (limiter ceiling -1.5 dBFS leaves room for AAC).
LOUDNESS='loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.84:attack=5:release=50:level=false'


def master(graph,filters):
    """The final [a] goes through the loudness/peak stage (limiter only when loudnorm is missing)."""
    at=graph.rfind('[a]')
    if at<0:return graph
    stage=LOUDNESS if 'loudnorm' in filters else 'alimiter=limit=0.84:level=false'
    return graph[:at]+'[premaster]'+graph[at+3:]+f';\n[premaster]{stage}[a]'
