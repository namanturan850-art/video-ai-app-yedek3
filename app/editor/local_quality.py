"""Bounded local timeline/source checks. No provider or external socket calls."""
from contextlib import closing
import hashlib
import json
import math
import subprocess
import struct
from pathlib import Path
from app.editor.advanced import AdvancedEditor
from app.projects import now
from app.editor.models import EditorError
from app.stock.models import StockError
from app.rendering.models import RenderError
from app.narration.models import NarrationError
from app.editor.previews import decoder

VERSION='naman-local-quality-v1'


def inspect(editor,pid):
    from app.editor.service import sha256_file
    from app.stock.download import asset_path
    with editor.projects.lock:
        view=editor.view(pid);state=AdvancedEditor(editor).get(pid);doc=state['document'];issues=[];sources=[];seen={};rendered=None;render_version=None;voice=None;audio_measurement=None;sample_times=[]
        def issue(t,category,message,**kw):issues.append({'timecode':max(0,float(t)),'category':category,'message':message,'severity':'warning','basis':'Yerel timeline ve doğrulanmış dosya bilgisi; görüntü/anlatım anlamı incelenmedi.',**kw})
        media=sorted((x for v in view['tracks'].values() for x in v if x.get('slot_id')),key=lambda x:x['start'])
        for slot in media:
            asset=slot.get('media');start=slot['start'];length=slot['end']-start
            if not asset:
                issue(start,'Boş sahne',f'{length:.2f} sn boş yuva.',severity='info' if slot.get('intentional_empty') else 'warning',intentional=bool(slot.get('intentional_empty')));continue
            try:
                path=asset_path(editor.projects,pid,asset);stat=path.stat();sources.append([str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
                verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
                actual=verifier(path,asset.get('sha256')) if verifier else sha256_file(path)
                if asset.get('sha256') and actual!=asset['sha256']:issue(start,'Değişmiş kaynak','Dosya özeti kayıtla eşleşmiyor.')
            except (OSError,RuntimeError,ValueError,EditorError,StockError):issue(start,'Eksik kaynak','Kaynak dosyası açılamadı; arşivi kontrol edin.');continue
            identity=asset.get('sha256') or str(path)
            if identity in seen:issue(start,'Tekrar',f'Aynı kaynak {seen[identity]:.2f} sn noktasında da kullanılıyor; kompozisyonu elle karşılaştırın.')
            else:seen[identity]=start
            if length>25:issue(start,'Uzun klip',f'{length:.1f} sn kesintisiz kaynak; ritmi kontrol edin.')
            w,h=asset.get('width'),asset.get('height')
            if w and h and (w<1280 or abs(w/h-16/9)>.1):issue(start,'Kaynak boyutu',f'{w}×{h} kaynak; 1080p ölçekleme/kırpma uygulanacak.')
        for clip in doc['clips']:
            if clip['kind']=='media':
                try:
                    path,asset=editor.archive_file(pid,clip['media']['provider'],clip['media']['media_id']);stat=path.stat();sources.append([str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
                    verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None);actual=verifier(path,clip['media']['sha256']) if verifier else sha256_file(path)
                    if actual!=clip['media']['sha256']:issue(clip['start'],'Değişmiş kaynak','Ek klibin kaynak özeti değişmiş.')
                except (OSError,RuntimeError,ValueError,EditorError,StockError):issue(clip['start'],'Eksik kaynak','Ek klip kaynağı kullanılamıyor.')
        for cue in view['tracks']['subtitles']:
            duration=cue['end']-cue['start'];chars=len(cue['text'])
            if duration<=0 or cue['end']>view['duration']+.04:issue(cue['start'],'Altyazı zamanı','Altyazı ana anlatım saatini aşıyor veya süresi geçersiz.')
            if chars/max(.01,duration)>25 or chars>200:issue(cue['start'],'Altyazı okunabilirliği','Altyazı çok uzun/hızlı; otomatik satır yerleşimi dışında okunabilirliği elle kontrol edin.')
        subtitle_state=editor.subtitles.view(pid)
        voice_meta=(subtitle_state.get('narration') or {}).get('metadata',{}).get('audio')
        if voice_meta:
            from app.narration.audio import audio_path
            try:
                voice=audio_path(editor.projects,pid,voice_meta);stat=voice.stat();sources.append([str(voice),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
                if sha256_file(voice)!=voice_meta.get('sha256'):issue(0,'Değişmiş anlatım','Anlatım dosyası özeti değişmiş.');voice=None
            except (OSError,RuntimeError,ValueError,NarrationError):voice=None
        if getattr(editor,'rendering',None):
            state_render=editor.rendering.view(pid);render_version=state_render.get('active')
            if render_version and render_version.get('status')=='completed' and not render_version.get('video_missing'):
                try:
                    rendered=editor.rendering.export(pid,render_version['id']);stat=rendered.stat();sources.append([str(rendered),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns])
                except (OSError,RuntimeError,ValueError,RenderError):rendered=None
        identity=hashlib.sha256(json.dumps([view,doc,sources],sort_keys=True,default=str).encode()).hexdigest()
        with closing(editor.projects._connection()) as c:
            row=c.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(pid,identity,VERSION)).fetchone()
        if row:return {**json.loads(row[0]),'cached':True}
    if voice:
        try:
            with decoder():decoded=subprocess.run(['ffmpeg','-v','error','-i',str(voice),'-t','4','-ar','48000','-ac','1','-f','f32le','-'],capture_output=True,timeout=15,check=True).stdout
            samples=struct.unpack('<'+'f'*(len(decoded)//4),decoded)
            peak=max((abs(v) for v in samples),default=0);rms=math.sqrt(sum(v*v for v in samples)/max(1,len(samples)))
            audio_measurement={'start':0.,'duration':len(samples)/48000,'peak_dbfs':round(20*math.log10(max(peak,1e-12)),2),'rms_dbfs':round(20*math.log10(max(rms,1e-12)),2),'scope':'narration_only_first_four_seconds'}
            if rms<.003:issue(0,'Düşük anlatım sesi','İlk dört saniyelik anlatım örneğinde düşük RMS ölçüldü; sessizlik bilinçli olabilir.')
            if peak>.98:issue(0,'Yüksek anlatım tepe seviyesi','İlk dört saniyede 0 dBFS sınırına yakın örnek ölçüldü.')
        except (OSError,subprocess.SubprocessError,ValueError,EditorError):issue(0,'Ses ölçülemedi','Kısa anlatım örneği çözülemedi; ses aygıtında elle kontrol edin.')
    if rendered:
        length=float(render_version.get('metadata',{}).get('duration') or view['duration']);pixel_hashes={}
        for i in range(6):
            at=math.floor(max(0,min(length*(i+.5)/6,length-2/30))*30)/30
            try:
                with decoder():pixels=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(rendered),'-frames:v','1','-vf','scale=32:18,format=gray','-f','rawvideo','-'],capture_output=True,timeout=10,check=True).stdout
                if len(pixels)!=576:continue
                sample_times.append(at)
                if max(pixels)<8:
                    slot=next((s for s in media if s['start']<=at<s['end']),{})
                    issue(at,'Siyah kare örneği','Bu örnek karenin bütün pikselleri siyaha yakın. Fade/boş yuva niyetini kontrol edin.',severity='info' if slot.get('intentional_empty') else 'warning')
                digest=hashlib.sha256(pixels).hexdigest()
                if digest in pixel_hashes:issue(at,'Tekrarlanan örnek kare',f'{pixel_hashes[digest]:.3f} sn ile aynı küçültülmüş örnek; durağan sahne bilinçli olabilir.')
                pixel_hashes[digest]=at
            except (OSError,subprocess.SubprocessError,EditorError):issue(at,'Kare çözülemedi','Tamamlanmış videonun bu örnek karesi açılamadı.')
    report={'render_version_id':'local-'+identity,'source_sha256':identity,'summary':f'Yerel kalite kontrolü: {len(issues)} bulgu',
            'basis':'Yerel timeline/hash/boyut kontrolleri; varsa tamamlanmış videodan en fazla altı küçültülmüş kare ve anlatımın ilk dört saniyesinin peak/RMS ölçümü. Tam video ve final miksin tamamı analiz edilmedi.',
            'analysis_scope':'local_metadata_and_samples' if sample_times else 'local_metadata','issues':issues,'cached':False,'external_calls':0,'samples':sample_times,'sample_timecodes':sample_times,'audio_measurement':audio_measurement,
            'unmeasured':['full_video_black_detection','final_mix_integrated_loudness','rendered_subtitle_overflow','semantic_media_match']}
    if AdvancedEditor(editor).get(pid)['revision']!=state['revision']:raise EditorError('stale_review','Kurgu inceleme sırasında değişti; yerel denetimi yeniden başlatın.',409)
    with closing(editor.projects._connection()) as c,c:c.execute('INSERT OR REPLACE INTO archive_analysis_cache VALUES (?,?,?,?,?)',(pid,identity,VERSION,json.dumps(report,ensure_ascii=False),now()))
    return report
