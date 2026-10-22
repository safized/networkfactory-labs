"""Shared helpers for the labs: render real command output and packet decodes as screenshot-style SVG panels.

Lines are only filtered, never edited; a dimmed line marks where output was skipped.
"""
import re
from html import escape

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
        elif re.match(r'^[\w-]+# ', l):   # a command prompt line
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
