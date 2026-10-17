"""Chromium UI checks with isolated HTTP fixtures, never production project writes.

Run a NAMAN server, then: python scripts/workspace_browser_smoke.py URL OUTPUT_DIR
Requires Playwright and Chromium on the development machine. This is not WebView2.
"""
import base64
import copy
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright


PROJECT = 'a' * 32
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def fixture():
    visual = {'scene_id': 's1', 'slot_id': 'v1', 'start': 0, 'end': 30, 'clip_start': 0,
              'locked': False, 'label': 'Yerel test görseli', 'preview_url': '/fixture.png',
              'media': {'provider': 'local', 'media_id': 'fixture', 'media_type': 'image'}}
    motion = {'scene_id': 's2', 'slot_id': 'm1', 'start': 30, 'end': 60, 'clip_start': 0,
              'locked': False, 'label': '40 km', 'preview_url': '/fixture.png',
              'media': {'provider': 'motion', 'media_id': 'motion', 'media_type': 'image'},
              'motion_spec': {'template': 'stat', 'data': {'value': '40 km', 'label': 'Rota'}, 'emphasis': '40'}}
    return {'duration': 60, 'fps': 30, 'plan_id': 'p', 'revision': 1,
            'stock_plan_id': 'p', 'stock_revision': 1, 'warnings': ['Stok test uyarısı'],
            'subtitle_version_id': 'sub1', 'subtitle_timing': 'estimated',
            'scenes': [{'scene_id': 's1', 'start': 0, 'end': 30, 'narration': 'Rota kırk kilometre.'},
                       {'scene_id': 's2', 'start': 30, 'end': 60, 'narration': 'Rota kırk kilometre.'}],
            'track_order': ['emphasis', 'layers', 'maps', 'infographics', 'visuals', 'audio', 'subtitles'],
            'tracks': {'emphasis': [], 'layers': [], 'maps': [], 'infographics': [motion],
                       'visuals': [visual], 'audio': [],
                       'subtitles': [{'index': 1, 'start': 0, 'end': 30, 'text': 'Rota kırk kilometre.'}]}}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8001'
    output = Path(sys.argv[2] if len(sys.argv) > 2 else '/tmp/naman-workspace-smoke')
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                    args=['--no-sandbox'])
        context = browser.new_context()
        page = context.new_page()
        state = fixture()
        requests = []
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def route(request):
            path = request.request.url.split(url, 1)[-1]
            if path == '/fixture.png':
                return request.fulfill(body=PNG, content_type='image/png')
            if path.startswith('/api/'):
                requests.append((path, request.request.method, request.request.post_data))
                if path == '/api/projects':
                    value = {'projects': [{'id': PROJECT, 'name': 'Workspace test projesi',
                                          'status': 'draft', 'updated_at': '2026-10-18T00:00:00Z'}]}
                elif path == '/api/settings':
                    value = {'general': {'appearance_theme': 'premiere', 'accent_color': '#8065E8'}}
                elif path.endswith('/editor/archive'):
                    value = {'items': [{'provider': 'local', 'media_id': 'fixture', 'media_type': 'image',
                                        'sha256': 'b' * 64, 'title': 'Yerel deneme', 'preview_url': '/fixture.png'}]}
                elif path.endswith('/editor/manual/package'):
                    value = {'output_template': {'sahneler': []}}
                else:
                    value = state
                return request.fulfill(json=value)
            return request.continue_()

        page.route('**/*', route)
        for width, height in [(1366, 768), (1600, 900), (1920, 1080), (1650, 900), (1093, 614)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.goto(f'{url}/projects/{PROJECT}/editor')
            page.locator('.workspace-media-card').wait_for()
            page.wait_for_timeout(150)
            metrics = page.evaluate('''() => {
              const bounds=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right};};
              return {scroll:document.documentElement.scrollHeight,viewport:innerHeight,
                work:bounds('.naman-work'),timeline:bounds('.naman-timeline'),
                toolbar:bounds('.naman-toolbar'),tracks:[...document.querySelectorAll('.naman-track')].map(n=>({bottom:n.getBoundingClientRect().bottom,height:n.getBoundingClientRect().height})),
                overflow:document.documentElement.scrollWidth>innerWidth};
            }''')
            assert metrics['scroll'] <= height, metrics
            assert not metrics['overflow'], metrics
            assert len(metrics['tracks']) == 7, metrics
            assert all(t['height'] >= 29 and t['bottom'] <= metrics['timeline']['bottom'] for t in metrics['tracks']), metrics
            assert metrics['work']['height'] > 150, metrics
            ratio=page.locator('.workspace-program-surface').evaluate('(n)=>n.clientWidth/n.clientHeight')
            assert abs(ratio-16/9)<.02, ratio
            page.screenshot(path=str(output / f'workspace-{width}x{height}.png'))
            results.append({'viewport': f'{width}x{height}', 'metrics': metrics})

        page.set_viewport_size({'width': 1366, 'height': 768})
        page.goto(f'{url}/projects/{PROJECT}/editor')
        page.locator('.workspace-media-card').wait_for()
        page.get_by_role('searchbox', name='Medya ara').fill('bulunmaz')
        assert page.locator('.workspace-media-card').count() == 0
        page.get_by_role('searchbox', name='Medya ara').fill('Yerel')
        assert page.locator('.workspace-media-card').count() == 1
        assert not any('/editor/timeline' in q[0] and q[1]=='PUT' for q in requests)
        page.locator('.workspace-media-card').drag_to(page.locator('.naman-clip[data-track=visuals]'))
        page.wait_for_timeout(300)
        assignments=[q for q in requests if q[0].endswith('/slots/v1/media') and q[1]=='PUT']
        assert assignments, requests
        assert json.loads(assignments[-1][2])['media_id']=='fixture'
        assert json.loads(assignments[-1][2])['start']==0
        page.locator('.workspace-media-card').wait_for()
        page.locator('.workspace-media-card').click()
        assert page.locator('.workspace-source img').is_visible()
        page.locator('.naman-clip[data-track=visuals]').click()
        assert page.locator('.naman-inspector form').is_visible()
        page.get_by_role('tab', name='Düzenle', exact=True).click()
        page.locator('.naman-inspector input').first.fill('1.5')
        page.locator('.naman-inspector input').first.press('ArrowRight')
        page.get_by_role('tab', name='JSON', exact=True).click()
        page.locator('.naman-clip[data-track=infographics]').click()
        assert page.locator('.naman-motion-json').is_visible()
        page.wait_for_timeout(400)
        page.locator('.naman-motion-json').fill('{"value":"40 km","label":"Yeni rota"}', timeout=3000)
        page.locator('.naman-motion-json').press('Space')
        assert not any('/timeline/' in q[0] for q in requests)
        page.get_by_role('tab', name='Motion', exact=True).click()
        assert page.locator('.naman-motion-visual').is_visible()
        page.locator('.naman-clip[data-track=subtitles]').click()
        page.get_by_role('tab', name='Metin', exact=True).click()
        assert page.locator('.naman-inspector textarea').is_visible()
        page.get_by_label('Dosya menüsü', exact=True).click()
        assert page.get_by_role('button', name='Projeyi kaydet', exact=True).is_visible()
        page.keyboard.press('Escape')
        for title in ['Dosya','Düzen','Klip','Sekans','İşaretleyiciler','Grafikler ve Başlıklar','Görünüm','Pencere','Yardım']:
            page.get_by_label(title+' menüsü', exact=True).click()
            rect=page.locator('.workspace-menubar details[open] .workspace-menu').bounding_box()
            assert rect['x']>=0 and rect['x']+rect['width']<=1366, rect
            page.keyboard.press('Escape')
        split=page.get_by_role('separator',name='Timeline yüksekliği')
        before=page.locator('.naman-timeline').bounding_box()['height']
        split.focus();page.keyboard.press('ArrowUp')
        assert page.locator('.naman-timeline').bounding_box()['height']>before
        page.get_by_label('Görünüm menüsü', exact=True).click()
        page.get_by_role('button', name='Çalışma düzenini sıfırla', exact=True).click()
        assert page.locator('.naman-library').is_visible()
        page.get_by_label('Pencere menüsü', exact=True).click()
        page.get_by_role('button', name='Medya paneli', exact=True).click()
        assert not page.locator('.naman-library').is_visible()
        page.reload();page.locator('.workspace').wait_for()
        assert not page.locator('.naman-library').is_visible()
        page.get_by_label('Görünüm menüsü', exact=True).click()
        page.get_by_role('button', name='Çalışma düzenini sıfırla', exact=True).click()
        page.get_by_label('Yardım menüsü', exact=True).click()
        page.keyboard.press('ArrowDown')
        page.keyboard.press('Enter')
        assert page.locator('dialog').is_visible()
        page.get_by_role('button', name='Kapat', exact=True).click()
        # Motion is moved only between existing slots in its own scene/track.
        state['tracks']['infographics'][0]['end']=45
        second=copy.deepcopy(state['tracks']['infographics'][0])
        second.update(slot_id='m2',start=45,end=60,label='İkinci grafik')
        state['tracks']['infographics'].append(second)
        page.reload();page.locator('.workspace-media-card').wait_for()
        page.locator('.naman-library').get_by_role('button',name='Motion',exact=True).click()
        page.locator('.workspace-motion-card').nth(1).drag_to(page.locator('.naman-clip[data-slot-id=m1]'))
        page.wait_for_timeout(300)
        moves=[q for q in requests if q[0].endswith('/editor/timeline') and q[1]=='PUT']
        assert moves, requests
        moved=json.loads(moves[-1][2])
        assert moved['scene_id']=='s2' and [s['slot_id'] for s in moved['slots']]==['m2','m1']
        assert moved['slots'][0]['start']==30 and moved['slots'][-1]['end']==60
        page.goto(url+'/')
        page.locator('.home-project').wait_for()
        assert page.locator('.home-project strong').inner_text()=='Workspace test projesi'
        page.screenshot(path=str(output/'home.png'))
        assert not errors, errors
        results.append({'interactions': 'search, source preview, media/motion drag revision requests, clip selection, text-safe keyboard, motion/JSON/subtitle tabs, nine menu bounds, menu keyboard, timeline resize, panel visibility/reload/reset and project-list fixture homepage passed'})
        browser.close()
    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
