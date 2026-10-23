"""Check the lab's healthy baseline. Run it after a build, and after every scenario (they all restore what they break).

Each check prints PASS or FAIL with the evidence; the exit code is the number of failures.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
from lab import Lab, save

lab = Lab()
results, log = [], []


def check(name, ok, evidence):
    results.append(ok)
    log.append(f'{"PASS" if ok else "FAIL"}  {name}\n      {evidence.strip()[:300]}')
    print(log[-1])


# control plane: every leaf sees every other leaf's VTEP, across vendors
nve = lab.sh('NX-LEAF-02', 'show nve peers')
up = set(re.findall(r'nve1\s+(10\.0\.\d\.\d+)\s+Up', nve))
check('NX-LEAF-02 has tunnels to all five other VTEPs', up == {'10.0.0.3', '10.0.0.4', '10.0.0.5', '10.0.1.10', '10.0.1.11'}, ' '.join(sorted(up)))
vni = lab.sh('LEAF-3', 'sudo vtysh -c "show evpn vni 10010"')
remote = set(re.findall(r'^\s+(10\.0\.\d\.\d+)', vni.split('Remote VTEPs for this VNI:')[-1], re.M))
check('LEAF-3 floods VNI 10010 to the other five VTEPs', remote == {'10.0.0.4', '10.0.0.5', '10.0.1.10', '10.0.1.11', '10.0.1.12'}, ' '.join(sorted(remote)))
bgp = lab.sh('LEAF-3', 'sudo vtysh -c "show bgp l2vpn evpn summary"')
check('LEAF-3 EVPN sessions: two spines and LEAF-BORDER established',
      len(re.findall(r'^(SPINE-\d\(swp\d\)|10\.255\.0\.1)\s+4\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\S+\s+\d+', bgp, re.M)) == 3,
      '\n'.join(l for l in bgp.splitlines() if 'SPINE' in l or '10.255' in l))

# configuration that the scenarios change and must restore
check('Explicit route target 65000:10010 on LEAF-3', '65000:10010' in lab.sh('LEAF-3', 'sudo vtysh -c "show bgp l2vpn evpn vni 10010"'), 'import/export')
check('Interconnect MTU 9216 on LEAF-3', 'mtu 9216' in lab.sh('LEAF-3', 'ip link show swp4'), 'swp4')
check('ARP suppression on NX-LEAF-02 VNI 10010', ' SA' in lab.sh('NX-LEAF-02', 'show nve vni 10010'), 'flags')

# one gateway MAC everywhere
for h, gw in (('SERVER-7', '10.20.20.1'), ('SERVER-11', '10.30.30.1'), ('CLIENT-16', '10.10.10.1')):
    out = lab.sh(h, f'ping -c 1 -W 1 {gw} >/dev/null; ip neigh show {gw}')
    check(f'{h} sees the anycast gateway MAC', '00:00:5e:00:01:01' in out, out)

# data plane: same subnet across vendors, routed across vendors, full-size frames
for src, dst, what in (('SERVER-6', '10.10.10.116', 'VLAN 10, Cumulus to NX-OS'),
                       ('CLIENT-16', '10.10.10.108', 'VLAN 10, NX-OS to Cumulus'),
                       ('SERVER-7', '10.30.30.111', 'routed VLAN 20 to VLAN 30, Cumulus to NX-OS'),
                       ('SERVER-11', '10.20.20.109', 'routed VLAN 30 to VLAN 20, NX-OS to Cumulus')):
    lab.sh(src, f'ping -c 2 -W 1 {dst} >/dev/null')      # warm up ARP and host routes
    out = lab.sh(src, f'ping -c 3 -W 1 -M do -s 1472 {dst} | tail -2')
    check(f'{what}: 1500-byte packets, no loss', ' 0% packet loss' in out, out)

save('results/verify.txt', '\n'.join(log))
print(f'\n{results.count(True)}/{len(results)} checks passed')
sys.exit(results.count(False))
