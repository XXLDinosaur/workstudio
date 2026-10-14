import tempfile
import time
import unittest
import json
from unittest.mock import patch
from pathlib import Path

from audio_analysis import atomic_json, fingerprint, read_results, store_result
from library import Library, source_record


class ContentResultTests(unittest.TestCase):
    def test_progress_recovers_from_windows_file_sharing_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'progress.json'
            path.write_text('{"done": 1}',encoding='utf-8')
            replace=Path.replace
            attempts=[]
            def temporarily_busy(source,target):
                attempts.append(source)
                if len(attempts)==1: raise PermissionError('File is being read')
                return replace(source,target)
            with patch.object(Path,'replace',temporarily_busy):
                atomic_json(path,{'done':2})
            self.assertEqual(json.loads(path.read_text('utf-8')),{'done':2})
            self.assertEqual(len(attempts),2)
            self.assertEqual(list(Path(temp).glob('*.tmp')),[])

    def test_content_persistence_manual_priority_and_changed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'audio';root.mkdir()
            source=root/'001.wav';source.write_bytes(b'original audio')
            lib=Library(Path(temp)/'data')
            def scan():
                lib.scan(sources=[source_record(root,'audio')])
                deadline=time.monotonic()+5
                while lib.status['scanning'] and time.monotonic()<deadline:time.sleep(.01)
                self.assertFalse(lib.status['scanning']);self.assertFalse(lib.status['error'])
            scan();item=lib.index['items'][0];ident=item['id']
            self.assertEqual(item['audio_classification']['id'],'unknown')
            store_result(lib.data,ident,fingerprint(item),{'accepted':False,'category':None,'candidates':[{'id':'nature','similarity':.2}]})
            lib.refresh_audio_results(force=True)
            self.assertEqual(lib.query({'type':'audio','audio_review':'1'})['total'],1)
            store_result(lib.data,ident,fingerprint(item),{'accepted':True,'category':'nature','duration':12.3,'candidates':[{'id':'nature','similarity':.4}]})
            lib.refresh_audio_results(force=True)
            self.assertEqual(lib.query({'type':'audio','audio_review':'1'})['total'],0)
            self.assertEqual(lib.item(ident)['audio_classification']['method'],'content')
            self.assertEqual(lib.query({'type':'audio','grouping':'smart','category':'nature'})['total'],1)
            self.assertEqual(lib.item(ident)['audio_duration'],12.3)
            self.assertEqual(Library(lib.data).item(ident)['audio_classification']['id'],'nature')
            lib.action({'op':'audio-category','id':ident,'category':'foley'})
            lib.refresh_audio_results(force=True);scan()
            self.assertEqual(lib.item(ident)['audio_classification']['id'],'foley')
            lib.action({'op':'audio-category','id':ident,'category':None})
            self.assertEqual(lib.item(ident)['audio_classification']['id'],'nature')
            source.write_bytes(b'changed content with new size');scan()
            self.assertEqual(lib.item(ident)['audio_classification']['id'],'unknown')
            self.assertNotIn('audio_duration',lib.item(ident))
            self.assertNotIn('audio_analysis',lib.item(ident))

    def test_uncertain_result_does_not_force_a_category(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            store_result(data,'example','fingerprint',{'accepted':False,'category':None,'candidates':[{'id':'voice','similarity':.19}]})
            value=read_results(data)['example']
            self.assertFalse(value['accepted'])
            self.assertEqual(value['candidates'][0]['id'],'voice')


if __name__=='__main__':unittest.main()
