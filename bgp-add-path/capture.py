#!/usr/bin/env python3
"""Record packet captures of the lab's key moments, for Wireshark.

Deploy a phase from its initial configuration first, then:
    python3 capture.py a     # BGP updates to leaf1, without and with ADD-PATH (eBGP fabric)
    python3 capture.py b     # same behind the route reflector, plus the failover micro-loop

tcpdump runs in a netshoot sidecar that shares the router's network namespace, so the FRR
containers need nothing extra. Files land in captures/ and open directly in Wireshark, which
decodes the ADD-PATH path identifiers because the OPEN messages are in the same capture.
"""
import os, subprocess, sys, time
from verify import Lab, sh, H2_ADDR

CAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'captures')


class Sniffer:
    def __init__(self, lab, node, ifc, name, bpf):
        self.name, self.file = f'sniff-{name}', f'{name}.pcap'
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)
        subprocess.run(['docker', 'run', '-d', '--name', self.name, '--network', f'container:{lab.c(node)}',
                        '-v', f'{CAP}:/cap', 'nicolaka/netshoot', 'tcpdump', '-Z', 'root', '-U', '-i', ifc,
                        '-w', f'/cap/{self.file}', bpf], check=True, capture_output=True)
        time.sleep(2)

    def stop(self):
        time.sleep(2)
        subprocess.run(['docker', 'stop', '-t', '5', self.name], capture_output=True)
        subprocess.run(['docker', 'run', '--rm', '-v', f'{CAP}:/cap', 'nicolaka/netshoot', 'chown',
                        f'{os.getuid()}:{os.getgid()}', f'/cap/{self.file}'], capture_output=True)
        subprocess.run(['docker', 'rm', '-f', self.name], capture_output=True)
        print('  saved', os.path.join('captures', self.file))


def reset_and_capture(L, node, ifc, name, reflector, peer, done):
    s = Sniffer(L, node, ifc, name, 'tcp port 179')
    L.vtysh(reflector, f'clear bgp ipv4 unicast {peer}')
    time.sleep(3)
    L.wait_established(reflector, [peer])
    L.wait_for(done)
    s.stop()


def phase_a():
    L = Lab('a')
    L.wait_established('spine1', ['10.0.1.0', '10.0.1.3', '10.0.1.5'])
    L.configure('spine1', 'router bgp 65000', 'bgp bestpath as-path multipath-relax')
    L.wait_for(lambda: len(L.kernel_nexthops('spine1')) == 2)
    reset_and_capture(L, 'leaf1', 'eth1', 'a1-ebgp-without-addpath', 'spine1', '10.0.1.0', lambda: len(L.bgp_paths('leaf1')) == 1)
    L.configure('spine1', 'router bgp 65000', 'address-family ipv4 unicast', 'neighbor 10.0.1.0 addpath-tx-all-paths')
    reset_and_capture(L, 'leaf1', 'eth1', 'a2-ebgp-with-addpath', 'spine1', '10.0.1.0', lambda: len(L.bgp_paths('leaf1')) == 2)


def phase_b():
    L = Lab('b')
    clients = ['10.255.0.11', '10.255.0.21', '10.255.0.22']
    L.wait_established('rr1', clients)
    L.wait_for(lambda: len(L.bgp_paths('rr1')) == 2)
    reset_and_capture(L, 'leaf1', 'eth3', 'b1-rr-without-addpath', 'rr1', '10.255.0.11', lambda: len(L.bgp_paths('leaf1')) == 1)
    L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast', 'neighbor 10.255.0.11 addpath-tx-all-paths')
    reset_and_capture(L, 'leaf1', 'eth3', 'b2-rr-with-addpath', 'rr1', '10.255.0.11', lambda: len(L.kernel_nexthops('leaf1')) == 2)

    # The micro-loop: both knobs on at leaf1, backup paths at the borders, then border1 loses its gateway link
    L.configure('leaf1', 'router bgp 65000', 'bgp bestpath as-path multipath-relax')
    L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast',
                'neighbor 10.255.0.21 addpath-tx-all-paths', 'neighbor 10.255.0.22 addpath-tx-all-paths')
    for p in clients:
        L.vtysh('rr1', f'clear bgp ipv4 unicast {p}')
    time.sleep(3)
    L.wait_established('rr1', clients)
    time.sleep(8)
    for s in range(11, 20):
        sh(L.c('h1'), 'ip', 'addr', 'add', f'10.20.1.{s}/24', 'dev', 'eth1', check=False)
    src = next(f'10.20.1.{s}' for s in [10] + list(range(11, 20))
               if 'dev eth1' in sh(L.c('leaf1'), 'ip', 'route', 'get', H2_ADDR, 'from', f'10.20.1.{s}', 'iif', 'eth9', 'ipproto', 'icmp'))
    s = Sniffer(L, 'leaf1', 'eth1', 'b3-failover-microloop', 'icmp')
    lost, ttl = L.ping_loss(src, 'border1', 'eth2')
    s.stop()
    print(f'  ping from {src}: {lost} lost, {ttl} TTL exceeded')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('a', 'b'):
        sys.exit(__doc__)
    os.makedirs(CAP, exist_ok=True)
    phase_a() if sys.argv[1] == 'a' else phase_b()
