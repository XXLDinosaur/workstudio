"""Add a relocatable, offline audio engine and its licenses to a desktop build."""
import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True, type=Path)
    args = parser.parse_args()
    payload = args.payload.resolve()
    cache = ROOT / '.build-deps'
    cache.mkdir(exist_ok=True)
    archive = cache / 'python-3.12.10-embed-amd64.zip'
    if not archive.exists():
        urllib.request.urlretrieve(PYTHON_URL, archive)
    runtime = payload / 'audio-runtime'
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (runtime / member.filename).resolve()
            if not target.is_relative_to(runtime):
                raise ValueError('Unsafe Python archive path')
        package.extractall(runtime)
    (runtime / 'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../audio-engine\nimport site\n', 'utf-8')
    dependencies = ROOT / '.audio-runtime' / 'Lib' / 'site-packages'
    if not dependencies.is_dir():
        raise RuntimeError('Run setup-audio.ps1 first')
    shutil.copytree(dependencies, runtime / 'Lib' / 'site-packages', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'pip', 'pip-*.dist-info'))
    source_model = ROOT / 'models' / 'clap'
    manifest = json.loads((source_model / 'manifest.json').read_text('utf-8'))
    model = payload / 'models' / 'clap'
    model.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest['files'].items():
        source = source_model / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('Model checksum mismatch: ' + name)
        target = model / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(source_model / 'manifest.json', model / 'manifest.json')
    notices = payload / 'licenses'
    notices.mkdir(exist_ok=True)
    for name, url in {
        'CLAP-code-CC0.txt': 'https://raw.githubusercontent.com/LAION-AI/CLAP/main/LICENSE',
        'Apache-2.0.txt': 'https://www.apache.org/licenses/LICENSE-2.0.txt',
        'CLAP-model-card.md': 'https://huggingface.co/laion/clap-htsat-unfused/raw/main/README.md',
        'CLAP-ONNX-model-card.md': 'https://huggingface.co/Xenova/clap-htsat-unfused/raw/c28f2883575e590e04d3146ff0713c2448d691ba/README.md',
        'Pillow.txt': 'https://raw.githubusercontent.com/python-pillow/Pillow/main/LICENSE',
        'pywebview.txt': 'https://raw.githubusercontent.com/r0x0r/pywebview/6.2.1/LICENSE',
        'pythonnet.txt': 'https://raw.githubusercontent.com/pythonnet/pythonnet/master/LICENSE',
        'clr-loader.txt': 'https://raw.githubusercontent.com/pythonnet/clr-loader/master/LICENSE',
    }.items():
        local = cache / name
        if not local.exists():
            urllib.request.urlretrieve(url, local)
        shutil.copy2(local, notices / name)
    shutil.copy2(runtime / 'LICENSE.txt', notices / 'Python.txt')
    shutil.copy2(ROOT / 'LICENSE', notices / 'GPL-3.0.txt')
    shutil.copy2(ROOT / 'bin' / 'ffprobe-manifest.json', notices / 'ffmpeg-build.json')
    shutil.copy2(ROOT / 'docs' / 'THIRD-PARTY-SOURCES.md', notices / 'THIRD-PARTY-SOURCES.md')
    (notices / 'audio-dependencies.txt').write_text(
        'Audio dependency licenses and original METADATA are retained in audio-runtime/Lib/site-packages/*.dist-info.\n', 'utf-8')
    (payload / 'BUILD-INFO.json').write_text(json.dumps({
        'version': (ROOT / 'VERSION').read_text().strip(),
        'python_embed_url': PYTHON_URL,
        'python_embed_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'model': manifest,
    }, indent=2), 'utf-8')
    print('Offline audio payload ready:', payload, flush=True)


if __name__ == '__main__':
    main()
