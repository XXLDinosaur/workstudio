"""Fetch pinned, checksum-verified FFmpeg and FFprobe binaries."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
SHA256 = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'


def install():
    archive = ROOT / '.build-deps' / 'ffmpeg-9.0.2-essentials_build.zip'
    archive.parent.mkdir(exist_ok=True)
    if not archive.is_file():
        temp = archive.with_suffix('.download')
        with urllib.request.urlopen(URL, timeout=60) as response, temp.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temp.replace(archive)
    with archive.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != SHA256:
        raise ValueError('FFprobe archive checksum mismatch')
    target = ROOT / 'bin'
    target.mkdir(exist_ok=True)
    hashes = {}
    with zipfile.ZipFile(archive) as package:
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            member = next(p for p in package.namelist() if p.endswith('/bin/' + name))
            binary = package.read(member)
            (target / name).write_bytes(binary)
            hashes[name] = hashlib.sha256(binary).hexdigest()
    (target / 'ffprobe-manifest.json').write_text(json.dumps({
        'version': '9.0.2', 'url': URL, 'archive_sha256': actual,
        'binaries': hashes, 'license': 'GPL-3.0',
    }, indent=2), encoding='utf-8')
    print('Bundled FFmpeg and FFprobe verified and installed')


if __name__ == '__main__':
    install()
