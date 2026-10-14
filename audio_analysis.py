"""Persistent content results and a resumable, isolated local inference job."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

VERSION = 'clap-v1'


def fingerprint(item):
    return f"{item['size']}:{item['modified']}"


@contextmanager
def connect(data):
    db = sqlite3.connect(str(Path(data)/'audio-analysis.sqlite'), timeout=20)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, fingerprint TEXT, version TEXT, payload TEXT)')
        with db:
            yield db
    finally:
        db.close()


def read_results(data):
    with connect(data) as db:
        return {ident:dict(json.loads(payload), fingerprint=fp) for ident,fp,payload in
                db.execute('SELECT id,fingerprint,payload FROM results WHERE version=?',(VERSION,))}


def store_result(data, ident, fp, result):
    with connect(data) as db:
        db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?)',
                   (ident,fp,VERSION,json.dumps(result,ensure_ascii=False)))


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    try:
        temp.write_text(json.dumps(value,ensure_ascii=False),'utf-8')
        for attempt in range(8):
            try:
                temp.replace(path)
                return
            except PermissionError:
                # Windows readers/antivirus may briefly deny replacing an open file.
                if attempt == 7: raise
                time.sleep(.025 * (attempt+1))
    finally:
        try: temp.unlink(missing_ok=True)
        except OSError: pass


def read_status(data):
    try: return json.loads((Path(data)/'audio-analysis-status.json').read_text('utf-8'))
    except (ValueError,OSError): return {}


def job_lock(data):
    """Kernel-held lock automatically releases even if the worker crashes."""
    import msvcrt
    handle = (Path(data)/'audio-analysis.lock').open('a+b')
    if handle.tell()==0: handle.write(b'0'); handle.flush()
    handle.seek(0)
    try: msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: handle.close(); return None
    return handle


def running(data):
    handle = job_lock(data)
    if handle is None: return True
    handle.close(); return False


class AudioAnalysis:
    def __init__(self, library, base):
        self.library, self.base = library, Path(base)
        self.lock = threading.Lock()
        # Optional runtime stays beside the project, independent from desktop packaging.
        self.home = Path(sys.executable).resolve().parents[2] if getattr(sys,'frozen',False) else self.base
        self.runtime = self.home/'.audio-runtime'/'Scripts'/'python.exe'
        self.model = self.home/'models'/'clap'
        if getattr(sys, 'frozen', False):
            installed = Path(sys.executable).resolve().parent
            if (installed/'audio-runtime'/'python.exe').is_file():
                self.runtime = installed/'audio-runtime'/'python.exe'
                self.model = installed/'models'/'clap'
        self.worker = (Path(sys.executable).parent/'audio-engine' if getattr(sys,'frozen',False) else self.base)/'audio_worker.py'
        self.process = None

    def status(self):
        d = read_status(self.library.data)
        active = running(self.library.data) or bool(self.process and self.process.poll() is None)
        if d.get('running') and not active:
            d.update(running=False, phase='interrupted', message='上次任务已中断，继续时会跳过已完成音频')
        d['running'] = active
        d['available'] = self.runtime.is_file() and (self.model/'manifest.json').is_file() and self.worker.is_file()
        return d

    def start(self):
        with self.lock:
            if self.status()['running']: raise ValueError('内容识别正在进行')
            if not self.status()['available']: raise ValueError('本地音频模型尚未安装')
            lib = self.library
            results = read_results(lib.data)
            with lib.lock:
                jobs = []
                completed = {'done':0,'accepted':0,'uncertain':0}
                for item in lib.index['items']:
                    if item['media_type']!='audio' or lib._audio_auto[item['id']]['group']!='待分类': continue
                    if item['id'] in lib.state['audio_categories']: continue
                    old = results.get(item['id'],{})
                    if old.get('fingerprint')==fingerprint(item) and not old.get('error'):
                        completed['done'] += 1
                        completed['accepted' if old.get('accepted') else 'uncertain'] += 1
                        continue
                    jobs.append({'id':item['id'],'path':item['audios'][0], 'fingerprint':fingerprint(item),
                                 'root':item['root_path'], 'name':item['name']})
            job_path=lib.data/'audio-analysis-job.json'
            atomic_json(job_path,{'items':jobs,'completed':completed})
            (lib.data/'audio-analysis.pause').unlink(missing_ok=True)
            atomic_json(lib.data/'audio-analysis-status.json',dict(running=True,phase='loading',total=len(jobs)+completed['done'],
                         **completed,errors=0,message='正在加载本地模型',updated=time.time()))
            env = os.environ.copy()
            env.update(PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            env.pop('PYTHONPATH',None)
            with (lib.data/'audio-analysis.log').open('a',encoding='utf-8') as log:
                # PyInstaller's DLL search directory is inherited by child processes.
                # The independent Python must load its own DLLs, not pin desktop files.
                frozen_windows = getattr(sys,'frozen',False) and os.name=='nt'
                if frozen_windows:
                    import ctypes
                    previous=ctypes.create_unicode_buffer(32768)
                    ctypes.windll.kernel32.GetDllDirectoryW(len(previous),previous)
                    ctypes.windll.kernel32.SetDllDirectoryW(None)
                try:
                    self.process=subprocess.Popen([str(self.runtime),str(self.worker),'--job',str(job_path),'--data',str(lib.data),
                                                   '--model',str(self.model),'--ffmpeg',str(self.base/'bin'/'ffmpeg.exe')],
                                                  stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,
                                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                finally:
                    if frozen_windows: ctypes.windll.kernel32.SetDllDirectoryW(previous.value)
            return self.status()

    def pause(self):
        (self.library.data/'audio-analysis.pause').touch()
        return {'ok':True}
