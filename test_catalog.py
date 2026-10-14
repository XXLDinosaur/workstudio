import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from catalog import scan_library
from server import Library, byte_range, make_server


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base/'模板库'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def make(self, path, content=b'file'):
        target = self.root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_versions_assets_autosaves_and_archives(self):
        self.make('片头/包图网_123科技片头/工程/Main.aep')
        self.make('片头/包图网_123科技片头/工程/Main 副本 17.x.aep')
        self.make('片头/包图网_123科技片头/工程/Adobe After Effects 自动保存/backup.aep')
        self.make('片头/包图网_123科技片头/预览视频.mp4')
        self.make('片头/包图网_123科技片头/封面.jpg')
        self.make('片头/包图网_123科技片头/工程/(素材)/preview.mp4')
        self.make('片头/包图网_123科技片头/工程/(素材)/preview.jpg')
        self.make('片头/包图网_123科技片头.zip')
        self.make('片头/未解压.rar')
        result = scan_library(self.root)
        self.assertEqual(len(result['items']), 2)
        item = next(x for x in result['items'] if x['projects'])
        self.assertEqual(item['name'], '科技片头')
        self.assertEqual(len(item['projects']), 2)
        self.assertTrue(item['projects'][0].endswith('Main.aep'))
        self.assertEqual(len(item['videos']), 1)
        self.assertEqual(len(item['images']), 1)
        self.assertEqual(scan_library(self.root)['items'][0]['id'], result['items'][0]['id'])

    def test_does_not_guess_footage_as_preview(self):
        self.make('图文/模板/Main.aep')
        self.make('图文/模板/Video/Light.mov')
        self.make('图文/模板/Video/1.jpg')
        item = scan_library(self.root)['items'][0]
        self.assertEqual(item['videos'], [])
        self.assertEqual(item['images'], [])

    def test_loose_project(self):
        self.make('标题/Main.aep')
        self.make('标题/预览.mp4')
        self.assertEqual(len(scan_library(self.root)['items'][0]['videos']), 1)

    def test_title_match_candidate_and_tutorial_exclusion(self):
        self.make('片头/科技片头 Corporate Slideshow 123/Main.aep')
        self.make('片头/科技片头 Corporate Slideshow 123/Corporate Slideshow 123.mp4')
        self.make('片头/科技片头 Corporate Slideshow 123/Help/preview.mp4')
        self.make('片头/另一模板/工程/Main.aep')
        self.make('片头/另一模板/工程/1.mp4')
        items = scan_library(self.root)['items']
        matched = next(x for x in items if 'Corporate' in x['name'])
        candidate = next(x for x in items if x['name'] == '另一模板')
        self.assertEqual(len(matched['videos']), 1)
        self.assertEqual(matched['video_confidence'], ['matched'])
        self.assertEqual(candidate['video_confidence'], ['candidate'])

    def test_invalid_root(self):
        with self.assertRaises(ValueError):
            scan_library(self.root/'missing')

    def test_ranges(self):
        self.assertEqual(byte_range(None, 100), (0, 99, False))
        self.assertEqual(byte_range('bytes=5-10', 100), (5, 10, True))
        self.assertEqual(byte_range('bytes=90-', 100), (90, 99, True))
        self.assertEqual(byte_range('bytes=-10', 100), (90, 99, True))
        self.assertEqual(byte_range('bytes=90-999', 100), (90, 99, True))
        for header in ['bytes=100-', 'bytes=10-1', 'bytes=-0', 'bytes=0-1,3-5']:
            with self.assertRaises(ValueError):
                byte_range(header, 100)

    def test_http_playback_auth_persistence_and_missing_file(self):
        video = self.make('片头/示例/预览视频.mp4', b'0123456789abcdef')
        self.make('片头/示例/Main.aep')
        lib = Library(self.base/'data')
        lib.index = scan_library(self.root)
        ident = lib.index['items'][0]['id']
        http = make_server(lib)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{http.server_port}'
        try:
            with urlopen(Request(url+f'/media/{ident}/videos/0', headers={'Range':'bytes=3-7'})) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.headers['Content-Range'], 'bytes 3-7/16')
                self.assertEqual(response.read(), b'34567')
            body = json.dumps({'op':'favorite','id':ident}).encode()
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url+'/api/action', data=body))
            self.assertEqual(error.exception.code, 403)
            with urlopen(Request(url+'/api/action', data=body, headers={'X-AE-Token':lib.token})) as response:
                self.assertIn(ident, json.load(response)['state']['favorites'])
            self.assertIn(ident, Library(self.base/'data').state['favorites'])
            with self.assertRaises(HTTPError):
                urlopen(Request(url+'/api/action', data=body, headers={'X-AE-Token':lib.token,'Origin':'https://example.com'}))
            with self.assertRaises(HTTPError):
                urlopen(url+'/../server.py')
            with patch('os.startfile') as opened:
                lib.action({'op':'open','id':ident,'kind':'projects','number':0})
                self.assertTrue(opened.call_args.args[0].endswith('Main.aep'))
            video.unlink()
            with self.assertRaises(HTTPError) as error:
                urlopen(url+f'/media/{ident}/videos/0')
            self.assertEqual(error.exception.code, 404)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
