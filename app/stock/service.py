"""Checkpointed stock assignment over the active Part 5 handoff, project scoped."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import time
from uuid import uuid4

from app.projects import now
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError
from app.stock.download import Downloader, asset_path, mirror
from app.stock.models import StockError, identity, make_slots, normalized_media, score
from app.stock.providers import make_stock_provider

LOG = logging.getLogger('uvicorn.error.stock')
PLAN_REQUIRED = 'Önce güncel Görsel / Kurgu Planını hazırlayın.'
ACTIVE = ('queued','running')
STATUSES = {'pending':'Bekliyor','searching':'Aranıyor','candidates':'Adaylar hazır',
            'downloading':'İndiriliyor','complete':'Tamamlandı','error':'Hata',
            'ai_needed':'AI görsel gerekebilir'}


def fingerprint(handoff):
    return hashlib.sha256(json.dumps(handoff,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def scene_binding(scene):
    return (scene['narration_text'], scene['start_estimate'], scene['end_estimate'])


class StockService:
    def __init__(self, production, settings):
        self.production, self.settings = production, settings
        self.projects = production.projects
        self.factory = make_stock_provider
        self.downloader = Downloader(self.projects)
        self.executor = ThreadPoolExecutor(max_workers=2,thread_name_prefix='stock-media')
        self.futures = {}
        self.closed = False

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)

    def recover(self):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute("UPDATE stock_jobs SET status='error',error_message=?,updated_at=? WHERE status IN ('queued','running')",
                               ('İşlem uygulama kapanırken durdu. Tamamlanan dosyalar korundu; Devam Et deyin.',now()))

    def _handoff(self, project_id):
        self.projects.get(project_id)
        try: return self.production.handoff(project_id)
        except ScriptError: raise StockError('plan_required',PLAN_REQUIRED,409) from None

    def _guard(self, value):
        SecretGuard(self.settings.secret_values()).validate(value)

    def _load(self, connection, project_id, plan_id):
        row = connection.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(project_id,plan_id)).fetchone()
        return json.loads(row[0]) if row else None

    def _save(self, connection, state):
        self._guard(state)
        state['revision'] += 1
        state['updated_at'] = now()
        connection.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?) ON CONFLICT(project_id,plan_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at',
                           (state['project_id'],state['plan_id'],state['source_version_id'],json.dumps(state,ensure_ascii=False),state['updated_at']))

    def _mirror(self, state):
        # SQLite is authoritative. A mirror failure never invalidates downloads.
        try: mirror(self.projects,state['project_id'],state['plan_id'],state)
        except (OSError, StockError): LOG.warning('stock operation=mirror category=local_storage')

    def _ensure(self, connection, handoff):
        project_id, plan_id = handoff['project_id'],handoff['plan_id']
        saved = self._load(connection,project_id,plan_id)
        stamp = fingerprint(handoff)
        if saved and saved['handoff_fingerprint']==stamp: return saved
        row = connection.execute('SELECT state_json FROM stock_plans WHERE project_id=? ORDER BY updated_at DESC LIMIT 1',(project_id,)).fetchone()
        previous = saved or (json.loads(row[0]) if row else None)
        state = {'project_id':project_id,'plan_id':plan_id,'source_version_id':handoff['source_script_version_id'],
                 'handoff_fingerprint':stamp,'revision':saved['revision'] if saved else 0,
                 'slots':[],'bindings':{},'warnings':[],'updated_at':now()}
        old_scenes = {}
        old_locked = []
        if previous and previous['source_version_id']==state['source_version_id']:
            for sid,binding in previous['bindings'].items():
                old_scenes[tuple(binding)] = [s for s in previous['slots'] if s['scene_id']==sid]
            old_locked = [s for s in previous['slots'] if s['locked'] and s['selected_media']]
        for scene in handoff['scenes']:
            sid = scene['scene_id']
            binding = scene_binding(scene)
            state['bindings'][sid] = binding
            old = old_scenes.get(binding)
            if old:
                slots = deepcopy(old)
                for slot in slots:
                    slot['scene_id'] = sid
                    if not slot['locked']:
                        slot['visual_goal'] = scene['visual_intent']
                        queries = [scene['primary_stock_query'],*scene['alternative_stock_queries']]
                        query = queries[min(slot['order']-1,len(queries)-1)]
                        if query != slot['search_query']: slot['candidates'] = []
                        slot.update(search_query=query,fallback_queries=[q for q in queries if q!=query],
                                    preferred_type=scene['preferred_media_type'],composition=scene['composition'])
            else:
                # A refreshed semantic scene may have different boundaries. Preserve
                # each locked visual interval, splitting its assignment at a new
                # scene boundary only. Narration/scene models are never rewritten.
                anchors = []
                for locked in old_locked:
                    a = max(scene['start_estimate'],locked['estimated_start'])
                    b = min(scene['end_estimate'],locked['estimated_end'])
                    if b-a < .001: continue
                    anchor = deepcopy(locked)
                    anchor.update(scene_id=sid,estimated_start=round(a,3),estimated_end=round(b,3),duration=round(b-a,3))
                    if a > locked['estimated_start']+.001:
                        anchor['slot_id']=uuid4().hex
                        anchor['warnings'].append('Kilitli medya yeni sahne sınırında paylaşıldı. Sonraki aşamada kesme zamanını kontrol edin.')
                    anchors.append(anchor)
                slots=[];cursor=scene['start_estimate']
                for anchor in sorted(anchors,key=lambda s:s['estimated_start']):
                    if anchor['estimated_start']>cursor+.001:
                        slots.extend(make_slots({**scene,'start_estimate':cursor,'end_estimate':anchor['estimated_start']}))
                    slots.append(anchor);cursor=anchor['estimated_end']
                if scene['end_estimate']>cursor+.001:
                    slots.extend(make_slots({**scene,'start_estimate':cursor,'end_estimate':scene['end_estimate']}))
                for index,slot in enumerate(slots): slot['order']=index+1
            state['slots'].extend(slots)
        if previous and any(s['locked'] and s['slot_id'] not in {n['slot_id'] for n in state['slots']} for s in previous['slots']):
            state['warnings'].append('Sahne sınırları veya senaryo değişti. Eski kilitli medya önceki plan kaydında korundu; yeni sahneleri kontrol edin.')
        self._save(connection,state)
        self._mirror(state)
        return state

    def _job(self, row):
        if not row: return None
        value = dict(row);value['progress'] = json.loads(value.pop('progress_json'))
        return value

    def view(self, project_id):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id)
            state = self._ensure(connection,handoff)
            public = deepcopy(state)
            for slot in public['slots']:
                if slot['selected_media']:
                    try: asset_path(self.projects,project_id,slot['selected_media'])
                    except (StockError,OSError):
                        slot['status']='error';slot['message']='Yerel dosya eksik veya değişmiş. Kilidi açıp Eksik Medyaları Tamamla deyin.'
                slot['status_label'] = STATUSES.get(slot['status'],'Bekliyor')
            rows = connection.execute('SELECT * FROM stock_jobs WHERE project_id=? AND plan_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                                      (project_id,handoff['plan_id'])).fetchone()
            public['job'] = self._job(rows)
            public['providers'] = {name:bool(self.settings.stock_config(name).get('api_key')) for name in ('pexels','pixabay')}
            media = [s['selected_media'] for s in public['slots'] if s['status']=='complete' and s['selected_media']]
            duplicates = len(media)-len({identity(m) for m in media})
            if duplicates: public['warnings'].append('Aynı stok medya birden fazla yuvada kullanılıyor. İsterseniz Değiştir ile çeşitlendirin.')
            if len(media)>=3 and any(all(m['media_type']=='image' for m in media[i:i+3]) for i in range(len(media)-2)):
                public['warnings'].append('Art arda durağan görseller var. Uygun video adaylarını kontrol edin.')
            if len(public['slots'])>=3 and any(all(s['composition']==public['slots'][i]['composition'] for s in public['slots'][i:i+3]) for i in range(len(public['slots'])-2)):
                public['warnings'].append('Benzer çekim kompozisyonları tekrarlanıyor. Medya önizlemelerini karşılaştırın.')
            self._guard(public)
            return public

    def _idle(self, connection, project_id):
        if connection.execute("SELECT 1 FROM stock_jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone():
            raise StockError('busy','Medya işlemi sürüyor. Tamamlanmasını bekleyin.',409)

    def _stamp(self, state, payload):
        if not isinstance(payload,dict) or payload.get('plan_id')!=state['plan_id'] or payload.get('revision')!=state['revision']:
            raise StockError('stale','Medya planı değişti. Yenileyip tekrar deneyin.',409)

    def _slot(self, state, slot_id):
        for slot in state['slots']:
            if slot['slot_id']==slot_id: return slot
        raise StockError('missing_slot','Medya yuvası bulunamadı. Planı yenileyin.',404)

    def mutate(self, project_id, slot_id, payload):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            state = self._ensure(connection,self._handoff(project_id))
            self._stamp(state,payload);self._idle(connection,project_id)
            if set(payload)-{'plan_id','revision','action'}: raise StockError('invalid_input','Medya işlemini kontrol edin.',422)
            slot = self._slot(state,slot_id)
            action = payload.get('action')
            if action=='unlock': slot['locked']=False
            elif action=='lock':
                if not slot['selected_media'] or slot['status']!='complete':
                    raise StockError('no_selection','Önce medya seçip indirin.',409)
                asset_path(self.projects,project_id,slot['selected_media']);slot['locked']=True
            elif action=='remove':
                if slot['locked']: raise StockError('locked','Önce medya kilidini açın.',409)
                slot.update(selected_media=None,status='pending',message='',warnings=[])
                # Project cache file stays; removing a slot never deletes shared assets.
            else: raise StockError('invalid_action','Bu medya işlemi kullanılamıyor.',422)
            self._save(connection,state);self._mirror(state)
        return self.view(project_id)

    def start(self, project_id, payload, *, slot_id=None):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id);state = self._ensure(connection,handoff)
            self._stamp(state,payload);self._idle(connection,project_id)
            if set(payload)-{'plan_id','revision','action','candidate_id','allow_duplicate'}:
                raise StockError('invalid_input','Medya işlemini kontrol edin.',422)
            action = payload.get('action')
            if action not in ('auto','missing','search','select'): raise StockError('invalid_action','Bu medya işlemi kullanılamıyor.',422)
            if (action in ('search','select')) != bool(slot_id): raise StockError('invalid_input','Geçerli medya yuvasını seçin.',422)
            progress = {'completed':[],'percent':0,'message':'Medya işlemi hazırlanıyor.','category':'none',
                        'handoff_fingerprint':state['handoff_fingerprint']}
            if slot_id:
                slot = self._slot(state,slot_id)
                if slot['locked']: raise StockError('locked','Önce medya kilidini açın.',409)
                if action=='select':
                    candidate = next((m for m in slot['candidates'] if candidate_id(m)==payload.get('candidate_id')),None)
                    if not candidate: raise StockError('invalid_candidate','Aday artık listede değil. Yeniden Ara deyin.',422)
                    duplicate = any(s['slot_id']!=slot_id and s['selected_media'] and identity(s['selected_media'])==identity(candidate) for s in state['slots'])
                    if duplicate and payload.get('allow_duplicate') is not True:
                        raise StockError('duplicate','Bu medya başka yuvada kullanılıyor. Başka aday seçin veya tekrar kullanımını onaylayın.',409)
                    progress['candidate'] = candidate
                    progress['duplicate'] = duplicate
            if not any(self.settings.stock_config(name).get('api_key') for name in ('pexels','pixabay')) and action!='select':
                raise StockError('missing_key','Ayarlar → Pexels veya Pixabay bölümünde API anahtarını kaydedin.',422)
            job_id = uuid4().hex;created = now()
            connection.execute('INSERT INTO stock_jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                (job_id,project_id,state['plan_id'],action,slot_id,'queued',json.dumps(progress,ensure_ascii=False),'',created,created))
        self.futures[job_id] = self.executor.submit(self._run,job_id)
        return {'job_id':job_id}

    def resume(self, project_id, job_id, payload):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            state = self._ensure(connection,self._handoff(project_id))
            self._stamp(state,payload);self._idle(connection,project_id)
            row = connection.execute('SELECT * FROM stock_jobs WHERE id=? AND project_id=?',(job_id,project_id)).fetchone()
            if (not row or row['plan_id']!=state['plan_id'] or row['status']!='error'
                    or json.loads(row['progress_json']).get('handoff_fingerprint')!=state['handoff_fingerprint']):
                raise StockError('stale_job','Bu işlem sürdürülemez. Güncel planda Eksik Medyaları Tamamla deyin.',409)
            connection.execute("UPDATE stock_jobs SET status='queued',error_message='',updated_at=? WHERE id=?",(now(),job_id))
        self.futures[job_id] = self.executor.submit(self._run,job_id)
        return {'job_id':job_id}

    def _checkpoint(self, job, progress, *, slot=None, status='running', error=''):
        project_id = job['project_id']
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id)
            state = self._load(connection,project_id,job['plan_id'])
            if (not state or handoff['plan_id']!=job['plan_id'] or state['handoff_fingerprint']!=fingerprint(handoff)
                    or progress.get('handoff_fingerprint')!=state['handoff_fingerprint']):
                raise StockError('stale_plan','Aktif sahne planı değişti. Tamamlanan dosyalar korundu; güncel planda Eksik Medyaları Tamamla deyin.',409)
            if slot:
                current = self._slot(state,slot['slot_id'])
                if current['locked']: raise StockError('locked','Kilitli medya değiştirilmedi.',409)
                current.update(slot);self._save(connection,state);self._mirror(state)
            self._guard(progress)
            connection.execute('UPDATE stock_jobs SET status=?,progress_json=?,error_message=?,updated_at=? WHERE id=?',
                               (status,json.dumps(progress,ensure_ascii=False),error,now(),job['id']))

    def _cache_search(self, project_id, name, kind, query):
        canonical = query[:100] if name=='pixabay' else query
        with self.projects.lock, closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT result_json,created_at FROM stock_search_cache WHERE project_id=? AND provider=? AND media_type=? AND query=?',
                                     (project_id,name,kind,canonical)).fetchone()
            if row and datetime.fromisoformat(row['created_at']) > datetime.now(timezone.utc)-timedelta(hours=24):
                return json.loads(row['result_json'])
        results = self.factory(name,self.settings).search(canonical,kind)
        results = [normalized_media(m) for m in results]
        self._guard(results)
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('INSERT OR REPLACE INTO stock_search_cache VALUES (?,?,?,?,?,?)',
                               (project_id,name,kind,canonical,json.dumps(results,ensure_ascii=False),now()))
        return results

    def _search(self, project_id, slot, used, progress, job):
        candidates, seen, failures, unavailable = [], set(), [], set()
        queries = list(dict.fromkeys([slot['search_query'],*slot['fallback_queries']]))[:6]
        # Search all video fallbacks before images, but only accept plausible matches.
        for kind in ('video','image'):
            for query in queries:
                for name in ('pexels','pixabay'):
                    if name in unavailable or not self.settings.stock_config(name).get('api_key'): continue
                    progress['message']=f"Sahne medyası aranıyor · {name.title()} {'video' if kind=='video' else 'görsel'}"
                    self._checkpoint(job,progress)
                    try: results = self._cache_search(project_id,name,kind,query)
                    except StockError as error:
                        failures.append(error)
                        unavailable.add(name)
                        continue
                    ranked = sorted((m for m in results if score(m,slot)>=0), key=lambda m:score(m,slot),reverse=True)
                    for media in ranked:
                        if identity(media) not in seen:
                            candidates.append(media);seen.add(identity(media))
                    if any(identity(m) not in used for m in candidates):
                        # A good usable result suffices: do not blindly call other APIs.
                        fresh = [m for m in candidates if identity(m) not in used]
                        repeated = [m for m in candidates if identity(m) in used]
                        return (fresh+repeated)[:12],failures
        return candidates[:12],failures

    def _run(self, job_id):
        started = time.monotonic();category = 'success';job = None
        try:
            with self.projects.lock, closing(self.projects._connection()) as connection:
                row = connection.execute('SELECT * FROM stock_jobs WHERE id=?',(job_id,)).fetchone()
                if not row: return
                job = self._job(row)
                state = self._load(connection,job['project_id'],job['plan_id'])
            progress = job['progress'];self._checkpoint(job,progress)
            slots = [deepcopy(s) for s in state['slots'] if not job['slot_id'] or s['slot_id']==job['slot_id']]
            used = {identity(s['selected_media']) for s in state['slots'] if s['selected_media'] and s['slot_id']!=job['slot_id']}
            for index,slot in enumerate(slots):
                if self.closed: raise StockError('interrupted','İşlem durdu. Tamamlanan medya korundu; Devam Et deyin.')
                progress['percent'] = int(index/max(1,len(slots))*100)
                if slot['locked']: continue
                if slot['slot_id'] in progress['completed']: continue
                if job['action'] in ('auto','missing') and slot['selected_media'] and slot['status']=='complete':
                    try:
                        asset_path(self.projects,job['project_id'],slot['selected_media'])
                        continue
                    except (StockError,OSError): pass
                progress['slot_id']=slot['slot_id'];progress['scene_id']=slot['scene_id'];progress['slot_order']=slot['order']
                # Keep existing selected media throughout replacement/search failures.
                progress['message']=f"Medya {index+1}/{len(slots)} aranıyor"
                self._checkpoint(job,progress)
                if job['action']=='select': candidates = [progress['candidate']];failures=[]
                else:
                    candidates,failures = self._search(job['project_id'],slot,used,progress,job)
                    slot['candidates']=candidates
                    self._checkpoint(job,progress,slot=slot)
                if job['action']=='search':
                    if not candidates and failures: raise failures[-1]
                    if not slot['selected_media']: slot['status']='candidates' if candidates else 'ai_needed'
                    slot['message']='Adayları önizleyip birini seçin.' if candidates else 'Uygun stok medya bulunamadı.'
                    self._checkpoint(job,progress,slot=slot)
                else:
                    available = [m for m in candidates if identity(m) not in used] if job['action']!='select' else candidates
                    duplicate = not available and bool(candidates)
                    if duplicate: available = candidates
                    if not available:
                        if failures: raise failures[-1]
                        if not slot['selected_media']: slot['status']='ai_needed'
                        slot['message']='Uygun stok medya bulunamadı. AI görsel gerekebilir; AI üretimi bu aşamada kapalı.'
                        self._checkpoint(job,progress,slot=slot)
                    else:
                        progress['message']=f"Medya {index+1}/{len(slots)} indiriliyor"
                        if not slot['selected_media']: slot['status']='downloading'
                        self._checkpoint(job,progress,slot=slot)
                        chosen = self.downloader.download(job['project_id'],available[0])
                        self._guard(chosen)
                        slot.update(selected_media=chosen,status='complete',message='İndirildi. Anlatıma uygunluğu Önizle ile kontrol edin.',warnings=[])
                        if duplicate or progress.get('duplicate'): slot['warnings'].append('Bu medya projede tekrar kullanılıyor. Değiştir ile başka aday seçebilirsiniz.')
                        if chosen['width']<1800 or chosen['height']<1000: slot['warnings'].append('Kaynak çözünürlüğü 1080p sınıfından düşük. Uygun daha yüksek çözünürlüklü aday varsa değiştirin.')
                        used.add(identity(chosen));self._checkpoint(job,progress,slot=slot)
                progress['completed'].append(slot['slot_id'])
                self._checkpoint(job,progress)
            progress.update(percent=100,message='Medya işlemi tamamlandı. Önizlemeleri kontrol edin.',category='none')
            self._checkpoint(job,progress,status='completed')
        except Exception as error:
            category = error.category if isinstance(error,StockError) else 'unexpected_backend'
            safe_message = str(error) if isinstance(error,StockError) else 'Medya işlemi tamamlanamadı. Tamamlanan dosyalar korundu; Devam Et deyin.'
            safe_message = SecretGuard(self.settings.secret_values()).clean(safe_message)
            if job:
                with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                    progress = job['progress'];progress['category']=category
                    progress = SecretGuard(self.settings.secret_values()).clean(progress)
                    state = self._load(connection,job['project_id'],job['plan_id'])
                    if state and progress.get('slot_id'):
                        failed = next((s for s in state['slots'] if s['slot_id']==progress['slot_id']),None)
                        if failed and not failed['selected_media'] and not failed['locked']:
                            failed.update(status='error',message=safe_message)
                            self._save(connection,state);self._mirror(state)
                    connection.execute("UPDATE stock_jobs SET status='error',progress_json=?,error_message=?,updated_at=? WHERE id=?",
                                       (json.dumps(progress,ensure_ascii=False),safe_message,now(),job_id))
        finally:
            LOG.info('stock operation=job result=%s category=%s elapsed_ms=%.0f',
                     'success' if category=='success' else 'failure',category,(time.monotonic()-started)*1000)

    def handoff(self, project_id):
        state = self.view(project_id)
        slots = []
        for slot in state['slots']:
            media = slot['selected_media']
            complete = slot['status']=='complete' and media is not None
            slots.append({'scene_id':slot['scene_id'],'slot_id':slot['slot_id'],'order':slot['order'],
                          'estimated_start':slot['estimated_start'],'estimated_end':slot['estimated_end'],
                          'slot_duration':slot['duration'],'status':slot['status'],'locked':slot['locked'],
                          **({key:media[key] for key in ('media_type','local_path','duration','width','height','provider','media_id')} if complete else
                             {key:None for key in ('media_type','local_path','duration','width','height','provider','media_id')}),
                          'trim_needed':bool(complete and media['media_type']=='video' and media['duration']>slot['duration']+0.05)})
        return {'contract_version':1,'project_id':project_id,'plan_id':state['plan_id'],
                'source_script_version_id':state['source_version_id'],'timing_source':'estimated',
                'ready':all(s['status']=='complete' for s in slots),'slots':slots,'rendered':False}


def candidate_id(media):
    return media['provider']+':'+media['media_type']+':'+media['media_id']
