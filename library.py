"""Multi-root catalog, migration, paged search and user state."""
import json
import os
import secrets
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

from catalog import scan_source, stable_id
from audio_categories import CATEGORIES, BY_ID, classify, effective
from audio_analysis import read_results, fingerprint

DATA = Path(os.environ.get('AE_STUDIO_DATA', str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AEStudio')))
DEFAULT_ROOT = str(Path.home() / 'Videos')


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


def source_record(path, kind='media', name=None):
    path = Path(path).resolve()
    if kind not in {'template', 'video', 'audio', 'image', 'media'}:
        raise ValueError('未知素材库类型')
    return dict(id=stable_id(path), path=str(path), kind=kind, name=str(name or path.name)[:80])


class ScanCancelled(Exception):
    pass


class Library:
    def __init__(self, data=DATA):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.config = read_json(self.data/'config.json', {'version': 2, 'sources': []})
        if 'sources' not in self.config:
            self.config['sources'] = [source_record(self.config.get('root', DEFAULT_ROOT), 'template', 'AE 模板')]
        self.state = read_json(self.data/'state.json', {})
        for key, value in {'favorites': [], 'recent': [], 'collections': {}, 'overrides': {}, 'audio_categories': {}}.items():
            self.state.setdefault(key, value)
        self.index = read_json(self.data/'index.json', {'root':self.config.get('root', DEFAULT_ROOT), 'items':[], 'categories':[], 'warnings':[]})
        self.status = {'scanning':False, 'count':0, 'name':'', 'error':'', 'revision':0}
        self.cancel = threading.Event()
        self.token = secrets.token_urlsafe(32)
        self.window = None
        self._indexed_object = None
        self._content_results = read_results(self.data)
        self._content_refresh = 0
        self._prepare()

    def _prepare(self):
        if self._indexed_object is self.index:
            return
        legacy_root = self.index.get('root', self.config.get('root', DEFAULT_ROOT))
        source_id = stable_id(legacy_root)
        self._by_id = {}
        self._search = {}
        self._audio_auto = {}
        for item in self.index['items']:
            item.setdefault('media_type', 'template')
            item.setdefault('audios', [])
            item.setdefault('source_id', source_id)
            item.setdefault('source_name', 'AE 模板')
            item.setdefault('root_path', legacy_root)
            self._by_id[item['id']] = item
            if item['media_type'] == 'audio':
                self._audio_auto[item['id']] = classify(item)
                self._apply_audio(item)
            self._update_search(item)
        self._ordered = {
            'name': sorted(self.index['items'], key=lambda x:x['name'].casefold()),
            'recent': sorted(self.index['items'], key=lambda x:x['modified'], reverse=True),
            'size': sorted(self.index['items'], key=lambda x:x['size'], reverse=True),
        }
        self._indexed_object = self.index

    def _apply_audio(self, item):
        automatic = self._audio_auto[item['id']]
        result = self._content_results.get(item['id'])
        item.pop('audio_analysis',None)
        item.pop('audio_duration',None)
        if result and result.get('fingerprint')==fingerprint(item):
            item['audio_analysis'] = result
            if result.get('duration'): item['audio_duration'] = result['duration']
            if automatic['group']=='待分类' and result.get('accepted') and result.get('category') in BY_ID:
                automatic = {**BY_ID[result['category']], 'method':'content',
                             'evidence':'本地 CLAP 根据声音片段识别 · '+result.get('note','')}
        item['audio_classification'] = effective(automatic,self.state['audio_categories'].get(item['id']))

    def refresh_audio_results(self, force=False):
        with self.lock:
            if not force and time.monotonic()-self._content_refresh<5: return
            self._content_refresh = time.monotonic()
            results = read_results(self.data)
            changed = [ident for ident,value in results.items() if self._content_results.get(ident)!=value]
            self._content_results = results
            for ident in changed:
                item = self._by_id.get(ident)
                if item and item['media_type']=='audio': self._apply_audio(item);self._update_search(item)
            if changed: self.status['audio_revision']=self.status.get('audio_revision',0)+1

    def _update_search(self, item):
        classification = item.get('audio_classification', {})
        self._search[item['id']] = (' '.join(str(item.get(k, '')) for k in ('name', 'original_name', 'category', 'relative_path', 'source_name', 'folder'))
                                   + ' ' + classification.get('group', '') + ' ' + classification.get('name', '')).casefold()

    def summary(self):
        with self.lock:
            self._prepare()
            counts = Counter(x['media_type'] for x in self.index['items'])
            roots = []
            for source in self.config['sources']:
                indexed = next((s for s in self.index.get('sources',[]) if s['id']==source['id']), {})
                roots.append({**source, 'offline':indexed.get('offline',False), 'count':sum(x['source_id']==source['id'] for x in self.index['items'])})
            return dict(total=len(self.index['items']), counts=counts, sources=roots,
                        size=sum(x['size'] for x in self.index['items']), warnings=self.index.get('warnings',[])[:200],
                        scanned_at=self.index.get('scanned_at'), favorites=sum(i in self._by_id for i in self.state['favorites']),
                        audio_categories=CATEGORIES)

    def query(self, params):
        with self.lock:
            self._prepare()
            get = lambda key, default='': str(params.get(key, default))
            kind, source, category = get('type'), get('source'), get('category')
            terms = get('q').casefold().split()
            view, preview = get('view'), get('preview')
            recent = {ident:n for n,ident in enumerate(self.state['recent'])}
            favorite = set(self.state['favorites'])
            members = set(self.state['collections'].get(get('collection'), [])) if get('collection') else None
            items = self._ordered.get(get('sort','name'), self._ordered['name'])
            scoped = [i for i in items if (not kind or i['media_type']==kind) and (not source or i['source_id']==source)]
            smart = kind == 'audio' and get('grouping') == 'smart'
            category_key = lambda i: i['audio_classification']['id'] if smart else i['category']
            categories = Counter(category_key(i) for i in scoped)
            result = []
            for item in scoped:
                if category and category_key(item) != category: continue
                if get('audio_review')=='1':
                    analysis_result=item.get('audio_analysis',{})
                    if not analysis_result or analysis_result.get('accepted') or analysis_result.get('error') or item['audio_classification']['method']=='manual': continue
                if view == 'favorites' and item['id'] not in favorite: continue
                if view == 'recent' and item['id'] not in recent: continue
                if members is not None and item['id'] not in members: continue
                if terms and not all(t in self._search[item['id']] for t in terms): continue
                if preview == 'missing' and (item['videos'] or item['images'] or item['audios']): continue
                if preview == 'video' and not item['videos']: continue
                if preview == 'image' and (item['videos'] or not item['images']): continue
                if preview == 'archive' and (item['projects'] or not item['archives']): continue
                result.append(item)
            if view == 'recent': result.sort(key=lambda i:recent[i['id']])
            limit = max(1,min(120,int(get('limit','48'))))
            offset = max(0,int(get('offset','0')))
            return dict(items=result[offset:offset+limit], total=len(result), offset=offset, limit=limit,
                        categories=([{**c,'count':categories[c['id']]} for c in CATEGORIES if categories[c['id']]] if smart else
                                    [{'name':n,'count':c} for n,c in sorted(categories.items())]))

    def scan(self, root=None, sources=None):
        with self.lock:
            if self.status['scanning']:
                raise ValueError('正在扫描，请等待完成或先取消')
            if sources is None:
                sources = [source_record(root,'template','AE 模板')] if root else self.config['sources']
            if not isinstance(sources,list) or not sources or len(sources)>50:
                raise ValueError('请至少保留一个素材库，最多支持 50 个')
            records = [source_record(s['path'],s['kind'],s.get('name')) for s in sources]
            if len({s['id'] for s in records}) != len(records):
                raise ValueError('同一个文件夹不能重复添加')
            old_ids = {s['id'] for s in self.config['sources']}
            for source in records:
                if source['id'] not in old_ids and not Path(source['path']).is_dir():
                    raise ValueError('路径不存在：'+source['path'])
            # Legacy API callers expect an invalid replacement root to fail immediately.
            if root and not Path(root).is_dir():
                raise ValueError('路径不存在，请确认磁盘已连接')
            self.cancel.clear()
            self.status.update(scanning=True,count=0,name='',error='')
        def work():
            try:
                items, warnings, seen = [], [], set()
                for source in records:
                    base_count = len(items)
                    def progress(count,name):
                        if self.cancel.is_set(): raise ScanCancelled()
                        with self.lock:
                            self.status.update(count=base_count+count,name=source['name']+' / '+name)
                    progress(0,'扫描中')
                    try:
                        result = scan_source(source, progress)
                        source['offline'] = False
                        warnings.extend(result['warnings'])
                    except (OSError, ValueError) as exc:
                        # A disconnected disk must not erase the cached catalog or favorites.
                        source['offline'] = True
                        warnings.append(str(exc))
                        result = {'items':[i for i in self.index['items'] if i['source_id']==source['id']]}
                    for item in result['items']:
                        if item['id'] not in seen:
                            seen.add(item['id']); items.append(item)
                if self.cancel.is_set(): raise ScanCancelled()
                index = dict(version=2, sources=records, items=items, warnings=warnings, scanned_at=time.time())
                config = {'version':2,'sources':[{k:v for k,v in s.items() if k!='offline'} for s in records]}
                with self.lock:
                    write_json(self.data/'index.json', index)
                    write_json(self.data/'config.json', config)
                    self.index, self.config = index, config
                    self._prepare()
                    self.status['revision'] += 1
                    self.status['count'] = len(items)
            except ScanCancelled:
                with self.lock: self.status['error']='扫描已取消，保留上次索引'
            except Exception as exc:
                with self.lock: self.status['error']=str(exc)
            finally:
                with self.lock: self.status['scanning']=False
        threading.Thread(target=work,daemon=True).start()
        return {'ok':True}

    def item(self, ident):
        self._prepare()
        item = self._by_id.get(ident)
        if item is None: raise ValueError('素材不在当前索引中，请重新扫描')
        return item

    def file(self, ident, kind, number=0):
        if kind not in {'videos','images','audios','projects','archives'}:
            raise ValueError('不支持的文件类型')
        item = self.item(ident)
        if number<0 or number>=len(item[kind]): raise ValueError('文件编号不存在')
        path = Path(item[kind][number]).resolve()
        if not path.is_relative_to(Path(item['root_path']).resolve()): raise ValueError('文件已移出素材库')
        if not path.is_file(): raise ValueError('素材文件不存在或磁盘未连接')
        return path

    def save_state(self):
        write_json(self.data/'state.json',self.state)

    def action(self, body):
        op = body.get('op')
        with self.lock:
            if op=='favorite':
                ident=self.item(body['id'])['id']; favorites=self.state['favorites']
                favorites.remove(ident) if ident in favorites else favorites.append(ident)
            elif op=='recent':
                ident=self.item(body['id'])['id']
                self.state['recent']=[ident]+[i for i in self.state['recent'] if i!=ident][:99]
            elif op=='collection-create':
                name=str(body.get('name','')).strip()[:60]
                if not name or name in self.state['collections']: raise ValueError('集合名称为空或已存在')
                self.state['collections'][name]=[]
            elif op=='collection-toggle':
                ident=self.item(body['id'])['id']; members=self.state['collections'].get(body.get('name'))
                if members is None: raise ValueError('集合不存在')
                members.remove(ident) if ident in members else members.append(ident)
            elif op=='collection-delete':
                self.state['collections'].pop(body.get('name'),None)
            elif op=='preview-select':
                ident,number=body['id'],int(body['number']); self.file(ident,'videos',number)
                self.state['overrides'][ident]=number
            elif op=='audio-category':
                item = self.item(body['id'])
                if item['media_type'] != 'audio': raise ValueError('仅音频支持音频分类')
                chosen = body.get('category')
                if chosen is not None and chosen not in BY_ID: raise ValueError('未知音频分类')
                if chosen is None: self.state['audio_categories'].pop(item['id'], None)
                else: self.state['audio_categories'][item['id']] = chosen
                self._apply_audio(item)
                self._update_search(item)
            elif op=='open':
                path=self.file(body['id'],body.get('kind','projects'),int(body.get('number',0)))
                os.startfile(str(path)); return {'ok':True}
            elif op=='folder':
                item=self.item(body['id']); path=Path(item['folder']).resolve()
                if not path.is_relative_to(Path(item['root_path']).resolve()) or not path.is_dir(): raise ValueError('素材文件夹不存在或已移出素材库')
                if item['media_type']!='template':
                    kind={'video':'videos','audio':'audios','image':'images'}[item['media_type']]
                    path=self.file(item['id'],kind)
                    subprocess.Popen(['explorer.exe','/select,',str(path)])
                else: subprocess.Popen(['explorer.exe',str(path)])
                return {'ok':True}
            else: raise ValueError('未知操作')
            self.save_state()
            return {'ok':True,'state':self.state}
