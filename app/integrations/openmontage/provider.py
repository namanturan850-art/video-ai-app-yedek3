"""Hybrid montage: only the graphic scenes go through Remotion, everything else FFmpeg.

Remotion draws frame by frame in a browser and is slow; stock B-roll gains
nothing from that. So:

1. Slots with a graphic layout (panel text, split screen, big number …) are
   drawn by Remotion in a few chunks rendered in parallel (one back-to-back
   "graphics reel" per chunk, own bundle/browser each).
2. The native FFmpeg engine (NVENC when available) then encodes every slot —
   the B-roll straight from its source, the graphic slots cut from the reels —
   several slots at a time, and does transitions, subtitles, emphasis, music
   and the final delivery pass.

AVS_REMOTION_SCOPE=all renders the whole film in Remotion again (the old
behaviour) — only useful to compare render times.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import time
from uuid import uuid4
from app.projects import linked
from app.rendering.models import RenderError
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.parallel import run_parallel

SUPPORTED=('.mp4','.jpg','.png','.webp')
REEL_CRF=16  # intermediate: re-encoded once more by the delivery pass


def text_layout(plan,props):
    """Share pixel-measured typography with FFmpeg; keep source strings intact."""
    from app.rendering.ass import fitted
    kit=plan.get('style_kit') or {}
    heading=kit.get('heading_font','arial')
    for clip in props.get('clips',[]):
        text='\n'.join(str(t) for t in clip.get('texts',[]))
        if text:
            width=800 if clip.get('layout') in ('split_media_text','dual_media') else 1400
            lines=3 if clip.get('layout') in ('minimal_title','quote_emphasis') else 6
            clip['text_font_size'],clip['display_text']=fitted(text,heading,width,lines,54)
        if clip.get('number'):
            clip['number_font_size'],clip['display_number']=fitted(str(clip['number']),heading,1400,1,110)
    for item in props.get('emphasis',[]):
        item['font_size'],item['display_text']=fitted(str(item.get('text','')),heading,1500,2,64)
    for cue in props.get('subtitles',[]):
        sub=kit.get('subtitle') or {}
        size=sub.get('size',50)
        if any(e.get('style') in ('lower_third','band2') and e['start']<cue['end'] and e['end']>cue['start'] for e in props.get('emphasis',[])):size=min(size,64)
        cue['font_size'],cue['display_text']=fitted(cue['text'],sub.get('font','arial'),1680,2,size)
    return props


def remotion_workers():
    chosen=os.environ.get('AVS_REMOTION_WORKERS','')
    if chosen.isdigit() and 1<=int(chosen)<=4:return int(chosen)
    return max(1,min(3,(os.cpu_count() or 2)//2))


def place(source,target):
    """Hard link where possible (no copy of big stock files), else a copy."""
    try:os.link(source,target)
    except OSError:shutil.copyfile(source,target)


class OpenMontageProvider:
    def __init__(self,bridge,tools,runner,progress=lambda *a:None,log=lambda *a:None):
        self.bridge,self.tools,self.runner,self.progress,self.log=bridge,tools,runner,progress,log

    def render(self,plan):
        if os.environ.get('AVS_REMOTION_SCOPE')=='all':return self.render_all(plan)
        return self.render_hybrid(plan)

    # ---- shared helpers -------------------------------------------------------------
    def staging_parent(self):
        root=self.bridge.root();parent=root/'remotion-composer'/'projects'
        if linked(parent) or not parent.resolve().is_relative_to(root):raise RenderError('openmontage_path','OpenMontage çalışma klasörü güvenli değil.')
        parent.mkdir(exist_ok=True);return parent

    @staticmethod
    def cleanup(staging):
        # Only the directory created by this call. Never upstream sources or
        # existing projects. Refuse cleanup if anything became a symlink.
        if not linked(staging) and not any(linked(p) for p in staging.rglob('*')):shutil.rmtree(staging)

    def kit_props(self,plan,public):
        """Channel “Tarzım”: subtitle style and the emphasis/panel look, with their bundled fonts."""
        kit=plan.get('style_kit') or {};props={}
        from app.channels import DEFAULT_STYLE,FONTS
        fonts=Path(__file__).resolve().parent.parent.parent/'static'/'fonts'
        sub=kit.get('subtitle')
        if sub and sub!=DEFAULT_STYLE['subtitle']:
            props['subtitle_style']={k:sub[k] for k in ('color','outline','position','size')}
            if FONTS[sub['font']][1]:
                shutil.copyfile(fonts/FONTS[sub['font']][1],public/'kit-subtitle.ttf');props['subtitle_style']['font_asset']='kit-subtitle.ttf'
        if kit.get('palette'):
            props['graphic_style']={k:kit['palette'][k] for k in ('background','accent','primary')}
            heading=FONTS[kit.get('heading_font','arial')][1]
            if heading:
                shutil.copyfile(fonts/heading,public/'kit-heading.ttf');props['graphic_style']['font_asset']='kit-heading.ttf'
        return props

    def compose(self,plan,request_props,public,staging,output,audio,folder,crf,runner,progress):
        request_props=text_layout(plan,deepcopy(request_props))
        self.bridge.settings_guard(request_props)
        props=staging/'props.json';props.write_text(json.dumps(request_props,ensure_ascii=False),encoding='utf-8')
        entry=staging/'index.tsx';shutil.copyfile(Path(__file__).with_name('composition.tsx'),entry)
        request={'operation':'render','output_path':str(output),'audio_path':str(audio),
            'edit_decisions':{'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke',
               'bespoke':{'entry':str(entry),'composition_id':'AIVideoStudio','props_path':str(props),'public_dir':str(public),'crf':crf,'concurrency':1}}}
        self.bridge.call('compose',request,folder,runner,progress)
        if linked(output) or not output.is_file():raise RenderError('output_invalid','OpenMontage çıktısı doğrulanamadı; önceki video korundu.')

    # ---- hybrid ---------------------------------------------------------------------
    def render_hybrid(self,plan):
        started=time.monotonic();edit=plan['smart_edit_plan']
        timing={s['slot_id']:s for s in plan['timeline']['slots']}
        graphic=[i for i in edit['slots'] if i.get('layout','full_broll')!='full_broll'
                 and plan['media'][i['slot_id']].get('path') and Path(plan['media'][i['slot_id']]['path']).suffix.lower() in SUPPORTED]
        replaced={};chunks=0;remotion_seconds=0.;warnings=[]
        if graphic:
            status=self.bridge.status(True)
            if not status['ready']:raise RenderError('openmontage_unavailable',status['message'])
            self.progress('preparing',2,'',[]);remote_started=time.monotonic()
            replaced,chunks,warnings=self.graphics(plan,graphic,timing)
            remotion_seconds=time.monotonic()-remote_started
        base=35 if graphic else 0
        delivery={**plan,'media':{**plan['media']},'smart_edit_plan':self.without_layouts(deepcopy(edit),replaced,timing)}
        for sid,piece in replaced.items():
            delivery['media'][sid]={'path':piece['path'],'type':'video','duration':piece['reel_seconds'],'width':1920,'height':1080,'sha256':piece['sha256']}
        native=FFmpegRenderProvider(self.tools,self.runner,lambda phase,percent,encoder,w:self.progress(phase,base+round(percent*(100-base)/100,1),encoder,list(dict.fromkeys([*warnings,*w]))),self.log)
        native.warnings.extend(warnings)
        result=native.render(delivery)
        total=time.monotonic()-started;details=result['metadata'].pop('render_timing',{})
        result['metadata'].update(editing_style=edit['editing_style'],montage_engine='openmontage',smart_edit_applied_summary=deepcopy(edit['summary']),
            render_timing={**details,'engine':'hybrid' if graphic else 'ffmpeg','graphic_slots':len(graphic),'graphic_slots_in_remotion':len(replaced),'broll_slots':len(edit['slots'])-len(graphic),
                           'remotion_chunks':chunks,'remotion_seconds':round(remotion_seconds,1),'ffmpeg_seconds':round(total-remotion_seconds,1),'total_seconds':round(total,1)})
        if graphic:result['metadata']['openmontage_commit']=self.bridge.status()['commit']
        self.log('render_timing_hybrid')
        return result

    @staticmethod
    def without_layouts(edit,replaced,timing):
        """A slot drawn by Remotion is a finished clip for FFmpeg: no second camera move, panel or crop."""
        for item in edit['slots']:
            piece=replaced.get(item['slot_id'])
            if not piece:continue
            frames=timing[item['slot_id']]['frames']
            item.update(layout='full_broll',texts=[],layout_window=None,secondary_slot_id=None,motion_effect='none',motion_strength=0.,fit='cover',
                        source_in=piece['offset'],graphics_rendered=True,
                        segments=[{'start_frame':0,'end_frame':frames,'frames':frames,'start':item['start'],'end':item['end'],'motion_effect':'none','motion_strength':0.,'camera_curve':'neutral_cycle'}])
        covered=[(i['start'],i['end']) for i in edit['slots'] if i['slot_id'] in replaced]
        for text in edit.get('emphasis',[]):
            if text.get('punch_in') and any(text['start']<b and text['end']>a for a,b in covered):text.update(punch_in=False,punch_suppressed='graphics')
        return edit

    def graphics(self,plan,items,timing):
        """→ ({slot_id: piece}, chunk count, warnings). A chunk that fails is left to FFmpeg's own layouts."""
        handles={}
        for item in items:
            media=plan['media'][item['slot_id']];frames=timing[item['slot_id']]['frames']
            handle=round(item.get('transition_duration',0)*30) if item.get('transition_out')=='crossfade' else 0
            if media['type']=='video' and media.get('duration'):
                available=max(0.,media['duration']-item.get('source_in',0)-frames/30);handle=min(handle,int(available*30))
            handles[item['slot_id']]=handle
        weight=lambda item:timing[item['slot_id']]['frames']+handles[item['slot_id']]
        count=max(1,min(remotion_workers(),len(items)));target=sum(weight(i) for i in items)/count
        groups=[[]];filled=0
        for item in items:
            if groups[-1] and filled>=target and len(groups)<count:groups.append([]);filled=0
            groups[-1].append(item);filled+=weight(item)
        parent=self.staging_parent();fractions=[0.]*len(groups)
        self.log('openmontage_composition_started')

        def job(k,runner):
            def report(fraction):
                fractions[k]=fraction;self.progress('rendering',2+round(33*sum(fractions)/len(fractions),1),'',[])
            return self.chunk(plan,groups[k],timing,handles,parent,k,runner,report)
        pieces={};warnings=[]
        def safe(k,runner):
            try:return job(k,runner)
            except RenderError as error:
                if error.category=='render_cancelled':raise
                self.log('openmontage_chunk_failed');return None
        outcomes=run_parallel(len(groups),safe,count,self.runner)
        for group,outcome in zip(groups,outcomes):
            if outcome is None:
                warnings.append('Bazı grafik sahneler Remotion ile çizilemedi; bu sahneler yerel FFmpeg düzeniyle yapıldı.');continue
            pieces.update(outcome)
        return pieces,len(groups),list(dict.fromkeys(warnings))

    def chunk(self,plan,group,timing,handles,parent,k,runner,report):
        """One Remotion run: the group's slots back to back (each with its crossfade handle) → one reel."""
        edit=plan['smart_edit_plan'];folder=plan['temporary']/f'om-chunk-{k}';public=folder/'public';public.mkdir(parents=True)
        staging=parent/('avs-'+uuid4().hex);staging.mkdir()
        try:
            clips=[];offsets={};cursor=0;by_id={i['slot_id']:i for i in edit['slots']};extra=0
            def asset(media,name):
                target=public/name;place(media['path'],target);return name
            for n,item in enumerate(group):
                sid=item['slot_id'];merged={**timing[sid],**item};media=plan['media'][sid]
                video=media['type']=='video';handle=handles[sid]
                clip={**merged,'handle':handle,'asset':asset(media,f'asset-{n}'+Path(media['path']).suffix.lower()),'type':media['type'],
                      'source_in':item.get('source_in',0) if video else 0,'start_frame':cursor,'end_frame':cursor+merged['frames'],
                      'transition_out':'crossfade' if handle else 'hard_cut','transition_duration':0.,'local_path':str(media['path'])}
                other=item.get('secondary_slot_id')
                if other and other in plan['media'] and plan['media'][other].get('path') and Path(plan['media'][other]['path']).suffix.lower() in SUPPORTED:
                    second=plan['media'][other];extra+=1
                    clip['secondary']={'asset':asset(second,f'second-{extra}'+Path(second['path']).suffix.lower()),'type':second['type'],
                                       'source_in':by_id.get(other,{}).get('source_in',0) if second['type']=='video' else 0}
                offsets[sid]=cursor;cursor+=merged['frames']+handle;clips.append(clip)
            from app.motion.clips import silent_wav
            silence=public/'silence.wav';silent_wav(silence,cursor/30+1)
            output=folder/'graphics.mp4'
            props={'project_id':plan['handoff']['project_id'],'duration':cursor/30,'frames':cursor,'fps':30,'width':1920,'height':1080,'narration_audio':str(silence),
                   'subtitle_display':'none','subtitles':[],'theme':edit.get('theme','minimal_dark'),'scenes':plan['timeline']['scenes'],'clips':clips,'emphasis':[],
                   'layout_hints':edit['summary'],'music':None,'avatar':None,'output_path':str(output),**self.kit_props(plan,public)}
            self.compose(plan,props,public,staging,output,silence,folder,REEL_CRF,runner,report)
            from app.rendering import probe
            measured=probe.stock(self.tools.get('ffprobe'),output,'video') if self.tools.get('ffprobe') else None
            seconds=measured['stock_duration'] if measured else cursor/30
            return {sid:{'path':output,'offset':offsets[sid]/30,'reel_seconds':seconds,'sha256':'graphics-reel'} for sid in offsets}
        finally:self.cleanup(staging)

    # ---- the whole film in Remotion (old behaviour, for comparing render times) -------
    def render_all(self,plan):
        started=time.monotonic()
        status=self.bridge.status(True)
        if not status['ready']:raise RenderError('openmontage_unavailable',status['message'])
        parent=self.staging_parent();staging=parent/('avs-'+uuid4().hex);staging.mkdir()
        public=plan['temporary']/'om-assets';public.mkdir();edit=plan['smart_edit_plan'];clips=[]
        timing={s['slot_id']:s for s in plan['timeline']['slots']}
        try:
            self.progress('preparing',5,'',[])
            for i,item in enumerate(edit['slots']):
                item={**timing[item['slot_id']],**item}
                media=plan['media'][item['slot_id']];extension=media['path'].suffix.lower()
                if extension not in SUPPORTED:raise RenderError('input_invalid','OpenMontage medya türü desteklenmiyor.')
                filename=f'asset-{i}{extension}';target=public/filename
                # A crossfade blends extra frames of this clip under the next
                # slot's start; cut them with the clip (never loops/speeds up).
                handle=round(item.get('transition_duration',0)*30) if item.get('transition_out')=='crossfade' else 0
                if media['type']=='video':
                    available=max(0.,(media.get('duration') or 0)-item.get('source_in',0)-item['frames']/30)
                    handle=min(handle,int(available*30)) if media.get('duration') else handle
                    self.bridge.call('trim',{'operation':'cut','input_path':str(media['path']),
                        'output_path':str(target),'start_seconds':item.get('source_in',0),
                        'end_seconds':item.get('source_in',0)+(item['frames']+handle)/30,'codec':'libx264'},plan['temporary'],self.runner)
                else:shutil.copyfile(media['path'],target)
                clips.append({**item,'handle':handle,'asset':filename,'type':media['type'],'source_in':0,'source_out':item['end']-item['start'],
                              'original_source_in':item.get('source_in',0),'local_path':str(media['path'])})
                self.progress('preparing',5+int(35*(i+1)/len(edit['slots'])),'',[])
            lookup={c['slot_id']:c for c in clips}
            for c in clips:
                if c.get('secondary_slot_id') in lookup:
                    c['secondary']={k:lookup[c['secondary_slot_id']][k] for k in ('asset','type','source_in')}
            neutral={'project_id':plan['handoff']['project_id'],'source_script_version_id':plan['handoff'].get('source_script_version_id'),
                     'source_subtitle_version_id':plan['handoff'].get('subtitle_version_id'),'duration':plan['timeline']['duration'],'frames':plan['timeline']['frames'],
                     'fps':30,'width':1920,'height':1080,'narration_audio':str(plan['audio']),
                     'subtitle_display':plan['options'].get('subtitle_display') or 'full','subtitles':plan['handoff']['subtitles'],
                     'theme':edit.get('theme','minimal_dark'),'scenes':plan['timeline']['scenes'],'clips':clips,'emphasis':edit.get('emphasis',[]),
                     'layout_hints':edit['summary'],'music':str(plan['music']) if plan['music'] else None,'output_path':str(plan['temporary']/'om-output.mp4'),
                     **self.kit_props(plan,public)}
            neutral['avatar']=None  # layer reserved for a future channel avatar
            self.progress('rendering',40,'',[]);self.log('openmontage_composition_started')
            # Real Remotion frame progress fills 40-90 %; the FFmpeg delivery pass 90-100 %.
            output=Path(neutral['output_path']);remote_started=time.monotonic()
            self.compose(plan,neutral,public,staging,output,plan['audio'],plan['temporary'],20,self.runner,lambda fraction:self.progress('rendering',40+round(min(1,fraction)*50,1),'',[]))
            remotion_seconds=time.monotonic()-remote_started
            # Native FFmpeg remains authoritative for delivery codecs, original
            # narration, music/ducking, NVENC choice and final validation.
            t=deepcopy(plan['timeline']);slot={**t['slots'][0],'start':0,'end':t['duration'],'duration':t['duration'],
                'start_frame':0,'end_frame':t['frames'],'frames':t['frames'],'editing':{'motion':'none','transition':'hard_cut'}}
            scene={**t['scenes'][0],'start':0,'end':t['duration']};t.update(slots=[slot],scenes=[scene],editing_scenes=[{'scene_id':scene['scene_id'],'motion':'none','transition':'hard_cut','overlay_text':''}])
            delivery={**plan,'timeline':t,'smart_edit_plan':None,
                'options':{**plan['options'],'editing_style':'basic','subtitle_display':'none','subtitle_burned':False},
                'media':{slot['slot_id']:{'path':output,'type':'video','duration':t['duration']}}}
            result=FFmpegRenderProvider(self.tools,self.runner,lambda phase,percent,encoder,warnings:self.progress(phase,90+round(percent*.1),encoder,warnings),self.log).render(delivery)
            # The composition renders the planned camera moves, punch-in splits,
            # transitions and emphasis texts itself (see composition.tsx).
            applied=deepcopy(edit['summary']);total=time.monotonic()-started;result['metadata'].pop('render_timing',None)
            result['metadata'].update(editing_style=edit['editing_style'],montage_engine='openmontage',openmontage_commit=status['commit'],
                subtitle_burned=neutral['subtitle_display']=='full',smart_edit_applied_summary=applied,
                render_timing={'engine':'remotion_all','remotion_seconds':round(remotion_seconds,1),'ffmpeg_seconds':round(total-remotion_seconds,1),'total_seconds':round(total,1)})
            return result
        finally:self.cleanup(staging)
