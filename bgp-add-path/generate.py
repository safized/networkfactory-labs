"""Generate topologies and FRR configurations for the BGP ADD-PATH lab.

Phase A, eBGP fabric: every switch has its own ASN and the spine rewrites the next hop.
  Shows that multipath-relax creates ECMP, while ADD-PATH only adds visibility.
Phase B, iBGP with an off-path route reflector: next hops are preserved, and the destination is
  dual-homed through two gateways in different ASes. Shows that neither knob alone changes forwarding:
  the leaf needs ADD-PATH (to learn both exits) and multipath-relax (to use exits with different AS paths).

Both phases START WITHOUT the features under test (no multipath-relax, no ADD-PATH),
so the lab guide switches them on one at a time.
Run: python3 generate.py
"""
from pathlib import Path

IMAGE = 'quay.io/frrouting/frr:10.2.1'   # any recent FRR 9.x or 10.x image works

PHASES = {
    'phase-a-ebgp': {
        'lo': {'leaf1': '10.255.0.11', 'spine1': '10.255.0.1', 'border1': '10.255.0.21', 'border2': '10.255.0.22', 'dcgw': '10.255.0.99'},
        'asn': {'leaf1': 65011, 'spine1': 65000, 'border1': 65021, 'border2': 65022, 'dcgw': 65099},
        # (node, ifc, address, peer, peer ifc, peer address); every link is a /31
        'links': [('leaf1', 'eth1', '10.0.1.0', 'spine1', 'eth1', '10.0.1.1'),
                  ('spine1', 'eth2', '10.0.1.2', 'border1', 'eth1', '10.0.1.3'),
                  ('spine1', 'eth3', '10.0.1.4', 'border2', 'eth1', '10.0.1.5'),
                  ('border1', 'eth2', '10.0.2.0', 'dcgw', 'eth1', '10.0.2.1'),
                  ('border2', 'eth2', '10.0.2.2', 'dcgw', 'eth2', '10.0.2.3')],
    },
    'phase-b-ibgp-rr': {
        'lo': {'leaf1': '10.255.0.11', 'rr1': '10.255.0.1', 'border1': '10.255.0.21', 'border2': '10.255.0.22',
               'dcgw1': '10.255.0.98', 'dcgw2': '10.255.0.99', 'wan': '10.255.0.100'},
        'asn': {'leaf1': 65000, 'rr1': 65000, 'border1': 65000, 'border2': 65000, 'dcgw1': 65098, 'dcgw2': 65099, 'wan': 65100},
        'links': [('leaf1', 'eth1', '10.0.1.0', 'border1', 'eth1', '10.0.1.1'),
                  ('leaf1', 'eth2', '10.0.1.2', 'border2', 'eth1', '10.0.1.3'),
                  ('leaf1', 'eth3', '10.0.1.4', 'rr1', 'eth1', '10.0.1.5'),
                  ('border1', 'eth2', '10.0.2.0', 'dcgw1', 'eth1', '10.0.2.1'),
                  ('border2', 'eth2', '10.0.2.2', 'dcgw2', 'eth1', '10.0.2.3'),
                  ('dcgw1', 'eth2', '10.0.3.0', 'wan', 'eth1', '10.0.3.1'),
                  ('dcgw2', 'eth2', '10.0.3.2', 'wan', 'eth2', '10.0.3.3')],
        'h2': 'wan',
    },
}
PHASES['phase-a-ebgp']['h2'] = 'dcgw'
EXTERNAL = ('dcgw', 'dcgw1', 'dcgw2', 'wan')   # outside the fabric: eBGP only, no OSPF
HOST_IMAGE = 'nicolaka/netshoot:latest'  # includes iperf3, tcpdump, mtr
# host: (router, router ifc, gateway address, host address, route back toward the other host)
def hosts(phase):
    return {'h1': ('leaf1', 'eth9', '10.20.1.1/24', '10.20.1.10/24', '10.99.0.0/24 via 10.20.1.1'),
            'h2': (PHASES[phase]['h2'], 'eth9', '10.99.0.1/24', '10.99.0.10/24', '10.20.1.0/24 via 10.99.0.1')}


def originate(phase):
    return {'leaf1': '10.20.1.0/24', PHASES[phase]['h2']: '10.99.0.0/24'}


def ends(links):
    """Both ends of every link, as (node, ifc, addr, peer, peer_addr)."""
    for a, ai, aa, b, bi, ba in links:
        yield a, ai, aa, b, ba
        yield b, bi, ba, a, aa


def nbr(addr, asn, extra=()):
    out = [f' neighbor {addr} remote-as {asn}', f' neighbor {addr} timers 3 9', f' neighbor {addr} advertisement-interval 0']
    return out + [f' neighbor {addr} {e}' for e in extra]


def config(phase, node):
    P = PHASES[phase]; lo = P['lo']; asn = P['asn']; ospf = phase == 'phase-b-ibgp-rr' and node not in EXTERNAL
    out = [f'hostname {node}', 'log stdout informational', '!', 'interface lo', f' ip address {lo[node]}/32']
    if ospf:
        out.append(' ip ospf area 0')
    out.append('exit')
    my = [e for e in ends(P['links']) if e[0] == node]
    for _, ifc, addr, peer, _ in my:
        out += [f'interface {ifc}', f' ip address {addr}/31']
        if ospf and peer not in EXTERNAL:
            out += [' ip ospf area 0', ' ip ospf network point-to-point']
        out.append('exit')
    for h, (r, ifc, gw, _, _) in hosts(phase).items():
        if r == node:
            out += [f'interface {ifc}', f' description server {h}', f' ip address {gw}', 'exit']
    out.append('!')
    if ospf:
        out += ['router ospf', f' ospf router-id {lo[node]}', 'exit', '!']
    out += [f'router bgp {asn[node]}', f' bgp router-id {lo[node]}', ' no bgp ebgp-requires-policy', ' no bgp default ipv4-unicast']
    af = []
    if phase == 'phase-a-ebgp':
        if node == 'spine1':
            out.append(' no bgp bestpath as-path multipath-relax')
        for _, _, _, peer, paddr in my:
            out += nbr(paddr, asn[peer]); af.append(f'  neighbor {paddr} activate')
        af.append(f'  network {lo[node]}/32')
    else:
        if node == 'rr1':
            for c in ('leaf1', 'border1', 'border2'):
                out += nbr(lo[c], 65000, ['update-source lo'])
                af += [f'  neighbor {lo[c]} activate', f'  neighbor {lo[c]} route-reflector-client']
        elif node in EXTERNAL:
            if node == 'wan':   # return traffic only: balance it over both gateways too
                out.append(' bgp bestpath as-path multipath-relax')
            for _, _, _, peer, paddr in my:
                out += nbr(paddr, asn[peer]); af.append(f'  neighbor {paddr} activate')
        else:
            out += nbr(lo['rr1'], 65000, ['update-source lo']); af.append(f'  neighbor {lo["rr1"]} activate')
            if node.startswith('border'):
                peer, gw = next((peer, paddr) for _, _, _, peer, paddr in my if peer in EXTERNAL)
                out += nbr(gw, asn[peer])
                af += [f'  neighbor {gw} activate', f'  neighbor {lo["rr1"]} next-hop-self']
    out += [' !', ' address-family ipv4 unicast', '  maximum-paths 8', '  maximum-paths ibgp 8'] + af
    if node in originate(phase):
        out.append(f'  network {originate(phase)[node]}')
    out += [' exit-address-family', 'exit', '!', 'end']
    return '\n'.join(out) + '\n'


def topology(phase):
    P = PHASES[phase]
    out = [f'# BGP ADD-PATH lab, {phase}. Deploy with: sudo containerlab deploy -t topology.clab.yml',
           f'name: addpath-{phase[6]}', 'topology:', '  defaults:', '    kind: linux', f'    image: {IMAGE}',
           '    sysctls:', '      net.ipv4.ip_forward: 1', '      net.ipv4.fib_multipath_hash_policy: 1   # hash on L4 ports, like a fabric switch',
           '  nodes:']
    for node in P['lo']:
        out += [f'    {node}:', '      binds:', '        - ../common/daemons:/etc/frr/daemons',
                '        - ../common/vtysh.conf:/etc/frr/vtysh.conf', f'        - {node}.conf:/etc/frr/frr.conf']
    for h, (_, _, _, addr, route) in hosts(phase).items():
        out += [f'    {h}:', f'      image: {HOST_IMAGE}', '      exec:', f'        - ip addr add {addr} dev eth1', f'        - ip route add {route}']
    out.append('  links:')
    for a, ai, _, b, bi, _ in P['links']:
        out.append(f'    - endpoints: ["{a}:{ai}", "{b}:{bi}"]')
    for h, (r, ifc, _, _, _) in hosts(phase).items():
        out.append(f'    - endpoints: ["{r}:{ifc}", "{h}:eth1"]')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    here = Path(__file__).parent
    for phase, P in PHASES.items():
        d = here / phase
        for f in d.glob('*.conf'):
            f.unlink()
        (d / 'topology.clab.yml').write_text(topology(phase))
        for node in P['lo']:
            (d / f'{node}.conf').write_text(config(phase, node))
    print('generated', ', '.join(PHASES))
