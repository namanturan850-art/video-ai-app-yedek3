from pathlib import Path
import shutil
import subprocess
import pytest


def test_local_subtitle_playback_and_timestamp_helpers():
    node=shutil.which('node')
    if not node:pytest.skip('Optional Node frontend checks')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,'--test','--test-reporter=tap','tests/frontend/subtitle_timing.test.cjs'],cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert '# pass 3' in result.stdout
