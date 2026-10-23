"""Source of truth for the multi-vendor EVPN-VXLAN lab, and the configuration generator.

Every address, ASN and VNI below is derived from this one plan. Output:
  configs/cumulus/<NODE>.nvue   NVUE commands for Cumulus Linux 5.x
  configs/nxos/<NODE>.cfg       NX-OS 10.x configuration
"""
from pathlib import Path

OUT = Path(__file__).parent / 'configs'

# ---- the plan --------------------------------------------------------------------------
TENANT, L3VNI, L3VLAN = 'TENANT1', 50001, 3001   # 3968-4095 are reserved on NX-OS
RT_ASN = 65000                         # explicit route targets: same value in both vendors
GW_MAC = '00:00:5e:00:01:01'           # one anycast gateway MAC for every leaf, both vendors

# VLAN -> (VNI, subnet prefix, where it lives)
VLANS = {
    10: (10010, '10.10.10', 'stretched'),   # one L2 segment across both fabrics
    20: (10020, '10.20.20', 'cumulus'),     # routed to the NX-OS side via symmetric IRB / type-5
    30: (10030, '10.30.30', 'nxos'),
}

CUMULUS = {   # name: (asn, loopback, fabric ports, role)
    'SPINE-1': (65100, '10.0.0.1', ['swp1', 'swp2', 'swp3'], 'spine'),
    'SPINE-2': (65100, '10.0.0.2', ['swp1', 'swp2', 'swp3'], 'spine'),
    'LEAF-3':  (65103, '10.0.0.3', ['swp1', 'swp2'], 'leaf'),
    'LEAF-4':  (65104, '10.0.0.4', ['swp1', 'swp2'], 'leaf'),
    'LEAF-5':  (65105, '10.0.0.5', ['swp1', 'swp2'], 'leaf'),
}
ACCESS = {    # leaf: {port: vlan}
    'LEAF-3': {'swp3': 10},
    'LEAF-4': {'swp3': 20},
    'LEAF-5': {'swp3': 10, 'swp4': 20},
}
# the inter-fabric link: LEAF-3 swp4 <-> LEAF-BORDER Ethernet1/1, numbered /31
DCI = {'LEAF-3': ('swp4', '10.255.0.0/31', '10.255.0.1', 65210)}


def cumulus(name):
    asn, lo, fabric, role = CUMULUS[name]
    c = [f'nv set system hostname {name}',
         f'nv set interface lo ip address {lo}/32',
         f'nv set interface {",".join(fabric)} type swp',
         f'nv set interface {",".join(fabric)} link mtu 9216',
         f'nv set router bgp autonomous-system {asn}',
         f'nv set router bgp router-id {lo}',
         'nv set vrf default router bgp address-family ipv4-unicast enable on',
         f'nv set vrf default router bgp address-family ipv4-unicast network {lo}/32',
         'nv set vrf default router bgp address-family ipv4-unicast multipath ebgp 8',
         'nv set evpn enable on']
    for p in fabric:                                    # eBGP unnumbered: the neighbor is the interface
        c += [f'nv set vrf default router bgp neighbor {p} remote-as external',
              f'nv set vrf default router bgp neighbor {p} address-family l2vpn-evpn enable on']
    if role == 'leaf':
        vl = sorted(set(ACCESS[name].values()) | {v for v, (_, _, w) in VLANS.items() if w == 'stretched'})
        c += [f'nv set nve vxlan source address {lo}',
              'nv set nve vxlan arp-nd-suppress on',
              'nv set nve vxlan mtu 9216',
              f'nv set vrf {TENANT} evpn vni {L3VNI}',
              f'nv set vrf {TENANT} evpn vlan {L3VLAN}',
              f'nv set vrf {TENANT} router bgp enable on',
              f'nv set vrf {TENANT} router bgp address-family ipv4-unicast redistribute connected enable on',
              f'nv set vrf {TENANT} router bgp address-family ipv4-unicast route-export to-evpn enable on',
              f'nv set vrf {TENANT} router bgp route-export to-evpn route-target {RT_ASN}:{L3VNI}',
              f'nv set vrf {TENANT} router bgp route-import from-evpn route-target {RT_ASN}:{L3VNI}',
              'nv set evpn route-advertise svi-ip off']
        n = int(lo.split('.')[-1])
        for v in vl:
            vni, net, _ = VLANS[v]
            c += [f'nv set bridge domain br_default vlan {v} vni {vni}',
                  f'nv set evpn vni {vni} route-target both {RT_ASN}:{vni}',
                  f'nv set interface vlan{v} type svi',
                  f'nv set interface vlan{v} vlan {v}',
                  f'nv set interface vlan{v} ip vrf {TENANT}',
                  f'nv set interface vlan{v} ip address {net}.{n}/24',
                  f'nv set interface vlan{v} ip vrr address {net}.1/24',
                  f'nv set interface vlan{v} ip vrr mac-address {GW_MAC}',
                  f'nv set interface vlan{v} ip vrr state up']
        for p, v in ACCESS[name].items():
            c += [f'nv set interface {p} bridge domain br_default access {v}']
    if name in DCI:
        p, addr, peer, peer_asn = DCI[name]
        c += [f'nv set interface {p} type swp',
              f'nv set interface {p} ip address {addr}',
              f'nv set interface {p} link mtu 9216',
              f'nv set vrf default router bgp neighbor {peer} remote-as {peer_asn}',
              f'nv set vrf default router bgp neighbor {peer} address-family l2vpn-evpn enable on']
    return c


NXOS = {      # name: (asn, loopback, role)
    'NX-SPINE-01': (65200, '10.0.1.1', 'spine'),
    'NX-SPINE-02': (65200, '10.0.1.2', 'spine'),
    'LEAF-BORDER': (65210, '10.0.1.10', 'leaf'),
    'NX-LEAF-01':  (65211, '10.0.1.11', 'leaf'),
    'NX-LEAF-02':  (65212, '10.0.1.12', 'leaf'),
}
# NX-OS fabric links, numbered /31: spine port -> leaf, leaf port; subnet 10.1.<spine>.<2*i>/31
NX_LINKS = {
    'NX-SPINE-01': [('Ethernet1/1', 'NX-LEAF-01', 'Ethernet1/1'), ('Ethernet1/2', 'NX-LEAF-02', 'Ethernet1/1'),
                    ('Ethernet1/3', 'LEAF-BORDER', 'Ethernet1/2')],
    'NX-SPINE-02': [('Ethernet1/1', 'NX-LEAF-01', 'Ethernet1/2'), ('Ethernet1/2', 'NX-LEAF-02', 'Ethernet1/2'),
                    ('Ethernet1/3', 'LEAF-BORDER', 'Ethernet1/3')],
}
NX_ACCESS = {'LEAF-BORDER': {'Ethernet1/11': 30}, 'NX-LEAF-01': {}, 'NX-LEAF-02': {'Ethernet1/3': 10}}
NX_DCI = {'LEAF-BORDER': ('Ethernet1/1', '10.255.0.1/31', '10.255.0.0', 65103)}


def nx_links(name):
    """(local port, local ip/31, peer ip, peer name) for every routed fabric link of this node."""
    out = []
    for sp, links in NX_LINKS.items():
        s = int(sp[-1]) - 1
        for i, (sport, leaf, lport) in enumerate(links):
            a, b = f'10.1.{s}.{2 * i}', f'10.1.{s}.{2 * i + 1}'
            if name == sp:
                out.append((sport, a + '/31', b, leaf))
            if name == leaf:
                out.append((lport, b + '/31', a, sp))
    return out


def nxos(name):
    asn, lo, role = NXOS[name]
    mac = GW_MAC.replace(':', '')
    c = [f'hostname {name}', 'nv overlay evpn', 'feature bgp']
    if role == 'leaf':
        c += ['feature interface-vlan', 'feature vn-segment-vlan-based', 'feature nv overlay',
              f'fabric forwarding anycast-gateway-mac {mac[0:4]}.{mac[4:8]}.{mac[8:12]}']
    c += ['route-map NH-UNCHANGED permit 10', '  set ip next-hop unchanged',
          'route-map CONNECTED permit 10', '  match tag 12345',
          'interface loopback0', f'  ip address {lo}/32']
    links = nx_links(name)
    peers = [(peer_ip, NXOS[peer][0]) for _, _, peer_ip, peer in links]
    for port, addr, _, peer in links:
        c += [f'interface {port}', f'  description to {peer}', '  no switchport', '  mtu 9216',
              f'  ip address {addr}', '  no shutdown']
    if name in NX_DCI:
        port, addr, peer_ip, peer_asn = NX_DCI[name]
        c += [f'interface {port}', '  description to LEAF-3 (Cumulus fabric)', '  no switchport', '  mtu 9216',
              f'  ip address {addr}', '  no shutdown']
        peers.append((peer_ip, peer_asn))
    if role == 'leaf':
        vlans = sorted(set(NX_ACCESS[name].values()) | {v for v, (_, _, w) in VLANS.items() if w in ('stretched', 'nxos')})
        n = int(lo.split('.')[-1])
        for v in vlans:
            c += [f'vlan {v}', f'  vn-segment {VLANS[v][0]}']
        c += [f'vlan {L3VLAN}', f'  vn-segment {L3VNI}',
              f'vrf context {TENANT}', f'  vni {L3VNI}', '  rd auto', '  address-family ipv4 unicast',
              f'    route-target both {RT_ASN}:{L3VNI}', f'    route-target both {RT_ASN}:{L3VNI} evpn',
              f'interface Vlan{L3VLAN}', '  no shutdown', '  mtu 9216', f'  vrf member {TENANT}', '  ip forward']
        for v in vlans:
            vni, net, _ = VLANS[v]
            c += [f'interface Vlan{v}', '  no shutdown', f'  vrf member {TENANT}',
                  f'  ip address {net}.1/24 tag 12345', '  fabric forwarding mode anycast-gateway']
        for port, v in NX_ACCESS[name].items():
            c += [f'interface {port}', '  switchport', '  switchport mode access', f'  switchport access vlan {v}',
                  '  spanning-tree port type edge', '  no shutdown']
        c += ['interface nve1', '  no shutdown', '  host-reachability protocol bgp', '  source-interface loopback0']
        for v in vlans:
            c += [f'  member vni {VLANS[v][0]}', '    ingress-replication protocol bgp']
        c += [f'  member vni {L3VNI} associate-vrf', 'evpn']
        for v in vlans:
            vni = VLANS[v][0]
            c += [f'  vni {vni} l2', '    rd auto', f'    route-target import {RT_ASN}:{vni}',
                  f'    route-target export {RT_ASN}:{vni}']
    c += [f'router bgp {asn}', f'  router-id {lo}', '  bestpath as-path multipath-relax',
          '  address-family ipv4 unicast', f'    network {lo}/32', '    maximum-paths 8',
          '  address-family l2vpn evpn', '    retain route-target all']
    for ip, pasn in peers:
        c += [f'  neighbor {ip}', f'    remote-as {pasn}', '    address-family ipv4 unicast',
              '    address-family l2vpn evpn', '      send-community', '      send-community extended',
              '      route-map NH-UNCHANGED out']
    if role == 'leaf':
        c += [f'  vrf {TENANT}', '    address-family ipv4 unicast',
              '      redistribute direct route-map CONNECTED', '      maximum-paths 8']
    return c


if __name__ == '__main__':
    (OUT / 'cumulus').mkdir(parents=True, exist_ok=True)
    for name in CUMULUS:
        (OUT / 'cumulus' / f'{name}.nvue').write_text('\n'.join(cumulus(name)) + '\n')
        print('wrote', name)
    (OUT / 'nxos').mkdir(parents=True, exist_ok=True)
    for name in NXOS:
        (OUT / 'nxos' / f'{name}.cfg').write_text('\n'.join(nxos(name)) + '\n')
        print('wrote', name)
