"""Render the lab's real outputs and packet decodes as screenshot-style SVG panels in images/.
Run after the scenario scripts. Lines are filtered, never edited.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
from panels import SKIP, block, drop, panel   # noqa: E402

HERE = Path(__file__).parent
RES, DEC = HERE / 'results', HERE / 'captures' / 'decoded'
NOISE = ('Status codes', 'Origin codes', 'EVPN type-', 'BGP table version', 'Flags -(Rmac)', '(Dup):', '(Ps):',
         '(Bh):', '(Piporp)', '(Pipporp)', 'Codes:', 'DP - Data', 'UC - Unconf', 'S-ND', 'SU - Supp', 'Xconn', 'MS-IR',
         'HYB -')


def show(run, file, node, cmd, *dropping):
    lines = drop(block(RES / run / f'{file}.txt', f'{node}# {cmd}'), *NOISE, *dropping)
    return [f'{node}# {cmd}'] + [l.rstrip() for l in lines if l.strip()]


def tree(file, start, stop=None, keep=None):
    """A slice of a tshark -V decode, from the line containing start up to the line containing stop."""
    lines = (DEC / file).read_text().split('\n')
    i = next(n for n, l in enumerate(lines) if start in l)
    j = next((n for n, l in enumerate(lines[i + 1:], i + 1) if stop and stop in l), len(lines))
    out = [l for l in lines[i:j] if l.strip() and not any(k in l for k in ('Checksum', 'Reserved', 'Status: Good', 'bit:'))]
    return [l for l in out if not keep or any(k in l for k in keep)]


def listing(file, *keep):
    return [l.strip() for l in (DEC / file).read_text().split('\n') if l.strip() and (not keep or any(k in l for k in keep))]


def vteps(file, n):
    """The VTEP-column decode as an aligned table: frame, outer src, outer dst, VNI, inner packet."""
    rows = [l.split(None, 4) for l in listing(file)[:n]]
    head = f"{'No.':>3}  {'Outer src':<10} {'Outer dst':<10} {'VNI':<6} Inner packet"
    return [head] + [f'{r[0]:>3}  {r[1]:<10} {r[2]:<10} {r[3]:<6} {r[4]}' for r in rows]


def write(name, svg):
    (HERE / 'images').mkdir(exist_ok=True)
    (HERE / 'images' / f'{name}.svg').write_text(svg)
    print(f'images/{name}.svg')


def s1():
    # 1a. the silent host: neither side knows CLIENT-16's IP, so the ARP has to be flooded
    a = show('s1a', 'LEAF-3-arp-cache', 'LEAF-3', 'sudo vtysh -c "show evpn arp-cache vni 10010"') + [''] + \
        show('s1a', 'NX-LEAF-02-l2route', 'NX-LEAF-02', 'show l2route evpn mac-ip all', '-----', 'Topology    Mac')
    write('s1a-silent-host', panel(a, {'10.10.10.106': 'key', '10.10.10.108': 'key', '10.10.10.116': 'bad'},
                                   'Phase a: no MAC+IP route for CLIENT-16 (10.10.10.116) on either vendor'))
    lines = vteps('s1a-dci-vteps.txt', 8)
    write('s1a-dci-flood', panel(lines, {'Who has 10.10.10.116': 'bad'},
                                 'Inter-fabric link, phase a: one ARP broadcast, one VXLAN copy per remote VTEP'))
    t = tree('s1a-dci-arp-detail.txt', 'Internet Protocol Version 4', 'Address Resolution Protocol',
             keep=('Internet Protocol', 'User Datagram', 'Destination Port', 'Virtual eXtensible', 'VNI', 'Ethernet II, Src: 50:01'))
    write('s1a-vxlan-headers', panel(t + ['Address Resolution Protocol (request): Who has 10.10.10.116? Tell 10.10.10.106'],
                                     {'VXLAN Network Identifier': 'key', 'Dst Port: 4789': 'key', 'Broadcast': 'bad'},
                                     'One flooded copy: outer 10.0.0.3 -> 10.0.1.10, UDP 4789, VNI 10010', tree=True))

    # 1b. CLIENT-16 has spoken once: its MAC+IP is in EVPN, Cumulus answers locally, NX-OS still floods
    b = show('s1b', 'LEAF-3-arp-cache', 'LEAF-3', 'sudo vtysh -c "show evpn arp-cache vni 10010"')
    write('s1b-learned', panel(b, {'10.10.10.116': 'key'},
                               'Phase b: CLIENT-16 pinged its gateway once; LEAF-3 now knows 10.10.10.116 via EVPN'))
    p = listing('s1b-server6-port.txt', 'ARP', 'Echo (ping) request  id=0xb2cc, seq=1')[:3]
    write('s1b-local-answer', panel(['(capture on SERVER-6\'s access port, LEAF-3 swp3)'] + p,
                                    {'is at 50:01:00:10:00:00': 'key'},
                                    'LEAF-3 answers for CLIENT-16 in 0.65 ms; the request never leaves the leaf'))
    v = vteps('s1b-dci-vteps.txt', 6)
    write('s1b-dci', panel(v, {'Tell 10.10.10.116': 'bad', 'Echo (ping) request  id=0xb2cc, seq=1': 'key'},
                           'Inter-fabric link, phase b: Cumulus side quiet, NX-OS side floods to every Cumulus VTEP'))

    # 1c. suppression on both vendors: the interconnect carries only the pings
    c = show('s1c', 'NX-LEAF-02-arp-suppression-after', 'NX-LEAF-02', 'show ip arp suppression-cache detail',
             'Flags:', '+ - Adj', 'L - Local', 'R - Remote', 'L2 - Learnt', 'PS - Added', 'RO - Der')
    write('s1c-suppression-cache', panel(c, {'10.10.10.116': 'key', '10.10.10.106': 'key'},
                                         'Phase c: NX-LEAF-02 answers ARP from its suppression cache (L = local host, R = learned via EVPN)'))
    write('s1c-dci', panel(vteps('s1c-dci-vteps.txt', 8), {},
                           'Inter-fabric link, phase c: zero ARP in either direction, only the pings'))


if __name__ == '__main__':
    for f in sys.argv[1:] or ['s1']:
        globals()[f]()
