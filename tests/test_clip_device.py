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
