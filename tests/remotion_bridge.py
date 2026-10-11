"""Test-only stand-in for the OpenMontage bridge: renders the bespoke Remotion
entry with the locally installed Remotion CLI (same entry/props/public dir)."""
import subprocess
from pathlib import Path
ROOT = Path('/tmp/claude-0/rem')
BROWSER = '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell'
class LocalRemotionBridge:
    def __init__(self): self.calls = []
    def status(self, refresh=False): return {'ready': True}
    def root(self): return ROOT
    def call(self, operation, inputs, folder, runner=None):
        b = inputs['edit_decisions']['bespoke']; self.calls.append(inputs)
        cli = ROOT / 'node_modules/@remotion/cli/remotion-cli.js'
        r = subprocess.run(['node', str(cli), 'render', b['entry'], b['composition_id'], inputs['output_path'], f'--props={b["props_path"]}',
                            f'--public-dir={b["public_dir"]}', f'--browser-executable={BROWSER}', '--concurrency=2', '--log=error'],
                           cwd=ROOT, capture_output=True, text=True, timeout=900)
        if r.returncode: raise RuntimeError(r.stderr[-2000:] + r.stdout[-2000:])
        return {'output': inputs['output_path']}
