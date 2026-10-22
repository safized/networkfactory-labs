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

# ---------------------------------------------------------------- phase B: off-path route reflector, two gateway ASes
INK, MUTED = '#1d2a2f', '#5b6b70'
b = ''
b += box(30, 30, 130, 44, 'rr1', 'route reflector', WHITE, 1.2, True)
b += box(30, 170, 130, 44, 'leaf1', 'AS 65000', TEAL, 1.4) + box(30, 290, 130, 40, 'h1', '10.20.1.10', AMBER)
b += box(235, 80, 120, 44, 'border1', '10.255.0.21', TEAL) + box(235, 260, 120, 44, 'border2', '10.255.0.22', TEAL)
b += box(405, 80, 120, 44, 'dcgw1', 'AS 65098', GRAY) + box(405, 260, 120, 44, 'dcgw2', 'AS 65099', GRAY)
b += box(570, 170, 110, 44, 'wan', 'AS 65100', GRAY) + box(570, 290, 110, 40, 'h2', '10.99.0.0/24', AMBER)
b += line(160, 184, 235, 102, PATH, 2.2) + text(186, 130, 'eth1', 10, PATH)
b += line(160, 200, 235, 282, PATH, 2.2) + text(186, 262, 'eth2', 10, PATH)
b += line(95, 74, 95, 170) + text(105, 126, 'eth3', 10, MUTED, 'start')
b += line(355, 102, 405, 102) + line(355, 282, 405, 282) + line(525, 102, 600, 170) + line(525, 282, 600, 214)
b += line(95, 214, 95, 290) + line(625, 214, 625, 290)
b += text(172, 46, 'iBGP to leaf1, border1, border2,', 10, '#b36a12', 'start') + text(172, 60, 'off the forwarding path', 10, '#b36a12', 'start')
b += text(465, 170, 'two exits, two AS paths:', 10.5, PATH) + text(465, 186, '65098 65100', 10, INK) + text(465, 200, '65099 65100', 10, INK)
b += text(355, 365, 'Next hops are preserved: leaf1 can use both links only if it learns both paths, and accepts different AS paths.', 10.5, INK)
out['phase-b-ibgp-rr'] = svg(700, 378, b, 'pb') + cap('B', 'Phase B: iBGP with an off-path route reflector.')

# ---------------------------------------------------------------- the 2x2 result grid (measured)
def cell(x, y, title, paths, hops, share, note, win=False):
    w, h = 300, 128
    c = TEAL if win else GRAY
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{c[0]}" stroke="{c[1]}" stroke-width="{1.6 if win else 1}"/>'
    s += text(x + 14, y + 22, title, 11.5, INK, 'start')
    s += text(x + 14, y + 42, f'paths leaf1 knows: {paths}    kernel next hops: {hops}', 10, MUTED, 'start')
    bw = w - 28; e1 = bw * share / 100
    s += f'<rect x="{x + 14}" y="{y + 56}" width="{e1}" height="22" fill="{PATH}"/>'
    if share < 100:
        s += f'<rect x="{x + 14 + e1}" y="{y + 56}" width="{bw - e1}" height="22" fill="#4f9d8a"/>'
    s += f'<rect x="{x + 14}" y="{y + 56}" width="{bw}" height="22" fill="none" stroke="{c[1]}"/>'
    s += text(x + 14 + e1 / 2, y + 71, f'eth1 {share}%', 10, '#ffffff')
    if share < 100:
        s += text(x + 14 + e1 + (bw - e1) / 2, y + 71, f'eth2 {100 - share}%', 10, '#ffffff')
    else:
        s += text(x + w - 18, y + 71, 'eth2 0%', 10, '#ffffff', 'end')
    s += text(x + 14, y + 100, note, 10.5, PATH if win else RATE, 'start')
    return s
b = text(255, 22, 'multipath-relax off', 11.5, MUTED) + text(565, 22, 'multipath-relax on', 11.5, MUTED)
b += f'<text x="34" y="105" font-size="11.5" fill="{MUTED}" text-anchor="middle" transform="rotate(-90 34 105)">ADD-PATH off</text>'
b += f'<text x="34" y="245" font-size="11.5" fill="{MUTED}" text-anchor="middle" transform="rotate(-90 34 245)">ADD-PATH on</text>'
b += cell(105, 40, 'Neither knob', 1, 1, 100, 'The reflector hides border2.')
b += cell(415, 40, 'multipath-relax only', 1, 1, 100, 'Nothing to balance: one path known.')
b += cell(105, 180, 'ADD-PATH only', 2, 1, 100, 'Both paths seen, AS paths differ.')
b += cell(415, 180, 'Both', 2, 2, 38, 'Both links carry traffic.', True)
b += text(410, 336, 'Measured with eight iperf3 streams, about 60 Gb/s, share of bytes leaving leaf1 per link.', 10.5, INK)
out['grid-2x2'] = svg(730, 348, b, 'gr') + cap('C', 'Each knob alone changes nothing; together they use both exits.')

# ---------------------------------------------------------------- what ADD-PATH changes in the UPDATE
def field(x, y, w, label, val, c):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="40" fill="{c[0]}" stroke="{c[1]}"/>'
            + text(x + w / 2, y + 16, label, 9.5, MUTED) + text(x + w / 2, y + 32, val, 11.5, INK))
b = text(20, 28, 'Without ADD-PATH: one path per prefix. A new announcement replaces the old one.', 11, INK, 'start')
b += field(20, 40, 230, 'path attributes', 'AS_PATH 65098 65100, NEXT_HOP .21', GRAY) + field(250, 40, 70, 'length', '24', WHITE) + field(320, 40, 110, 'prefix', '10.99.0.0', WHITE)
b += text(20, 118, 'With ADD-PATH: each path carries a 4-byte Path ID, so a second path is added, not replaced.', 11, INK, 'start')
b += field(20, 130, 230, 'path attributes', 'AS_PATH 65098 65100, NEXT_HOP .21', GRAY) + field(250, 130, 90, 'Path ID', '3', AMBER) + field(340, 130, 70, 'length', '24', WHITE) + field(410, 130, 110, 'prefix', '10.99.0.0', WHITE)
b += field(20, 180, 230, 'path attributes', 'AS_PATH 65099 65100, NEXT_HOP .22', GRAY) + field(250, 180, 90, 'Path ID', '4', AMBER) + field(340, 180, 70, 'length', '24', WHITE) + field(410, 180, 110, 'prefix', '10.99.0.0', WHITE)
b += text(540, 150, 'Path IDs are local to', 10.5, '#b36a12', 'start') + text(540, 165, 'one session. Both sides', 10.5, '#b36a12', 'start') + text(540, 180, 'agree in the OPEN', 10.5, '#b36a12', 'start') + text(540, 195, '(capability 69).', 10.5, '#b36a12', 'start')
b += text(350, 248, 'Values from the lab capture b2-rr-with-addpath.pcap, rr1 to leaf1.', 10.5, MUTED)
out['update-anatomy'] = svg(700, 260, b, 'ua') + cap('D', 'What ADD-PATH adds to an UPDATE.')

# ---------------------------------------------------------------- the failover micro-loop, from the capture
b = box(30, 40, 120, 44, 'leaf1', 'still sends to border1', TEAL) + box(290, 40, 120, 44, 'border1', 'gateway link down', RED) + box(290, 140, 120, 44, 'border2', 'healthy exit', TEAL)
b += path('M150 54 L290 54', 'ml', RATE) + path('M290 72 L150 72', 'ml', RATE)
b += text(220, 46, 'via eth1', 10, RATE) + text(220, 88, 'backup path: via leaf1', 10, RATE)
b += f'<path d="M90 84V162H290" fill="none" stroke="#8aa09a" stroke-dasharray="4 3"/>' + text(190, 154, 'unused until leaf1 hears the withdrawal', 10, MUTED)
b += line(410, 162, 470, 162) + text(480, 158, 'dcgw2, wan, h2', 10, MUTED, 'start')
b += text(440, 48, 'One ping crossed the leaf1-border1', 10.5, RATE, 'start') + text(440, 63, 'link 63 times in 0.3 ms, TTL 63 to 1,', 10.5, RATE, 'start') + text(440, 78, 'then border1 sent TTL exceeded.', 10.5, RATE, 'start')
X0, SC = 40, 3.4
b += text(X0, 222, '0 ms: border1 loses its gateway link', 10, INK, 'start')
b += f'<rect x="{X0}" y="232" width="{66 * SC}" height="26" fill="#d9dedd"/>' + text(X0 + 33 * SC, 249, 'dropped at border1: 6 pings', 10, INK)
b += f'<rect x="{X0 + 66 * SC}" y="232" width="{88 * SC}" height="26" fill="{RATE}"/>' + text(X0 + 110 * SC, 249, 'looping leaf1 ⇄ border1: 9 pings', 10, '#ffffff')
b += f'<rect x="{X0 + 154 * SC}" y="232" width="{660 - 154 * SC - X0}" height="26" fill="{PATH}"/>' + text((X0 + 154 * SC + 660) / 2, 249, 'via border2', 10, '#ffffff')
for t in (0, 66, 154):
    b += line(X0 + t * SC, 228, X0 + t * SC, 262, INK) + text(X0 + t * SC, 276, f'{t} ms', 10, INK)
b += text(350, 300, 'Timings from the capture b3-failover-microloop.pcap: 15 pings lost at 100 per second.', 10.5, MUTED)
out['microloop'] = svg(700, 312, b, 'ml') + cap('E', 'A backup path behind the ingress loops until the withdrawal arrives.')

# ---------------------------------------------------------------- decision flow
def q(x, y, w, t1, t2=''):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="48" rx="24" fill="#ffffff" stroke="{INK}"/>'
    return s + (text(x + w / 2, y + 20, t1, 11, INK) + text(x + w / 2, y + 36, t2, 11, INK) if t2 else text(x + w / 2, y + 28, t1, 11, INK))
def ans(x, y, w, t1, t2, c):
    return box(x, y, w, 48, t1, t2, c)
b = q(20, 20, 300, 'Does the router that chooses the path', 'learn every path itself?')
b += arrow(320, 44, 400, 44, 'df') + text(360, 38, 'yes', 10)
b += ans(400, 20, 280, 'ADD-PATH adds visibility only', 'eBGP fabric: use multipath-relax', GRAY)
b += arrow(170, 68, 170, 104, 'df') + text(182, 90, 'no', 10, MUTED, 'start')
b += q(20, 104, 300, 'Do the hidden paths have different', 'next hops on different links?')
b += arrow(320, 128, 400, 128, 'df') + text(360, 122, 'no', 10)
b += ans(400, 104, 280, 'ADD-PATH adds visibility only', 'paths collapse onto one next hop', GRAY)
b += arrow(170, 152, 170, 188, 'df') + text(182, 174, 'yes', 10, MUTED, 'start')
b += q(20, 188, 300, 'Do their AS paths differ?')
b += arrow(320, 212, 400, 212, 'df') + text(360, 206, 'yes', 10)
b += ans(400, 188, 280, 'ADD-PATH and multipath-relax', 'neither works alone', TEAL)
b += arrow(170, 236, 170, 272, 'df') + text(182, 258, 'no', 10, MUTED, 'start')
b += ans(20, 272, 300, 'ADD-PATH', 'plus maximum-paths ibgp', TEAL)
b += text(350, 345, 'For failover, add one question: is the backup reachable without going back through the router still sending you traffic?', 10.5, RATE)
out['decision'] = svg(700, 358, b, 'df') + cap('F', 'When ADD-PATH changes forwarding.')

d = Path(__file__).parent / 'images'
for name, fig in out.items():
    (d / f'{name}.svg').write_text(standalone(fig))
print(sorted(out))
