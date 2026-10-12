"""Create separate public-upload and source archives without credentials/runtime data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
with ZipFile(root.parent / 'internet-of-light-pages.zip', 'w', ZIP_DEFLATED) as archive:
    for file in sorted((root / 'public').rglob('*')):
        if file.is_file(): archive.write(file, file.relative_to(root / 'public').as_posix())

allowed_dirs = {'public', 'relay', 'agent', 'tests'}
allowed_root = {'.gitignore', 'README.md', 'HOSTING.md', 'VALIDATION.md', 'package.json', 'preview.mjs', 'launch-preview.cmd', 'package_site.py'}
files = []
for file in sorted(root.rglob('*')):
    if not file.is_file(): continue
    relative = file.relative_to(root)
    if any(part in {'__pycache__', 'node_modules', '.wrangler', '.venv', 'browser-results'} for part in relative.parts): continue
    if len(relative.parts) == 1 and file.name in allowed_root: files.append(file)
    elif relative.parts[0] in allowed_dirs and file.suffix in {'.py', '.js', '.mjs', '.html', '.css', '.svg', '.png', '.toml', '.txt'}:
        files.append(file)
with ZipFile(root.parent / 'internet-of-light-source.zip', 'w', ZIP_DEFLATED) as archive:
    for file in files: archive.write(file, file.relative_to(root.parent).as_posix())
print('Created public upload and source archives; source folder structure preserved.')
