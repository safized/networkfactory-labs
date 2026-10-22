#!/usr/bin/env python3
"""Run and verify the BGP ADD-PATH lab end to end, capturing every output.

Deploy a phase first (it must start from its initial configuration), then:
    python3 verify.py a            # phase A, eBGP fabric
    python3 verify.py b            # phase B, off-path route reflector
    python3 verify.py b --failover # phase B plus the three-case failover comparison (about 5 minutes)

Each step applies one change, asserts the expected state and saves the raw outputs under
results/<frr-version>/phase-<x>/. The summary table at the end is the lab's test report.
Standard library only: no virtual environment needed. Needs docker access (docker group).
"""
import json, re, subprocess, sys, time
from pathlib import Path

PREFIX, H2_ADDR = '10.99.0.0/24', '10.99.0.10'
HERE = Path(__file__).parent
results = []


def sh(container, *cmd, check=True):
    p = subprocess.run(['docker', 'exec', container, *cmd], capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit(f'command failed in {container}: {" ".join(cmd)}\n{p.stderr}')
    return p.stdout


class Lab:
    def __init__(self, phase):
        self.phase = phase
        ver = re.search(r'FRRouting/([\w.]+)', self.vtysh('leaf1', 'show version')) or re.search(r'FRRouting ([\w.]+)', self.vtysh('leaf1', 'show version'))
        self.out = HERE / 'results' / f'frr-{ver.group(1) if ver else "unknown"}' / f'phase-{phase}'
        self.out.mkdir(parents=True, exist_ok=True)

    def c(self, node):
        return f'clab-addpath-{self.phase}-{node}'

    def vtysh(self, node, *cmds, check=True):
        args = []
        for c in cmds:
            args += ['-c', c]
        return sh(self.c(node), 'vtysh', *args, check=check)

    def configure(self, node, *lines, check=True):
        self.vtysh(node, 'configure terminal', *lines, 'end', check=check)

    def bgp_paths(self, node):
        return json.loads(self.vtysh(node, f'show bgp ipv4 unicast {PREFIX} json')).get('paths', [])

    def kernel_nexthops(self, node):
        r = json.loads(sh(self.c(node), 'ip', '-j', 'route', 'show', PREFIX) or '[]')
        if not r:
            return []
        r = r[0]
        return [(n['gateway'], n['dev']) for n in r['nexthops']] if 'nexthops' in r else [(r['gateway'], r['dev'])]

    def save(self, name, *pairs):
        text = ''
        for node, cmd in pairs:
            out = sh(self.c(node), *cmd.split()) if cmd.startswith('ip ') else self.vtysh(node, cmd)
            text += f'### {node}# {cmd}\n{out}\n'
        (self.out / f'{name}.txt').write_text(text)

    def wait_established(self, node, peers, timeout=90):
        end = time.time() + timeout
        while time.time() < end:
            s = json.loads(self.vtysh(node, 'show bgp ipv4 unicast summary json')).get('peers', {})
            if all(s.get(p, {}).get('state') == 'Established' for p in peers):
                return True
            time.sleep(2)
        return False

    def wait_for(self, fn, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            if fn():
                return True
            time.sleep(1)
        return fn()

    def traffic(self, node, a, b, seconds=8):
        """Run 8 iperf3 streams h1 -> h2 and return the share of bytes leaving node on interface a."""
        sh(self.c('h2'), 'sh', '-c', 'pgrep iperf3 >/dev/null || iperf3 -s -D')
        time.sleep(1)
        tx = lambda i: int(sh(self.c(node), 'cat', f'/sys/class/net/{i}/statistics/tx_bytes'))
        a0, b0 = tx(a), tx(b)
        out = sh(self.c('h1'), 'iperf3', '-c', H2_ADDR, '-P', '8', '-t', str(seconds))
        da, db = tx(a) - a0, tx(b) - b0
        gbps = re.findall(r'SUM\].*?([\d.]+) Gbits/sec.*sender', out)
        return round(100 * da / max(1, da + db)), (gbps[0] if gbps else '?')

    def ping_loss(self, src, fail_node, fail_ifc):
        """Ping 100 per second from h1 (source src) while fail_node loses fail_ifc. Returns (lost, ttl_errors)."""
        p = subprocess.Popen(['docker', 'exec', self.c('h1'), 'ping', '-I', src, '-c', '800', '-i', '0.01', H2_ADDR],
                             stdout=subprocess.PIPE, text=True)
        time.sleep(3)
        sh(self.c(fail_node), 'ip', 'link', 'set', fail_ifc, 'down')
        out = p.communicate()[0]
        sh(self.c(fail_node), 'ip', 'link', 'set', fail_ifc, 'up')
        m = re.search(r'(\d+) packets transmitted, (\d+) received', out)
        return int(m.group(1)) - int(m.group(2)), out.count('Time to live exceeded')


def check(step, ok, detail):
    results.append((step, 'PASS' if ok else 'FAIL', detail))
    print(f'  [{"PASS" if ok else "FAIL"}] {step}: {detail}')


def phase_a():
    L = Lab('a')
    print('Phase A: eBGP fabric')
    ok = L.wait_established('spine1', ['10.0.1.0', '10.0.1.3', '10.0.1.5'])
    L.save('A1-sessions', ('spine1', 'show bgp ipv4 unicast summary'))
    check('A1 sessions', ok, 'spine1 has 3 established eBGP sessions')

    L.wait_for(lambda: len(L.bgp_paths('spine1')) == 2)
    paths, nh = L.bgp_paths('spine1'), L.kernel_nexthops('spine1')
    L.save('A2-spine-before', ('spine1', f'show bgp ipv4 unicast {PREFIX}'), ('spine1', f'ip route show {PREFIX}'))
    check('A2 spine paths', len(paths) == 2 and not any(p.get('multipath') for p in paths) and len(nh) == 1,
          f'{len(paths)} BGP paths, multipath on {sum(bool(p.get("multipath")) for p in paths)}, {len(nh)} kernel next hop')
    share, gbps = L.traffic('spine1', 'eth2', 'eth3')
    (L.out / 'A3-traffic.txt').write_text(f'eth2 share {share}%, {gbps} Gb/s total\n')
    check('A3 traffic', share in (0, 100), f'{share}% on eth2 (all on one uplink), {gbps} Gb/s')

    L.configure('spine1', 'router bgp 65000', 'bgp bestpath as-path multipath-relax')
    L.wait_for(lambda: len(L.kernel_nexthops('spine1')) == 2)
    paths, nh = L.bgp_paths('spine1'), L.kernel_nexthops('spine1')
    L.save('A4-spine-multipath-relax', ('spine1', f'show bgp ipv4 unicast {PREFIX}'), ('spine1', f'ip route show {PREFIX}'))
    share, gbps = L.traffic('spine1', 'eth2', 'eth3')
    (L.out / 'A4-traffic.txt').write_text(f'eth2 share {share}%, {gbps} Gb/s total\n')
    check('A4 multipath-relax', all(p.get('multipath') for p in paths) and len(nh) == 2 and 0 < share < 100,
          f'both paths multipath, {len(nh)} kernel next hops, {share}% on eth2 (per-flow hashing)')

    L.save('A5-leaf-before', ('leaf1', f'show bgp ipv4 unicast {PREFIX}'))
    L.configure('spine1', 'router bgp 65000', 'address-family ipv4 unicast', 'neighbor 10.0.1.0 addpath-tx-all-paths')
    L.vtysh('spine1', 'clear bgp ipv4 unicast 10.0.1.0')
    time.sleep(3)
    L.wait_established('spine1', ['10.0.1.0'])
    L.wait_for(lambda: len(L.bgp_paths('leaf1')) == 2)
    paths, nh = L.bgp_paths('leaf1'), L.kernel_nexthops('leaf1')
    nexthops = {p['nexthops'][0]['ip'] for p in paths}
    L.save('A5-leaf-after-addpath', ('spine1', 'show bgp neighbors 10.0.1.0'), ('leaf1', f'show bgp ipv4 unicast {PREFIX}'), ('leaf1', f'ip route show {PREFIX}'))
    check('A5 ADD-PATH in eBGP', len(paths) == 2 and nexthops == {'10.0.1.1'} and len(nh) == 1,
          f'leaf1 has {len(paths)} paths, BGP next hops {sorted(nexthops)}, {len(nh)} kernel next hop: visibility, not forwarding')

    lost, ttl = L.ping_loss('10.20.1.10', 'border1', 'eth2') if L.kernel_nexthops('spine1') else (None, None)
    (L.out / 'A6-failover.txt').write_text(f'border1 loses its gateway link: {lost} of 800 pings lost (10 ms each), {ttl} TTL errors\n')
    check('A6 failover', lost is not None and lost < 100, f'{lost} pings lost (~{lost * 10} ms)')


def phase_b(failover):
    L = Lab('b')
    print('Phase B: iBGP with an off-path route reflector')
    ok = L.wait_established('rr1', ['10.255.0.11', '10.255.0.21', '10.255.0.22'])
    L.wait_established('wan', ['10.0.3.0', '10.0.3.2'])
    L.save('B1-underlay-and-sessions', ('leaf1', 'show ip ospf neighbor'), ('rr1', 'show bgp ipv4 unicast summary'),
           ('border1', 'show bgp ipv4 unicast summary'), ('wan', 'show bgp ipv4 unicast summary'))
    check('B1 sessions', ok, 'rr1 has 3 established iBGP clients')

    L.wait_for(lambda: len(L.bgp_paths('rr1')) == 2)
    rr, leaf, nh = L.bgp_paths('rr1'), L.bgp_paths('leaf1'), L.kernel_nexthops('leaf1')
    L.save('B2-reflector-hides-a-path', ('rr1', f'show bgp ipv4 unicast {PREFIX}'), ('leaf1', f'show bgp ipv4 unicast {PREFIX}'),
           ('leaf1', f'ip route show {PREFIX}'))
    check('B2 reflector hides a path', len(rr) == 2 and len(leaf) == 1 and len(nh) == 1,
          f'rr1 knows {len(rr)} paths ({" / ".join(p["aspath"]["string"] for p in rr)}), leaf1 receives {len(leaf)}, kernel next hops {nh}')

    def leaf_state(name):
        """Save leaf1's view, measure traffic, return (paths, kernel next hops, eth1 share, Gb/s)."""
        L.save(name, ('leaf1', f'show bgp ipv4 unicast {PREFIX}'), ('leaf1', f'ip route show {PREFIX}'))
        share, gbps = L.traffic('leaf1', 'eth1', 'eth2')
        (L.out / f'{name}-traffic.txt').write_text(f'eth1 share {share}%, {gbps} Gb/s total\n')
        return len(L.bgp_paths('leaf1')), L.kernel_nexthops('leaf1'), share, gbps

    def relax(on):
        L.configure('leaf1', 'router bgp 65000', ('' if on else 'no ') + 'bgp bestpath as-path multipath-relax')
        time.sleep(3)

    def addpath(policy, peers=('10.255.0.11',)):
        L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast',
                    *[f'{"" if policy else "no "}neighbor {p} addpath-tx-{policy or "all-paths"}' for p in peers], check=bool(policy))
        for p in peers:
            L.vtysh('rr1', f'clear bgp ipv4 unicast {p}')
        time.sleep(3)
        L.wait_established('rr1', list(peers))

    n, nh, share, gbps = leaf_state('B3-neither')
    check('B3 neither knob', n == 1 and len(nh) == 1 and share in (0, 100), f'{n} path, {len(nh)} next hop, {share}% on eth1, {gbps} Gb/s')

    relax(True)
    n, nh, share, gbps = leaf_state('B4-relax-only')
    check('B4 multipath-relax only', n == 1 and len(nh) == 1 and share in (0, 100), f'{n} path, {len(nh)} next hop, {share}% on eth1: nothing to balance')
    relax(False)

    addpath('all-paths')
    L.wait_for(lambda: len(L.bgp_paths('leaf1')) == 2)
    L.save('B5-addpath-capability', ('rr1', 'show bgp neighbors 10.255.0.11'))
    n, nh, share, gbps = leaf_state('B5-addpath-only')
    check('B5 ADD-PATH only', n == 2 and len(nh) == 1 and share in (0, 100), f'{n} paths, {len(nh)} next hop, {share}% on eth1: AS paths differ')

    relax(True)
    L.wait_for(lambda: len(L.kernel_nexthops('leaf1')) == 2)
    n, nh, share, gbps = leaf_state('B6-both')
    check('B6 ADD-PATH and multipath-relax', n == 2 and sorted(d for _, d in nh) == ['eth1', 'eth2'] and 0 < share < 100,
          f'{n} paths, kernel via {sorted(d for _, d in nh)}, {share}% / {100 - share}% on eth1 / eth2')

    addpath(None)
    addpath('bestpath-per-AS')
    L.wait_for(lambda: len(L.kernel_nexthops('leaf1')) == 2)
    n, nh = len(L.bgp_paths('leaf1')), L.kernel_nexthops('leaf1')
    L.save('B7-best-per-as', ('leaf1', f'show bgp ipv4 unicast {PREFIX}'), ('leaf1', f'ip route show {PREFIX}'))
    check('B7 best-per-AS policy', n == 2 and len(nh) == 2, f'leaf1 receives {n} paths: the exits lead to different neighbor ASes')
    L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast', 'no neighbor 10.255.0.11 addpath-tx-bestpath-per-AS')

    if not failover:
        return
    # B8, with multipath-relax left on at leaf1: which source address hashes through border1, so the failure hits the ping flow
    for s in range(11, 20):
        sh(L.c('h1'), 'ip', 'addr', 'add', f'10.20.1.{s}/24', 'dev', 'eth1', check=False)
    report = []
    cases = [('no ADD-PATH', []), ('ADD-PATH to leaf1', ['10.255.0.11']), ('ADD-PATH to leaf1 and borders', ['10.255.0.11', '10.255.0.21', '10.255.0.22'])]
    for label, peers in cases:
        for p in ('10.255.0.11', '10.255.0.21', '10.255.0.22'):   # removing an absent setting is an error in FRR: ignore it
            L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast', f'no neighbor {p} addpath-tx-all-paths', check=False)
        if peers:
            L.configure('rr1', 'router bgp 65000', 'address-family ipv4 unicast', *[f'neighbor {p} addpath-tx-all-paths' for p in peers])
        for p in ('10.255.0.11', '10.255.0.21', '10.255.0.22'):
            L.vtysh('rr1', f'clear bgp ipv4 unicast {p}')
        time.sleep(3)
        L.wait_established('rr1', ['10.255.0.11', '10.255.0.21', '10.255.0.22'])
        time.sleep(8)
        src = next(f'10.20.1.{s}' for s in [10] + list(range(11, 20))
                   if 'dev eth1' in sh(L.c('leaf1'), 'ip', 'route', 'get', H2_ADDR, 'from', f'10.20.1.{s}', 'iif', 'eth9', 'ipproto', 'icmp'))
        runs = []
        for _ in range(3):
            runs.append(L.ping_loss(src, 'border1', 'eth2'))
            time.sleep(12)
        report.append(f'{label}: lost {[r[0] for r in runs]} pings (10 ms each), TTL-exceeded errors {[r[1] for r in runs]}')
        print('   ', report[-1])
    (L.out / 'B8-failover.txt').write_text('border1 loses its gateway link; flow hashed through border1\n' + '\n'.join(report) + '\n')
    check('B8 failover comparison', True, 'see B8-failover.txt')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('a', 'b'):
        sys.exit(__doc__)
    phase_a() if sys.argv[1] == 'a' else phase_b('--failover' in sys.argv)
    lab = Lab(sys.argv[1])
    summary = '| Step | Result | Detail |\n|---|---|---|\n' + ''.join(f'| {s} | {r} | {d} |\n' for s, r, d in results)
    (lab.out / 'summary.md').write_text(summary)
    print(f'\n{sum(r == "PASS" for _, r, _ in results)}/{len(results)} passed; outputs in {lab.out}')
    sys.exit(0 if all(r == 'PASS' for _, r, _ in results) else 1)
