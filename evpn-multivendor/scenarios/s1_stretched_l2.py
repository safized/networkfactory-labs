"""Scenario 1: one VLAN across two vendors, and what ARP suppression really needs.

SERVER-6 (behind Cumulus LEAF-3) and CLIENT-16 (behind NX-OS NX-LEAF-02) share VLAN 10 / VNI 10010.
Captures run on the inter-fabric link (LEAF-3 swp4) and on both access ports at the same time.

    python3 scenarios/s1_stretched_l2.py a    silent CLIENT-16, NX-OS suppress-arp off
    python3 scenarios/s1_stretched_l2.py b    CLIENT-16 has spoken to its gateway once, NX-OS suppress-arp off
    python3 scenarios/s1_stretched_l2.py c    the same, NX-OS suppress-arp on (needs the TCAM carve and a reload)

Phase a pings in one direction (SERVER-6 to CLIENT-16); phases b and c ping both ways, flushing ARP first.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
from lab import Lab, tshark, first, save

phase = sys.argv[1]
# list view with the outer (VTEP) addresses and the VNI next to the inner packet
VTEP_COLUMNS = ['-o', 'gui.column.format:"No.","%m","Outer src","%Cus:ip.src:1","Outer dst","%Cus:ip.dst:1","VNI","%Cus:vxlan.vni","Info","%i"']
R, C = f'results/s1{phase}', Path(__file__).parent.parent / 'captures'
lab = Lab()

if phase in ('b', 'c'):
    lab.sh('CLIENT-16', 'ping -c 1 -W 1 10.10.10.1')       # one packet to the gateway: NX-OS learns the host IP
    lab.sh('SERVER-6', 'ping -c 1 -W 1 10.10.10.1')
    time.sleep(5)                                          # let the type-2 MAC+IP routes reach the other side

state = {
    'LEAF-3-macip.txt': lab.show('LEAF-3', 'sudo vtysh -c "show bgp l2vpn evpn route vni 10010 type macip"'),
    'LEAF-3-arp-cache.txt': lab.show('LEAF-3', 'sudo vtysh -c "show evpn arp-cache vni 10010"'),
    'LEAF-3-vni.txt': lab.show('LEAF-3', 'sudo vtysh -c "show evpn vni 10010"'),
    'LEAF-3-neigh-suppress.txt': lab.show('LEAF-3', 'bridge -d link show dev vxlan48 | grep -o "neigh_suppress [a-z]*"'),
    'NX-LEAF-02-l2route.txt': lab.show('NX-LEAF-02', 'show l2route evpn mac-ip all'),
    'NX-LEAF-02-nve-vni.txt': lab.show('NX-LEAF-02', 'show nve vni 10010'),
    'NX-LEAF-02-evpn-10.10.10.116.txt': lab.show('NX-LEAF-02', 'show bgp l2vpn evpn 10.10.10.116'),
}
if phase == 'c':
    state['NX-LEAF-02-arp-suppression.txt'] = lab.show('NX-LEAF-02', 'show ip arp suppression-cache detail')
for f, t in state.items():
    save(f'{R}/{f}', t)

lab.sh('SERVER-6', 'ip neigh flush all')
lab.sh('CLIENT-16', 'ip neigh flush all')
caps = [('LEAF-3', 4, 'dci', 'udp port 4789'), ('NX-LEAF-02', 3, 'client16-port', ''), ('LEAF-3', 3, 'server6-port', '')]
ctx = [lab.capture(n, i, C / f's1{phase}-{name}.pcap', bpf) for n, i, name, bpf in caps]
for x in ctx:
    x.__enter__()
pings = lab.show('SERVER-6', 'ping -c 3 -i 0.5 10.10.10.116')
if phase != 'a':
    time.sleep(2)
    lab.sh('SERVER-6', 'ip neigh flush all')
    lab.sh('CLIENT-16', 'ip neigh flush all')
    pings += '\n' + lab.show('CLIENT-16', 'ping -c 3 -i 0.5 10.10.10.106')
for x in ctx:
    x.__exit__(None, None, None)
save(f'{R}/pings.txt', pings)
if phase == 'c':                                           # the cache once both hosts have spoken
    save(f'{R}/NX-LEAF-02-arp-suppression-after.txt', lab.show('NX-LEAF-02', 'show ip arp suppression-cache detail'))

for _, _, name, _ in caps:
    save(f'captures/decoded/s1{phase}-{name}.txt', tshark(C / f's1{phase}-{name}.pcap'))
save(f'captures/decoded/s1{phase}-dci-vteps.txt', tshark(C / f's1{phase}-dci.pcap', *VTEP_COLUMNS))
save(f'captures/decoded/s1{phase}-dci-arp-detail.txt', first(C / f's1{phase}-dci.pcap', 'arp'))
save(f'captures/decoded/s1{phase}-dci-icmp-detail.txt', first(C / f's1{phase}-dci.pcap', 'icmp'))

arp_dci = tshark(C / f's1{phase}-dci.pcap', '-Y', 'arp.opcode == 1', '-T', 'fields', '-e', 'ip.src', '-e', 'ip.dst', '-e', 'arp.src.proto_ipv4', '-e', 'arp.dst.proto_ipv4')
print('loss:', [l for l in pings.splitlines() if 'packet loss' in l])
print('ARP requests carried in VXLAN over the inter-fabric link (outer src, outer dst, who asks, for whom):')
print(arp_dci or '  none')
