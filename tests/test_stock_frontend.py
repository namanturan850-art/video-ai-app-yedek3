"""Real browser stock controller exercised with Node; no Windows runtime dependency."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which('node'),reason='Node is an optional development test tool.')
def test_stock_relevance_controls_preserve_explicit_confirmation_and_safe_labels():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([shutil.which('node'),'--test',str(root/'tests/frontend/stock-relevance.test.cjs')],
                          cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
