#!/usr/bin/env python3
"""Generate the BGP unnumbered and ASN-plan lab from one small source of truth.

This file is also the automation example of the article: every per-device value
(hostname, loopback, ASN) is derived from the device's position, and the fabric
interfaces need no addresses at all, so the BGP block is the same on every leaf.

Fabric: 2 spines, 4 leaves in a rail-optimized layout (2 scalable units x 2 rails).
    leaf1 = SU1 rail 1    leaf2 = SU1 rail 2    leaf3 = SU2 rail 1    leaf4 = SU2 rail 2
Every leaf connects eth1 to spine1 and eth2 to spine2. No IPv4 address on any fabric link.

ASN plans (one topology per plan):
    rfc7938          spines share one ASN, every leaf has its own        (the recommended plan)
    per-rail         leaves of the same rail share an ASN                (a tidy-looking trap)
    unique-spines    every spine and every leaf has its own ASN          (valley paths)
Run: python3 generate.py            -> writes plans/<plan>/topology.clab.yml and *.conf
"""
from pathlib import Path

IMAGE = 'quay.io/frrouting/frr:10.2.1'
SPINES = ['spine1', 'spine2']
LEAVES = {'leaf1': (1, 1), 'leaf2': (1, 2), 'leaf3': (2, 1), 'leaf4': (2, 2)}   # name: (scalable unit, rail)


def loopback(node):
    """Loopbacks from position: spines 10.255.0.x, leaves 10.255.<su>.<rail>."""
    if node in SPINES:
        return f'10.255.0.{SPINES.index(node) + 1}'
    su, rail = LEAVES[node]
    return f'10.255.{su}.{rail}'


def asn(plan, node):
    if node in SPINES:
        return 65000 + (SPINES.index(node) + 1 if plan == 'unique-spines' else 0)
    su, rail = LEAVES[node]
    if plan == 'per-rail':
        return 65200 + rail                      # leaf1 and leaf3 share 65201: the trap
    return 65100 + (su - 1) * 10 + rail          # 65101, 65102, 65111, 65112: unique, readable


def fabric_ports(node):
    """Fabric interfaces: a leaf has one uplink per spine, a spine one downlink per leaf."""
    return [f'eth{i + 1}' for i in range(len(LEAVES) if node in SPINES else len(SPINES))]


def config(plan, node, allowas_in=False):
    ports = fabric_ports(node)
    out = [f'hostname {node}', 'log stdout informational', '!',
           'interface lo', f' ip address {loopback(node)}/32', 'exit']
    for p in ports:                              # IPv6 router advertisements carry the link-local address and MAC
        out += [f'interface {p}', ' ipv6 nd ra-interval 3', ' no ipv6 nd suppress-ra', 'exit']
    out += ['!', f'router bgp {asn(plan, node)}', f' bgp router-id {loopback(node)}',
            ' no bgp ebgp-requires-policy', ' bgp bestpath as-path multipath-relax',
            ' neighbor FABRIC peer-group', ' neighbor FABRIC remote-as external', ' neighbor FABRIC timers 3 9',
            ' neighbor FABRIC advertisement-interval 0']
    out += [f' neighbor {p} interface peer-group FABRIC' for p in ports]
    out += [' !', ' address-family ipv4 unicast', f'  network {loopback(node)}/32', '  maximum-paths 8',
            '  neighbor FABRIC soft-reconfiguration inbound']   # keeps what each peer sent, even routes we reject
    if allowas_in:
        out.append('  neighbor FABRIC allowas-in 1')
    out += [' exit-address-family', 'exit', '!', 'end']
    return '\n'.join(out) + '\n'


def topology(plan):
    out = [f'# BGP unnumbered and ASN plans, plan "{plan}". Deploy: containerlab deploy -t topology.clab.yml',
           f'name: unnum-{plan}', 'topology:', '  defaults:', '    kind: linux', f'    image: {IMAGE}',
           '    sysctls:', '      net.ipv4.ip_forward: 1', '      net.ipv6.conf.all.disable_ipv6: 0',
           '      net.ipv6.conf.default.disable_ipv6: 0', '      net.ipv6.conf.all.forwarding: 1',
           '      net.ipv4.fib_multipath_hash_policy: 1', '  nodes:']
    for node in SPINES + list(LEAVES):
        out += [f'    {node}:', '      binds:', '        - ../../common/daemons:/etc/frr/daemons',
                '        - ../../common/vtysh.conf:/etc/frr/vtysh.conf', f'        - {node}.conf:/etc/frr/frr.conf']
    out.append('  links:')
    for li, leaf in enumerate(LEAVES):
        for si, spine in enumerate(SPINES):
            out.append(f'    - endpoints: ["{leaf}:eth{si + 1}", "{spine}:eth{li + 1}"]')
    return '\n'.join(out) + '\n'


PLANS = ['rfc7938', 'per-rail', 'unique-spines']

if __name__ == '__main__':
    here = Path(__file__).parent
    for plan in PLANS:
        d = here / 'plans' / plan
        d.mkdir(parents=True, exist_ok=True)
        (d / 'topology.clab.yml').write_text(topology(plan))
        for node in SPINES + list(LEAVES):
            (d / f'{node}.conf').write_text(config(plan, node))
    print('generated', ', '.join(PLANS))
