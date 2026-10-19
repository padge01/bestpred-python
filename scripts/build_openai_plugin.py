"""Build the ZIP for OpenAI's plugin directory (ChatGPT and Codex): openai/plugin.json and mcp.json, the skill from the
Claude plugin, and the icon as assets. Writes dist/bestpred-openai-<version>.zip."""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'openai'
SKILLS = ROOT / 'plugins' / 'bestpred' / 'skills'
ICON = ROOT / 'plugins' / 'bestpred' / '.claude-plugin' / 'icon.png'
ASSETS = ['icon.png', 'icon-dark.png', 'logo.png', 'logo-dark.png']

version = json.loads((SRC / 'plugin.json').read_text(encoding='utf-8'))['version']
out = ROOT / 'dist' / f'bestpred-openai-{version}.zip'
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in ('plugin.json', 'mcp.json'):
        z.write(SRC / name, name)
    for f in sorted(SKILLS.rglob('*')):
        if f.is_file():
            z.write(f, 'skills/' + f.relative_to(SKILLS).as_posix())
    for name in ASSETS:
        z.write(ICON, 'assets/' + name)
    shot = SRC / 'screenshot.png'
    if shot.exists():
        z.write(shot, 'assets/screenshot.png')
print(out)
