"""Trusted tool aliases only; project media symlink policy remains strict."""
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.projects import linked
from app.settings import ffmpeg_status
from app.rendering import tools
from app.rendering.models import RenderError


@pytest.fixture
def installation(tmp_path,monkeypatch):
    local=tmp_path/'Local AppData (Türkçe)';links=local/'Microsoft'/'WinGet'/'Links';links.mkdir(parents=True)
    package=local/'Microsoft'/'WinGet'/'Packages'/'Gyan.FFmpeg_fixture'/'bin';package.mkdir(parents=True)
    ffmpeg=package/'ffmpeg.exe';ffprobe=package/'ffprobe.exe';ffmpeg.touch();ffprobe.touch()
    monkeypatch.setenv('LOCALAPPDATA',str(local))
    monkeypatch.setattr(tools.shutil,'which',lambda name:None)
    calls=[]
    def run(args,**kwargs):
        assert kwargs['shell'] is False and isinstance(args,list)
        assert Path(args[0]) in (ffmpeg,ffprobe)
        assert not linked(Path(args[0]))
        calls.append(args)
        output=('ffprobe version fixture' if Path(args[0])==ffprobe else 'ffmpeg version 9.0.2-full_build-www.gyan.dev') if args[1:]==['-version'] else 'V....D libx264\nV....D h264_nvenc\nass xfade fade zoompan sidechaincompress amix afade'
        return SimpleNamespace(returncode=0,stdout=output,stderr='')
    monkeypatch.setattr(tools.subprocess,'run',run)
    return SimpleNamespace(local=local,links=links,package=package,ffmpeg=ffmpeg,ffprobe=ffprobe,calls=calls,root=tmp_path/'app')


def alias(path,target):
    try:path.symlink_to(target,target_is_directory=target.is_dir())
    except OSError:pytest.skip('Symlink creation requires Windows developer mode/permission')
    return path


def test_direct_path_validated(installation,monkeypatch):
    st=installation;monkeypatch.setattr(tools.shutil,'which',lambda name:str(st.ffmpeg) if name=='ffmpeg' else str(st.ffprobe))
    result=tools.discover(root=st.root)
    assert result['found'] and result['ffmpeg']==str(st.ffmpeg.resolve())
    assert result['ffprobe']==str(st.ffprobe.resolve()) and 'h264_nvenc' in result['encoders']
    assert [str(st.ffmpeg),'-version'] in st.calls and [str(st.ffprobe),'-version'] in st.calls


def test_winget_path_alias_resolves_regular_targets(installation,monkeypatch):
    st=installation;exe=alias(st.links/'ffmpeg.exe',st.ffmpeg);probe=alias(st.links/'ffprobe.exe',st.ffprobe)
    assert linked(exe) and linked(probe)  # the precise old reject condition
    monkeypatch.setattr(tools.shutil,'which',lambda name:str(exe if name=='ffmpeg' else probe))
    result=tools.discover(root=st.root)
    assert result['found'] and result['ffmpeg']==str(st.ffmpeg) and result['ffprobe']==str(st.ffprobe)
    assert all(Path(c[0]).parent==st.package for c in st.calls)
    assert linked(exe) and linked(probe)  # no project-path protection was changed


def test_winget_fallback_older_path(installation):
    st=installation;alias(st.links/'ffmpeg.exe',st.ffmpeg);alias(st.links/'ffprobe.exe',st.ffprobe)
    result=tools.discover(root=st.root);assert result['found'] and result['ffmpeg']==str(st.ffmpeg) and result['ffprobe']==str(st.ffprobe)


def test_sibling_probe_next_to_resolved_ffmpeg(installation,monkeypatch):
    st=installation;exe=alias(st.links/'ffmpeg.exe',st.ffmpeg)
    monkeypatch.setattr(tools.shutil,'which',lambda name:str(exe) if name=='ffmpeg' else None)
    result=tools.discover(root=st.root);assert result['ffprobe']==str(st.ffprobe)


@pytest.mark.parametrize('kind',['broken','directory','loop'])
def test_bad_alias_rejected(installation,kind):
    st=installation;path=st.links/'ffmpeg.exe'
    if kind=='broken':alias(path,st.package/'missing.exe')
    elif kind=='directory':alias(path,st.package)
    else:alias(path,path)
    result=tools.discover(root=st.root);assert not result['found'] and not st.calls


@pytest.mark.parametrize('path',[r'\\server\share\ffmpeg.exe','//server/share/ffmpeg.exe',r'\\?\UNC\server\share\ffmpeg.exe',r'\\?\C:\ffmpeg.exe','https://host/ffmpeg.exe','http://host/tool','file:///C:/ffmpeg.exe','file:C:/ffmpeg.exe','ssh://host/tool'])
def test_network_and_url_paths_rejected_before_resolution(installation,monkeypatch,path):
    st=installation;monkeypatch.setattr(tools.shutil,'which',lambda _:path)
    assert tools.resolve_executable(path) is None
    result=tools.discover(root=st.root);assert not result['found'] and not st.calls


def test_resolved_target_network_rejected(installation,monkeypatch):
    st=installation
    monkeypatch.setattr(Path,'resolve',lambda self,strict=False:Path('//server/share/ffmpeg.exe'))
    assert tools.resolve_executable(st.ffmpeg) is None and not st.calls


def test_reparse_alias_resolved_before_link_rejection(installation,monkeypatch):
    st=installation;exe=st.links/'ffmpeg.exe';exe.touch();original=Path.resolve
    monkeypatch.setattr(Path,'resolve',lambda self,strict=False:st.ffmpeg if self==exe else original(self,strict=strict))
    monkeypatch.setattr(tools,'linked',lambda p:p==exe)
    result=tools.discover(configured=exe,root=st.root);assert result['found'] and result['ffmpeg']==str(st.ffmpeg)


def test_fake_binary_banner_rejected(installation,monkeypatch):
    st=installation;monkeypatch.setattr(tools.shutil,'which',lambda name:str(st.ffmpeg) if name=='ffmpeg' else None)
    monkeypatch.setattr(tools,'inspect',lambda *a:'Not a trusted FFmpeg version')
    with pytest.raises(RenderError) as error:tools.discover(root=st.root)
    assert error.value.category=='ffmpeg_invalid' and not ffmpeg_status()['found']


def test_invalid_probe_is_optional_and_not_used(installation,monkeypatch):
    st=installation;alias(st.links/'ffmpeg.exe',st.ffmpeg);alias(st.links/'ffprobe.exe',st.ffprobe)
    original=tools.inspect
    monkeypatch.setattr(tools,'inspect',lambda exe,args:'not ffprobe' if Path(exe)==st.ffprobe else original(exe,args))
    result=tools.discover(root=st.root);assert result['found'] and result['ffprobe'] is None


def test_statuses_share_discovery_and_hide_paths(installation,tmp_path):
    st=installation;alias(st.links/'ffmpeg.exe',st.ffmpeg)
    with TestClient(create_app(tmp_path/'data')) as c:
        pid=c.app.state.projects.create({'name':'Winget','topic':'Detection'})['id']
        settings=c.get('/api/settings').json()['ffmpeg'];render=c.get(f'/api/projects/{pid}/render?refresh_tools=true').json()['ffmpeg'];diagnostics=c.get('/api/diagnostics').json()
        assert settings['found']==render['found']==diagnostics['ffmpeg_found']==True
        assert settings['status']==render['status']=='Hazır'
        assert str(st.package) not in str(settings) and str(st.package) not in str(render)


def test_manual_refresh_bypasses_missing_cache(installation,tmp_path):
    st=installation
    with TestClient(create_app(tmp_path/'data')) as c:
        pid=c.app.state.projects.create({'name':'Refresh','topic':'Existing PATH'})['id'];url=f'/api/projects/{pid}/render'
        assert not c.get(url).json()['ffmpeg']['found']
        alias(st.links/'ffmpeg.exe',st.ffmpeg)
        assert not c.get(url).json()['ffmpeg']['found']  # ordinary polling retains short cache
        assert c.get(url+'?refresh_tools=true').json()['ffmpeg']['found']
        assert c.get(url).json()['ffmpeg']['found']
        assert c.get('/api/settings').json()['ffmpeg']['found']


def test_real_ffmpeg_alias_without_mocks(tmp_path,monkeypatch):
    ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('Real FFmpeg/ffprobe optional')
    local=tmp_path/'Local AppData (şü)';links=local/'Microsoft'/'WinGet'/'Links';links.mkdir(parents=True)
    exe=alias(links/'ffmpeg.exe',Path(ffmpeg).resolve());probe=alias(links/'ffprobe.exe',Path(ffprobe).resolve())
    monkeypatch.setenv('LOCALAPPDATA',str(local));monkeypatch.setattr(tools.shutil,'which',lambda _:None)
    result=tools.discover(root=tmp_path/'app')
    assert result['found'] and result['ffmpeg']==str(Path(ffmpeg).resolve()) and result['ffprobe']==str(Path(ffprobe).resolve())
    assert 'libx264' in result['encoders'] and linked(exe) and linked(probe)

@pytest.mark.parametrize('drive_type,accepted',[(0,False),(1,False),(4,False),(2,True),(3,True),(5,True),(6,True)])
def test_windows_mapped_drive_policy(monkeypatch,drive_type,accepted):
    import ctypes
    import os
    calls=[]
    def get_type(anchor):calls.append(anchor);return drive_type
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(kernel32=SimpleNamespace(GetDriveTypeW=get_type)),raising=False)
    monkeypatch.setattr(tools,'os',SimpleNamespace(name='nt',environ=os.environ))
    assert tools.local_path(r'Z:\Apps\ffmpeg.exe') is accepted
    assert calls==['Z:\\'] and get_type.argtypes==[ctypes.c_wchar_p]


def test_invalid_binary_status_consistency(installation,tmp_path,monkeypatch):
    st=installation;alias(st.links/'ffmpeg.exe',st.ffmpeg)
    monkeypatch.setattr(tools,'inspect',lambda *a:'wrong version banner')
    with TestClient(create_app(tmp_path/'data')) as c:
        pid=c.app.state.projects.create({'name':'Invalid','topic':'Status'})['id']
        settings=c.get('/api/settings').json()['ffmpeg'];render=c.get(f'/api/projects/{pid}/render?refresh_tools=true').json()['ffmpeg']
        assert settings['status']==render['status']=='Hata' and settings['found']==render['found']==False
        assert not c.get('/api/diagnostics').json()['ffmpeg_found']


def test_executable_failure_is_safe(installation,monkeypatch):
    st=installation;alias(st.links/'ffmpeg.exe',st.ffmpeg)
    def fail(*args,**kwargs):raise OSError('private system path or sensitive process failure')
    monkeypatch.setattr(tools.subprocess,'run',fail)
    with pytest.raises(RenderError) as error:tools.discover(root=st.root)
    assert error.value.category=='ffmpeg_invalid' and 'private' not in str(error.value)

# Existing local sources/provider-forbidden fixture; no paid calls/downloads.
from test_rendering import ready, url, await_job


def test_real_render_through_winget_alias_with_old_path(ready,monkeypatch,tmp_path):
    executable=shutil.which('ffmpeg');probe=shutil.which('ffprobe')
    if not executable or not probe:pytest.skip('Real FFmpeg/ffprobe optional')
    local=tmp_path/'Local AppData';links=local/'Microsoft'/'WinGet'/'Links';links.mkdir(parents=True)
    alias(links/'ffmpeg.exe',Path(executable).resolve());alias(links/'ffprobe.exe',Path(probe).resolve())
    monkeypatch.setenv('LOCALAPPDATA',str(local));monkeypatch.setattr(tools.shutil,'which',lambda _:None)
    client=ready['client']
    assert client.get(url(ready)+'?refresh_tools=true').json()['ffmpeg']['found']
    assert client.get('/api/settings').json()['ffmpeg']['found']
    assert client.post(url(ready)+'/jobs',json={'encoder':'cpu'}).status_code==202
    state=await_job(ready);assert state['job']['status']=='completed',state
    assert state['active']['metadata']['encoder_used']=='libx264'
    for name,data in ready['originals'].items():assert (ready['root']/name).read_bytes()==data
