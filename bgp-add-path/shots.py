"""Render lab outputs as screenshot-style SVG panels in images/. Run: python3 shots.py

Every line shown comes from a real file: router outputs from results/, packet decodes from
captures/decoded/ (tshark 4.6, the engine inside Wireshark). Lines are only filtered, never edited;
a dimmed line marks where output was skipped.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
from panels import SKIP, block, drop, panel, bgp_tree   # noqa: E402

HERE = Path(__file__).parent
RES = HERE / 'results' / 'frr-10.2.1_git'
DEC = HERE / 'captures' / 'decoded'


def show(path, node, cmd, *dropping):
    lines = drop(block(path, f'{node}# {cmd}'), 'Last update', 'BGP routing table entry', 'dvertised', '10.255.0.11 10.255.0.21')
    lines = [l for l in lines if l.strip() and not any(d in l for d in dropping)]
    return [f'{node}# {cmd}'] + lines


def write(name, svg):
    (HERE / 'images' / f'{name}.svg').write_text(svg)
    print('images/' + name + '.svg')


B, A = RES / 'phase-b', RES / 'phase-a'

# 1. The reflector knows two exits and tells leaf1 about one
lines = show(B / 'B2-reflector-hides-a-path.txt', 'rr1', 'show bgp ipv4 unicast 10.99.0.0/24') + [''] + \
        show(B / 'B2-reflector-hides-a-path.txt', 'leaf1', 'show bgp ipv4 unicast 10.99.0.0/24') + [''] + \
        show(B / 'B2-reflector-hides-a-path.txt', 'leaf1', 'ip route show 10.99.0.0/24')
write('shot-b2-reflector-hides', panel(lines, {'Paths: (2': 'key', 'Paths: (1': 'bad', 'nhid 31 via': 'bad'}, 'rr1 and leaf1, before ADD-PATH'))

# 2. ADD-PATH only: two paths, still one next hop
lines = show(B / 'B5-addpath-only.txt', 'leaf1', 'show bgp ipv4 unicast 10.99.0.0/24', 'Originator') + [''] + \
        show(B / 'B5-addpath-only.txt', 'leaf1', 'ip route show 10.99.0.0/24')
write('shot-b5-addpath-only', panel(lines, {'Paths: (2': 'key', '  65098 65100': 'key', '  65099 65100': 'key', 'nhid 31 via': 'bad'},
                                    'leaf1, ADD-PATH on, multipath-relax off'))

# 3. Both knobs: two next hops
lines = show(B / 'B6-both.txt', 'leaf1', 'show bgp ipv4 unicast 10.99.0.0/24', 'Originator', 'AddPath ID') + [''] + \
        show(B / 'B6-both.txt', 'leaf1', 'ip route show 10.99.0.0/24')
write('shot-b6-both', panel(lines, {'internal, multipath': 'key', 'nexthop via': 'key'}, 'leaf1, ADD-PATH and multipath-relax on'))

# 4. Phase A: two paths, one next hop
lines = show(A / 'A5-leaf-after-addpath.txt', 'leaf1', 'show bgp ipv4 unicast 10.99.0.0/24') + [''] + \
        show(A / 'A5-leaf-after-addpath.txt', 'leaf1', 'ip route show 10.99.0.0/24')
write('shot-a5-ebgp-addpath', panel(lines, {'10.0.1.1 from': 'key', 'via 10.0.1.1 dev eth1': 'bad'}, 'leaf1 in the eBGP fabric, ADD-PATH on'))

# 5. Wireshark: the reflector's UPDATEs with path identifiers
write('ws-b2-update', panel(bgp_tree(DEC / 'b2-update.txt', '10.99.0.0/24'),
                            {'PathId': 'key', 'NEXT_HOP: 10.255': 'key'},
                            'b2-rr-with-addpath.pcap · frame 68 · rr1 → leaf1', dark=False, tree=True))
write('ws-a2-update', panel(bgp_tree(DEC / 'a2-update.txt', '10.99.0.0/24'),
                            {'PathId': 'key', 'NEXT_HOP: 10.0.1.1': 'bad'},
                            'a2-ebgp-with-addpath.pcap · spine1 → leaf1', dark=False, tree=True))

# 6. Wireshark: the capability in the OPEN messages
opens = re.split(r'\n(?=Frame \d+:)', (DEC / 'b2-open.txt').read_text())
cap = []
for who, src in (('OPEN from rr1, frame 10', 'Src: 10.255.0.1,'), ('OPEN from leaf1, frame 12', 'Src: 10.255.0.11,')):
    f = next(o for o in opens if src in o)
    sub = re.search(r'( +)Capability: Support for Additional Paths\n(.*?)(?=\n {8}Optional Parameter)', f, re.S)
    base = len(sub.group(1))
    cap += [who] + ['    ' + l[base:] for l in ([sub.group(1) + 'Capability: Support for Additional Paths'] + sub.group(2).split('\n'))] + ['']
write('ws-b2-open', panel(cap[:-1], {'Send/Receive': 'key'}, 'b2-rr-with-addpath.pcap · ADD-PATH capability (69)', dark=False, tree=True))

# 7. Wireshark packet list: one ping caught in the loop
rows = [l.split('\t') for l in (DEC / 'b3-loop.txt').read_text().strip().split('\n')]
names = {'aa:c1:ab:94:5d:12': 'leaf1', 'aa:c1:ab:00:dc:3e': 'border1'}
fmt = lambda r: f'{r[0]:>5}  {float(r[1]):.6f}  {names.get(r[2], r[2]):<8} {r[3] if "," not in r[3] else r[3].split(",")[0]:>4}  {r[4][:70]}'
loop = [r for r in rows if 'request' in r[4]]
err = next(r for r in rows if 'Time-to-live' in r[4])
lines = ['   No  Time      eth.src  ttl   Info'] + [fmt(r) for r in loop[:4]] + [SKIP] + [fmt(r) for r in loop[-3:]] + [fmt(err)]
write('ws-b3-microloop', panel(lines, {'Time-to-live': 'bad', 'ttl=63': 'key'}, f'b3-failover-microloop.pcap · ping seq 279 on the leaf1–border1 link ({len(loop)} frames)', dark=False))
