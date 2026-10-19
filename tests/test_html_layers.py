"""HTML/CSS overlay layers: safety, exact frames, shared cache, review and approval."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time

import pytest
from PIL import Image

from app.motion import html_layer
from app.motion.html_layer import LayerError, contract, sanitize

FFMPEG = 'ffmpeg'
EXAMPLE = contract()['example']


def probe(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(path)])
    return json.loads(out)['streams'][0]


def test_contract_example_is_safe_and_sanitizing_is_idempotent():
    html, css = sanitize(EXAMPLE['html'], EXAMPLE['css'])
    assert '<div class="kart">' in html and '@keyframes gir' in css
    assert sanitize(html, css) == (html, css)  # cache keys stay stable after document re-validation


def test_svg_gradients_local_references_and_keyframes_are_allowed():
    svg = ('<svg viewBox="0 0 100 100"><defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
           '<path d="M0 0L100 100" stroke="url(#g)" fill="none"/><text x="5" y="20">Roma &amp; Ren</text></svg>')
    html, css = sanitize(svg, 'path{animation:ciz 2s both}@keyframes ciz{from{stroke-dashoffset:300}to{stroke-dashoffset:0}}')
    assert 'url(#g)' in html and 'Roma &amp; Ren' in html and sanitize(html, css) == (html, css)


@pytest.mark.parametrize('html,css,reason', [
    ('<script>alert(1)</script>', '', '<script>'),
    ('<img src=x onerror=alert(1)>', '', '<img>'),
    ('<div onclick="x()">a</div>', '', 'olay'),
    ('<a href="http://x">a</a>', '', '<a>'),
    ('<iframe src=x></iframe>', '', '<iframe>'),
    ('<svg><use href="#a"/></svg>', '', '<use>'),
    ('<foreignObject></foreignObject>', '', 'foreignobject'),
    ('<div style="background:url(http://evil/x.png)">a</div>', '', 'url'),
    ('<div style="color:red}a{color:blue">a</div>', '', 'style'),
    ('<div>a</div>', '@import "http://x.css";', '@import'),
    ('<div>a</div>', '@font-face{font-family:x;src:local(a)}', '@font-face'),
    ('<div>a</div>', '.a{background:url(https://x)}', 'url'),
    ('<div>a</div>', '</style><script>x</script>', '<'),
    ('<div>a</div>', '.a{b:\\75 rl(x)}', 'kaçış'),
    ('<div>a</div>', '.a{width:expression(alert(1))}', 'expression'),
    ('', '', 'boş'),
])
def test_unsafe_layers_are_rejected_with_a_reason_not_silently_cleaned(html, css, reason):
    with pytest.raises(LayerError) as error:
        sanitize(html, css)
    assert reason.lower() in str(error.value).lower()


def scenes(locked=False):
    return {'s1': {'scene_id': 's1', 'start': 10.0, 'end': 50.0, 'locked': locked}}


def test_record_window_track_lock_and_duration_rules():
    item = {'scene_id': 's1', 'start': 12.0, 'end': 18.0, 'track': 'maps', 'html': EXAMPLE['html'], 'css': EXAMPLE['css']}
    scene, start, end, data = html_layer.validate_item(item, scenes())
    assert (start, end) == (12.0, 18.0) and set(data) == {'html', 'css'}
    bad = [({**item, 'end': 51.0}, 'aralığında'), ({**item, 'start': 12.0, 'end': 43.0}, '30 sn'),
           ({**item, 'track': 'visuals'}, 'track'), ({**item, 'js': 'x'}, 'Desteklenmeyen alan'),
           ({**item, 'scene_id': 'nope'}, 'scene_id')]
    for record, reason in bad:
        with pytest.raises(LayerError, match=reason):
            html_layer.validate_item(record, scenes())
    with pytest.raises(LayerError, match='kilitli'):
        html_layer.validate_item(item, scenes(locked=True))


class FakeBridge:
    """Stands in for OpenMontage: writes Remotion-like transparent PNG frames."""

    def __init__(self, root, frames=None):
        self.root_path = root
        (root / 'remotion-composer' / 'projects').mkdir(parents=True)
        self.calls = []
        self.frames = frames

    def status(self):
        return {'ready': True}

    def root(self):
        return self.root_path

    def call(self, operation, inputs, folder, runner=None, progress=None):
        entry = Path(inputs['entry'])
        props = json.loads(Path(inputs['props_path']).read_text(encoding='utf-8'))
        assert operation == 'html_layer' and entry.name == 'index.tsx' and 'NAMANHtmlLayer' in entry.read_text(encoding='utf-8')
        assert props['frames'] == inputs['frames'] and '<script' not in props['html']
        self.calls.append(props)
        for index in range(self.frames if self.frames is not None else inputs['frames']):
            Image.new('RGBA', (1920, 1080), (index * 8 % 256, 40, 200, 128)).save(Path(inputs['output_dir']) / f'element-{index:03d}.png')
        return {'output': inputs['output_dir']}


def test_render_makes_one_cached_alpha_clip_with_exact_frames(tmp_path):
    bridge = FakeBridge(tmp_path / 'om')
    folder = tmp_path / 'stock'
    folder.mkdir()
    data = dict(zip(('html', 'css'), sanitize(EXAMPLE['html'], EXAMPLE['css'])))
    path = html_layer.render(bridge, folder, data, 1.0, FFMPEG)
    stream = probe(path)
    assert stream['codec_name'] == 'qtrle' and stream['pix_fmt'] == 'argb' and int(stream['nb_read_frames']) == 30
    assert path == html_layer.cached(folder, data, 1.0)
    assert html_layer.render(bridge, folder, data, 1.0, FFMPEG) == path and len(bridge.calls) == 1
    assert not list((bridge.root_path / 'remotion-composer' / 'projects').iterdir())  # staging removed
    assert not [p for p in (folder / 'html-layers').iterdir() if p.name.startswith('.')]


def test_missing_frames_are_an_error_and_never_cached(tmp_path):
    from app.rendering.models import RenderError
    bridge = FakeBridge(tmp_path / 'om', frames=29)
    folder = tmp_path / 'stock'
    folder.mkdir()
    data = {'html': '<div>a</div>', 'css': ''}
    with pytest.raises(RenderError, match='29 kare'):
        html_layer.render(bridge, folder, data, 1.0, FFMPEG)
    with pytest.raises(RenderError, match='hazırlanmamış'):
        html_layer.cached(folder, data, 1.0)


def test_without_openmontage_the_layer_reports_why_it_is_missing(tmp_path):
    from app.rendering.models import RenderError
    item = {'scene_id': 's1', 'start': 12.0, 'end': 13.0, 'html': '<div>Roma</div>'}
    assert html_layer.prerender(None, tmp_path, [item], scenes(), FFMPEG) == 1
    with pytest.raises(RenderError, match='OpenMontage'):
        html_layer.cached(tmp_path, {'html': '<div>Roma</div>', 'css': ''}, 1.0)


def test_preview_and_export_read_the_same_file_and_samples_are_exact_frames(tmp_path):
    from app.motion.clips import render_clip
    from app.channels import DEFAULT_STYLE
    bridge = FakeBridge(tmp_path / 'om')
    folder = tmp_path / 'stock'
    folder.mkdir()
    data = {'html': '<div>a</div>', 'css': ''}
    full = html_layer.render(bridge, folder, data, 1.0, FFMPEG)
    spec = {'template': 'html', 'data': data, 'local_only': True}
    path, scene, engine = render_clip(folder, spec, DEFAULT_STYLE, 1.0, 0, render_window=(0.0, 1.0))
    assert path == full and engine == 'html' and '_render_start' not in scene and scene['alpha']
    sample, _, _ = render_clip(folder, spec, DEFAULT_STYLE, 1.0, 0, sample_time=0.5)
    assert int(probe(sample)['nb_read_frames']) == 1
    raw = subprocess.check_output([FFMPEG, '-v', 'error', '-i', str(sample), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
    assert raw[:4] == bytes((15 * 8 % 256, 40, 200, 128))  # frame 15 == 0.5 s


def test_templates_accept_only_sanitized_html_and_never_draw_it_locally():
    from app.motion.templates import validate, build, MotionError
    from app.channels import DEFAULT_STYLE
    clean = validate({'template': 'html', 'data': {'html': '<div>a</div>', 'css': ''}}, '')
    assert clean == {'template': 'html', 'data': {'html': '<div>a</div>', 'css': ''}, 'emphasis': ''}
    with pytest.raises(MotionError, match='güvenli değil'):
        validate({'template': 'html', 'data': {'html': '<script>x</script>'}}, '')
    with pytest.raises(MotionError):
        validate({'template': 'html', 'data': {'html': '<div>a</div>', 'js': 'x'}}, '')
    assert build(clean, DEFAULT_STYLE, 2.0, 0)['elements'] == []


def test_reference_selection_uses_purposes_skips_3d_and_caps_the_package():
    from app.animation.references import select_techniques, excerpts
    texts = ['Die Bevölkerung wuchs um 40 Prozent.', 'Der Fluss bildet die Grenze zur Stadt.', 'Im Jahr 1871 begann das Reich.',
             'Und dann ging er nach Hause.'] * 12
    result = select_techniques([{'scene_id': f's{i}', 'text': t, 'start': i, 'end': i + 1} for i, t in enumerate(texts)])
    refs = [r for s in result['scenes'] for r in s['references']]
    from app.animation.references import PACKAGE_LIMIT
    assert len(refs) <= PACKAGE_LIMIT and all(r['renderable'] != 'unsupported_3d' for r in refs)
    assert all(excerpts()[r['reference_id']]['renderable'] == r['renderable'] for r in refs)
    assert [s['purpose'] for s in result['scenes'][:4]] == ['İnfografik', 'Coğrafya', 'Zaman çizelgesi', None]
    assert result['scenes'][3]['references'] == [] and result['scenes'][3]['ideas'] == []
    encoded = json.dumps(result, ensure_ascii=False)
    assert 'http' not in encoded.lower() and 'prompt_sha256' not in encoded


def fake_package():
    from app.animation.references import select_techniques
    narration = [{'scene_id': 'a1', 'text': 'Roma liegt am Tiber.', 'start': 0.0, 'end': 4.0, 'locked': False},
                 {'scene_id': 'a2', 'text': 'Danach kam der Krieg.', 'start': 4.0, 'end': 8.0, 'locked': True}]
    template = {'schema': 'naman.manual-plan.v1', 'base': {'plan_id': 'p', 'revision': 3}, 'sahneler': [], 'infografikler': [],
                'harita_sahneleri': [], 'vurgular': [], 'katmanlar': [], 'animasyon_sahneleri': [], 'html_katmanlari': []}
    return {'project': {'name': 'Roma', 'topic': 'Tarih', 'language': 'de'}, 'base': template['base'], 'narration': narration,
            'sentence_index': [{'index': 0, 'start': 0.0, 'end': 4.0, 'text': 'Roma liegt am Tiber.'}],
            'archive': [{'provider': 'local', 'media_id': 'm1', 'sha256': 'x' * 64, 'media_type': 'video', 'file_name': 'roma.mp4',
                         'title': 'Roma', 'duration': 9.0, 'rights': 'free'}],
            'editing_slots': [{'slot_id': 'v1', 'scene_id': 'a1', 'start': 0.0, 'end': 4.0}], 'maps': [],
            'output_template': template, 'output_contract': {'html_katmanlari': contract()},
            'animation_reference_selection': select_techniques(narration)}


def test_single_message_is_self_sufficient_and_the_zip_has_both_ways():
    import io
    import zipfile
    from app.editor.manual_brief import brief, files, zip_bytes
    package = fake_package()
    text = brief(package, ['Önce haritayı göster.'])
    for needle in ('NAMAN — BELGESEL KURGU PLANI GÖREVİ', '"plan_id": "p"', 'html_katmanlari', 'GÖNDERMEDEN ÖNCE KONTROL ET',
                   '[a1] (0.00–4.00 sn)', '[KİLİTLİ — dokunma]', 'roma.mp4', 'Almanca (de)', 'Önce haritayı göster.', 'Zaman çizelgesi'):
        assert needle in text, needle
    short = files(package)['00_TALIMAT.md']
    assert '01_sahneler_ve_cumleler.txt' in short and 'roma.mp4' not in short
    with zipfile.ZipFile(io.BytesIO(zip_bytes(package))) as archive:
        assert {'OKU_BENI.txt', '00_TALIMAT.md', '01_sahneler_ve_cumleler.txt', '02_arsiv.json', '03_mevcut_kurgu.json',
                '04_referanslar.md', '05_cikti_sablonu.json', 'NAMAN_GOREV_PAKETI.json', 'NAMAN_CIKTI_SABLONU.json',
                'TEK_MESAJ.txt'} == set(archive.namelist())
        assert json.loads(archive.read('05_cikti_sablonu.json'))['base'] == {'plan_id': 'p', 'revision': 3}


# ---------- real app: brief route, review issues, approval, program frame ----------

def wait(client, url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = client.get(url).json()
        if job['status'] in ('completed', 'failed'):
            return job
        time.sleep(.05)
    raise AssertionError('review did not complete')


@pytest.fixture
def workflow(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_manual_first import install_manual_example
    from test_scripts import HEADERS
    with TestClient(create_app(tmp_path), headers=HEADERS) as client:
        st = install_manual_example(client.app)
        yield client, st['pid']


def plan_with_layer(client, pid):
    base = f'/api/projects/{pid}/editor'
    pack = client.get(base + '/manual/package').json()
    scene = pack['narration'][0]
    plan = deepcopy(pack['output_template'])
    end = min(scene['end'], scene['start'] + 1.0)
    plan['katmanlar'] = [{'scene_id': scene['scene_id'], 'start': scene['start'], 'end': end, 'text': 'Roma', 'effect': 'none'}]
    plan['html_katmanlari'] = [{'scene_id': scene['scene_id'], 'start': scene['start'], 'end': end, 'track': 'infographics',
                                'html': '<div class="k">40 km</div>', 'css': '.k{position:absolute;inset:0;background:rgba(255,0,0,.9)}'}]
    return base, pack, plan


def test_brief_route_is_free_and_contains_the_html_contract(workflow):
    client, pid = workflow
    base = f'/api/projects/{pid}/editor'
    brief = client.post(base + '/manual/package/brief', json={})
    assert brief.status_code == 200 and brief.json()['characters'] == len(brief.json()['text'])
    assert 'html_katmanlari' in brief.json()['text'] and 'output_contract' not in client.get(base + '/manual/package').json()['output_template']
    assert client.post(base + '/manual/package/brief', json={'gemini_instructions': ['x' * 2001]}).status_code == 422
    assert client.post(base + '/manual/package/brief', json={'other': 1}).status_code == 422


def test_layer_without_openmontage_is_kept_as_issue_and_valid_proposals_survive(workflow):
    client, pid = workflow
    base, _, plan = plan_with_layer(client, pid)
    job = wait(client, client.post(base + '/manual/response-jobs', json={'text': json.dumps(plan)}).json()['status_url'])
    assert job['status'] == 'completed', job
    draft = job['draft']
    issue = next(i for i in draft['import_issues'] if i['section'] == 'html_katmanlari')
    assert issue['category'] == 'html_layer_not_ready' and 'OpenMontage' in issue['message']
    assert [c['kind'] for c in draft['clips']] == ['text']  # the valid text layer is still proposed
    assert 'html_katmanlari[0]' in draft['correction_message']


def test_prepared_layer_is_drafted_approved_and_drawn_in_the_program_frame(workflow, monkeypatch):
    client, pid = workflow
    base, _, plan = plan_with_layer(client, pid)

    def fake_render(bridge, folder, data, duration, ffmpeg, **kwargs):
        target = html_layer.cache_path(folder, data, duration)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=red:s=1920x1080:r=30:d={duration}',
                        '-vf', 'format=argb', '-frames:v', str(html_layer.frames_for(duration)), '-c:v', 'qtrle', '-pix_fmt', 'argb',
                        str(target)], check=True)
        return target
    monkeypatch.setattr(html_layer, 'render', fake_render)
    scene_start = plan['html_katmanlari'][0]['start']
    before = client.get(base + f'/advanced/program-frame?time={scene_start + .5}')
    job = wait(client, client.post(base + '/manual/response-jobs', json={'text': json.dumps(plan)}).json()['status_url'])
    draft = job['draft']
    assert not draft['import_issues'], draft['import_issues']
    layer = next(c for c in draft['clips'] if (c.get('motion') or {}).get('template') == 'html')
    assert '<script' not in layer['motion']['data']['html'] and layer['animation_duration'] == pytest.approx(layer['end'] - layer['start'])
    approve = base + f'/editorial/drafts/{draft["id"]}/approve'
    assert client.post(approve, json={'confirmed': False, 'clip_ids': [layer['id']]}).status_code == 422
    assert client.post(approve, json={'confirmed': True, 'clip_ids': [layer['id']]}).status_code == 200
    document = client.get(base + '/advanced').json()['document']
    assert [c['motion']['template'] for c in document['clips'] if c['kind'] == 'motion'] == ['html']
    after = client.get(base + f'/advanced/program-frame?time={scene_start + .5}')
    assert after.status_code == 200, after.text
    if before.status_code == 200:
        assert after.content != before.content


def test_plain_text_proposals_become_designed_layers_without_losing_odd_ones():
    from app.motion.text_layers import convert
    from app.motion.html_layer import sanitize, MAX_SECONDS
    scenes = {'a': {'scene_id': 'a', 'start': 0., 'end': 6.}, 'b': {'scene_id': 'b', 'start': 6., 'end': 12., 'locked': True}}
    payload = {'vurgular': [{'scene_id': 'a', 'start': 1., 'end': 5., 'text': 'Dijo "hola" & <b>adiós</b>', 'object_id': 'x'},
                            {'scene_id': 'a', 'start': 1., 'end': 5., 'text': 'pulse kalır', 'effect': 'pulse'},
                            {'scene_id': 'b', 'text': 'kilitli sahne'},
                            {'scene_id': 'a', 'start': 1., 'end': 1.5, 'text': 'çok kısa'}],
               'katmanlar': [{'scene_id': 'a', 'start': 0., 'end': 4., 'text': 'de noche la tierra se enfría rápido'}]}
    assert convert(payload, scenes, MAX_SECONDS) == 2
    assert [i['text'] for i in payload['vurgular']] == ['pulse kalır', 'kilitli sahne', 'çok kısa'] and payload['katmanlar'] == []
    layers = payload['html_katmanlari']
    assert [l['track'] for l in layers] == ['emphasis', 'layers'] and layers[0]['object_id'] == 'x'
    assert '<b>' not in layers[0]['html'] and '&lt;b&gt;' in layers[0]['html']
    for layer in layers:
        sanitize(layer['html'], layer['css'])


def test_designed_text_enters_word_by_word_and_underlines_the_key_word():
    from app.motion.text_layers import design
    from app.motion.html_layer import sanitize
    html, css = design('vurgular', 'el sol calienta 28 grados la tierra', 4.0)
    assert html.count("class='w ") == 7 and html.count(' hl') == 1 and "hl'>28<" in html
    html, css = design('katmanlar', 'el aire frío baja desde las montañas', 4.0, 1)
    assert 'right:0' in css and "hl'>montañas" in html
    for section in ('vurgular', 'katmanlar'):
        for variant in (0, 1):
            sanitize(*design(section, 'Dijo "hola" & <b>adiós</b>', 4.0, variant))


def test_every_text_variant_passes_the_sanitizer_and_teletype_falls_back_for_long_text():
    from app.motion.text_layers import design, VARIANTS
    from app.motion.html_layer import sanitize
    for section, names in VARIANTS.items():
        for variant in range(len(names) + 1):
            for text in ('28 grados', 'el sol calienta la tierra más rápido que el agua', 'Dijo "hola" & <b>adiós</b>', 'x' * 150):
                sanitize(*design(section, text, 4.0, variant))
    html, _ = design('katmanlar', 'y' * 80, 4.0, 2)
    assert "class='ty'" not in html and "class='k'" in html
    html, _ = design('katmanlar', 'corto y claro', 4.0, 2)
    assert "class='ty'" in html
