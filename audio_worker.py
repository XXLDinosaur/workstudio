"""Offline CLAP inference worker. Run only with the dedicated audio runtime."""
import argparse
import hashlib
import json
import os
import subprocess
import time
import traceback
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '4'
from audio_analysis import atomic_json, fingerprint, job_lock, read_results, store_result
from audio_prompts import PROMPTS


class ContentModel:
    def __init__(self, folder):
        import numpy as np
        import onnxruntime as ort
        from transformers import AutoTokenizer
        from transformers.audio_utils import mel_filter_bank, window_function
        self.np = np
        folder = Path(folder)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.enable_mem_pattern = False
        opts.log_severity_level = 3
        self.mels = mel_filter_bank(513,64,50,14000,48000,norm='slaney',mel_scale='slaney')
        self.window = window_function(1024,'hann')
        self.ids, descriptions = [], []
        for ident, texts in PROMPTS.items():
            self.ids.extend([ident]*len(texts)); descriptions.extend(texts)
        token = hashlib.sha256(json.dumps(PROMPTS,sort_keys=True).encode()).hexdigest()[:16]
        embeddings = folder/('prompts-'+token+'.npy')
        if embeddings.is_file():
            self.text = np.load(embeddings,allow_pickle=False)
        else:
            tokenizer = AutoTokenizer.from_pretrained(str(folder),local_files_only=True)
            session = ort.InferenceSession(str(folder/'onnx'/'text_model_quantized.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
            inputs = tokenizer(descriptions,padding=True,truncation=True,return_tensors='np')
            self.text = session.run(None,{x.name:inputs[x.name].astype(np.int64) for x in session.get_inputs()})[0]
            self.text /= np.linalg.norm(self.text,axis=-1,keepdims=True).clip(1e-8)
            np.save(embeddings,self.text,allow_pickle=False)
            del session
        providers = ['DmlExecutionProvider','CPUExecutionProvider'] if 'DmlExecutionProvider' in ort.get_available_providers() else ['CPUExecutionProvider']
        try:
            self.audio = ort.InferenceSession(str(folder/'onnx'/'audio_model.onnx'),sess_options=opts,providers=providers)
        except Exception:
            self.audio = ort.InferenceSession(str(folder/'onnx'/'audio_model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
        self.device = 'DirectML / GPU' if self.audio.get_providers()[0]=='DmlExecutionProvider' else 'CPU'

    def prepare(self, source, binary, duration):
        np = self.np
        offsets = [0.0] if duration<=15 else [min(5.0,duration*.1),max(0.0,duration*.55-5)]
        prepared = []
        for offset in offsets:
            proc = subprocess.run([str(binary),'-hide_banner','-loglevel','error','-nostdin','-threads','1',
                                   '-ss',str(offset),'-i',str(source),'-t','10','-vn','-ac','1','-ar','48000',
                                   '-f','f32le','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode: raise ValueError('音频无法解码')
            audio = np.frombuffer(proc.stdout,dtype='<f4')
            if not len(audio) or not np.isfinite(audio).all(): raise ValueError('音频为空或损坏')
            if float(np.sqrt(np.mean(audio**2))) < .00005:
                continue
            # Match CLAP unfused rand_trunc/repeatpad preprocessing using the
            # official Transformers numpy audio utilities (fusion needs torch).
            audio = audio[:480000]
            if len(audio)<480000:
                audio=np.tile(audio,480000//len(audio))
                audio=np.pad(audio,(0,480000-len(audio)))
            mel=self.extract_features(audio)
            features={'input_features':mel[None,None,:,:].astype(np.float32),'is_longer':np.array([[False]])}
            prepared.append(features['input_features'])
        return {'features':prepared,'duration':duration,'offsets':offsets}

    def extract_features(self, audio):
        np=self.np
        frames=np.lib.stride_tricks.sliding_window_view(np.pad(audio,(512,512),mode='reflect').astype(np.float64),1024)[::480]
        spectrum=np.fft.rfft(frames*self.window,axis=1).astype(np.complex64)
        power=np.abs(spectrum,dtype=np.float64)**2
        return (10*np.log10(np.maximum(1e-10,power @ self.mels))).astype(np.float32)

    def classify(self, source, binary, duration):
        return self.predict([self.prepare(source,binary,duration)])[0]

    def predict(self, records):
        np=self.np
        features=[f for record in records for f in record['features']]
        all_scores=[]
        # Fixed batches avoid repeated DirectML graph compilation for differing shapes.
        for start in range(0,len(features),8):
            batch=features[start:start+8]
            count=len(batch)
            batch=batch+[batch[-1]]*(8-count)
            inputs={'input_features':np.concatenate(batch,axis=0),'is_longer':np.zeros((8,1),dtype=bool)}
            vectors=self.audio.run(None,{x.name:inputs[x.name] for x in self.audio.get_inputs()})[0][:count]
            vectors/=np.linalg.norm(vectors,axis=-1,keepdims=True).clip(1e-8)
            for similarities in vectors @ self.text.T:
                all_scores.append({ident:max(float(similarities[n]) for n,k in enumerate(self.ids) if k==ident) for ident in PROMPTS})
        results=[]
        cursor=0
        for record in records:
            count=len(record['features'])
            scores=all_scores[cursor:cursor+count];cursor+=count
            if record['duration']>45:
                for score in scores:score['logo']=-1.0
            results.append(self.decide(scores,record['duration'],record['offsets']))
        return results

    @staticmethod
    def decide(scores, duration, offsets):
        if not scores:
            return dict(accepted=False, category=None, candidates=[], duration=duration, offsets=offsets, note='片段过于安静，保留待分类')
        mean = {k:sum(s[k] for s in scores)/len(scores) for k in PROMPTS}
        ranked = sorted(mean,key=mean.get,reverse=True)
        best, second = ranked[:2]
        margin = mean[best]-mean[second]
        agreement = len({max(s,key=s.get) for s in scores})==1
        accepted = (best not in {'unknown','sfx-other','music-other'} and mean[best]>=.24 and margin>=.018
                    and (agreement or margin>=.035))
        return dict(accepted=accepted,category=best if accepted else None,
                    candidates=[{'id':k,'similarity':round(mean[k],4)} for k in ranked[:3]],
                    margin=round(margin,4),duration=duration,offsets=offsets,
                    note='片段判断一致' if agreement else '片段风格不同，综合判断')


def run(args):
    data = Path(args.data)
    lock = job_lock(data)
    if lock is None: return
    status = dict(running=True,phase='loading',done=0,accepted=0,uncertain=0,errors=0,total=0,message='正在加载本地音频模型')
    def report(**updates):
        status.update(updates,updated=time.time())
        try:
            atomic_json(data/'audio-analysis-status.json',status)
        except PermissionError:
            # Classification results are already committed to SQLite. A busy progress
            # file must not terminate a multi-hour job; the next report retries it.
            print('Progress file temporarily busy; continuing classification',flush=True)
    try:
        manifest = json.loads(Path(args.job).read_text('utf-8'))
        jobs = manifest['items'] if isinstance(manifest,dict) else manifest
        if isinstance(manifest,dict): status.update(manifest['completed'])
        existing = read_results(data)
        jobs = [j for j in jobs if existing.get(j['id'],{}).get('fingerprint')!=j['fingerprint'] or existing.get(j['id'],{}).get('error')]
        report(total=len(jobs)+status['done'])
        if not jobs: report(running=False,phase='complete',message='待分类音频已全部分析'); return
        model = ContentModel(args.model)
        report(phase='processing',device=model.device,message='正在分析声音内容')
        from media_cache import metadata
        from concurrent.futures import ThreadPoolExecutor
        def prepare_job(job):
            try:
                source=Path(job['path']).resolve()
                if not source.is_relative_to(Path(job['root']).resolve()):raise ValueError('音频已移出素材库')
                stat=source.stat()
                if fingerprint({'size':stat.st_size,'modified':stat.st_mtime})!=job['fingerprint']:raise ValueError('文件已变化，请重新扫描')
                meta=metadata(source,Path(args.ffmpeg),data)
                prepared=model.prepare(source,args.ffmpeg,float(meta.get('duration',0)))
                stat=source.stat()
                if fingerprint({'size':stat.st_size,'modified':stat.st_mtime})!=job['fingerprint']:raise ValueError('分析期间文件已变化')
                return prepared
            except Exception as exc:return {'error':str(exc)}
        with ThreadPoolExecutor(max_workers=3) as pool:
            for start in range(0,len(jobs),8):
                if (data/'audio-analysis.pause').exists():
                    report(running=False,phase='paused',message='已暂停，继续时跳过已完成音频');return
                batch=jobs[start:start+8]
                report(name=batch[0]['name'])
                prepared=list(pool.map(prepare_job,batch))
                valid=[x for x in prepared if 'error' not in x]
                predictions=iter(model.predict(valid)) if valid else iter([])
                for job,ready in zip(batch,prepared):
                    if 'error' in ready:
                        result={'error':ready['error'],'accepted':False}
                        status['errors']+=1
                    else:
                        result=next(predictions)
                        status['accepted' if result['accepted'] else 'uncertain']+=1
                    result.update(model='CLAP',analyzed_at=time.time())
                    store_result(data,job['id'],job['fingerprint'],result)
                    report(done=status['done']+1)
        report(running=False,phase='complete',message='声音内容分析完成')
    except Exception as exc:
        traceback.print_exc()
        report(running=False,phase='failed',message='内容识别失败：'+str(exc))
    finally:
        lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['job','data','model','ffmpeg']: parser.add_argument('--'+name,required=True)
    run(parser.parse_args())
