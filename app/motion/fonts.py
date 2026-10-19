"""Fonts for HTML/CSS layers, loaded by NAMAN itself (never by AI-written CSS).

Bundled: Montserrat (OFL). Optional, supplied by the user: put Gilroy files into
app/static/fonts/user/ (e.g. Gilroy-Bold.ttf, Gilroy-Light.ttf). They are embedded into the render
page as @font-face, so nothing has to be installed in Windows. Gilroy is commercial and is never bundled.
"""
import base64
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / 'static' / 'fonts'
USER_DIR = FONT_DIR / 'user'
KINDS = {'.ttf': 'truetype', '.otf': 'opentype', '.woff': 'woff', '.woff2': 'woff2'}
MAX_BYTES = 8_000_000
BOLD_FAMILY = 'NamanBold'
LIGHT_FAMILY = 'NamanLight'


def _pick(names):
    """First user file whose lowercase name contains every word of one of the alternatives."""
    if not USER_DIR.is_dir():
        return None
    files = sorted(p for p in USER_DIR.iterdir() if p.suffix.lower() in KINDS and p.is_file() and 0 < p.stat().st_size <= MAX_BYTES)
    for words in names:
        for path in files:
            if all(w in path.name.lower() for w in words):
                return path
    return None


def user_fonts():
    """{family: Path}: bold = Gilroy Bold (or any '*bold*'), light = Gilroy Light/Regular."""
    found = {}
    bold = _pick((('gilroy', 'bold'), ('bold',)))
    light = _pick((('gilroy', 'light'), ('gilroy', 'regular'), ('light',), ('regular',)))
    if bold:
        found[BOLD_FAMILY] = bold
    if light and light != bold:
        found[LIGHT_FAMILY] = light
    return found


def signature():
    """Changes when a font file is added, replaced or removed (used in the layer cache key)."""
    parts = [f'{FONT_DIR / "Montserrat.ttf"}:{(FONT_DIR / "Montserrat.ttf").stat().st_size}']
    parts += [f'{family}:{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}' for family, p in sorted(user_fonts().items())]
    return '|'.join(parts)


@lru_cache(maxsize=4)
def _css(_signature):
    def face(family, path, weight):
        data = base64.b64encode(path.read_bytes()).decode()
        return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
                f"src:url(data:font/{path.suffix.lower().lstrip('.')};base64,{data}) format('{KINDS[path.suffix.lower()]}')}}")
    rules = [face('Montserrat', FONT_DIR / 'Montserrat.ttf', '100 900')]
    for family, path in user_fonts().items():
        rules.append(face(family, path, '700' if family == BOLD_FAMILY else '300 400'))
    return ''.join(rules)


def font_css():
    return _css(signature())
