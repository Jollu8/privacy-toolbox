"""Stage only public assets for GitHub Pages; no bundling or dependencies."""
from pathlib import Path
import shutil
from generate_pages import generate

generate()

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / '_site'
if DEST.exists():
    shutil.rmtree(DEST)
DEST.mkdir()
for name in ['index.html', '.nojekyll', 'about', 'tools', 'assets', 'python']:
    source = ROOT / name
    if source.is_dir():
        shutil.copytree(source, DEST / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        shutil.copy2(source, DEST / name)
print('Static site staged in _site/')
