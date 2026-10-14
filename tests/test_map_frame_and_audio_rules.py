"""General rules (every project, language and map style): real borders for [BÖLGE]
(never an oval), names inside the safe area, both ends of [OK]/[ROTA] on screen,
the whoosh's loudest moment on the visible cut, and the master loudness stage."""
import subprocess
from pathlib import Path

from app.motion import relief
from app.rendering.engine import cut_aligned, master
from app.rendering.service import sound_peak

WHOOSH = Path('app/static/sfx/whoosh.wav')


def test_whoosh_peak_lands_on_the_cut():
    peak = sound_peak(WHOOSH)
    assert .1 < peak < .5
    slots = [{'slot_id': 'a', 'end_frame': 69}, {'slot_id': 'b', 'end_frame': 200}]
    event = cut_aligned({'t': 0., 'sound': 'whoosh', 'slot_id': 'a', 'peak': peak, 'path': str(WHOOSH)}, slots, [0, 12])
    assert abs(event['t'] + peak - (69 / 30 + 12 / 30 / 2)) < .002  # cut 2,30 s + half of the 0,4 s crossfade
    hard = cut_aligned({'t': 0., 'sound': 'whoosh', 'slot_id': 'a', 'peak': peak}, slots, [0, 0])
    assert abs(hard['t'] + peak - 69 / 30) < .002  # a crossfade turned into a hard cut: the cut itself
    other = {'t': 1.2, 'sound': 'hit'}
    assert cut_aligned(other, slots, [0, 12]) is other


def test_master_stage_on_the_final_audio():
    graph = master('[1:a]aresample=48000[nar];\n[nar]anull[a]', ['loudnorm', 'alimiter'])
    assert graph.endswith('[premaster]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.84:attack=5:release=50:level=false[a]')
    assert graph.count('[a]') == 1


def test_master_stage_keeps_true_peak_below_minus_one(tmp_path):
    source, out = tmp_path / 'in.wav', tmp_path / 'out.m4a'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', "aevalsrc='0.99*sin(2*PI*180*t)*gt(sin(2*PI*2*t),0.5)':s=48000:d=8",
                    '-ac', '2', str(source)], check=True)
    graph = master('[0:a]anull[a]', ['loudnorm', 'alimiter'])
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-filter_complex', graph, '-map', '[a]', '-c:a', 'aac', '-b:a', '192k', str(out)], check=True)
    report = subprocess.run(['ffmpeg', '-nostats', '-i', str(out), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    summary = report[report.rindex('Summary'):]
    loudness = float(summary.split('I:')[1].split('LUFS')[0]); peak = float(summary.split('Peak:')[1].split('dBFS')[0])
    assert peak <= -1.0 and abs(loudness + 14) < 1.5, (loudness, peak)


def test_crop_keeps_every_point_inside_the_safe_area():
    cw, ch = 2343, 1318
    points = [(420., 700.), (1900., 560.)]  # both ends of an arrow, far apart: the start crop (300..1500) misses one
    left, top, w, h = relief.contain(300., 120., 1200., 675., points, cw, ch)
    for x, y in points:
        sx, sy = (x - left) * relief.W / w, (y - top) * relief.H / h
        assert relief.SAFE[0] <= sx <= relief.SAFE[2] and relief.SAFE[1] <= sy <= relief.SAFE[3], (sx, sy)
    assert 0 <= left and left + w <= cw + .01 and 0 <= top and top + h <= ch + .01
