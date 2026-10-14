import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from library import Library
from audio_analysis import AudioAnalysis


class ReleaseTests(unittest.TestCase):
    def test_first_run_has_no_personal_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            lib = Library(temp)
            self.assertEqual(lib.config['sources'], [])
            self.assertEqual(lib.query({})['total'], 0)

    def test_installed_audio_engine_uses_relocatable_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp).resolve() / 'workstudio'
            (install / 'audio-runtime').mkdir(parents=True)
            (install / 'audio-runtime' / 'python.exe').touch()
            with patch('sys.frozen', True, create=True), patch('sys.executable', str(install / 'workstudio.exe')):
                engine = AudioAnalysis(Library(Path(temp) / 'data'), install / '_internal')
            self.assertEqual(engine.runtime, install / 'audio-runtime' / 'python.exe')
            self.assertEqual(engine.model, install / 'models' / 'clap')
            self.assertEqual(engine.worker, install / 'audio-engine' / 'audio_worker.py')
