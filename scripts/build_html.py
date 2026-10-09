"""
Rebuild index.html by injecting fresh tile data from data/tiles.json
into scripts/template.html.
"""
import json
import os

ROOT     = os.path.join(os.path.dirname(__file__), '..')
DATA     = os.path.join(ROOT, 'data', 'tiles.json')
TEMPLATE = os.path.join(ROOT, 'scripts', 'template.html')
OUTPUT   = os.path.join(ROOT, 'index.html')

with open(DATA) as f:
    tiles = json.load(f)

with open(TEMPLATE) as f:
    html = f.read()

tiles_str = json.dumps(tiles)
html = html.replace('__TILES_JSON__', tiles_str)

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Built index.html ({len(html)//1024} KB)')
