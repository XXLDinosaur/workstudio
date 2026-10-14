"""Loopback-only application server with authorized file IDs and video byte ranges."""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from library import Library, DATA, DEFAULT_ROOT

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA = Path(os.environ.get('AE_STUDIO_DATA', str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AEStudio')))
POSTER_WORKERS = threading.Semaphore(2)
MEDIA_MIME = {'.webp':'image/webp', '.svg':'image/svg+xml', '.js':'text/javascript', '.css':'text/css',
              '.mp4':'video/mp4', '.m4v':'video/mp4', '.mov':'video/quicktime', '.mp3':'audio/mpeg',
              '.wav':'audio/wav', '.m4a':'audio/mp4', '.flac':'audio/flac', '.ogg':'audio/ogg',
              '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg'}


def read_json(path, fallback):
    try:
        return json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        return fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), 'utf-8')
    temp.replace(path)


def byte_range(header, size):
    if not header:
        return 0, size - 1, False
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or size == 0 or not any(match.groups()):
        raise ValueError('Invalid Range')
    first, last = match.groups()
    if first:
        start, end = int(first), min(int(last), size-1) if last else size-1
    else:
        start, end = max(0, size-int(last)), size-1
    if start >= size or start > end:
        raise ValueError('Unsatisfiable Range')
    return start, end, True


def make_server(library, port=0):
    from audio_analysis import AudioAnalysis
    analysis = AudioAnalysis(library, BASE)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def json(self, obj, status=200):
            data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def trusted_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.trusted_host():
                return self.json({'error': 'Invalid host'}, 403)
            try:
                route = urlparse(self.path)
                if route.path == '/api/library':
                    library.refresh_audio_results()
                    with library.lock:
                        return self.json({'index': library.summary(), 'state': library.state, 'status': library.status,
                                          'token': library.token, 'native': library.window is not None, 'analysis':analysis.status()})
                if route.path == '/api/items':
                    return self.json(library.query({k:v[0] for k,v in parse_qs(route.query).items()}))
                if route.path.startswith('/api/item/'):
                    return self.json(library.item(route.path.rsplit('/',1)[-1]))
                if route.path.startswith('/api/metadata/'):
                    from media_cache import metadata
                    item = library.item(route.path.rsplit('/',1)[-1])
                    query = parse_qs(route.query)
                    kind = query.get('kind', ['audios' if item['audios'] else 'videos' if item['videos'] else 'images'])[0]
                    if kind not in {'audios','videos','images'}:
                        raise ValueError('无效的媒体类型')
                    source = library.file(item['id'],kind,int(query.get('number',['0'])[0]))
                    return self.json(metadata(source, BASE/'bin'/'ffmpeg.exe', library.data))
                if route.path == '/api/status':
                    library.refresh_audio_results()
                    return self.json({**library.status,'analysis':analysis.status()})
                if route.path.startswith('/media/'):
                    _, _, ident, kind, number = route.path.split('/')
                    if kind not in {'videos', 'images', 'posters', 'audios', 'waveform', 'waveform-full', 'compatible', 'compatible-video'}:
                        raise ValueError('禁止访问')
                    source_kind = {'posters':'videos','waveform':'audios','waveform-full':'audios','compatible':'audios','compatible-video':'videos'}.get(kind,kind)
                    path = library.file(ident, source_kind, int(number))
                    if kind in {'waveform','waveform-full','compatible','compatible-video'}:
                        from media_cache import audio_cache
                        path = audio_cache(path, BASE/'bin'/'ffmpeg.exe', library.data,kind)
                    if kind == 'posters':
                        path = self.video_poster(path)
                    if kind == 'images' and parse_qs(route.query).get('thumb'):
                        path = self.thumbnail(path)
                    elif kind == 'images' and parse_qs(route.query).get('display') and path.suffix.lower() != '.gif':
                        path = self.thumbnail(path, large=True)
                    return self.send_file(path)
                name = 'index.html' if route.path == '/' else route.path.lstrip('/')
                path = (BASE/'public'/name).resolve()
                if path.parent != (BASE/'public').resolve():
                    return self.json({'error': 'Not found'}, 404)
                return self.send_file(path)
            except (ValueError, OSError, KeyError, IndexError) as exc:
                return self.json({'error': str(exc)}, 404)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def thumbnail(self, source, large=False):
            key = hashlib.sha256((str(source)+str(source.stat().st_mtime_ns)+str(large)+'webp-v2').encode()).hexdigest()
            dest = library.data/'thumbnails'/(key+'.webp')
            if dest.is_file():
                return dest
            try:
                from PIL import Image, ImageOps
                with Image.open(source) as im:
                    target = (2560,2560) if large else (640,400)
                    im.draft('RGB', target)
                    im = ImageOps.exif_transpose(im)
                    im.thumbnail(target)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    temp = dest.with_name(key+'.'+secrets.token_hex(4)+'.tmp')
                    im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB').save(temp, 'WEBP', quality=88)
                    temp.replace(dest)
                return dest
            except Exception:
                return source

        def video_poster(self, source):
            key = hashlib.sha256((str(source)+str(source.stat().st_mtime_ns)).encode()).hexdigest()
            dest = library.data/'thumbnails'/(key+'-video.jpg')
            if dest.is_file():
                return dest
            with POSTER_WORKERS:
                if dest.is_file():
                    return dest
                binary = BASE/'bin'/'ffmpeg.exe'
                if not binary.is_file():
                    return BASE/'public'/'video-placeholder.svg'
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(key+'.'+secrets.token_hex(4)+'.jpg')
                try:
                    result = subprocess.run([str(binary), '-hide_banner', '-loglevel', 'error', '-nostdin',
                                             '-threads', '1', '-ss', '1', '-i', str(source), '-frames:v', '1',
                                             '-vf', 'scale=640:360:force_original_aspect_ratio=decrease',
                                             '-q:v', '3', '-y', str(temp)],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=25,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode == 0 and temp.is_file():
                        temp.replace(dest)
                        return dest
                except (OSError, subprocess.TimeoutExpired):
                    pass
                finally:
                    temp.unlink(missing_ok=True)
                return BASE/'public'/'video-placeholder.svg'

        def send_file(self, path):
            # Open before sending headers so missing files never produce a partial response.
            with path.open('rb') as stream:
                size = os.fstat(stream.fileno()).st_size
                try:
                    start, end, partial = byte_range(self.headers.get('Range'), size)
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                self.send_response(206 if partial else 200)
                mime = MEDIA_MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                self.send_header('Content-Type', mime)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(max(0, end-start+1)))
                if partial:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                stream.seek(start)
                left = end-start+1
                try:
                    while left > 0:
                        block = stream.read(min(left, 256*1024))
                        if not block:
                            break
                        self.wfile.write(block)
                        left -= len(block)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        def do_POST(self):
            if not self.trusted_host() or self.headers.get('X-AE-Token') != library.token:
                return self.json({'error': '未授权的请求'}, 403)
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                return self.json({'error': '禁止跨域请求'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length > 65536:
                    raise ValueError('请求过大')
                body = json.loads(self.rfile.read(length))
                if self.path == '/api/scan':
                    return self.json(library.scan(body.get('root'),body.get('sources')))
                if self.path == '/api/cancel-scan':
                    library.cancel.set()
                    return self.json({'ok':True})
                if self.path == '/api/action':
                    return self.json(library.action(body))
                if self.path == '/api/audio-analysis/start':
                    return self.json(analysis.start())
                if self.path == '/api/audio-analysis/pause':
                    return self.json(analysis.pause())
                return self.json({'error': 'Not found'}, 404)
            except Exception as exc:
                return self.json({'error': str(exc)}, 400)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=47841)
    parser.add_argument('--root')
    args = parser.parse_args()
    lib = Library()
    if args.root or lib.config['sources']:
        lib.scan(args.root)
    print(f'workstudio: http://127.0.0.1:{args.port}', flush=True)
    make_server(lib, args.port).serve_forever()
