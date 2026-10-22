| Step | Result | Detail |
|---|---|---|
| B1 sessions | PASS | rr1 has 3 established iBGP clients |
| B2 reflector hides a path | PASS | rr1 knows 2 paths (65098 65100 / 65099 65100), leaf1 receives 1, kernel next hops [('10.0.1.1', 'eth1')] |
| B3 neither knob | PASS | 1 path, 1 next hop, 100% on eth1, 64.0 Gb/s |
| B4 multipath-relax only | PASS | 1 path, 1 next hop, 100% on eth1: nothing to balance |
| B5 ADD-PATH only | PASS | 2 paths, 1 next hop, 100% on eth1: AS paths differ |
| B6 ADD-PATH and multipath-relax | PASS | 2 paths, kernel via ['eth1', 'eth2'], 63% / 37% on eth1 / eth2 |
| B7 best-per-AS policy | PASS | leaf1 receives 2 paths: the exits lead to different neighbor ASes |
| B8 failover comparison | PASS | see B8-failover.txt |
| B9 local failure | PASS | see B9-local-failure.txt |
