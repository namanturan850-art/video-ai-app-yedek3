"""External composition followed by our existing local delivery/validation pass."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from uuid import uuid4
from app.projects import linked
from app.rendering.models import RenderError
from app.rendering.engine import FFmpegRenderProvider


class OpenMontageProvider:
    def __init__(self,bridge,tools,runner,progress=lambda *a:None,log=lambda *a:None):
        self.bridge,self.tools,self.runner,self.progress,self.log=bridge,tools,runner,progress,log

    def render(self,plan):
        status=self.bridge.status(True)
        if not status['ready']:raise RenderError('openmontage_unavailable',status['message'])
        root=self.bridge.root();parent=root/'remotion-composer'/'projects'
        if linked(parent) or not parent.resolve().is_relative_to(root):raise RenderError('openmontage_path','OpenMontage çalışma klasörü güvenli değil.')
        parent.mkdir(exist_ok=True);staging=parent/('avs-'+uuid4().hex);staging.mkdir()
        public=plan['temporary']/'om-assets';public.mkdir();edit=plan['smart_edit_plan'];clips=[]
        timing={s['slot_id']:s for s in plan['timeline']['slots']}
        try:
            self.progress('preparing',5,'',[])
            for i,item in enumerate(edit['slots']):
                item={**timing[item['slot_id']],**item}
                media=plan['media'][item['slot_id']];extension=media['path'].suffix.lower()
                if extension not in ('.mp4','.jpg','.png','.webp'):raise RenderError('input_invalid','OpenMontage medya türü desteklenmiyor.')
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
                     'subtitle_display':plan['options'].get('subtitle_display') or 'emphasis','subtitles':plan['handoff']['subtitles'],
                     'theme':edit.get('theme','minimal_dark'),'scenes':plan['timeline']['scenes'],'clips':clips,'emphasis':edit.get('emphasis',[]),
                     'layout_hints':edit['summary'],'music':str(plan['music']) if plan['music'] else None,'output_path':str(plan['temporary']/'om-output.mp4')}
            kit=plan.get('style_kit') or {}
            from app.channels import DEFAULT_STYLE,FONTS
            sub=kit.get('subtitle')
            if sub and sub!=DEFAULT_STYLE['subtitle']:
                neutral['subtitle_style']={k:sub[k] for k in ('color','outline','position','size')}
                if FONTS[sub['font']][1]:
                    shutil.copyfile(Path(__file__).resolve().parent.parent.parent/'static'/'fonts'/FONTS[sub['font']][1],public/'kit-subtitle.ttf')
                    neutral['subtitle_style']['font_asset']='kit-subtitle.ttf'
            neutral['avatar']=None  # layer reserved for a future channel avatar
            self.bridge.settings_guard(neutral)
            props=staging/'props.json';props.write_text(json.dumps(neutral,ensure_ascii=False),encoding='utf-8')
            entry=staging/'index.tsx';shutil.copyfile(Path(__file__).with_name('composition.tsx'),entry)
            request={'operation':'render','output_path':neutral['output_path'],'audio_path':str(plan['audio']),
                'edit_decisions':{'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke',
                   'bespoke':{'entry':str(entry),'composition_id':'AIVideoStudio','props_path':str(props),'public_dir':str(public),'crf':20,'concurrency':1}}}
            self.progress('rendering',40,'',[]);self.log('openmontage_composition_started')
            self.bridge.call('compose',request,plan['temporary'],self.runner)
            output=Path(neutral['output_path'])
            if linked(output) or not output.is_file():raise RenderError('output_invalid','OpenMontage çıktısı doğrulanamadı; önceki video korundu.')
            # Native FFmpeg remains authoritative for delivery codecs, original
            # narration, music/ducking, NVENC choice and final validation.
            t=deepcopy(plan['timeline']);slot={**t['slots'][0],'start':0,'end':t['duration'],'duration':t['duration'],
                'start_frame':0,'end_frame':t['frames'],'frames':t['frames'],'editing':{'motion':'none','transition':'hard_cut'}}
            scene={**t['scenes'][0],'start':0,'end':t['duration']};t.update(slots=[slot],scenes=[scene],editing_scenes=[{'scene_id':scene['scene_id'],'motion':'none','transition':'hard_cut','overlay_text':''}])
            delivery={**plan,'timeline':t,'smart_edit_plan':None,
                'options':{**plan['options'],'editing_style':'basic','subtitle_display':'none','subtitle_burned':False},
                'media':{slot['slot_id']:{'path':output,'type':'video','duration':t['duration']}}}
            result=FFmpegRenderProvider(self.tools,self.runner,lambda phase,percent,encoder,warnings:self.progress(phase,70+round(percent*.3),encoder,warnings),self.log).render(delivery)
            # The composition renders the planned camera moves, punch-in splits,
            # transitions and emphasis texts itself (see composition.tsx).
            applied=deepcopy(edit['summary'])
            result['metadata'].update(editing_style=edit['editing_style'],montage_engine='openmontage',openmontage_commit=status['commit'],
                subtitle_burned=neutral['subtitle_display']=='full',smart_edit_applied_summary=applied)
            return result
        finally:
            # Only the directory created by this call. Never upstream sources or
            # existing projects. Refuse cleanup if anything became a symlink.
            if not linked(staging) and not any(linked(p) for p in staging.rglob('*')):shutil.rmtree(staging)
