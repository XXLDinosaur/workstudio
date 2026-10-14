import json
import tempfile
import time
import unittest
from pathlib import Path

from catalog import scan_source
from library import Library, source_record, write_json


class MultiLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.data=self.base/'data'

    def tearDown(self):
        self.temp.cleanup()

    def make(self,path):
        p=self.base/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture');return p

    def wait(self,lib):
        deadline=time.monotonic()+10
        while lib.status['scanning'] and time.monotonic()<deadline: time.sleep(.01)
        self.assertFalse(lib.status['scanning'])
        self.assertFalse(lib.status['error'])

    def test_mixed_types_and_typed_root(self):
        self.make('mix/城市/夜景.MP4');self.make('mix/城市/封面.PNG');self.make('mix/音效/风声.CAF');self.make('mix/manual.pdf')
        s=source_record(self.base/'mix','media')
        mixed=scan_source(s)['items']
        self.assertEqual({i['media_type'] for i in mixed},{'video','audio','image'})
        self.assertEqual({i['category'] for i in mixed},{'城市','音效'})
        self.assertEqual(len(scan_source({**s,'kind':'audio'})['items']),1)

    def test_migration_preserves_ae_ids_favorites_and_collections(self):
        path=self.make('AE/片头/模板/main.aep');root=path.parents[2]
        from catalog import scan_library
        old=scan_library(root);ident=old['items'][0]['id']
        write_json(self.data/'config.json',{'root':str(root)})
        write_json(self.data/'index.json',old)
        write_json(self.data/'state.json',{'favorites':[ident],'recent':[ident],'collections':{'项目':[ident]}})
        lib=Library(self.data)
        self.assertEqual(lib.item(ident)['media_type'],'template')
        lib.scan();self.wait(lib)
        restored=Library(self.data)
        self.assertEqual(restored.query({'view':'favorites'})['items'][0]['id'],ident)
        self.assertEqual(restored.state['collections']['项目'],[ident])

    def test_paging_search_scope_and_offline(self):
        root=self.base/'Audio'
        for n in range(135): self.make(f'Audio/风声/风声{n:03}.wav')
        image=self.make('Images/封面.jpg')
        sources=[source_record(root,'audio','音效'),source_record(image.parent,'image','图片')]
        lib=Library(self.data);lib.scan(sources=sources);self.wait(lib)
        first=lib.query({'type':'audio','limit':'48'})
        second=lib.query({'type':'audio','limit':'48','offset':'48'})
        self.assertEqual(first['total'],135)
        self.assertEqual(len(first['items']),48)
        self.assertFalse({i['id'] for i in first['items']}&{i['id'] for i in second['items']})
        self.assertEqual(len(lib.query({'q':'风声 012'})['items']),1)
        self.assertEqual(lib.query({'source':sources[1]['id']})['total'],1)
        ident=first['items'][0]['id'];lib.action({'op':'favorite','id':ident})
        root.rename(self.base/'unplugged')
        lib.scan();self.wait(lib)
        self.assertEqual(lib.summary()['total'],136)
        self.assertTrue(lib.summary()['sources'][0]['offline'])
        self.assertIn(ident,lib.state['favorites'])
        with self.assertRaises(ValueError): lib.file(ident,'audios')

    def test_root_removal_and_overlap_dedup(self):
        p=self.make('Music/sub/a.mp3')
        outer=source_record(p.parents[1],'audio');inner=source_record(p.parent,'audio')
        lib=Library(self.data);lib.scan(sources=[outer,inner]);self.wait(lib)
        self.assertEqual(lib.summary()['total'],1)
        lib.scan(sources=[inner]);self.wait(lib)
        self.assertTrue(p.is_file())
        self.assertEqual(lib.summary()['total'],1)
        self.assertEqual(lib.query({})['items'][0]['source_id'],inner['id'])

    def test_outside_root_cannot_be_served(self):
        p=self.make('music/sound.wav');outside=self.make('secret.wav')
        lib=Library(self.data);lib.scan(sources=[source_record(p.parent,'audio')]);self.wait(lib)
        item=lib.index['items'][0];item['audios']=[str(outside)]
        with self.assertRaises(ValueError): lib.file(item['id'],'audios')

    def test_source_validation_does_not_replace_index(self):
        p=self.make('music/sound.wav');s=source_record(p.parent,'audio');lib=Library(self.data)
        lib.scan(sources=[s]);self.wait(lib)
        for bad in [[],[s,s],[source_record(self.base/'absent','image')]]:
            with self.assertRaises(ValueError):lib.scan(sources=bad)
            self.assertEqual(lib.summary()['total'],1)


if __name__=='__main__': unittest.main()
