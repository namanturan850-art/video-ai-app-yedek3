"""Persistent local-only renders. Source contracts are consumed, never rebuilt."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4

from app.projects import now, linked
from app.scripts.models import ScriptError
from app.scripts.engine import SecretGuard
from app.narration.audio import audio_path
from app.stock.download import asset_path
from app.subtitles.files import file_path
from app.rendering import files, tools, timeline, probe
from app.rendering.models import ACTIVE, LABELS, SOURCE_MESSAGE, RenderError, options, encoder_label
from app.rendering.runner import ProcessRunner
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.diagnostics import safe_diagnostic
from app.rendering import smart_edit

LOG=logging.getLogger('uvicorn.error.rendering')


class RenderService:
    def __init__(self,subtitles,production,settings):
        self.subtitles,self.production,self.settings=subtitles,production,settings
        self.projects=production.scripts.projects
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='local-render')
        self.runners={};self.lock=RLock();self.tool_lock=RLock();self.tool_cache=None;self.tool_time=0
        self.hashes={};self.closed=False;self.factory=FFmpegRenderProvider
        from app.integrations.openmontage.bridge import Bridge
        self.openmontage=Bridge(self.projects,settings)

    def _guard(self,value):
        SecretGuard(self.settings.secret_values()).validate(value)

    def _tools(self,refresh=False):
        with self.tool_lock:
            if refresh or self.tool_cache is None or time.monotonic()-self.tool_time>30:
                self.tool_cache=tools.discover();self.tool_time=time.monotonic()
            return deepcopy(self.tool_cache)

    def _hash(self,path,force=False):
        stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        with self.lock:
            if force or key not in self.hashes:
                if len(self.hashes)>2048:self.hashes.clear()
                self.hashes[key]=files.sha256(path)
            return self.hashes[key]

    def _music(self,c,pid):
        row=c.execute('SELECT metadata_json FROM render_music WHERE project_id=?',(pid,)).fetchone()
        return json.loads(row[0]) if row else None

    def _inputs(self,pid,opts,force=False,*,stored_edit_plan=None):
        try:
            h=self.subtitles.handoff(pid);p=self.production.handoff(pid)
            with closing(self.projects._connection()) as c:
                voice=self.subtitles.narration._version(c,pid,h['narration_version_id'])
                row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,h['scene_plan_id'])).fetchone()
                if not row:raise RenderError('source_stale',SOURCE_MESSAGE)
                stock=json.loads(row[0]);music=self._music(c,pid)
            from app.rendering import reflow
            h,recovery=reflow.project(h,p,stock,self.projects,lambda path:self._hash(path,force))
            t=timeline.build(h,p)
            audio=audio_path(self.projects,pid,voice['metadata']['audio'])
            audio_hash=self._hash(audio,force)
            if audio_hash!=voice['metadata']['audio']['sha256']:raise RenderError('source_stale',SOURCE_MESSAGE)
            originals={str(audio):audio_hash};media={};identities=[]
            selected={s['slot_id']:s for s in stock['slots']}
            for slot in t['slots']:
                if slot.get('graphic_text'):
                    if opts.get('editing_style')!='adaptive':raise RenderError('recovery_style_required','Grafik içeren akıllı kurgu için Uyarlanabilir YouTube stilini seçin.')
                    media[slot['slot_id']]={'type':'graphic','path':None,'duration':None,'sha256':smart_edit.digest(slot['graphic_text'])}
                    identities.append({'slot_id':slot['slot_id'],'graphic_text':slot['graphic_text']});continue
                # A continuation keeps running the same verified file as its root shot.
                owner=slot.get('continuation_of') or slot['slot_id']
                m=selected.get(owner,{}).get('selected_media');identity=slot['selected_media_local_identity']
                if not m or any(m.get(k)!=v for k,v in identity.items()):raise RenderError('source_stale',SOURCE_MESSAGE)
                path=asset_path(self.projects,pid,m);digest=self._hash(path,force)
                originals[str(path)]=digest;media[slot['slot_id']]={'path':path,'type':m['media_type'],'duration':m.get('duration'),'width':m.get('width',0),'height':m.get('height',0),'description':m.get('description',''),'sha256':digest}
                if selected.get(owner,{}).get('segment_start') is not None:media[slot['slot_id']]['segment_start']=float(selected[owner]['segment_start'])
                if recovery:
                    proof=selected[owner].get('local_validation',{})
                    media[slot['slot_id']].update({k:proof[k] for k in ('duration','width','height') if k in proof})
                identities.append({'slot_id':slot['slot_id'],'identity':identity,'sha256':digest})
            for name in ('srt_local_path','vtt_local_path'):
                path=file_path(self.projects,pid,h[name]);originals[str(path)]=self._hash(path,force)
            music_file=None;music_identity=None
            if opts['music_enabled']:
                if not music or music.get('license_confirmed') is not True:raise RenderError('music_invalid','Önce müzik dosyasını ekleyin ve kullanma hakkınızı onaylayın.')
                music_file=files.music_path(self.projects,pid,music)
                music_hash=self._hash(music_file,force)
                if music_hash!=music['sha256']:raise RenderError('music_invalid','Müzik dosyası değişmiş. Yeniden ekleyin.')
                music_identity={'local_path':music['local_path'],'sha256':music_hash};originals[str(music_file)]=music_hash
            fingerprint_data={'contract':h,'editing':t['editing_scenes'],'media':identities,'audio_sha256':audio_hash,'originals':{str(Path(k).relative_to(self.projects._path(pid))):v for k,v in originals.items()},'options':opts,'music':music_identity}
            # All contract values are local identities and safe scene/subtitle text, not URLs or secrets.
            self._guard(fingerprint_data)
            fingerprint=hashlib.sha256(json.dumps(fingerprint_data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            base_fingerprint=fingerprint
            plan=None
            # Pre-9.5 versions have no style key: retain their EXACT old fingerprint.
            if 'editing_style' in opts:
                # Existing completed versions keep their saved deterministic plan
                # when its source is still exact; tuning a new algorithm cannot
                # invalidate an owner's successful render.
                if (isinstance(stored_edit_plan,dict) and stored_edit_plan.get('source_fingerprint')==fingerprint
                        and stored_edit_plan.get('editing_style')==opts['editing_style']):
                    plan=deepcopy(stored_edit_plan)
                else:
                    seed=opts.get('edit_variation_seed')
                    # Default editorial choices depend on source content, not
                    # encoder/music settings or preview-only option defaults.
                    if not seed and opts['editing_style']=='adaptive':
                        seed=smart_edit.digest({'contract':h,'editing':t['editing_scenes'],'media':identities,'audio_sha256':audio_hash})[:16]
                    plan=smart_edit.build(t,h,opts['editing_style'],fingerprint,seed=seed,subtitle_mode=opts.get('subtitle_display') or ('emphasis' if opts['editing_style']=='adaptive' else 'full' if opts['subtitle_burned'] else 'none'),media_details=media)
                self._guard(plan)
                fingerprint=smart_edit.digest({'source':fingerprint,'smart_edit_plan':plan})
            inputs={'handoff':h,'timeline':t,'media':media,'audio':audio,'music':music_file,'options':opts,'fingerprint':fingerprint,'originals':originals,'smart_edit_plan':plan,'recovery':recovery}
            reflow.apply_graphics(inputs)
            if plan and any(s.get('graphic_text') for s in h['stock_slots']):inputs['fingerprint']=smart_edit.digest({'source':base_fingerprint,'smart_edit_plan':plan})
            return inputs
        except RenderError:raise
        except ScriptError:raise RenderError('source_stale',SOURCE_MESSAGE) from None
        except (OSError,ValueError,KeyError,TypeError):raise RenderError('input_invalid','Yerel video kaynakları okunamadı. Ses, altyazı ve stok medya dosyalarını kontrol edin.') from None

    def _version(self,c,pid,vid):
        row=c.execute('SELECT * FROM render_versions WHERE project_id=? AND id=?',(pid,vid)).fetchone()
        if not row:raise RenderError('input_missing','Video sürümü bulunamadı.',404)
        result=dict(row);result['metadata']=json.loads(result.pop('metadata_json'));return result

    def _idle(self,c,pid):
        if c.execute("SELECT 1 FROM render_jobs WHERE project_id=? AND status IN ('queued','preparing','rendering','validating')",(pid,)).fetchone():
            raise RenderError('render_busy','Bu proje için video zaten oluşturuluyor. Tamamlanmasını bekleyin veya iptal edin.')

    def start(self,pid,payload):
        opts=options(payload);self.projects.get(pid)
        with self.projects.lock:
            with closing(self.projects._connection()) as c:self._idle(c,pid)
            inputs=self._inputs(pid,opts,True);tool=self._tools(True)
            if opts.get('montage_engine')=='openmontage' and not self.openmontage.status(True)['ready']:raise RenderError('openmontage_unavailable',self.openmontage.status()['message'])
            if not tool['found']:raise RenderError('ffmpeg_missing','Video oluşturmak için FFmpeg gerekli.')
            tools.select_encoder(opts['encoder'],tool)
            with self.lock:
                if self.closed:raise RenderError('render_cancelled','Uygulama kapanıyor. Yeniden açıp deneyin.')
                jid,vid=uuid4().hex,uuid4().hex;stamp=now()
                with closing(self.projects._connection()) as c,c:
                    c.execute('BEGIN IMMEDIATE');self._idle(c,pid)
                    version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM render_versions WHERE project_id=?',(pid,)).fetchone()[0]
                    h=inputs['handoff'];meta={'options':opts,'encoder_requested':opts['encoder'],'target_language':h['target_language'],'warnings':h.get('warnings',[])}
                    if inputs['smart_edit_plan']:
                        meta.update(editing_style=opts['editing_style'],smart_edit_plan=inputs['smart_edit_plan'],smart_edit_summary=inputs['smart_edit_plan']['summary'])
                    c.execute('INSERT INTO render_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(vid,pid,version,h['source_script_version_id'],h['narration_version_id'],h['subtitle_version_id'],h['scene_plan_id'],inputs['fingerprint'],json.dumps(meta,ensure_ascii=False),'queued',stamp,stamp))
                    c.execute('INSERT INTO render_jobs VALUES (?,?,?,?,?,?,?,?,?)',(jid,pid,vid,'queued',json.dumps({'percent':0,'encoder_used':'','elapsed_seconds':0}),'','',stamp,stamp))
                runner=ProcessRunner();self.runners[jid]=runner
                self.executor.submit(self._run,pid,jid,vid,version,inputs,tool,runner)
        return {'job_id':jid,'render_version_id':vid,'version':version,'status':'queued'}

    def _log(self,pid,version,event,*,encoder="",elapsed=0,diagnostic=None):
        # Caller supplies controlled event/category tokens only; never stderr/commands/text.
        if not isinstance(event,str) or not event.replace('_','').isalnum():event='unexpected_backend'
        encoder=encoder if encoder in ('libx264','h264_nvenc') else 'pending'
        elapsed=round(max(0,elapsed),1)
        safe=safe_diagnostic(diagnostic)
        details=' diagnostic='+json.dumps(safe,ensure_ascii=False,separators=(',',':')) if safe else ''
        LOG.info('render operation=%s version=%s encoder=%s elapsed_seconds=%s%s',event,version,encoder,elapsed,details)
        path=files.directory(self.projects,pid)/f'render-v{version}.log'
        if linked(path):raise RenderError('local_storage','Render günlüğü güvenli değil.')
        with path.open('a',encoding='utf-8') as f:f.write(f'{now()} event={event} encoder={encoder} elapsed_seconds={elapsed}{details}\n')

    def _progress(self,pid,jid,vid,start,phase,percent,encoder,warnings):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            row=c.execute('SELECT status,progress_json FROM render_jobs WHERE id=? AND project_id=?',(jid,pid)).fetchone()
            if not row or row['status'] not in ACTIVE:return
            previous=json.loads(row['progress_json'])
            progress={'percent':round(min(99,max(previous['percent'],percent)),1),'encoder_used':encoder,'elapsed_seconds':round(time.monotonic()-start,1),'warnings':list(dict.fromkeys(warnings))}
            self._guard(progress)
            c.execute('UPDATE render_jobs SET status=?,progress_json=?,updated_at=? WHERE id=?',(phase,json.dumps(progress,ensure_ascii=False),now(),jid))
            c.execute('UPDATE render_versions SET status=?,updated_at=? WHERE id=?',(phase,now(),vid))

    def _run(self,pid,jid,vid,version,inputs,tool,runner):
        started=time.monotonic();final=None
        try:
            def record_diagnostic(value):
                try:self._log(pid,version,'render_failed',diagnostic=value,encoder=value['encoder'],elapsed=time.monotonic()-started)
                except (OSError,RenderError):pass  # Logging failure must not replace the actual safe failure.
            runner.diagnostic_callback=record_diagnostic
            self._log(pid,version,'started');inputs['temporary']=files.job_directory(self.projects,pid,jid)
            from app.rendering.reflow import materialize
            materialize(inputs,tool,runner)
            if runner.event.is_set():raise RenderError('render_cancelled','Render iptal edildi.')
            engine=self.factory(tool,runner,lambda *args:self._progress(pid,jid,vid,started,*args),lambda event:self._log(pid,version,event))
            if inputs['options'].get('montage_engine')=='openmontage':
                from app.integrations.openmontage.provider import OpenMontageProvider
                engine=OpenMontageProvider(self.openmontage,tool,runner,lambda *args:self._progress(pid,jid,vid,started,*args),lambda event:self._log(pid,version,event))
            result=engine.render(inputs)
            # Reject activation if a source changed during the job. No source is modified here.
            with self.projects.lock,self.lock:
                if runner.event.is_set():raise RenderError('render_cancelled','Render iptal edildi.')
                current=self._inputs(pid,inputs['options'],True)
                if current['fingerprint']!=inputs['fingerprint']:raise RenderError('source_stale',SOURCE_MESSAGE)
                final=files.directory(self.projects,pid)/f'video-v{version}.mp4'
                if final.exists() or linked(final):raise RenderError('local_storage','Video sürüm dosyası zaten var. Önceki video korundu.')
                with result['path'].open('r+b') as f:os.fsync(f.fileno())
                os.replace(result['path'],final)
                with closing(self.projects._connection()) as c,c:
                    item=self._version(c,pid,vid);meta=item['metadata']
                    meta.update(result['metadata'],output_local_path=f'renders/{final.name}',file_size=final.stat().st_size,sha256=files.sha256(final))
                    meta['warnings']=list(dict.fromkeys(inputs['handoff'].get('warnings',[])+meta['warnings']));self._guard(meta)
                    stamp=now();progress={'percent':100,'encoder_used':meta['encoder_used'],'elapsed_seconds':round(time.monotonic()-started,1),'warnings':meta['warnings']}
                    c.execute('UPDATE render_versions SET metadata_json=?,status=?,updated_at=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),'completed',stamp,vid))
                    c.execute('UPDATE render_jobs SET status=?,progress_json=?,updated_at=? WHERE id=?',('completed',json.dumps(progress,ensure_ascii=False),stamp,jid))
                    c.execute('INSERT INTO render_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(pid,vid,stamp))
            self._log(pid,version,'completed',encoder=meta['encoder_used'],elapsed=time.monotonic()-started)
        except Exception as error:
            if final and final.exists():
                # A validated final may already be committed: never remove completed output.
                with closing(self.projects._connection()) as c:
                    completed=c.execute("SELECT 1 FROM render_versions WHERE id=? AND status='completed'",(vid,)).fetchone()
                if completed:return
                final.unlink(missing_ok=True)
            category=error.category if isinstance(error,RenderError) else 'local_storage' if isinstance(error,OSError) else 'render_failed'
            message=str(error) if isinstance(error,RenderError) else 'Video oluşturulamadı. Boş alanı ve yerel dosyaları kontrol edip yeniden deneyin. Önceki videolar korundu.'
            status='cancelled' if category=='render_cancelled' else 'error'
            safe=safe_diagnostic(error.diagnostic) if isinstance(error,RenderError) else None
            with self.projects.lock,closing(self.projects._connection()) as c,c:
                row=c.execute('SELECT progress_json FROM render_jobs WHERE id=?',(jid,)).fetchone()
                progress=json.loads(row[0]);progress['elapsed_seconds']=round(time.monotonic()-started,1)
                if safe:progress['diagnostic']=safe
                c.execute('UPDATE render_jobs SET progress_json=? WHERE id=?',(json.dumps(progress,ensure_ascii=False),jid))
                c.execute('UPDATE render_jobs SET status=?,error_category=?,error_message=?,updated_at=? WHERE id=?',(status,category,message,now(),jid))
                c.execute('UPDATE render_versions SET status=?,updated_at=? WHERE id=?',(status,now(),vid))
            try:self._log(pid,version,category,elapsed=time.monotonic()-started,diagnostic=safe,encoder=safe['encoder'] if safe else '')
            except (OSError,RenderError):pass
        finally:
            try:files.cleanup(self.projects,pid,jid)
            except (OSError,RenderError):LOG.warning('render operation=cleanup result=failure category=local_storage')
            with self.lock:self.runners.pop(jid,None)

    def cancel(self,pid,jid):
        with self.lock:
            with closing(self.projects._connection()) as c:
                row=c.execute('SELECT status FROM render_jobs WHERE project_id=? AND id=?',(pid,jid)).fetchone()
            if not row:raise RenderError('input_missing','Render görevi bulunamadı.',404)
            runner=self.runners.get(jid)
            if row[0] in ACTIVE and runner:
                runner.cancel()
                if row[0]=='queued':
                    with closing(self.projects._connection()) as c,c:
                        c.execute("UPDATE render_jobs SET status='cancelled',error_category='render_cancelled',error_message='Render iptal edildi.',updated_at=? WHERE id=? AND status='queued'",(now(),jid))
                        c.execute("UPDATE render_versions SET status='cancelled',updated_at=? WHERE id=(SELECT render_version_id FROM render_jobs WHERE id=? AND status='cancelled')",(now(),jid))
        return {'message':'İptal isteği alındı. Kaynak dosyalar korunur.'}

    def recover(self):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            rows=c.execute("SELECT * FROM render_jobs WHERE status IN ('queued','preparing','rendering','validating')").fetchall()
            for row in rows:
                c.execute("UPDATE render_jobs SET status='error',error_category='render_interrupted',error_message=?,updated_at=? WHERE id=?",('Uygulama kapanırken render durdu. Yeniden Render Et ile yerel olarak tekrar deneyin.',now(),row['id']))
                c.execute("UPDATE render_versions SET status='error',updated_at=? WHERE id=?",(now(),row['render_version_id']))
                try:files.cleanup(self.projects,row['project_id'],row['id'])
                except (OSError,RenderError):LOG.warning('render operation=recovery category=local_storage')

    def close(self):
        with self.lock:
            self.closed=True;runners=list(self.runners.values())
        for runner in runners:runner.cancel()
        # Queued work runs only to observe cancellation and persist terminal status.
        self.executor.shutdown(wait=True)

    def view(self,pid,*,refresh_tools=False,editing_style='adaptive',edit_variation_seed=None,subtitle_display=None,montage_engine='openmontage'):
        self.projects.get(pid);source=None;source_error='';source_category='';error=None;opts=options({'editing_style':editing_style,'edit_variation_seed':edit_variation_seed,'subtitle_display':subtitle_display,'montage_engine':montage_engine})
        try:source=self._inputs(pid,opts)
        except RenderError as e:source_error=str(e);source_category=e.category;error=e
        try:tool=self._tools(True) if refresh_tools else self._tools()
        except RenderError as e:tool={'found':False,'status':'Hata','message':str(e),'encoders':[]};source_category=e.category
        summary=None
        if source:
            t=source['timeline'];summary={'duration':t['duration'],'scenes':len(t['scenes']),'slots':len(t['slots']),'videos':sum(m['type']=='video' for m in source['media'].values()),'images':sum(m['type']=='image' for m in source['media'].values()),'subtitles':len(source['handoff']['subtitles']),'overlays':sum(bool(s.get('overlay_text')) for s in t['editing_scenes'])}
        with self.projects.lock,closing(self.projects._connection()) as c:
            state=c.execute('SELECT active_version_id FROM render_state WHERE project_id=?',(pid,)).fetchone();active_id=state[0] if state else None
            versions=[];fingerprints={}
            for row in c.execute('SELECT id FROM render_versions WHERE project_id=? ORDER BY version DESC',(pid,)).fetchall():
                item=self._version(c,pid,row['id']);meta=item['metadata'];saved_plan=meta.get('smart_edit_plan');key=smart_edit.digest([meta['options'],saved_plan])
                if key not in fingerprints:
                    try:fingerprints[key]=self._inputs(pid,meta['options'],stored_edit_plan=saved_plan)['fingerprint']
                    except RenderError:fingerprints[key]=None
                item['stale']=item['source_fingerprint']!=fingerprints[key];item['stale_message']='Eski kaynaklara ait' if item['stale'] else '';item['status_label']=LABELS[item['status']]
                item['video_missing']=False
                if item['status']=='completed':
                    try:self._output(pid,item)
                    except RenderError:item['video_missing']=True
                item['encoder_label']=encoder_label(meta.get('encoder_used'));versions.append(item)
            jobs=c.execute('SELECT * FROM render_jobs WHERE project_id=? ORDER BY rowid DESC LIMIT 1',(pid,)).fetchone()
            job=dict(jobs) if jobs else None
            if job:
                job['progress']=json.loads(job.pop('progress_json'));job['status_label']=LABELS[job['status']];job['encoder_label']=encoder_label(job['progress'].get('encoder_used'))
                if 'diagnostic' in job['progress']:job['progress']['diagnostic']=safe_diagnostic(job['progress']['diagnostic'])
                if job['status'] in ACTIVE:
                    from datetime import datetime,timezone
                    job['progress']['elapsed_seconds']=round((datetime.now(timezone.utc)-datetime.fromisoformat(job['created_at'])).total_seconds(),1)
            music=self._music(c,pid)
        result={'ready':bool(source and tool['found']),'source_ready':bool(source),'source_message':source_error,'safe_error_category':source_category,'ffmpeg':{k:tool[k] for k in ('found','status','message','encoders')},'summary':summary,'versions':versions,'active':next((v for v in versions if v['id']==active_id),None),'job':job,'music':music,'smart_edit_plan':source['smart_edit_plan'] if source else None}
        from app.rendering.readiness import inspect,estimated_plan
        om=self.openmontage.status(refresh_tools)
        r,h,p=inspect(self,pid,tool,source,error,om if montage_engine=='openmontage' else None)
        with closing(self.projects._connection()) as c:
            stock_row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,p['plan_id'])).fetchone() if p else None
        raw=json.loads(stock_row[0]) if stock_row else None
        recovery=None
        if raw and p:
            from app.rendering.reflow import project
            _,recovery=project(h,p,raw,self.projects,self._hash)
        result['recovery']=recovery
        if recovery and recovery.get('render_ready') and source and r['narration_ready'] and r['subtitles_ready']:
            r['blockers']=[b for b in r['blockers'] if b['code'] not in ('stock_unresolved','media_file_missing')]
            r['stock_ready']=True;r['ready']=not r['blockers']
        elif recovery and recovery.get('effective_uncovered_duration'):
            r['blockers'].append({'code':'effective_gap','message':f"Akıllı kurguda {recovery['effective_uncovered_duration']:.1f} saniye güvenli biçimde kapatılamadı.",'screen':'production'})
        if job and job['status'] in ACTIVE:
            r['blockers'].append({'code':'render_active','message':'Başka render işlemi devam ediyor.','screen':'render'});r['ready']=False
        result.update(ready=r['ready'],readiness=r,openmontage=om,montage_engine=montage_engine)
        if not source:result['smart_edit_plan']=estimated_plan(h,p,opts)
        return SecretGuard(self.settings.secret_values()).clean(result)

    def _output(self,pid,item):
        if item['status']!='completed':raise RenderError('input_missing','Bu video henüz tamamlanmadı.',404)
        path=files.video_path(self.projects,pid,item['metadata'])
        if self._hash(path)!=item['metadata'].get('sha256'):raise RenderError('input_invalid','Video dosyası değişmiş. Önceki kayıtlar korundu.',404)
        return path

    def export(self,pid,vid):
        with closing(self.projects._connection()) as c:item=self._version(c,pid,vid)
        return self._output(pid,item)

    def activate(self,pid,vid):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self._idle(c,pid);item=self._version(c,pid,vid);self._output(pid,item)
            if self._inputs(pid,item['metadata']['options'],stored_edit_plan=item['metadata'].get('smart_edit_plan'))['fingerprint']!=item['source_fingerprint']:raise RenderError('source_stale',SOURCE_MESSAGE)
            c.execute('INSERT INTO render_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(pid,vid,now()))
        return {'message':'Aktif video seçildi.'}

    def handoff(self,pid):
        view=self.view(pid);active=view['active']
        if not active or active['stale'] or active['video_missing'] or active['status']!='completed':return {'contract_version':1,'project_id':pid,'ready':False}
        m=active['metadata'];result={'contract_version':1,'project_id':pid,'ready':True,'render_version_id':active['id'],'video_local_path':m['output_local_path'],'target_language':m['target_language']}
        result.update({k:active[k] for k in ('source_script_version_id','narration_version_id','subtitle_version_id','scene_plan_id')})
        result.update({k:m[k] for k in ('duration','width','height','fps','video_codec','audio_codec','encoder_used','file_size')});return result

    def music_upload(self,pid,suffix,data,confirmed):
        if confirmed is not True:raise RenderError('music_invalid','Bu müziği kullanma hakkına sahip olduğunuzu onaylayın.',422)
        if suffix not in ('mp3','wav','m4a','ogg','flac') or not 12<len(data)<=100_000_000:raise RenderError('music_invalid','En fazla 100 MB boyutunda MP3, WAV, M4A, OGG veya FLAC seçin.',422)
        from app.narration.audio import valid_signature
        if not valid_signature(data[:128],suffix):raise RenderError('music_invalid','Müzik dosyasının biçimi geçersiz.',422)
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);self._idle(c,pid)
            path=files.directory(self.projects,pid,'music')/(uuid4().hex+'.'+suffix)
            try:
                with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                from app.subtitles.duration import discover_duration
                duration,_=discover_duration(path)
                if not duration or duration<=0:raise ValueError()
                meta={'local_path':'music/'+path.name,'file_size':len(data),'sha256':files.sha256(path),'duration':duration,'license_confirmed':True}
                c.execute('INSERT INTO render_music VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET metadata_json=excluded.metadata_json,updated_at=excluded.updated_at',(pid,json.dumps(meta),now()))
            except Exception:
                path.unlink(missing_ok=True);raise RenderError('music_invalid','Müzik dosyası okunamadı. Geçerli bir ses dosyası seçin.',422) from None
        return {'message':'Müzik bilgisayarınızda kaydedildi.','music':meta}
