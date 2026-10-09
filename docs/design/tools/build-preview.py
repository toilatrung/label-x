#!/usr/bin/env python3
"""Build a portable preview directly from the canonical DC sources (stdlib only)."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
screens = root / 'screens'
sources = {p.name.removesuffix('.dc.html'): p.read_text() for p in sorted(screens.glob('*.dc.html'))}
# Inline only the supplied reference symbols; raster source crops remain shared assets.
icons = (screens / 'assets/icons.svg').read_text().replace('<svg xmlns="http://www.w3.org/2000/svg">', '<svg width="0" height="0" style="position:absolute" aria-hidden="true">')
for name in sources:
    sources[name] = sources[name].replace('assets/icons.svg#', '#')
registry = json.dumps(sources, ensure_ascii=False).replace('</', '<\\/')
output = f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LabelX Design Preview</title><link rel="stylesheet" href="ds/labelx/tokens.css"><link rel="stylesheet" href="ds/labelx/components/bundle.css">
<style>body{{margin:0;background:var(--canvas)}}x-dc,dc-import{{display:block}}</style>
<script>window.LabelXDesignSources={registry};</script>
<script src="review-data.js"></script><script src="support.js"></script></head>
<body>{icons}<x-dc></x-dc></body></html>
'''
(screens / 'preview.html').write_text(output)
print(f'Built preview.html from {len(sources)} canonical screens/components.')
