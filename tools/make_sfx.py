"""Generate the bundled sound effects (click, rise, hit) from math only.

No samples or third-party recordings are used, so the files belong to this
project (see docs/LICENSES.md). Run: python tools/make_sfx.py
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / 'app' / 'static' / 'sfx'


def write(name, samples):
    peak = max(1e-9, max(abs(s) for s in samples))
    data = b''.join(struct.pack('<h', int(max(-1, min(1, s / peak * .89)) * 32767)) for s in samples)
    with wave.open(str(OUT / f'{name}.wav'), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(RATE); f.writeframes(data)


def click():
    n = int(.09 * RATE)
    return [math.sin(2 * math.pi * 2200 * t / RATE) * math.exp(-t / (RATE * .008)) + .35 * math.sin(2 * math.pi * 880 * t / RATE) * math.exp(-t / (RATE * .02)) for t in range(n)]


def rise():
    n, rnd, phase, out, low = int(.9 * RATE), random.Random(7), 0.0, [], 0.0
    for t in range(n):
        x = t / n
        phase += 2 * math.pi * (180 + 900 * x * x) / RATE
        low += .08 * (rnd.uniform(-1, 1) - low)  # soft filtered noise (air)
        env = x ** 1.6 * (1 - max(0, (x - .92) / .08))
        out.append(env * (.6 * math.sin(phase) + .5 * low))
    return out


def hit():
    n, rnd, out, low = int(.7 * RATE), random.Random(11), [], 0.0
    for t in range(n):
        s = t / RATE
        low += .15 * (rnd.uniform(-1, 1) - low)
        body = math.sin(2 * math.pi * (55 + 90 * math.exp(-s * 30)) * s) * math.exp(-s * 6)
        out.append(body + .6 * low * math.exp(-s * 25))
    return out


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in (('click', click), ('rise', rise), ('hit', hit)):
        write(name, make())
        print(name, (OUT / f'{name}.wav').stat().st_size)
