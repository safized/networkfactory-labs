"""Scenario 3: a host moves from one vendor to the other and back, keeping its MAC and IP.

SERVER-8 (MAC 50:01:00:08:00:00, 10.10.10.108) lives behind Cumulus LEAF-5. A "move" shuts its port down and
brings the same MAC and IP up on SERVER-8-NEW, behind NX-OS NX-LEAF-01, with a gratuitous ARP, the way a
hypervisor announces a migrated VM. Then it moves back.

While it moves, SERVER-6 (Cumulus side) and CLIENT-16 (NX-OS side) ping 10.10.10.108 every 100 ms, and the
interconnect is captured: BGP (to see the EVPN updates) and VXLAN (to see where the traffic goes).

What it shows:
  - the MAC Mobility extended community (RFC 7432 section 7.7): sequence 0 at home, 1 after the move, 2 back
  - both vendors agree on the sequence number and on the new location
  - how many pings each side loses per move

    python3 scenarios/s3_mobility.py a    one move to NX-OS and back, with continuous pings
    python3 scenarios/s3_mobility.py b    flapping: eight moves 5 s apart, then what duplicate detection did
"""
import re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
from lab import Lab, tshark, save
from host import PROMPT as HOST_PROMPT

phase = sys.argv[1]
R, C = f'results/s3{phase}', Path(__file__).parent.parent / 'captures'
MAC, IP, GW = '50:01:00:08:00:00', '10.10.10.108', '10.10.10.1'
lab = Lab()


def state(tag):
    save(f'{R}/{tag}.txt', '\n'.join([
        lab.show('LEAF-3', f'sudo vtysh -c "show evpn mac vni 10010 mac {MAC}"'),
        lab.show('LEAF-3', f'sudo vtysh -c "show bgp l2vpn evpn route type macip" | grep -A3 "{MAC}\\]:\\[32"'),
        lab.show('NX-LEAF-02', 'show l2route evpn mac all | include 5001.0008'),
        lab.show('NX-LEAF-02', 'show bgp l2vpn evpn 5001.0008.0000 | include "Route Dist|Extcommunity|from|AS-Path"'),
    ]))


def go_home():
    lab.sh('SERVER-8-NEW', 'ip addr flush dev eth0; ip link set eth0 down')
    lab.sh('SERVER-8', f'ip link set eth0 up; ip addr replace {IP}/24 dev eth0; ip route replace default via {GW}')
    lab.sh('SERVER-8', f'arping -U -c 2 -I eth0 {IP} >/dev/null 2>&1')


def go_away():
    lab.sh('SERVER-8', 'ip link set eth0 down')
    lab.sh('SERVER-8-NEW', f'ip link set eth0 down; ip link set eth0 address {MAC}; ip link set eth0 up; '
                           f'ip addr replace {IP}/24 dev eth0; ip route replace default via {GW}')
    lab.sh('SERVER-8-NEW', f'arping -U -c 2 -I eth0 {IP} >/dev/null 2>&1')


if phase == 'b':
    go_home(); time.sleep(5)
    state('0-before-flapping')
    for i in range(8):                                     # 4 round trips in about 40 s
        (go_away if i % 2 == 0 else go_home)()
        time.sleep(5)
    time.sleep(5)
    state('1-after-8-moves')
    save(f'{R}/dad.txt', '\n'.join([
        lab.show('LEAF-5', f'sudo vtysh -c "show evpn mac vni 10010 duplicate"', f'sudo vtysh -c "show evpn mac vni 10010 mac {MAC}"'),
        lab.show('LEAF-5', 'sudo vtysh -c "show evpn"'),
        lab.show('NX-LEAF-01', 'show l2rib internal permanently-frozen-list', 'show fabric forwarding ip local-host-db vrf TENANT1 | include 10.10.10.108',
                 'show l2route evpn mac all | include 5001.0008'),
    ]))
    print((Path(__file__).parent.parent / R / 'dad.txt').read_text())
    sys.exit()

# start from home, with a clean sequence: SERVER-8 behind LEAF-5
go_home()
time.sleep(5)
state('0-home')

pingers = {}
for name in ('SERVER-6', 'CLIENT-16'):
    c, _ = lab._console(name)
    c.drain(0.2)
    c.send(f'ping -i 0.1 -c 400 -W 1 {IP}')                # 40 s of pings, read back at the end
    pingers[name] = c

t0 = time.time()
with lab.capture('LEAF-3', 4, C / f's3{phase}-dci.pcap', 'tcp port 179 or udp port 4789', seconds=120):
    time.sleep(8)
    t_away = time.time() - t0
    go_away()
    time.sleep(12)
    state('1-moved-to-nxos')
    t_back = time.time() - t0
    go_home()
    time.sleep(12)
    state('2-back-on-cumulus')
    for name, c in pingers.items():
        _, out = c.expect([HOST_PROMPT], 120)
        save(f'{R}/ping-{name}.txt', out)

summary = [f'move to NX-OS at t={t_away:.1f}s, back to Cumulus at t={t_back:.1f}s (pings every 100 ms)']
for name in pingers:
    out = (Path(__file__).parent.parent / R / f'ping-{name}.txt').read_text()
    seqs = sorted(int(s) for s in re.findall(r'icmp_seq=(\d+)', out))
    lost = sorted(set(range(1, 401)) - set(seqs))
    runs, start = [], None
    for i, s in enumerate(lost):                           # group consecutive lost sequence numbers
        if start is None:
            start = s
        if i + 1 == len(lost) or lost[i + 1] != s + 1:
            runs.append((start, s)); start = None
    summary.append(f'{name}: {len(lost)} lost of 400; gaps (icmp_seq): ' +
                   ', '.join(f'{a}-{b} ({(b - a + 1) * 100} ms)' for a, b in runs))
save(f'{R}/summary.txt', '\n'.join(summary))

save(f'captures/decoded/s3{phase}-bgp-updates.txt', tshark(C / f's3{phase}-dci.pcap', '-Y', 'bgp.type == 2 && bgp.evpn.nlri.mac_addr == 50:01:00:08:00:00', '-V'))
save(f'captures/decoded/s3{phase}-bgp-list.txt', tshark(C / f's3{phase}-dci.pcap', '-Y', 'bgp.type == 2', '-T', 'fields', '-E', 'occurrence=a', '-E', 'aggregator=/', '-e', 'frame.time_relative',
                                              '-e', 'ip.src', '-e', 'ip.dst', '-e', 'bgp.evpn.nlri.mac_addr', '-e', 'bgp.evpn.nlri.ip.addr',
                                              '-e', 'bgp.ext_com_evpn.mmac.seq', '-e', 'bgp.evpn.nlri.rd', '-e', 'bgp.update.path_attribute.type_code'))
print('\n'.join(summary))
