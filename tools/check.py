"""Run the existing test suites with an isolated Windows user-data folder."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix='FokusWache-tests-') as folder:
    env = dict(os.environ, LOCALAPPDATA=folder, QT_QPA_PLATFORM='offscreen')
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                   cwd=ROOT, env=env, check=True)
    subprocess.run(['node', str(ROOT / 'tests/test_extension.js')],
                   cwd=ROOT, env=env, check=True)
