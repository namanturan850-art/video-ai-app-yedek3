"""Bounded local timeline/source checks. No provider or external socket calls."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
from app.editor.advanced import AdvancedEditor
from app.projects import now
from app.editor.models import EditorError
from app.stock.models import StockError

VERSION='naman-local-quality-v1'


def inspect(editor,pid):
    from app.editor.service import sha256_file
    from app.stock.download import asset_path
    with editor.projects.lock:
        view=editor.view(pid);state=AdvancedEditor(editor).get(pid);doc=state['document'];issues=[];sources=[];seen={}
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
        identity=hashlib.sha256(json.dumps([view,doc,sources],sort_keys=True,default=str).encode()).hexdigest()
        with closing(editor.projects._connection()) as c:
            row=c.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(pid,identity,VERSION)).fetchone()
        if row:return {**json.loads(row[0]),'cached':True}
        report={'render_version_id':'local-'+identity,'source_sha256':identity,'summary':f'Yerel kalite kontrolü: {len(issues)} bulgu',
                'basis':'Yalnız timeline, kaynak hash/boyutları ve altyazı süreleri. Siyah kare pikselleri, ses sinyalleri ve anlamsal doğruluk bu kontrolde ölçülmedi.',
                'analysis_scope':'local_metadata','issues':issues,'cached':False,'external_calls':0,'samples':[],
                'unmeasured':['unexpected_black_pixels','audio_peak_loudness','rendered_subtitle_overflow','semantic_media_match']}
        with closing(editor.projects._connection()) as c,c:c.execute('INSERT OR REPLACE INTO archive_analysis_cache VALUES (?,?,?,?,?)',(pid,identity,VERSION,json.dumps(report,ensure_ascii=False),now()))
        return report
