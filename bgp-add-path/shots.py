"""Render lab outputs as screenshot-style SVG panels in images/. Run: python3 shots.py

Every line shown comes from a real file: router outputs from results/, packet decodes from
captures/decoded/ (tshark 4.6, the engine inside Wireshark). Lines are only filtered, never edited;
a dimmed line marks where output was skipped.
"""
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
RES = HERE / 'results' / 'frr-10.2.1_git'
DEC = HERE / 'captures' / 'decoded'
MONO = "JetBrains Mono, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
FS, LH, CW = 12, 18, 7.25            # font size, line height, character width
SKIP = object()                       # marker for skipped output


def block(path, cmd):
    """The output of one command from a results file."""
    text = path.read_text()
    m = re.search(r'### ' + re.escape(cmd) + r'\n(.*?)(?=\n### |\Z)', text, re.S)
    return m.group(1).rstrip().split('\n')


def drop(lines, *patterns):
    return [l for l in lines if not any(p in l for p in patterns)]


def panel(lines, marks, title, dark=True, tree=False, rows=None):
    """lines: str or SKIP; marks: {substring: color key}; returns standalone SVG text."""
    width = int(max(len(l) for l in lines if l is not SKIP) * CW) + 48
    width = max(width, 520)
    head = 30
    h = head + 14 + LH * len(lines) + 10
    bg, fg, chrome, dim = (('#0f1c20', '#d5e1de', '#1b2b30', '#5f7a78') if dark else
                           ('#ffffff', '#1d2a2f', '#e9eef0', '#8a9a9c'))
    hl = {'key': '#1f6a5a' if dark else '#d8ecff', 'bad': '#5a2323' if dark else '#fde2e2',
          'err': '#121212'}
    s = [f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}">',
         f'<rect width="{width}" height="{h}" rx="10" fill="{bg}"/>',
         f'<path d="M0 10a10 10 0 0 1 10-10h{width - 20}a10 10 0 0 1 10 10v{head - 10}h-{width}z" fill="{chrome}"/>',
         ''.join(f'<circle cx="{18 + i * 16}" cy="15" r="5" fill="{c}"/>' for i, c in enumerate(('#e0605a', '#e3b341', '#5cb85c'))),
         f'<text x="{width / 2}" y="19.5" font-family="Poppins, Helvetica, Arial, sans-serif" font-size="11.5" fill="{dim}" text-anchor="middle">{escape(title)}</text>']
    y = head + 14
    for i, l in enumerate(lines):
        if l is SKIP:
            s.append(f'<text x="24" y="{y + 13}" font-family="{MONO}" font-size="{FS}" fill="{dim}">  ⋯</text>')
            y += LH
            continue
        kind = next((k for sub, k in marks.items() if sub in l), None)
        if kind:
            s.append(f'<rect x="12" y="{y}" width="{width - 24}" height="{LH}" rx="3" fill="{hl[kind]}"/>')
        color = fg
        if kind == 'err':
            color = '#ff7b72'
        elif l.startswith(('leaf1#', 'rr1#', 'spine1#')):
            color = '#7fd1b9' if dark else '#1f6a5a'
        txt = l
        if tree:
            ind = len(l) - len(l.lstrip())
            nxt = next((m for m in lines[i + 1:] if m is not SKIP), '')
            has_kids = len(nxt) - len(nxt.lstrip()) > ind
            collapsed = l.endswith('\u0000')
            txt = ' ' * ind + ('▸ ' if collapsed else '▾ ' if has_kids else '  ') + l.strip().rstrip('\u0000')
        s.append(f'<text x="24" y="{y + 13}" font-family="{MONO}" font-size="{FS}" fill="{color}" xml:space="preserve">{escape(txt)}</text>')
        y += LH
    s.append('</svg>')
    return '\n'.join(s) + '\n'


def show(path, node, cmd, *dropping):
    lines = drop(block(path, f'{node}# {cmd}'), 'Last update', 'BGP routing table entry', 'dvertised', '10.255.0.11 10.255.0.21')
    lines = [l for l in lines if l.strip() and not any(d in l for d in dropping)]
    return [f'{node}# {cmd}'] + lines


def bgp_tree(path, prefix, keep_attrs=('AS_PATH', 'NEXT_HOP')):
    """UPDATE messages that carry prefix, with path attributes collapsed except keep_attrs."""
    text = path.read_text()
    msgs = re.split(r'\n(?=Border Gateway Protocol - UPDATE Message)', text)
    out = []
    for m in msgs:
        if not m.startswith('Border Gateway Protocol') or f'{prefix} PathId' not in m and f'        {prefix}\n' not in m:
            continue
        lines = m.split('\n')
        keep, mode = [], None
        for l in lines:
            if not l.strip() or l.startswith(('Frame ', 'Ethernet', 'Internet', 'Transmission')):
                continue
            ind = len(l) - len(l.lstrip())
            if ind == 0:
                keep.append(l); mode = None
            elif ind == 4 and l.strip() in ('Path attributes', 'Network Layer Reachability Information (NLRI)'):
                keep.append(l); mode = 'nlri' if 'NLRI' in l else 'attrs'
            elif mode == 'attrs' and ind == 8:
                name = re.search(r'Path Attribute - (\w+)', l)
                keep.append(l if name and name.group(1) in keep_attrs else l + '\u0000')   # \0 = shown collapsed
            elif mode == 'nlri' and ind >= 8:
                keep.append(l)
        out += keep
    return out


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
