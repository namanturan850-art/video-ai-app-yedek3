"""Execute the real browser request helper with Node's built-in test runner.

Node is a development-only optional test tool, never required by the launcher.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Frontend helper regression tests require Node.js (development only).')
def test_settings_request_timeout_and_classification():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([shutil.which('node'), '--test', str(root / 'tests/frontend/settings_http.test.cjs')],
                            cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
