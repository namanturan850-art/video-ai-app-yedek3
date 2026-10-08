"""Bounded per-slot commands + small transition pieces + one concat/final pass.

Crossfade handles occupy the start of the next slot; they add no time and never
subtract master-clock frames. All temporary inputs use internally fixed names.
"""
from pathlib import Path
from app.rendering.models import RenderError
from app.rendering.tools import select_encoder
from app.rendering.files import write
from app.rendering import ass,probe


class FFmpegRenderProvider:
    def __init__(self,tools,runner,progress=lambda *a:None,log=lambda *a:None):
        self.tools,self.runner,self.progress,self.log=tools,runner,progress,log
        self.warnings=[];self.counter=0

    def command(self):return [self.tools['ffmpeg'],'-hide_banner','-loglevel','error','-nostdin','-y','-filter_threads','1','-filter_complex_threads','1','-progress','pipe:1','-nostats']

    def codec(self,encoder):
        if encoder=='h264_nvenc':return ['-c:v','h264_nvenc','-preset','p5','-cq','20','-b:v','0','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r','30']
        return ['-c:v','libx264','-preset','medium','-crf','20','-threads','4','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r','30']

    def graph(self,folder,text):
        self.counter+=1;name=f'filter-{self.counter}.txt';write(folder/name,text);return ['-filter_complex_script',name]

    def render(self,plan):
        requested=plan['options']['encoder'];encoder=select_encoder(requested,self.tools)
        try:return self.attempt(plan,encoder)
        except RenderError as error:
            if error.category!='nvenc_failed' or requested!='auto' or 'libx264' not in self.tools['encoders']:raise
            self.warnings.append('NVIDIA NVENC başlatılamadı; aynı render görevi bir kez CPU / libx264 ile yeniden deneniyor.')
            self.log('nvenc_initialization_failed_cpu_retry')
            # Same job/version, no recursive fallback and no retry for other failures.
            return self.attempt(plan,'libx264')

    def attempt(self,plan,encoder):
        folder=plan['temporary'];timeline=plan['timeline'];duration=timeline['duration'];slots=timeline['slots'];opts=plan['options']
        self.progress('preparing',2,encoder,self.warnings)
        if opts['subtitle_burned'] and 'ass' not in self.tools['filters']:
            raise RenderError('subtitle_invalid','Bu FFmpeg sürümü altyazı yazmayı desteklemiyor. Altyazı seçimini kapatın veya libass destekli FFmpeg kullanın.')
        incoming=[0]*len(slots);outgoing=[0]*len(slots);fades=[False]*len(slots)
        for i,slot in enumerate(slots[:-1]):
            if slot['scene_id']==slots[i+1]['scene_id']:continue
            transition=slot['editing']['transition']
            if transition=='crossfade':
                frames=min(10,slot['frames']//4,slots[i+1]['frames']//4)
                if frames>=2 and 'xfade' in self.tools['filters']:outgoing[i]=incoming[i+1]=frames
                else:self.warnings.append('Kısa veya desteklenmeyen sahne geçişi temiz kesmeye dönüştürüldü.')
            elif transition=='fade':
                if 'fade' in self.tools['filters'] and min(slot['frames'],slots[i+1]['frames'])>=4:fades[i]=True
                else:self.warnings.append('Desteklenmeyen kısa fade geçişi temiz kesmeye dönüştürüldü.')
        completed=0
        for i,slot in enumerate(slots):
            count=slot['frames'];total=count+outgoing[i];length=total/30
            media=plan['media'][slot['slot_id']];args=self.command();actual=probe.metadata(self.tools['ffprobe'],media['path'])
            video=next((s for s in actual['streams'] if s.get('codec_type')=='video'),None) if actual else None
            if actual and not video:raise RenderError('input_invalid','Seçili stok dosyasında görsel/video akışı bulunamadı.')
            if media['type']=='video':
                source_duration=float(actual.get('format',{}).get('duration',media.get('duration') or 0)) if actual else media.get('duration') or 0
                seek=max(0,(source_duration-length)/2) if source_duration>length else 0
                args+=['-stream_loop','-1','-ss',f'{seek:.6f}','-t',f'{length:.6f}','-i',str(media['path'])]
            else:args+=['-loop','1','-framerate','30','-t',f'{length:.6f}','-i',str(media['path'])]
            normalize='scale=1920:1080:force_original_aspect_ratio=increase:out_range=tv,crop=1920:1080,setsar=1,fps=30,format=yuv420p'
            motion=slot['editing']['motion']
            if media['type']=='image' and motion in ('slow_zoom','ken_burns','pan'):
                if 'zoompan' not in self.tools['filters']:self.warnings.append('Görsel hareketi desteklenmiyor; durağan görsel kullanıldı.')
                else:
                    if motion=='pan':z='1.04';x=f'(iw-iw/zoom)*min(on/{max(total-1,1)},1)'
                    else:z=f'min(1.05,1+on*0.05/{max(total-1,1)})';x='iw/2-iw/zoom/2'
                    normalize+=f",scale=3840:2160,zoompan=z='{z}':x='{x}':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30"
            normalize+=',setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,settb=1/30,setpts=PTS-STARTPTS'
            parts=[('core',incoming[i],count)]
            if incoming[i]:parts.append(('head',0,incoming[i]))
            if outgoing[i]:parts.append(('tail',count,total))
            labels=''.join(f'[p{j}]' for j in range(len(parts)))
            graph=f'[0:v]{normalize},split={len(parts)}{labels};\n'
            for j,(name,start,end) in enumerate(parts):
                extra=''
                if name=='core':
                    if i and fades[i-1]:extra+=f',fade=t=in:st=0:d={min(.15,(end-start)/90):.6f}'
                    if fades[i]:extra+=f',fade=t=out:st={max(0,(end-start)/30-.15):.6f}:d={min(.15,(end-start)/90):.6f}'
                graph+=f'[p{j}]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS{extra}[{name}];\n'
            args+=self.graph(folder,graph.rstrip(';\n'))
            for name,start,end in parts:args+=['-map',f'[{name}]','-an',*self.codec(encoder),'-frames:v',str(end-start),f'{name}-{i}.mp4']
            self.progress('rendering',8+62*completed/timeline['frames'],encoder,self.warnings)
            self.runner.run(args,folder,lambda seconds:self.progress('rendering',min(70,8+62*(completed+min(count,seconds*30))/timeline['frames']),encoder,self.warnings),encoder=encoder)
            completed+=count
        assembly=[]
        for i,slot in enumerate(slots):
            if incoming[i]:
                d=incoming[i]/30;transition=f'transition-{i}.mp4'
                args=self.command()+['-i',f'tail-{i-1}.mp4','-i',f'head-{i}.mp4']
                graph=f'[0:v]settb=1/30,setpts=PTS-STARTPTS,fps=30[a];[1:v]settb=1/30,setpts=PTS-STARTPTS,fps=30[b];[a][b]xfade=transition=fade:duration={d:.6f}:offset=0,format=yuv420p[v]'
                args+=self.graph(folder,graph)+['-map','[v]','-an',*self.codec(encoder),'-frames:v',str(incoming[i]),transition]
                try:self.runner.run(args,folder,encoder=encoder);assembly.append(transition)
                except RenderError as error:
                    if error.category!='render_failed':raise
                    self.warnings.append('Bir crossfade uygulanamadı; aynı süre korunarak temiz kesme kullanıldı.')
                    assembly.append(f'head-{i}.mp4')
            assembly.append(f'core-{i}.mp4')
        concat='ffconcat version 1.0\n'+''.join(f"file '{name}'\n" for name in assembly)
        self.counter+=1;manifest=f'assembly-{self.counter}.ffconcat';write(folder/manifest,concat)
        timed=[{**s,**next(m for m in timeline['editing_scenes'] if m['scene_id']==s['scene_id'])} for s in timeline['scenes']]
        # Timings MUST come from Part 8, not editing metadata's estimates.
        for scene,original in zip(timed,timeline['scenes']):scene.update(start=original['start'],end=original['end'])
        content,warnings,has_text=ass.create(plan['handoff']['subtitles'],timed,duration,subtitles=opts['subtitle_burned'],overlays='ass' in self.tools['filters'])
        self.warnings+=warnings
        if 'ass' not in self.tools['filters'] and any(s.get('overlay_text') for s in timed):self.warnings.append('Vurgu yazıları desteklenmiyor; atlandı.')
        args=self.command()+['-f','concat','-safe','1','-i',manifest,'-i',str(plan['audio'])]
        vf='[0:v]null'
        if has_text:
            self.counter+=1;name=f'captions-{self.counter}.ass';write(folder/name,content);vf+=f",ass=filename={name}"
        graph=vf+'[v];\n'+f'[1:a]aresample=48000,apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[nar]'
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
        args+=self.graph(folder,graph)+['-map','[v]','-map','[a]',*self.codec(encoder),'-frames:v',str(timeline['frames']),
            '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{duration:.6f}','-movflags','+faststart','output.mp4']
        self.progress('rendering',75,encoder,self.warnings)
        self.runner.run(args,folder,lambda seconds:self.progress('rendering',min(95,75+20*seconds/duration),encoder,self.warnings),encoder=encoder)
        self.progress('validating',96,encoder,self.warnings)
        output=folder/'output.mp4';validated=probe.validate(self.tools['ffprobe'],output,duration)
        if validated is None:
            # Without ffprobe verify both streams actually decode and the measured end.
            cmd=self.command()+['-i','output.mp4','-map','0:v:0','-map','0:a:0','-f','null','-']
            end=self.runner.run(cmd,folder)
            if abs(end-duration)>.04:raise RenderError('output_invalid','Video süresi yerel dekod kontrolünde eşleşmedi.')
            validated={'duration':duration,'width':1920,'height':1080,'fps':30,'video_codec':'h264','audio_codec':'aac','validation_method':'ffmpeg_decode_configured_format'}
            self.warnings.append('ffprobe bulunamadı; akışlar ve süre FFmpeg dekoduyla kontrol edildi. Biçim alanları render ayarlarından alınmıştır.')
        validated.update(encoder_used=encoder,subtitle_burned=opts['subtitle_burned'],music_enabled=opts['music_enabled'],warnings=list(dict.fromkeys(self.warnings)))
        return {'path':output,'metadata':validated}
