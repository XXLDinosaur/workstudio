"""Install pinned public ONNX weights. No user audio is sent to the network."""
import hashlib
import json
import urllib.request
from pathlib import Path

REVISION = 'c28f2883575e590e04d3146ff0713c2448d691ba'
REPO = 'Xenova/clap-htsat-unfused'
FILES = ['config.json', 'preprocessor_config.json', 'tokenizer.json', 'tokenizer_config.json',
         'special_tokens_map.json', 'vocab.json', 'merges.txt', 'onnx/audio_model.onnx',
         'onnx/text_model_quantized.onnx']


def install(folder):
    folder = Path(folder)
    manifest = {'repository':REPO, 'revision':REVISION, 'files':{}}
    for name in FILES:
        dest = folder/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            temp = dest.with_suffix(dest.suffix+'.download')
            print('Downloading '+name, flush=True)
            with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}', timeout=120) as src, temp.open('wb') as out:
                while chunk := src.read(1024*1024): out.write(chunk)
            temp.replace(dest)
        manifest['files'][name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
    print('Model ready: '+str(folder), flush=True)


if __name__ == '__main__':
    install(Path(__file__).parent/'models'/'clap')
