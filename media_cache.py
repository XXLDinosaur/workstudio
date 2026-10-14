"""On-demand metadata, real audio waveforms and compatibility listening cache."""
import hashlib
import json
import re
import secrets
import subprocess
import threading
from pathlib import Path

WORKERS = threading.Semaphore(2)
VIDEO_WORKERS = threading.Semaphore(1)
CACHE_LOCKS = [threading.Lock() for _ in range(128)]
METADATA_VERSION = 2


def number(value):
    try:
        value = float(value)
        return value if 0 < value < float('inf') else None
    except (ValueError, TypeError):
        return None


def frame_rate(value):
    try:
        parts = str(value).split('/')
        return number(float(parts[0]) / float(parts[1])) if len(parts) == 2 else number(value)
    except (ValueError, ZeroDivisionError):
        return None


def probe_metadata(source, probe):
    proc = subprocess.run([str(probe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(source)],
                          capture_output=True, timeout=25, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if proc.returncode:
        raise ValueError('无法读取媒体信息')
    info = json.loads(proc.stdout)
    fmt = info.get('format', {})
    streams = info.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), {})
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), {})
    result = {'format': source.suffix.lstrip('.').upper(), 'container': fmt.get('format_long_name') or fmt.get('format_name')}
    result['duration'] = number(fmt.get('duration')) or number(video.get('duration')) or number(audio.get('duration'))
    result['bitrate'] = number(fmt.get('bit_rate'))
    if not result['bitrate'] and result['duration']:
        result['bitrate'] = round(source.stat().st_size * 8 / result['duration'])
        result['bitrate_estimated'] = True
    if video:
        result.update(codec=video.get('codec_name'), codec_name=video.get('codec_long_name'),
                      profile=video.get('profile'), width=video.get('width'), height=video.get('height'),
                      pixel_format=video.get('pix_fmt'), fps=frame_rate(video.get('avg_frame_rate')) or frame_rate(video.get('r_frame_rate')),
                      frame_count=number(video.get('nb_frames')), video_bitrate=number(video.get('bit_rate')))
        if not result['frame_count'] and result['fps'] and result['duration']:
            result['frame_count'] = round(result['fps'] * result['duration'])
            result['frames_estimated'] = True
    if audio:
        result.update(audio_codec=audio.get('codec_name'), audio_codec_name=audio.get('codec_long_name'),
                      sample_rate=number(audio.get('sample_rate')), channels=audio.get('channel_layout') or audio.get('channels'),
                      audio_bitrate=number(audio.get('bit_rate')))
    return {k:v for k,v in result.items() if v is not None}


def cache_key(source):
    stat=source.stat()
    return hashlib.sha256((str(source)+str(stat.st_mtime_ns)+str(stat.st_size)).encode()).hexdigest()


def metadata(source, binary, data):
    dest=Path(data)/'metadata'/(cache_key(source)+'.json')
    if dest.is_file():
        try:
            saved=json.loads(dest.read_text('utf-8'))
            if saved.get('_version') == METADATA_VERSION: return saved
        except (ValueError, OSError):
            pass
    result={}
    try:
        from PIL import Image
        with Image.open(source) as im:
            result={'width':im.width,'height':im.height,'format':im.format}
    except Exception:
        probe=Path(binary).with_name('ffprobe.exe')
        if probe.is_file():
            with WORKERS:
                result=probe_metadata(source,probe)
            return save_metadata(dest,result)
        with WORKERS:
            proc=subprocess.run([str(binary),'-hide_banner','-nostdin','-i',str(source)],stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        info=proc.stderr.decode('utf-8','replace')
        duration=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',info)
        if duration: result['duration']=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
        video=re.search(r'Video: ([^,]+).*?\b(\d{2,6})x(\d{2,6})\b',info)
        if video: result.update(codec=video[1],width=int(video[2]),height=int(video[3]))
        audio=re.search(r'Audio: ([^,]+), (\d+) Hz, ([^,\r\n]+)',info)
        if audio: result.update(audio_codec=audio[1],sample_rate=int(audio[2]),channels=audio[3])
        fps=re.search(r'(\d+(?:\.\d+)?) fps',info)
        if fps: result['fps']=float(fps[1])
        bitrate=re.search(r'Duration:.*?bitrate: (\d+(?:\.\d+)?) kb/s',info)
        if bitrate: result['bitrate']=round(float(bitrate[1])*1000)
        result['format']=source.suffix.lstrip('.').upper()
    return save_metadata(dest,result)


def save_metadata(dest,result):
    result['_version']=METADATA_VERSION
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name(dest.stem+'.'+secrets.token_hex(4)+'.tmp')
    temp.write_text(json.dumps(result),'utf-8');temp.replace(dest)
    return result


def audio_cache(source,binary,data,kind):
    suffix='-full.png' if kind=='waveform-full' else '.png' if kind=='waveform' else '.mp4' if kind=='compatible-video' else '.mp3'
    dest=Path(data)/'audio-cache'/(cache_key(source)+suffix)
    if dest.is_file(): return dest
    lock=CACHE_LOCKS[int(dest.stem.split('-')[0][:8],16)%len(CACHE_LOCKS)]
    with lock, VIDEO_WORKERS if kind=='compatible-video' else WORKERS:
        if dest.is_file(): return dest
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.with_name(dest.stem+'.'+secrets.token_hex(4)+suffix)
        command=[str(binary),'-hide_banner','-loglevel','error','-nostdin','-threads','1']
        if kind=='waveform': command+=['-t','60']
        command+=['-i',str(source)]
        if kind=='waveform':
            command+=['-filter_complex','atrim=duration=60,aformat=channel_layouts=mono,showwavespic=s=1000x180:colors=0x94c4cf','-frames:v','1']
        elif kind=='waveform-full':
            command+=['-filter_complex','aformat=channel_layouts=mono,aresample=2000,showwavespic=s=640x120:colors=0x94c4cf:scale=sqrt','-frames:v','1']
        elif kind=='compatible-video':
            command+=['-map','0:v:0','-map','0:a:0?','-vf',"scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                      '-c:v','libx264','-preset','veryfast','-crf','24','-pix_fmt','yuv420p','-threads','2',
                      '-c:a','aac','-b:a','128k','-movflags','+faststart']
        else:
            command+=['-vn','-c:a','libmp3lame','-b:a','192k']
        command+=['-y',str(temp)]
        try:
            proc=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=600 if kind=='compatible-video' else 120,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode or not temp.is_file(): raise ValueError('无法生成试听缓存，可使用系统默认软件打开原文件')
            temp.replace(dest)
        except subprocess.TimeoutExpired:
            raise ValueError('试听转换超时，请用系统默认软件打开此文件')
        finally:
            temp.unlink(missing_ok=True)
    return dest
