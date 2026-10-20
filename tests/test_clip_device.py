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
