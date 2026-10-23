"""Make a draw.io SVG export web-ready: drop the PNG fallbacks draw.io embeds for every HTML label (browsers render
the HTML itself), drop the "viewer does not support" notice, and put a white card behind the drawing so it reads
on dark pages too.

Usage: python3 web_svg.py IN.svg OUT.svg
"""
import re, sys

src, dst = sys.argv[1:3]
s = open(src).read()
s = re.sub(r'<image [^>]*xlink:href="data:image/png;base64,[^"]*"[^>]*/>', '', s)
s = re.sub(r'<switch>\s*<g requiredFeatures="http://www.w3.org/TR/SVG11/feature#Extensibility"/>\s*<a[^>]*>.*?</a>\s*</switch>', '', s, flags=re.S)

vb = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', s)
x, y, w, h = map(float, vb.groups())
pad = 24
nx, ny, nw, nh = x - pad, y - pad, w + 2 * pad, h + 2 * pad
s = s.replace(vb.group(0), f'viewBox="{nx:g} {ny:g} {nw:g} {nh:g}"', 1)
s = re.sub(r'(<svg[^>]*?) width="[^"]*"', rf'\1 width="{nw:g}px"', s, 1)
s = re.sub(r'(<svg[^>]*?) height="[^"]*"', rf'\1 height="{nh:g}px"', s, 1)
s = re.sub(r'(<svg[^>]*?) style="background[^"]*"', r'\1', s, 1)
card = f'<rect x="{nx:g}" y="{ny:g}" width="{nw:g}" height="{nh:g}" rx="14" fill="#ffffff" stroke="#e3e8ea"/>'
s = re.sub(r'(<svg[^>]*>)', r'\1' + card, s, 1)
open(dst, 'w').write(s)
print(f'{dst}: {len(s) // 1024} KB')
