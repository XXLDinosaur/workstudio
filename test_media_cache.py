import subprocess
import tempfile
import unittest
from pathlib import Path

from media_cache import audio_cache,metadata,cache_key

FFMPEG=Path(__file__).parent/'bin'/'ffmpeg.exe'


@unittest.skipUnless(FFMPEG.is_file(),'Bundled FFmpeg is required')
class CompatibilityTests(unittest.TestCase):
    def test_audio_and_video_compatibility_preserve_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);audio=root/'sample.caf';video=root/'sample.mov';data=root/'cache'
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            for args in [
                ['-f','lavfi','-i','sine=frequency=440:duration=0.5','-c:a','pcm_s16le',str(audio)],
                ['-f','lavfi','-i','testsrc2=size=160x90:rate=12','-t','0.5','-c:v','prores_ks','-pix_fmt','yuv422p10le',str(video)]
            ]:
                subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-y',*args],check=True,capture_output=True,creationflags=flags)
            original_audio=audio.read_bytes();original_video=video.read_bytes()
            # Previously cached minimal information is upgraded for original files.
            old=data/'metadata'/(cache_key(video)+'.json');old.parent.mkdir(parents=True)
            old.write_text('{"duration": 0.5}',encoding='utf-8')
            source_info=metadata(video,FFMPEG,data)
            self.assertEqual(source_info['format'],'MOV')
            self.assertIn('prores',source_info['codec'])
            self.assertEqual(source_info['fps'],12)
            self.assertGreater(source_info['bitrate'],0)
            if FFMPEG.with_name('ffprobe.exe').is_file():
                self.assertEqual(source_info['frame_count'],6)
            converted_audio=audio_cache(audio,FFMPEG,data,'compatible')
            wave=audio_cache(audio,FFMPEG,data,'waveform')
            converted_video=audio_cache(video,FFMPEG,data,'compatible-video')
            self.assertGreater(metadata(converted_audio,FFMPEG,data)['duration'],.4)
            self.assertEqual(metadata(converted_video,FFMPEG,data)['width'],160)
            self.assertTrue(wave.read_bytes().startswith(b'\x89PNG'))
            self.assertEqual(audio_cache(audio,FFMPEG,data,'compatible'),converted_audio)
            self.assertEqual(audio.read_bytes(),original_audio)
            self.assertEqual(video.read_bytes(),original_video)


if __name__=='__main__':unittest.main()
