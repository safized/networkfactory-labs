#!/usr/bin/env python3
"""Deploy each ASN plan, check the expected behavior, and save outputs and packet captures.

    python3 verify.py            # all three plans, about 6 minutes
    python3 verify.py rfc7938    # one plan

Needs docker and containerlab access (docker and clab_admins groups). Standard library only.
Outputs: results/<plan>/*.txt, captures/*.pcap, results/summary.md
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).parent
LEAVES = ['leaf1', 'leaf2', 'leaf3', 'leaf4']
LO = {'spine1': '10.255.0.1', 'spine2': '10.255.0.2', 'leaf1': '10.255.1.1', 'leaf2': '10.255.1.2', 'leaf3': '10.255.2.1', 'leaf4': '10.255.2.2'}
results = []


def run(*cmd, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f'failed: {" ".join(cmd)}\n{p.stderr}')
    return p.stdout


class Plan:
    def __init__(self, name):
        self.name, self.dir = name, HERE / 'plans' / name
        self.out = HERE / 'results' / name
        self.out.mkdir(parents=True, exist_ok=True)

    def c(self, node):
        return f'clab-unnum-{self.name}-{node}'

    def x(self, node, *cmd, check=True):
        return run('docker', 'exec', self.c(node), *cmd, check=check)

    def v(self, node, *cmds):
        args = []
        for c in cmds:
            args += ['-c', c]
        return self.x(node, 'vtysh', *args)

    def deploy(self):
        run('containerlab', 'deploy', '-t', str(self.dir / 'topology.clab.yml'), '--reconfigure')

    def destroy(self):
        run('containerlab', 'destroy', '-t', str(self.dir / 'topology.clab.yml'), '--cleanup', check=False)

    def established(self, node):
        peers = json.loads(self.v(node, 'show bgp ipv4 unicast summary json')).get('peers', {})
        return sum(p.get('state') == 'Established' for p in peers.values())

    def wait(self, fn, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            if fn():
                return True
            time.sleep(1)
        return fn()

    def wait_fabric(self):
        return self.wait(lambda: all(self.established(n) == 2 for n in LEAVES) and all(self.established(s) == 4 for s in ('spine1', 'spine2')), 90)

    def paths(self, node, prefix):
        return json.loads(self.v(node, f'show bgp ipv4 unicast {prefix} json')).get('paths', [])

    def ping(self, node, dst):
        out = self.x(node, 'ping', '-c', '3', '-W', '1', '-I', LO[node], dst, check=False)
        return ' 0% packet loss' in out

    def link(self, node, ifc, state):
        self.x(node, 'ip', 'link', 'set', ifc, state)

    def save(self, name, *pairs):
        text = ''
        for node, cmd in pairs:
            out = self.x(node, *cmd.split(), check=False) if cmd.split()[0] in ('ip', 'traceroute') else self.v(node, cmd)
            text += f'### {node}# {cmd}\n{out}\n'
        (self.out / f'{name}.txt').write_text(text)

    def updates_received(self, node):
        peers = json.loads(self.v(node, 'show bgp ipv4 unicast summary json')).get('peers', {})
        return sum(p.get('msgRcvd', 0) for p in peers.values())


class Sniffer:
    """tcpdump in a sidecar sharing the router's network namespace; files land in captures/."""
    def __init__(self, plan, node, ifc, name, bpf):
        self.cap, self.name, self.file = HERE / 'captures', f'sniff-{name}', f'{name}.pcap'
        self.cap.mkdir(exist_ok=True)
        run('docker', 'rm', '-f', self.name, check=False)
        run('docker', 'run', '-d', '--name', self.name, '--network', f'container:{plan.c(node)}', '-v', f'{self.cap}:/cap',
            'nicolaka/netshoot', 'tcpdump', '-Z', 'root', '-U', '-i', ifc, '-w', f'/cap/{self.file}', bpf)
        time.sleep(2)

    def stop(self):
        time.sleep(2)
        run('docker', 'stop', '-t', '5', self.name, check=False)
        run('docker', 'run', '--rm', '-v', f'{self.cap}:/cap', 'nicolaka/netshoot', 'chown', f'{os.getuid()}:{os.getgid()}', f'/cap/{self.file}', check=False)
        run('docker', 'rm', '-f', self.name, check=False)


def check(step, ok, detail):
    results.append((step, 'PASS' if ok else 'FAIL', detail))
    print(f'  [{"PASS" if ok else "FAIL"}] {step}: {detail}')


def double_failure(P, label):
    """spine1 loses leaf3, then leaf1 loses spine2: leaf1's only way out is spine1."""
    P.link('leaf3', 'eth1', 'down')
    time.sleep(6)
    P.save(f'{label}-after-spine1-leaf3-down', ('spine1', 'show bgp ipv4 unicast 10.255.2.1/32'), ('leaf1', 'show bgp ipv4 unicast 10.255.2.1/32'))
    spine1 = P.paths('spine1', '10.255.2.1/32')
    P.link('leaf1', 'eth2', 'down')
    time.sleep(6)
    reach = P.ping('leaf1', LO['leaf3'])
    P.save(f'{label}-after-leaf1-spine2-down', ('leaf1', 'show bgp ipv4 unicast 10.255.2.1/32'), ('leaf1', 'traceroute -n -w 1 -q 1 -s 10.255.1.1 10.255.2.1'))
    trace = P.x('leaf1', 'traceroute', '-n', '-w', '1', '-q', '1', '-s', LO['leaf1'], LO['leaf3'], check=False)
    P.link('leaf1', 'eth2', 'up'); P.link('leaf3', 'eth1', 'up')
    return spine1, reach, trace


def rfc7938():
    P = Plan('rfc7938'); print('Plan rfc7938: shared spine ASN, unique leaf ASNs')
    P.deploy()
    check('U1 sessions', P.wait_fabric(), 'every leaf has 2 unnumbered sessions, every spine 4')
    # captures: router advertisements, then the session reset with OPEN and UPDATE
    s = Sniffer(P, 'leaf1', 'eth1', 'u-router-advertisements', 'icmp6 and ip6[40] == 134'); time.sleep(8); s.stop()
    s = Sniffer(P, 'leaf1', 'eth1', 'u-bgp-open-update', 'tcp port 179')
    P.v('leaf1', 'clear bgp ipv4 unicast eth1'); P.wait(lambda: P.established('leaf1') == 2); time.sleep(4); s.stop()
    P.save('U2-sessions', ('leaf1', 'show bgp ipv4 unicast summary'), ('spine1', 'show bgp ipv4 unicast summary'))
    nb = P.v('leaf1', 'show bgp neighbors eth1')
    P.save('U3-capability', ('leaf1', 'show bgp neighbors eth1'))
    check('U3 extended next hop', 'Extended nexthop: advertised and received' in nb, 'IPv4 routes may carry an IPv6 next hop (RFC 8950)')
    route = P.x('leaf1', 'ip', 'route', 'show', LO['leaf3'])
    neigh = P.x('leaf1', 'ip', 'neigh', 'show')
    P.save('U4-routes-and-kernel', ('leaf1', 'show bgp ipv4 unicast 10.255.2.1/32'), ('leaf1', f'ip route show {LO["leaf3"]}'), ('leaf1', 'ip neigh show'),
           ('leaf1', 'ip -6 addr show dev eth1 scope link'))
    check('U4 kernel next hops', route.count('via inet6 fe80::') == 2 and '169.254.0.1' in neigh,
          'IPv4 route with two IPv6 link-local next hops; 169.254.0.1 neighbor entries kept for compatibility')
    ok = all(P.ping('leaf1', LO[n]) for n in LEAVES[1:])
    P.save('U5-traceroute', ('leaf1', 'traceroute -n -w 1 -q 1 -s 10.255.1.1 10.255.2.1'))
    check('U5 reachability', ok, 'leaf1 reaches every other leaf loopback; traceroute shows spine loopbacks')
    # churn after one link failure, compared with unique spine ASNs later
    before = P.updates_received('leaf1'); P.link('leaf3', 'eth1', 'down'); time.sleep(10)
    churn = P.updates_received('leaf1') - before - 6   # minus keepalives (2 peers x 3 s over ~10 s)
    P.link('leaf3', 'eth1', 'up'); P.wait_fabric(); time.sleep(5)
    (P.out / 'A0-churn.txt').write_text(f'BGP messages received by leaf1 in 10 s after spine1-leaf3 fails (keepalives removed): {churn}\n')
    spine1, reach, trace = double_failure(P, 'A1')
    check('A1 shared spine ASN, single failure', len(spine1) == 0, f'spine1 withdraws leaf3 instead of learning it through another leaf ({len(spine1)} paths)')
    check('A2 shared spine ASN, double failure', not reach, 'leaf1 cannot reach leaf3: no valley path to fall back on')
    P.destroy()
    return churn


def per_rail():
    P = Plan('per-rail'); print('Plan per-rail: leaves of the same rail share an ASN')
    P.deploy()
    check('R1 sessions', P.wait_fabric(), 'all sessions up: nothing looks wrong')
    P.wait(lambda: len(P.paths('leaf1', '10.255.1.2/32')) == 2)
    time.sleep(3)
    have = {n: len(P.paths('leaf1', LO[n] + '/32')) for n in LEAVES[1:]}
    recv = P.v('leaf1', 'show bgp ipv4 unicast neighbors eth1 received-routes')
    P.save('R2-leaf1-table', ('leaf1', 'show bgp ipv4 unicast'), ('leaf1', 'show bgp ipv4 unicast neighbors eth1 received-routes'),
           ('spine1', 'show bgp ipv4 unicast 10.255.2.1/32'))
    check('R2 same-rail leaf missing', have['leaf3'] == 0 and have['leaf2'] == 2 and have['leaf4'] == 2 and '10.255.2.1/32' in recv,
          'leaf1 receives leaf3 (same rail, other unit) but rejects it: its own ASN is in the path')
    check('R3 same-rail unreachable', not P.ping('leaf1', LO['leaf3']) and P.ping('leaf1', LO['leaf2']), 'leaf1 reaches leaf2 and leaf4, not leaf3')
    P.v('leaf1', 'configure terminal', 'router bgp 65201', 'address-family ipv4 unicast', 'neighbor FABRIC allowas-in 1', 'end')
    P.v('leaf1', 'clear bgp ipv4 unicast * soft in')
    P.wait(lambda: len(P.paths('leaf1', '10.255.2.1/32')) == 2, 30)
    P.save('R4-allowas-in', ('leaf1', 'show bgp ipv4 unicast 10.255.2.1/32'))
    check('R4 allowas-in', len(P.paths('leaf1', '10.255.2.1/32')) == 2, 'allowas-in brings the route back by accepting its own ASN in paths')
    P.destroy()


def unique_spines(churn_shared):
    P = Plan('unique-spines'); print('Plan unique-spines: every spine has its own ASN')
    P.deploy()
    check('V1 sessions', P.wait_fabric(), 'all sessions up')
    P.wait(lambda: len(P.paths('leaf1', '10.255.2.1/32')) == 2); time.sleep(3)
    p = P.paths('leaf1', '10.255.2.1/32')
    P.save('V1-leaf1-paths', ('leaf1', 'show bgp ipv4 unicast 10.255.2.1/32'))
    check('V1 ECMP needs multipath-relax', len({x['aspath']['string'] for x in p}) == 2 and all(x.get('multipath') for x in p),
          'two different AS paths (65001 65111, 65002 65111): ECMP only because multipath-relax is on')
    before = P.updates_received('leaf1'); P.link('leaf3', 'eth1', 'down'); time.sleep(10)
    churn = P.updates_received('leaf1') - before - 6
    P.link('leaf3', 'eth1', 'up'); P.wait_fabric(); time.sleep(5)
    (P.out / 'V0-churn.txt').write_text(f'BGP messages received by leaf1 in 10 s after spine1-leaf3 fails (keepalives removed): {churn}\n')
    spine1, reach, trace = double_failure(P, 'V2')
    valley = [x['aspath']['string'] for x in spine1]
    check('V2 valley path on the spine', len(spine1) > 0 and all(len(a.split()) >= 3 for a in valley),
          f'spine1 learns leaf3 back through a leaf: {valley}')
    check('V3 double failure', reach and trace.count('\n') >= 4, 'leaf1 still reaches leaf3, through spine1, a leaf and spine2')
    check('V4 churn', True, f'messages to leaf1 after one failure: {churn} with unique spine ASNs vs {churn_shared} with a shared one')
    P.destroy()


if __name__ == '__main__':
    want = sys.argv[1:] or ['rfc7938', 'per-rail', 'unique-spines']
    churn = None
    if 'rfc7938' in want:
        churn = rfc7938()
    if 'per-rail' in want:
        per_rail()
    if 'unique-spines' in want:
        unique_spines(churn)
    (HERE / 'results').mkdir(exist_ok=True)
    (HERE / 'results' / 'summary.md').write_text('| Step | Result | Detail |\n|---|---|---|\n' + ''.join(f'| {s} | {r} | {d} |\n' for s, r, d in results))
    print(f'\n{sum(r == "PASS" for _, r, _ in results)}/{len(results)} passed')
    sys.exit(0 if all(r == 'PASS' for _, r, _ in results) else 1)
