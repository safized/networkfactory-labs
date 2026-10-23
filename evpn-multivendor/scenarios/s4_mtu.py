"""Scenario 4a: the inter-fabric link at MTU 1500, the most common VXLAN mistake.

VXLAN adds 50 bytes (outer Ethernet 14 + IP 20 + UDP 8 + VXLAN 8). A host sending a full 1500-byte packet needs
1550 bytes on every underlay link. Here the interconnect is set to 1500 on both ends while everything else stays
at 9216, and the same tests run before and after:

  - pings of 1400 and 1472 bytes with don't-fragment (1428 and 1500 bytes of IP)
  - a 5-second TCP transfer (iperf3)
  - the BGP session over the same link

Two paths: SERVER-6 -> CLIENT-16 (LEAF-3 is the VTEP that sends onto the small link) and
SERVER-8 -> CLIENT-16 (LEAF-5 is the VTEP; LEAF-3 only routes the VXLAN packet onto the small link).
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
from lab import Lab, tshark, save

R, C = 'results/s4a', Path(__file__).parent.parent / 'captures'
DST = '10.10.10.116'
lab = Lab()
lab.sh('CLIENT-16', 'pkill iperf3; iperf3 -s -D')


def tests(tag):
    out = []
    for src in ('SERVER-6', 'SERVER-8'):
        out.append(lab.show(src, f'ping -c 3 -W 1 -M do -s 1400 {DST} | tail -2',
                                 f'ping -c 3 -W 1 -M do -s 1472 {DST} | tail -2',
                                 f'iperf3 -c {DST} -t 5 -f m 2>&1 | grep -E "sender|receiver|error|unable" || echo "(no result: transfer failed)"',
                            timeout=60))
    out.append(lab.show('LEAF-3', 'sudo vtysh -c "show bgp summary" | grep 10.255.0.1'))
    out.append(lab.show('LEAF-3', 'ip -s link show swp4 | head -8'))
    save(f'{R}/{tag}.txt', '\n'.join(out))


def set_mtu(mtu):
    lab.sh('LEAF-3', f'nv set interface swp4 link mtu {mtu} && nv config apply -y >/dev/null 2>&1; ip link show swp4 | grep -o "mtu [0-9]*"')
    lab.sh('LEAF-BORDER', 'configure terminal', 'interface Ethernet1/1', f'mtu {mtu}', 'end')
    time.sleep(5)


tests('1-mtu-9216')
set_mtu(1500)
with lab.capture('LEAF-3', 4, C / 's4a-dci.pcap', 'udp port 4789 or icmp or (ip[6:2] & 0x1fff != 0)', seconds=200):
    tests('2-mtu-1500')
set_mtu(9216)
tests('3-restored')

save('captures/decoded/s4a-dci.txt', tshark(C / 's4a-dci.pcap', '-Y', 'icmp.type == 3 or ip.flags.mf == 1 or ip.frag_offset > 0 or frame.len > 1400'))
save('captures/decoded/s4a-dci-fragments.txt', tshark(C / 's4a-dci.pcap', '-Y', 'ip.flags.mf == 1 or ip.frag_offset > 0', '-T', 'fields',
                                                    '-e', 'frame.number', '-e', 'ip.src', '-e', 'ip.dst', '-e', 'ip.id', '-e', 'ip.frag_offset',
                                                    '-e', 'ip.flags.mf', '-e', 'frame.len'))
for tag in ('1-mtu-9216', '2-mtu-1500', '3-restored'):
    print('=====', tag); print((Path(__file__).parent.parent / R / f'{tag}.txt').read_text())
