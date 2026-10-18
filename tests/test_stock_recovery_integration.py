"""Real API/SQLite/download/PNG decoding, mocked providers; no paid/network calls."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json

import httpx
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import create_app
from app.editor.editorial import Preferences
from app.production import narration_units, visual_blocks
from app.stock.models import StockError
from app.stock.download import Downloader
from app.stock.search_evidence import remember, failed_recently, reasons
from app.stock.search_session import SearchSession
from test_scripts import HEADERS
from test_production import scene
from test_subtitles import seed, no_network
from test_stock_media import media


def setup_recovery(app, count=32):
    text=' '.join('Lake lightning storm.' for _ in range(count))
    st=seed(app,text=text,seconds=count*5,language='en');pid=st['pid']
    with closing(app.state.projects._connection()) as c,c:
        c.execute('UPDATE editorial_state SET payload_json=? WHERE project_id=?',
                  (json.dumps(Preferences(editing_mode='manual',media_preparation_mode='sources_only',legacy_decorations=False).model_dump()),pid))
    units=narration_units(text)
    scenes=[{**scene([u['unit_id']]),'visual_intent':'lake lightning storm','stock_query':'lake lightning storm',
             'alternative_stock_queries':['storm lake','lake landscape'],'overlay_text':''} for u in units]
    blocks=visual_blocks({'scenes':scenes},text,'en',135,units=units)
    app.state.production.save_generated(pid,st['sid'],'en',blocks)
    app.state.narration.factory=no_network;app.state.scripts.provider_factory=no_network
    app.state.settings.save('pixabay',{'api_key':'synthetic-recovery-secret'})
    pngs={}
    for i in range(3):
        im=Image.new('RGB',(1920,1080),'#293e65');draw=ImageDraw.Draw(im)
        for x in range(0,1920,37+i*7):draw.rectangle((x,0,x+17,1080),fill=('#e3a957','#75c2c9','#ae7fd7')[i])
        b=BytesIO();im.save(b,format='PNG');pngs[str(i)]=b.getvalue()
    calls=[];downloads=[]
    class Provider:
        def __init__(self,name):self.name=name
        def search(self,query,kind,page=1):
            calls.append((self.name,kind,query,page))
            if self.name=='pixabay':raise StockError('rate_limit','Test kotası',429)
            if kind=='video':return []
            return [media(str(i),provider='wikimedia',kind='image',description='lake lightning storm',
                          query= query,page_url=f'https://commons.wikimedia.org/wiki/File:Lake{i}.png',
                          preview_url='',download_url=f'https://upload.wikimedia.org/wikipedia/commons/{i}.png',
                          source_metadata={'license':'CC0','license_url':'https://creativecommons.org/publicdomain/zero/1.0/'}) for i in range(3)]
    app.state.stock.factory=lambda name,settings:Provider(name)
    def download(request):
        downloads.append(str(request.url));return httpx.Response(200,headers={'Content-Type':'image/png'},content=pngs[request.url.path.rsplit('/',1)[-1][:-4]])
    app.state.stock.downloader=Downloader(app.state.projects,transport=httpx.MockTransport(download))
    return st,calls,downloads


def complete(client,pid,slot_id=None):
    base=f'/api/projects/{pid}/production/stock';state=client.get(base).json()
    r=client.post(base+(f'/slots/{slot_id}/jobs' if slot_id else '/jobs'),json={'plan_id':state['plan_id'],'revision':state['revision'],'action':'reselect' if slot_id else 'complete_media'})
    assert r.status_code==202,r.text
    client.app.state.stock.futures[r.json()['job_id']].result(timeout=60)
    state=client.get(base).json();assert state['job']['status']=='completed',state['job']
    assert not state['job']['progress'].get('slot_errors'),state['job']['progress']
    return state


def test_32_slot_recovery_preserves_sources_and_manual_document_and_downloads_diagnostics(tmp_path):
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as client:
        st,calls,downloads=setup_recovery(client.app);pid=st['pid'];base=f'/api/projects/{pid}/production/stock'
        advanced=client.app.state.editor
        from app.editor.advanced import AdvancedEditor
        editor=AdvancedEditor(advanced);before=editor.get(pid)
        result=complete(client,pid)
        assert len(result['slots'])>=32
        filled=[s for s in result['slots'] if s.get('selected_media')]
        assert len(filled)==3,result['media_summary']
        assert all(s['selected_media']['media_type']=='image' and s['local_validation']['accepted'] for s in filled)
        assert len({s['selected_media']['sha256'] for s in filled})==3
        assert len(downloads)==3
        missing=[s for s in result['slots'] if not s.get('selected_media')]
        assert len(missing)>=29 and all(s['director']['stage']=='sources_only' for s in missing)
        assert all(s['missing_reason_messages'] for s in missing)
        assert result['media_summary']['missing_seconds']>0
        assert any(c[0]=='wikimedia' for c in calls) and not any(c[0]=='pexels' for c in calls)
        assert any(c[1]=='image' for c in calls)
        assert result['job']['progress']['provider_searches']<=120
        locked=filled[0];r=client.post(base+f'/slots/{locked["slot_id"]}/actions',json={'plan_id':result['plan_id'],'revision':result['revision'],'action':'lock'})
        assert r.status_code==200,r.text
        snapshot={s['slot_id']:deepcopy(s['selected_media']) for s in filled}
        again=complete(client,pid)
        assert all(s['selected_media']['sha256']==snapshot[s['slot_id']]['sha256'] for s in again['slots'] if s['slot_id'] in snapshot)
        assert len(downloads)==3
        assert next(s for s in again['slots'] if s['slot_id']==locked['slot_id'])['locked']
        assert any(s['director'].get('history') for s in again['slots'] if not s.get('selected_media'))
        target=next(s for s in again['slots'] if not s.get('selected_media') and s.get('search_attempts'))
        retried=complete(client,pid,target['slot_id'])
        current=next(s for s in retried['slots'] if s['slot_id']==target['slot_id'])
        assert any(s.get('skipped')=='previous_failure' for s in current['director']['searches'])
        assert current['director']['history']
        assert len(downloads)==3
        assert editor.get(pid)==before
        diag=client.get(base+'/diagnostics');assert diag.status_code==200,diag.text
        assert 'attachment' in diag.headers['Content-Disposition'] and diag.headers['Cache-Control']=='no-store'
        report=diag.json();assert report['schema_version']==2 and len(report['slots'])>=32
        assert 'synthetic-recovery-secret' not in diag.text and 'local_path' not in diag.text and str(tmp_path) not in diag.text
        with closing(client.app.state.projects._connection()) as c:
            saved=json.loads(c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone()[0])
        assert any(s.get('search_attempts') for s in saved['slots'])
        print('RECOVERY',result['media_summary'],'provider calls',len(calls),'downloads',len(downloads))


def test_failed_attempt_ledger_expires_and_does_not_suppress_errors_or_changed_subject():
    slot={};entry={'provider':'wikimedia','media_type':'image','query':'Lake   lightning','page':1,'results':0}
    remember(slot,{'searches':[entry]},'subject',datetime.now(timezone.utc).isoformat())
    assert failed_recently(slot,{**entry,'query':'lake lightning'},'subject')
    assert not failed_recently(slot,entry,'other-subject')
    slot['search_attempts'][0]['normalization']={'raw_count':0}
    assert failed_recently(slot,{**entry,'page':2},'subject')
    slot['search_attempts'][0]['at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    assert not failed_recently(slot,entry,'subject')
    remember(slot,{'searches':[{**entry,'error':'rate_limit'}]},'subject',datetime.now(timezone.utc).isoformat())
    assert not failed_recently(slot,entry,'subject')
    assert reasons({'searches':[{'error':'rate_limit'}]})==['provider_rate_limited']
    assert reasons({})==['sources_only_no_approved_stock']
    assert reasons({'searches':[{'skipped':'previous_failure'}]})==['previous_search_failures_skipped']
    assert reasons({'rejected':{'duration':1}})==['candidate_duration_too_short']


def test_empty_search_cache_has_short_ttl(monkeypatch):
    import app.stock.search_session as module
    clock=[0];monkeypatch.setattr(module,'monotonic',lambda:clock[0]);session=SearchSession();calls=[]
    def empty():calls.append(1);return [],{'raw_count':0},False
    session.call('q',empty);clock[0]=299;session.call('q',empty);assert len(calls)==1
    clock[0]=301;session.call('q',empty);assert len(calls)==2


def test_job_budget_counts_shared_query_once_across_slots(monkeypatch):
    from types import SimpleNamespace
    from app.stock.director_media import MediaDirector
    import app.stock.search_evidence as evidence
    monkeypatch.setattr(evidence,'JOB_REQUESTS',1)
    director=MediaDirector.__new__(MediaDirector);director.language='en';director.pid='p';director.progress={};director.job={}
    director.providers=lambda scene=None:['wikimedia'];calls=[]
    def search(*args,**kw):
        calls.append(args);return [{'media_id':'shared'}],{'raw_count':1},False
    director.service=SimpleNamespace(_cache_search=search,_checkpoint=lambda *a,**kw:None)
    log={'searches':[]}
    assert director.search({'slot_id':'a','order':1},['video'],'lake lightning',log)
    assert director.search({'slot_id':'b','order':2},['video'],'lake lightning',log)
    assert not director.search({'slot_id':'b','order':2},['video'],'lake mountain',log)
    assert len(calls)==1 and log['searches'][-1]['skipped']=='budget'


def test_source_preparation_never_calls_configured_paid_translation(tmp_path):
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as client:
        st,_,_=setup_recovery(client.app,count=1)
        response=client.put('/api/settings/claude',json={'api_key':'sk-ant-synthetic-no-paid-translation','default_engine':True},headers={'X-AI-Video-Studio':'settings'})
        assert response.status_code==200,response.text
        paid=[]
        def forbidden():
            paid.append('called');raise AssertionError('No cloud request during manual media preparation')
        client.app.state.stock.ai_factory=forbidden
        result=complete(client,st['pid'])
        assert not paid
        assert 'otomatik bulut çevirisi yapılmadı' in result['translation_note']
        assert result['slots'][0]['sentence']=='Lake lightning storm.'
