"""Draw the lab diagrams as standalone SVG files in images/. Run: python3 diagrams.py"""
import re
from pathlib import Path
from svgkit import *

PATH, RATE = '#1f6a5a', '#a83535'
out = {}

def standalone(fig):
    svg = re.search(r'<svg.*?</svg>', fig, re.S).group(0)
    w, h = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups()
    svg = svg.replace('<svg ', f'<svg width="{w}" height="{h}" font-family="Poppins, Segoe UI, Helvetica, Arial, sans-serif" ', 1)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + re.sub(r'(</defs>)', r'\1' + f'<rect width="{w}" height="{h}" rx="10" fill="#ffffff"/>', svg, count=1)

# ---------------------------------------------------------------- phase A: eBGP fabric
b = ''
b += box(270, 20, 160, 44, 'spine1', 'AS 65000', GRAY, 1.4)
b += box(40, 150, 140, 44, 'leaf1', 'AS 65011', TEAL) + box(40, 250, 140, 40, 'h1', '10.20.1.10', AMBER)
b += box(320, 150, 140, 44, 'border1', 'AS 65021', TEAL) + box(520, 150, 140, 44, 'border2', 'AS 65022', TEAL)
b += box(420, 250, 140, 44, 'dcgw', 'AS 65099', GRAY) + box(420, 330, 140, 40, 'h2', '10.99.0.0/24', AMBER)
b += line(110, 150, 300, 64) + line(390, 150, 340, 64) + line(590, 150, 400, 64)
b += line(390, 194, 470, 250) + line(590, 194, 510, 250) + line(110, 194, 110, 250) + line(490, 294, 490, 330)
b += text(560, 84, 'spine1 learns two paths:', 10.5, PATH, 'start')
b += text(560, 99, '65021 65099 via border1', 10, '#1d2a2f', 'start') + text(560, 113, '65022 65099 via border2', 10, '#1d2a2f', 'start')
b += text(40, 92, 'leaf1 receives next hop', 10.5, RATE, 'start') + text(40, 107, '10.0.1.1 (spine1) for every', 10.5, RATE, 'start') + text(40, 122, 'path, with or without ADD-PATH', 10.5, RATE, 'start')
b += text(350, 395, 'eBGP rewrites the next hop at every hop, so the spine, not the leaf, decides how traffic is split.', 10.5, '#1d2a2f')
out['phase-a-ebgp'] = svg(700, 408, b, 'pa') + cap('A', 'Phase A: an eBGP fabric.')

# ---------------------------------------------------------------- phase B: off-path route reflector
b = ''
b += box(40, 160, 140, 44, 'leaf1', 'AS 65000', TEAL, 1.4) + box(40, 270, 140, 40, 'h1', '10.20.1.10', AMBER)
b += box(300, 70, 140, 44, 'border1', '10.255.0.21', TEAL) + box(300, 250, 140, 44, 'border2', '10.255.0.22', TEAL)
b += box(530, 160, 140, 44, 'dcgw', 'AS 65099', GRAY) + box(530, 270, 140, 40, 'h2', '10.99.0.0/24', AMBER)
b += box(40, 30, 140, 44, 'rr1', 'route reflector', WHITE, 1.2, True)
b += line(180, 175, 300, 92, PATH, 2.2) + text(228, 120, 'eth1', 10, PATH)
b += line(180, 190, 300, 272, PATH, 2.2) + text(228, 248, 'eth2', 10, PATH)
b += line(110, 74, 110, 160) + text(122, 120, 'eth3', 10, '#5b6b70', 'start')
b += line(440, 92, 560, 160) + line(440, 272, 560, 204) + line(110, 204, 110, 270) + line(600, 204, 600, 270)
b += text(194, 46, 'iBGP to leaf1, border1, border2', 10, '#b36a12', 'start') + text(194, 60, 'off the forwarding path', 10, '#b36a12', 'start')
b += text(350, 345, 'Next hops are preserved: leaf1 can only use both links if it learns both paths.', 10.5, '#1d2a2f')
out['phase-b-ibgp-rr'] = svg(700, 358, b, 'pb') + cap('B', 'Phase B: iBGP with an off-path route reflector.')

d = Path(__file__).parent / 'images'
for name, fig in out.items():
    (d / f'{name}.svg').write_text(standalone(fig))
print(sorted(out))
