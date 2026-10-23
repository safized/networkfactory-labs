"""Scenario 4b: what automatic route targets do in a multi-vendor eBGP fabric.

The lab sets every route target by hand (65000:<VNI>). Here the three Cumulus leaves drop the explicit RT for
VNI 10010 and derive their own (Cumulus/FRR: <own ASN>:<VNI>), while NX-OS keeps 65000:10010.
Then the stretched VLAN is tested inside the Cumulus fabric (SERVER-6 -> SERVER-8) and across vendors
(SERVER-6 -> CLIENT-16), and the route targets on the wire are compared.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
from lab import Lab, save

R = 'results/s4b'
LEAVES = ('LEAF-3', 'LEAF-4', 'LEAF-5')
lab = Lab()


def check(tag):
    save(f'{R}/{tag}.txt', '\n'.join([
        lab.show('LEAF-3', 'sudo vtysh -c "show bgp l2vpn evpn vni 10010" | grep -E "Import Route Target|Export Route Target|^ +[0-9]+:[0-9]+"'),
        lab.show('LEAF-3', 'sudo vtysh -c "show evpn mac vni 10010" | grep -E "50:01:00:(08|10)"'),
        lab.show('NX-LEAF-02', 'show l2route evpn mac all | include 5001.0006|5001.0008'),
        lab.show('NX-LEAF-02', 'show bgp l2vpn evpn 5001.0006.0000 | include Extcommunity'),
        lab.show('SERVER-6', 'ip neigh flush all; ping -c 3 -W 1 10.10.10.108 | tail -2', 'ping -c 3 -W 1 10.10.10.116 | tail -2'),
    ]))


check('1-explicit-rt')
for leaf in LEAVES:
    lab.sh(leaf, 'nv unset evpn vni 10010 route-target && nv config apply -y >/dev/null 2>&1; echo done')
time.sleep(10)
check('2-auto-rt-on-cumulus')
for leaf in LEAVES:
    lab.sh(leaf, 'nv set evpn vni 10010 route-target both 65000:10010 && nv config apply -y >/dev/null 2>&1; echo done')
time.sleep(10)
check('3-restored')
for tag in ('1-explicit-rt', '2-auto-rt-on-cumulus', '3-restored'):
    print('=====', tag); print((Path(__file__).parent.parent / R / f'{tag}.txt').read_text())
