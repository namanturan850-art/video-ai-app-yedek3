from types import SimpleNamespace

from app.stock.clip_check import ClipCheck


class Bridge:
    def status(self):
        return {'semantic_ready': True, 'semantic_model_version': 'v1'}

    def call(self, name, payload, work):
        return {'results': [{'key': 'a', 'verdict': 'match', 'score': 8}], 'metrics': {'device': 'cuda', 'image_vector_hits': 1}}


def test_clip_reports_where_it_ran(tmp_path):
    check = ClipCheck(SimpleNamespace(openmontage=Bridge()))
    out = check.score('a photo of a river', [('a', [b'not an image'])], tmp_path)
    assert out['a']['verdict'] == 'match'
    assert check.metrics['device'] == 'cuda' and check.metrics['image_vector_hits'] == 1


class BrokenBridge(Bridge):
    def call(self, name, payload, work):
        raise RuntimeError('CUDA error: no kernel image is available for execution on the device')


def test_clip_failure_keeps_the_real_reason_for_the_diagnostics(tmp_path):
    check = ClipCheck(SimpleNamespace(openmontage=BrokenBridge()))
    assert check.score('a photo of a river', [('a', [b'x'])], tmp_path) == {}
    assert check.broken and check.ready() is False
    assert check.error.startswith('RuntimeError: CUDA error')


def test_frames_process_keeps_the_real_cause_when_the_worker_reports_failure(tmp_path):
    import os, sys
    from app.integrations.openmontage.frames_process import FramesError, FramesProcess
    script = tmp_path / 'worker.py'
    script.write_text('import sys,json\nfor line in sys.stdin:\n print(json.dumps({"success":False,"error_class":"OSError","detail":"DLL load failed [torch 2.9; cuda=False]"}),flush=True)\n')
    worker = FramesProcess()
    try:
        try:
            worker.call([sys.executable, str(script)], tmp_path, dict(os.environ), {})
            assert False, 'must fail'
        except FramesError as error:
            assert error.reason == 'semantic_worker_failed'
            assert 'OSError' in error.detail and 'DLL load failed' in error.detail
    finally:
        worker.close()


def test_frames_process_reports_exit_code_when_the_worker_dies(tmp_path):
    import os, sys
    from app.integrations.openmontage.frames_process import FramesError, FramesProcess
    script = tmp_path / 'worker.py'
    script.write_text('import sys\nsys.stdin.readline()\nsys.exit(7)\n')
    worker = FramesProcess()
    try:
        try:
            worker.call([sys.executable, str(script)], tmp_path, dict(os.environ), {})
            assert False, 'must fail'
        except FramesError as error:
            assert error.reason == 'semantic_worker_stopped' and '7' in error.detail
    finally:
        worker.close()


def test_any_gpu_error_retries_on_cpu_not_only_runtime_error():
    from app.integrations.openmontage.visual_engine import inference
    cuda = SimpleNamespace(is_available=lambda: True)
    torch = SimpleNamespace(cuda=cuda)
    clip = SimpleNamespace(_DEVICE='cuda', _MODEL='old', _PROCESSOR='old')
    def compute(value):
        if cuda.is_available(): raise OSError('[WinError 126] c10_cuda.dll could not be loaded')
        return 'cpu-result'
    assert inference(compute, [], clip, torch) == 'cpu-result'


def test_device_metric_reports_where_the_model_really_lives():
    from app.integrations.openmontage.visual_engine import actual_device
    on = lambda kind: SimpleNamespace(_DEVICE='cuda', _MODEL=SimpleNamespace(parameters=lambda: iter([SimpleNamespace(device=SimpleNamespace(type=kind))])))
    assert actual_device(on('cpu')) == 'cpu' and actual_device(on('cuda')) == 'cuda'
    assert actual_device(SimpleNamespace(_DEVICE='cuda', _MODEL=None)) == 'cuda'


def test_child_env_always_has_a_user_name_so_torch_can_start(monkeypatch, tmp_path):
    """Real failure (diagnostics 2026-10-21): CLIP died with “OSError: No username set in the environment”
    because the helper process had no USERNAME. The variable is now passed on, and invented if the app has none."""
    from app.integrations.openmontage.bridge import child_env
    monkeypatch.setenv('USERNAME', 'naman')
    assert child_env(tmp_path)['USERNAME'] == 'naman'
    for name in ('USERNAME', 'USER', 'LOGNAME', 'LNAME'):
        monkeypatch.delenv(name, raising=False)
    import getpass
    monkeypatch.setattr(getpass, 'getuser', lambda: (_ for _ in ()).throw(OSError('No username set in the environment')))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'Users' / 'ayse'))
    assert child_env(tmp_path)['USERNAME'] == 'ayse'


def test_child_env_still_hides_provider_keys(monkeypatch, tmp_path):
    from app.integrations.openmontage.bridge import child_env
    monkeypatch.setenv('PIXABAY_API_KEY', 'secret-value-123')
    monkeypatch.setenv('USERNAME', 'naman')
    assert 'PIXABAY_API_KEY' not in child_env(tmp_path)


def test_clip_skip_reason_and_real_error_reach_the_diagnostics(tmp_path):
    from app.stock.director_media import MediaDirector
    director = MediaDirector(SimpleNamespace(), {'project_id': 'p', 'progress': {}})
    director.clip = SimpleNamespace(broken=True, error='OSError: No username set in the environment', ready=lambda: False)
    assert director.clip_judge({}, {}, [object()]) == {}
    progress = director.progress
    assert progress['clip_skipped'] == {'not_ready': 1} and progress['clip_error'].startswith('OSError: No username')
    assert 'CLIP' in progress['clip_warning']
