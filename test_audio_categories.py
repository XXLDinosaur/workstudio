import tempfile
import time
import unittest
from pathlib import Path

from audio_categories import classify
from library import Library, source_record


class AudioClassificationTests(unittest.TestCase):
    def category(self, path):
        return classify({'relative_path':path})['id']

    def test_real_library_examples_and_bilingual_paths(self):
        cases = {
            r'音效库\转场\001 Reverse - TRFX02 Zenhiser.wav':'transition',
            r'音效\Whooshes\DS 03 Travelers.wav':'transition',
            r'音效\动物音效\鲸鱼\鲸鱼卡通.mp3':'animal',
            r'音效\武器\TOYMech_TOY GUN RELOAD.wav':'weapon',
            r'音效\iPhone音效\KeypressSpacebar.wav':'ui',
            r'音效\人声\MaleAngry_I_Said_No.wav':'voice',
            r'音效\门_窗户_家具\门08.caf':'foley',
            r'AudioJungle合集\Corporate Upbeat\01_main.wav':'corporate',
            r'AudioJungle合集\An Ocean\An Ocean Main.wav':'music-other',
            r'AudioJungle合集\The Frost Logo\Short.wav':'logo',
            r'AudioJungle合集\Epic Trailer\track.mp3':'epic',
            r'AudioJungle合集\Learning Lofi\Main.mp3':'ambient',
            r'AudioJungle合集\短音效\LampSwitch_31.wav':'foley',
            r'AudioJungle合集\Paper Crumpling\Paper Crumpling.wav':'foley',
            r'AudioJungle合集\Electro Streak Logo\Logo with SFX.wav':'logo',
            r'音效\体育音效\溜冰\溜冰场(现场音乐).mp3':'sport',
            r'包图网励志宣传片配乐\672f48fd.mp3':'corporate',
            r'素材\123456.wav':'unknown',
            r'音效\scary white carpeting.wav':'sfx-other',
        }
        for path, expected in cases.items():
            with self.subTest(path=path): self.assertEqual(self.category(path),expected)

    def test_override_persists_rescan_restart_and_updates_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); root=base/'audio';root.mkdir()
            wav=root/'Whoosh.wav';wav.write_bytes(b'unchanged')
            lib=Library(base/'data')
            def scan():
                lib.scan(sources=[source_record(root,'audio')])
                deadline=time.monotonic()+5
                while lib.status['scanning'] and time.monotonic()<deadline:time.sleep(.01)
                self.assertFalse(lib.status['scanning']);self.assertFalse(lib.status['error'])
            scan();ident=lib.index['items'][0]['id']
            self.assertEqual(lib.query({'type':'audio','grouping':'smart','category':'transition'})['total'],1)
            original_category=lib.item(ident)['category']
            lib.action({'op':'favorite','id':ident})
            lib.action({'op':'audio-category','id':ident,'category':'nature'})
            self.assertEqual(lib.query({'type':'audio','grouping':'smart','category':'transition'})['total'],0)
            result=lib.query({'type':'audio','grouping':'smart','category':'nature','q':'自然'})
            self.assertEqual(result['total'],1)
            self.assertEqual(result['categories'][0]['count'],1)
            self.assertEqual(lib.query({'type':'audio','category':original_category})['total'],1)
            scan();lib=Library(base/'data')
            self.assertEqual(lib.item(ident)['audio_classification']['method'],'manual')
            self.assertEqual(lib.item(ident)['audio_classification']['id'],'nature')
            self.assertIn(ident,lib.state['favorites'])
            with self.assertRaises(ValueError):lib.action({'op':'audio-category','id':ident,'category':'invalid'})
            lib.action({'op':'audio-category','id':ident,'category':None})
            self.assertEqual(Library(base/'data').item(ident)['audio_classification']['id'],'transition')
            self.assertEqual(wav.read_bytes(),b'unchanged')


if __name__=='__main__': unittest.main()
