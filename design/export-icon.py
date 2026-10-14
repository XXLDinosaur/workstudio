"""Export the SVG renderer's 1024 px master as a multi-resolution Windows icon."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
with Image.open(ROOT / 'design' / 'workstudio-icon.png') as image:
    image.save(ROOT / 'workstudio.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
