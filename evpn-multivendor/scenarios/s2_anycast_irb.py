"""Scenario 2: one anycast gateway on both vendors, and symmetric IRB between them.

SERVER-7 (VLAN 20, only on the Cumulus fabric, behind LEAF-4) pings SERVER-11 (VLAN 30, only on the NX-OS fabric,
behind LEAF-BORDER). No leaf has both VLANs, so the packet must be routed at the ingress leaf, carried in the L3VNI,
and routed again at the egress leaf.

What it shows:
  - both hosts resolve their gateway to the same MAC, 00:00:5e:00:01:01, one from Cumulus and one from NX-OS
  - the routed packet crosses the interconnect in VNI 50001 (the L3VNI), not in VNI 10020 or 10030
  - the inner Ethernet header carries the two leaves' router MACs, learned from the EVPN Router MAC community
  - TTL drops by two: one routing hop at each end

    python3 scenarios/s2_anycast_irb.py a    cold: LEAF-BORDER has no ARP entry for SERVER-11 (silent destination)
    python3 scenarios/s2_anycast_irb.py b    warm: run straight after a
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
from lab import Lab, tshark, first, save

phase = sys.argv[1]
R, C = f'results/s2{phase}', Path(__file__).parent.parent / 'captures'
VTEP_COLUMNS = ['-o', 'gui.column.format:"No.","%m","Outer src","%Cus:ip.src:1","Outer dst","%Cus:ip.dst:1","VNI","%Cus:vxlan.vni","Inner TTL","%Cus:ip.ttl:2","Info","%i"']
lab = Lab()
if phase == 'a':                                       # forget SERVER-11 at its leaf: the /32 route is withdrawn too
    lab.sh('LEAF-BORDER', 'clear ip arp 10.30.30.111 vrf TENANT1 force-delete')
    save(f'{R}/LEAF-4-route-before.txt', lab.show('LEAF-4', 'sudo vtysh -c "show ip route vrf TENANT1 10.30.30.111"'))

lab.sh('SERVER-7', 'ip neigh flush all')
lab.sh('SERVER-11', 'ip neigh flush all')
with lab.capture('LEAF-3', 4, C / f's2{phase}-dci.pcap', 'udp port 4789'), \
     lab.capture('LEAF-4', 3, C / f's2{phase}-server7-port.pcap'), \
     lab.capture('LEAF-BORDER', 11, C / f's2{phase}-server11-port.pcap'):
    ping = lab.show('SERVER-7', 'ping -c 3 -i 0.5 10.30.30.111')
save(f'{R}/ping.txt', ping)
save(f'{R}/LEAF-4-route-after.txt', lab.show('LEAF-4', 'sudo vtysh -c "show ip route vrf TENANT1 10.30.30.111"'))

save(f'{R}/gateway-macs.txt', '\n'.join([
    lab.show('SERVER-7', 'ip neigh show 10.20.20.1'),
    lab.show('SERVER-11', 'ip neigh show 10.30.30.1'),
    lab.show('LEAF-4', 'nv show interface vlan20 ip vrr'),
    lab.show('LEAF-BORDER', 'show running-config | include anycast-gateway-mac'),
]))
save(f'{R}/LEAF-4-route.txt', lab.show('LEAF-4', 'sudo vtysh -c "show ip route vrf TENANT1 10.30.30.111"'))
save(f'{R}/LEAF-4-evpn-type2.txt', lab.show('LEAF-4', 'sudo vtysh -c "show bgp l2vpn evpn route type macip" | grep -A3 "10.30.30.111"'))
save(f'{R}/LEAF-4-rmac.txt', lab.show('LEAF-4', 'sudo vtysh -c "show evpn rmac vni 50001"'))
save(f'{R}/LEAF-BORDER-route.txt', lab.show('LEAF-BORDER', 'show ip route 10.20.20.107 vrf TENANT1'))
save(f'{R}/LEAF-BORDER-evpn-10.20.20.107.txt', lab.show('LEAF-BORDER', 'show bgp l2vpn evpn 10.20.20.107'))

for name in (f's2{phase}-dci', f's2{phase}-server7-port', f's2{phase}-server11-port'):
    save(f'captures/decoded/{name}.txt', tshark(C / f'{name}.pcap'))
save(f'captures/decoded/s2{phase}-dci-vteps.txt', tshark(C / f's2{phase}-dci.pcap', *VTEP_COLUMNS))
save(f'captures/decoded/s2{phase}-dci-icmp-detail.txt', first(C / f's2{phase}-dci.pcap', 'icmp.type == 8'))
save(f'captures/decoded/s2{phase}-server7-port-detail.txt', first(C / f's2{phase}-server7-port.pcap', 'icmp.type == 8'))

print([l for l in ping.splitlines() if 'loss' in l or 'ttl=' in l][:2])
print((Path(__file__).parent.parent / f'captures/decoded/s2{phase}-dci-vteps.txt').read_text())
