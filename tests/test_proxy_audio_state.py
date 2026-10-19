"""Full audio state must not restart loudnorm/ducking every four seconds."""
from array import array
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import struct
import subprocess
import wave

from fastapi.testclient import TestClient
from app.main import create_app
from app.editor.advanced import Document,AdvancedEditor
from app.editor.proxy_audio import master
from app.editor.proxies import snapshot
from app.rendering.engine import LOUDNESS
from test_manual_first import install_manual_example


def tone(path,frequency,vary=False):
    def sample(i):
        amplitude=(3000 if i<3*48000 or i>=7*48000 else 18000) if vary else 5000
        return round(amplitude*math.sin(2*math.pi*frequency*i/48000))
    samples=array('h',(sample(i) for i in range(12*48000)))
    with wave.open(str(path),'wb') as output:output.setnchannels(1);output.setsampwidth(2);output.setframerate(48000);output.writeframes(samples.tobytes())


def decoded(path,start=0,duration=12):
    raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(start),'-i',str(path),'-t',str(duration),'-ar','48000','-ac','2','-f','f32le','-'])
    data=array('f');data.frombytes(raw);return data


def test_full_mix_matches_existing_operators_with_fades_and_ducking_across_slices(tmp_path):
    voice=tmp_path/'voice.wav';music=tmp_path/'music.wav';tone(voice,220,True);tone(music,660)
    digest=hashlib.sha256(music.read_bytes()).hexdigest();cid='a'*32
    doc=Document.model_validate({'clips':[{'id':cid,'kind':'media','track':'audio','start':0.,'end':12.,'media':{'provider':'local','media_id':'music','sha256':digest},'transform':{'volume':.2},'ducking':True,'fade_in':1.,'fade_out':1.}]}).model_dump()
    data={'document':doc,'assets':{cid:{'path':music,'type':'audio','has_audio':True}},'slots':{},'duration':12.,'narration':voice,'mix':{'narration_volume':.7,'narration_fade_in':1.,'narration_fade_out':1.}}
    before=deepcopy(data);cached=master(tmp_path,'a'*64,data,'ffmpeg');stamp=cached.stat().st_mtime_ns
    assert master(tmp_path,'a'*64,data,'ffmpeg')==cached and cached.stat().st_mtime_ns==stamp
    graph=(f'[0:a]asplit[vin][side];[vin]aresample=48000,apad,atrim=duration=12,asetpts=PTS-STARTPTS,volume=0.7,afade=t=in:st=0:d=1,afade=t=out:st=11:d=1,{LOUDNESS}[voice];'
           '[1:a]aresample=48000,atrim=duration=12,asetpts=PTS-STARTPTS,atempo=1,asetpts=N/SR/TB,volume=0.2,volume=min(1\\,t/1):eval=frame,volume=max(0\\,min(1\\,(12-t)/1)):eval=frame,apad=whole_len=576000,atrim=end_sample=576000,asetpts=N/SR/TB[music];'
           '[side]aresample=48000,asetpts=PTS-STARTPTS,apad[duck];[music][duck]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250,atrim=end_sample=576000,asetpts=N/SR/TB[bg];'
           '[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.84:level=false[mixed]')
    reference=tmp_path/'reference.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-filter_complex_threads','1','-i',str(voice),'-i',str(music),'-filter_complex',graph,'-map','[mixed]','-c:a','pcm_f32le','-ar','48000','-ac','2','-t','12',str(reference)],check=True)
    expected=decoded(reference);actual=array('f')
    for start in (0,4,8):actual.extend(decoded(cached,start,4))
    assert len(actual)==len(expected)==12*48000*2
    assert max(abs(a-b) for a,b in zip(actual,expected))<3e-7  # only 24-bit FLAC quantization
    assert data==before


def test_audio_cache_identity_ignores_visual_changes_but_tracks_mix_changes(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app);ed=app.state.editor;pid=st['pid'];advanced=AdvancedEditor(ed)
        _,first,_=snapshot(ed,advanced,pid,0,'high');before=advanced.get(pid)
        changed=deepcopy(before);changed['document']['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':3.,'text':'Manuel'})
        advanced.save(pid,changed);_,second,_=snapshot(ed,advanced,pid,0,'high')
        assert second['audio_key']==first['audio_key']
        settings=ed.audio_settings(pid);settings.pop('project_id');settings['narration_volume']=.5
        ed.save_audio_settings(pid,settings)
        _,third,_=snapshot(ed,advanced,pid,0,'high');assert third['audio_key']!=first['audio_key']


def test_silent_visual_file_is_not_required_for_audio_only_preparation(tmp_path):
    from app.editor.proxy_audio import snapshot as audio_snapshot
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app);editor=app.state.editor;asset=st['assets'][1]
        doc=Document.model_validate({'clips':[{'id':'b'*32,'kind':'media','track':'layers','start':2.,'end':3.,'media':{'provider':asset['provider'],'media_id':asset['media_id'],'sha256':asset['sha256']}}]}).model_dump()
        (st['root']/asset['local_path']).unlink()  # only disposable synthetic data
        before=deepcopy(doc)
        key,data=audio_snapshot(editor,st['pid'],doc,{'duration':4.,'tracks':{}},None,editor.audio_settings(st['pid']),None)
        assert data['document']['clips']==[] and not data['assets'] and doc==before and len(key)==64


def test_muted_video_with_audio_is_not_probed_or_required_by_narration_mix(tmp_path):
    from contextlib import closing
    import json
    import pytest
    from app.stock.models import StockError
    from app.editor.proxy_audio import snapshot as audio_snapshot
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app);editor=app.state.editor;asset=st['assets'][0]
        metadata={**asset,'has_audio':True}
        with closing(app.state.projects._connection()) as c,c:
            c.execute('UPDATE stock_assets SET metadata_json=? WHERE project_id=? AND provider=? AND media_id=?',
                      (json.dumps(metadata),st['pid'],asset['provider'],asset['media_id']))
        doc=Document.model_validate({'clips':[{'id':'c'*32,'kind':'media','track':'layers','start':0.,'end':1.,
            'media':{k:asset[k] for k in ('provider','media_id','sha256')},'transform':{'volume':0.}}]}).model_dump()
        (st['root']/asset['local_path']).unlink()  # only disposable test data
        before=deepcopy(doc)
        _,data=audio_snapshot(editor,st['pid'],doc,{'duration':4.,'tracks':{}},None,editor.audio_settings(st['pid']),None)
        assert data['document']['clips']==[] and data['assets']=={} and doc==before
        doc['clips'][0]['transform']['volume']=.2
        with pytest.raises(StockError):audio_snapshot(editor,st['pid'],doc,{'duration':4.,'tracks':{}},None,editor.audio_settings(st['pid']),None)
