"""Build compact, URL-free reference excerpts and the 24 NAMAN ideas from the
user's NAMAN_Animasyon_300_CODEX_SECKISI folder.

Usage: python scripts/build_reference_excerpts.py PATH/TO/NAMAN_Animasyon_300_CODEX_SECKISI

Writes docs/ANIMATION_REFERENCE_EXCERPTS_300.json and docs/NAMAN_24_ANIMATION_IDEAS.json.
Only a short excerpt of each prompt is kept (inspiration for the external AI);
the full prompt files are not copied into the repository.
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCERPT = 420
URL = re.compile(r'https?://\s*\S+|www\.\S+', re.I)
THREE_D = re.compile(r'three\.?js|webgl|\bshader|glsl|\br3f\b|react-three|blender|babylon|\b3d model|unity|unreal', re.I)
CSS_SVG = re.compile(r'\bsvg\b|\bcss\b|keyframes|\bhtml\b', re.I)
JS_2D = re.compile(r'\bcanvas\b|\bgsap\b|\bd3\b|p5\.?js|anime\.js|lottie|framer', re.I)


def prompt_text(markdown):
    """Text of the first fenced block after '## Prompt' (the author's prompt)."""
    part = markdown.split('## Prompt', 1)[-1]
    match = re.search(r'```[^\n]*\n(.*?)```', part, re.S)
    return match.group(1) if match else part


def excerpt(text):
    text = ' '.join(URL.sub('', text).split())
    if len(text) <= EXCERPT:
        return text
    cut = text[:EXCERPT]
    end = max(cut.rfind('. '), cut.rfind('; '))
    return (cut[:end + 1] if end > EXCERPT * .5 else cut.rsplit(' ', 1)[0]) + ' …'


def renderable(tags, text):
    blob = tags + ' ' + text
    if THREE_D.search(blob):
        return 'unsupported_3d'
    if CSS_SVG.search(blob):
        return 'css_svg'
    if JS_2D.search(blob):
        return 'js_2d'
    return 'idea'


def main(source):
    source = Path(source)
    selected = json.loads((source / 'CODEX_SECILEN_300.json').read_text(encoding='utf-8'))
    review = {r['id']: r for r in json.loads((ROOT / 'docs/ANIMATION_REFERENCE_REVIEW_300.json').read_text(encoding='utf-8'))['references']}
    out = []
    for row in selected:
        rid = row['ID']
        if rid not in review:
            raise SystemExit(f'{rid} is not in docs/ANIMATION_REFERENCE_REVIEW_300.json')
        md = (source / 'CODEX_SECILEN_300_PROMPT' / (rid + '.md')).read_text(encoding='utf-8')
        title = next((line[2:].strip() for line in md.splitlines() if line.startswith('# ')), rid)
        text = prompt_text(md)
        out.append({'id': rid, 'title': ' '.join(URL.sub('', title).split())[:120],
                    'renderable': renderable(row.get('Teknoloji etiketleri') or '', text),
                    'excerpt': excerpt(text)})
    if len(out) != 300 or len({x['id'] for x in out}) != 300:
        raise SystemExit('expected 300 unique references')
    ideas = json.loads((source / 'NAMAN_24_ANIMASYON_TASARIM_FIKRI.json').read_text(encoding='utf-8'))
    keep = ('id', 'ad', 'kategori', 'naman_izi', 'animasyon_tarifi', 'dogruluk_kurali')
    ideas = [{k: idea[k] for k in keep} for idea in ideas]
    if len(ideas) != 24:
        raise SystemExit('expected 24 ideas')
    note = ('Kısa özetler kullanıcının awesome-opus5-5-videos arşivinden (MIT liste; promptlar yazarlarına aittir) '
            'yalnız teknik ilham için alınmıştır. Tam promptlar ve bağlantılar repoya kopyalanmadı.')
    (ROOT / 'docs/ANIMATION_REFERENCE_EXCERPTS_300.json').write_text(
        json.dumps({'note': note, 'count': len(out), 'references': out}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (ROOT / 'docs/NAMAN_24_ANIMATION_IDEAS.json').write_text(json.dumps(ideas, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    counts = {}
    for x in out:
        counts[x['renderable']] = counts.get(x['renderable'], 0) + 1
    print(json.dumps(counts))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
