"""Check offline inference using synthetic audio, never a user's media library."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('payload', type=Path)
args = parser.parse_args()
payload = args.payload.resolve()
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
with tempfile.TemporaryDirectory(prefix='workstudio-release-') as temp:
    data = Path(temp)
    source = data / 'synthetic.wav'
    ffmpeg = payload / '_internal' / 'bin' / 'ffmpeg.exe'
    subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', str(source)], check=True, creationflags=flags)
    stat = source.stat()
    job = data / 'job.json'
    job.write_text(json.dumps({'items': [{'id': 'release-test', 'path': str(source), 'root': str(data), 'name': 'synthetic', 'fingerprint': f'{stat.st_size}:{stat.st_mtime}'}], 'completed': {'done': 0, 'accepted': 0, 'uncertain': 0}}), 'utf-8')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    subprocess.run([str(payload / 'audio-runtime' / 'python.exe'), str(payload / 'audio-engine' / 'audio_worker.py'), '--job', str(job), '--data', str(data), '--model', str(payload / 'models' / 'clap'), '--ffmpeg', str(ffmpeg)], check=True, timeout=180, env=env, creationflags=flags)
    status = json.loads((data / 'audio-analysis-status.json').read_text('utf-8'))
    assert status['phase'] == 'complete' and status['done'] == 1 and status['errors'] == 0, status
    assert not list(data.glob('*.aep'))
    print(json.dumps({'offline_inference': 'passed', 'device': status.get('device'), 'done': status['done']}))
