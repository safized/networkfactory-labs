"""Render the lab's real outputs and packet decodes as screenshot-style SVG panels in images/.
Run after verify.py and the tshark decodes (see README). Lines are filtered, never edited.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
from panels import SKIP, block, drop, panel   # noqa: E402

HERE = Path(__file__).parent
RES, DEC = HERE / 'results', HERE / 'captures' / 'decoded'
NOISE = ('Last update', 'BGP routing table entry', 'dvertised to', 'eth1 eth2', 'altname', 'valid_lft')


def show(plan, file, node, cmd, *dropping):
    lines = drop(block(RES / plan / f'{file}.txt', f'{node}# {cmd}'), *NOISE, *dropping)
    return [f'{node}# {cmd}'] + [l for l in lines if l.strip()]


def tree(file, start, stop=None, keep=None):
    """A slice of a tshark -V decode, from the line containing start up to the line containing stop."""
    lines = (DEC / file).read_text().split('\n')
    i = next(n for n, l in enumerate(lines) if start in l)
    j = next((n for n, l in enumerate(lines[i + 1:], i + 1) if stop and stop in l), len(lines))
    out = [l for l in lines[i:j] if l.strip() and not any(k in l for k in ('Checksum', 'Reserved', 'Status: Good'))]
    base = len(out[0]) - len(out[0].lstrip())
    return [l[base:] for l in out if not keep or any(k in l for k in keep)]


def write(name, svg):
    (HERE / 'images').mkdir(exist_ok=True)
    (HERE / 'images' / f'{name}.svg').write_text(svg)
    print(f'images/{name}.svg')


# 1. sessions named by interface, not by address
write('shot-sessions', panel(show('rfc7938', 'U2-sessions', 'leaf1', 'show bgp ipv4 unicast summary', 'RIB entries', 'Peers 2', 'Peer groups', 'Total number', 'table version'),
                             {'eth1 ': 'key', 'eth2 ': 'key'}, 'leaf1: two BGP sessions, no IPv4 address on either link'))

# 2. the routing table and the kernel
lines = show('rfc7938', 'U4-routes-and-kernel', 'leaf1', 'show bgp ipv4 unicast 10.255.2.1/32', '(fe80') + [''] + \
        show('rfc7938', 'U4-routes-and-kernel', 'leaf1', 'ip route show 10.255.2.1') + [''] + \
        show('rfc7938', 'U4-routes-and-kernel', 'leaf1', 'ip neigh show')
write('shot-kernel', panel(lines, {'nexthop via inet6': 'key', '169.254.0.1': 'bad'}, 'leaf1: an IPv4 route with IPv6 next hops, FRR 10.2.1'))

# 3. packet decodes
write('ws-ra', panel(tree('ra.txt', 'Internet Control Message Protocol v6', None,
                          keep=('Internet Control', 'Type: Router Advertisement', 'Router lifetime', 'ICMPv6 Option', 'Link-layer address')),
                     {'Link-layer address': 'key', 'Router Advertisement': 'key'}, 'u-router-advertisements.pcap · router advertisement from spine1', dark=False, tree=True))
cap = tree('open.txt', 'Capability: Extended Next Hop Encoding', 'Optional Parameter: Capability')
write('ws-open', panel(cap, {'Next hop AFI': 'key', 'Extended Next Hop': 'key'}, 'u-bgp-open-update.pcap · OPEN from leaf1, capability 5', dark=False, tree=True))
blocks = (DEC / 'update.txt').read_text().split('Border Gateway Protocol - UPDATE Message')
leaf3 = next(b for b in blocks if '10.255.2.1/32' in b).split('\n')
upd, keep = [], False
for l in leaf3:
    if 'Path Attribute - ' in l:
        keep = 'MP_REACH_NLRI' in l or 'AS_PATH' in l
        if 'AS_PATH' in l:
            upd.append(l.rstrip() + '\u0000')   # shown collapsed
            keep = False
            continue
    if keep and l.strip() and not l.lstrip().startswith(('0...', '1...', '.0..', '..0.', '...1', '.... 0000', 'Flags', 'Type Code', 'Length:')):
        upd.append(l)
base = len(upd[0]) - len(upd[0].lstrip())
upd = [l[base:] for l in upd]
write('ws-update', panel(upd, {'Next hop:': 'key', 'AFI): IPv4': 'key', '/32': 'key'}, 'u-bgp-open-update.pcap · UPDATE from spine1: leaf3 loopback, IPv6 next hop', dark=False, tree=True))

# 4. the per-rail trap: received, but not in the table
lines = show('per-rail', 'R2-leaf1-table', 'leaf1', 'show bgp ipv4 unicast', 'Status codes', 'i internal', 'Nexthop codes', 'Origin codes', 'RPKI', 'Default local', 'table version') + [''] + \
        show('per-rail', 'R2-leaf1-table', 'leaf1', 'show bgp ipv4 unicast neighbors eth1 received-routes', 'Status codes', 'i internal', 'Nexthop codes', 'Origin codes', 'RPKI', 'Default local', 'table version')
lines = [l for l in lines if 'fe80::' not in l or l.strip().startswith('*')]
write('shot-per-rail', panel(lines, {'local AS 65201': 'bad', '65000 65201 i': 'bad', 'Displayed 5 routes': 'bad'}, 'leaf1 in the per-rail plan: leaf3 (10.255.2.1) received, then dropped'))

# 5. unique spine ASNs: the valley path on spine1, and the double failure
lines = show('unique-spines', 'V2-after-spine1-leaf3-down', 'spine1', 'show bgp ipv4 unicast 10.255.2.1/32', '(fe80', 'Origin IGP') + [''] + \
        show('unique-spines', 'V2-after-leaf1-spine2-down', 'leaf1', 'traceroute -n -w 1 -q 1 -s 10.255.1.1 10.255.2.1')
write('shot-valley', panel(lines, {' 65002 65111': 'bad', '10.255.1.2 ': 'bad'}, 'unique spine ASNs: spine1 learns leaf3 back through the leaves'))
lines = show('rfc7938', 'A1-after-leaf1-spine2-down', 'leaf1', 'show bgp ipv4 unicast 10.255.2.1/32') + [''] + \
        show('rfc7938', 'A1-after-leaf1-spine2-down', 'leaf1', 'traceroute -n -w 1 -q 1 -s 10.255.1.1 10.255.2.1')[:5] + [SKIP]
write('shot-shared-double', panel(lines, {'not in table': 'bad'}, 'shared spine ASN: the same double failure, no path left'))
