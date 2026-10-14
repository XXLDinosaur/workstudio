"""Read-only AE library indexing. A package is one card, not one .aep version."""
import hashlib
import os
import re
from pathlib import Path

VIDEO = {'.mp4', '.mov', '.m4v', '.webm', '.avi'}
IMAGE = {'.jpg', '.jpeg', '.png', '.webp'}
PROJECT = {'.aep', '.aepx'}
ARCHIVE = {'.zip', '.rar', '.7z'}
AUDIO = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.wma', '.aif', '.aiff', '.caf'}
MEDIA_VIDEO = VIDEO | {'.mkv', '.wmv', '.mpg', '.mpeg', '.mts', '.m2ts', '.mxf'}
MEDIA_IMAGE = IMAGE | {'.bmp', '.gif', '.tif', '.tiff', '.tga', '.heic', '.avif'}
IGNORE = re.compile(r'auto.?save|自动保存|__MACOSX|\.git', re.I)
ASSETS = re.compile(r'^(?:\(?素材\)?|\(?footage\)?|assets?|textures?|图片|音频|视频素材|贴图|elements?)$', re.I)
PREVIEW = re.compile(r'预览|preview|demo|样机|效果展示|成品', re.I)
COVER = re.compile(r'预览|封面|首图|preview|poster|cover|thumbnail', re.I)
RENDER = re.compile(r'总合成|^合成\s*\d*$|^comp\s*\d*$|导出|输出|成片|render|final|^main$|^综合$|^SPYL$|水印', re.I)
HELP = re.compile(r'help|tutorial|tutor|教程|教学|使用说明', re.I)


def normalized(name):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', name.casefold())


def stable_id(path):
    return hashlib.sha256(str(Path(path).resolve()).casefold().encode()).hexdigest()[:20]


def clean_name(name):
    name = re.sub(r'^(?:包图网|摄图网)[_\s-]*\d+[_\s-]*', '', name)
    name = re.sub(r'^AE模板\s*[-_—]\s*', '', name, flags=re.I)
    return name or '未命名模板'


def media_score(path, base, kind):
    rel = path.relative_to(base)
    internal = any(ASSETS.fullmatch(p) for p in rel.parts[:-1])
    # Even a file named preview inside Footage is an input, not a package preview.
    if internal or any(HELP.search(p) for p in rel.parts):
        return -1
    name = path.stem
    explicit = PREVIEW.search(name) if kind == 'video' else COVER.search(name)
    if explicit:
        return 120 - len(rel.parts)
    if kind == 'video' and RENDER.search(name):
        return 80 - len(rel.parts)
    if kind == 'video' and path.suffix.lower() in {'.mp4', '.m4v', '.webm'}:
        stem = normalized(name)
        package = normalized(base.name)
        parent = normalized(path.parent.name)
        if len(stem) >= 5 and (stem in package or stem in parent):
            return 60 - len(rel.parts)
    return -1


def inspect_package(base, category, files=None, warnings=None):
    warnings = warnings if warnings is not None else []
    if files is None:
        files = []
        def walk_error(error):
            warnings.append(str(error))
        for parent, dirs, names in os.walk(base, followlinks=False, onerror=walk_error):
            dirs[:] = [d for d in dirs if not IGNORE.search(d) and not (Path(parent)/d).is_symlink() and not (Path(parent)/d).is_junction()]
            files.extend(Path(parent)/n for n in names if not IGNORE.search(n))
    projects, videos, images, archives, possible = [], [], [], [], []
    total, modified = 0, 0
    for path in files:
        try:
            stat = path.stat()
            total += stat.st_size
            modified = max(modified, stat.st_mtime)
        except OSError as exc:
            warnings.append(str(exc))
            continue
        ext = path.suffix.lower()
        if ext in PROJECT:
            projects.append(path)
        elif ext in ARCHIVE:
            archives.append(path)
        elif ext in VIDEO:
            score = media_score(path, base, 'video')
            if score >= 0:
                videos.append((score, path))
            elif ext == '.mp4' and len(path.relative_to(base).parts) <= 2:
                rel = path.relative_to(base)
                if not any(ASSETS.fullmatch(p) or HELP.search(p) for p in rel.parts[:-1]) and not HELP.search(path.stem):
                    possible.append(path)
        elif ext in IMAGE:
            score = media_score(path, base, 'image')
            if score >= 0:
                images.append((score, path))
    # Keep a small number of plausible adjacent MP4s visibly marked as candidates.
    # Never silently represent an arbitrary source clip as the final composition.
    if not videos and len(possible) <= 3:
        videos.extend((10, p) for p in possible if p.parent == base or any(q.parent == p.parent for q in projects))
    # Main files come before compatibility copies. Never include autosaves.
    projects.sort(key=lambda p: (bool(re.search(r'副本|copy|转换|backup', p.stem, re.I)), len(p.parts), p.name.casefold()))
    videos.sort(key=lambda pair: (-pair[0], pair[1].suffix.lower() != '.mp4', str(pair[1])))
    images.sort(key=lambda pair: (-pair[0], str(pair[1])))
    if not (projects or videos or images or archives):
        return None
    return dict(id=stable_id(base), name=clean_name(base.name), original_name=base.name,
                category=category, folder=str(base), projects=[str(p) for p in projects],
                videos=[str(p) for _, p in videos], images=[str(p) for _, p in images],
                video_confidence=['candidate' if score < 40 else 'matched' if score < 80 else 'explicit' for score, _ in videos],
                archives=[str(p) for p in archives], size=total, modified=modified)


def scan_library(root, progress=lambda count, name: None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('模板库路径不存在或磁盘未连接：' + str(root))
    items, categories, warnings = [], [], []
    for category in sorted(root.iterdir(), key=lambda p: p.name):
        if not category.is_dir() or category.is_symlink() or category.is_junction() or category.name.startswith('.'):
            continue
        categories.append(category.name)
        try:
            entries = list(category.iterdir())
        except OSError as exc:
            warnings.append(str(exc))
            continue
        packages = [p for p in entries if p.is_dir() and not p.is_symlink() and not p.is_junction() and not IGNORE.search(p.name)]
        folder_names = {p.name.casefold() for p in packages}
        for base in sorted(packages):
            item = inspect_package(base, category.name, warnings=warnings)
            if item:
                items.append(item)
            progress(len(items), base.name)
        # An archive alongside its extracted directory is one package, not two.
        for path in entries:
            if path.is_file() and path.suffix.lower() in ARCHIVE and path.stem.casefold() not in folder_names:
                stat = path.stat()
                items.append(dict(id=stable_id(path), name=clean_name(path.stem), original_name=path.name,
                                  category=category.name, folder=str(category), projects=[], videos=[], images=[],
                                  archives=[str(path)], size=stat.st_size, modified=stat.st_mtime))
        loose = [p for p in entries if p.is_file() and p.suffix.lower() in PROJECT]
        if loose:
            item = inspect_package(category, category.name, [p for p in entries if p.is_file() and p.suffix.lower() not in ARCHIVE], warnings)
            if item:
                items.append(item)
    # Also support an unclassified package placed directly in the library root.
    root_files = [p for p in root.iterdir() if p.is_file()]
    if any(p.suffix.lower() in PROJECT | ARCHIVE | VIDEO for p in root_files):
        item = inspect_package(root, '未分类', root_files, warnings)
        if item:
            categories.append('未分类')
            items.append(item)
    return dict(root=str(root), items=items, categories=categories, warnings=warnings)


def scan_source(source, progress=lambda count, name: None):
    """Scan an independent root without opening or decoding media content."""
    root = Path(source['path']).resolve()
    if not root.is_dir():
        raise OSError('目录不存在或磁盘未连接：' + str(root))
    if source['kind'] == 'template':
        result = scan_library(root, progress)
        for item in result['items']:
            item.update(media_type='template', audios=[], source_id=source['id'], source_name=source['name'], root_path=str(root))
        return result
    items, warnings = [], []
    kinds = {'video': MEDIA_VIDEO, 'audio': AUDIO, 'image': MEDIA_IMAGE}
    allowed = kinds.get(source['kind'], MEDIA_VIDEO | AUDIO | MEDIA_IMAGE)
    def walk_error(error):
        warnings.append(str(error))
    for parent, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not IGNORE.search(d) and not (Path(parent)/d).is_symlink() and not (Path(parent)/d).is_junction()]
        for name in names:
            path = Path(parent)/name
            ext = path.suffix.lower()
            if ext not in allowed or name.startswith('.') or path.is_symlink():
                continue
            try:
                stat = path.stat()
            except OSError as exc:
                warnings.append(str(exc))
                continue
            kind = next(k for k, extensions in kinds.items() if ext in extensions)
            rel = path.relative_to(root)
            item = dict(id=stable_id(path), media_type=kind, name=clean_name(path.stem), original_name=name,
                        category=rel.parts[0] if len(rel.parts) > 1 else '未分类', relative_path=str(rel),
                        folder=str(path.parent), root_path=str(root), source_id=source['id'], source_name=source['name'],
                        projects=[], archives=[], images=[], videos=[], audios=[], video_confidence=[],
                        size=stat.st_size, modified=stat.st_mtime, extension=ext.lstrip('.').upper())
            item[{'video':'videos', 'audio':'audios', 'image':'images'}[kind]] = [str(path)]
            items.append(item)
            if len(items) % 100 == 0:
                progress(len(items), name)
    progress(len(items), root.name)
    return dict(items=items, warnings=warnings, categories=sorted({i['category'] for i in items}))
