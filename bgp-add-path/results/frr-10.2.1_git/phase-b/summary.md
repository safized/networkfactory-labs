| Step | Result | Detail |
|---|---|---|
| B1 sessions | PASS | rr1 has 3 established iBGP clients |
| B2 reflector hides a path | PASS | rr1 knows 2 paths, leaf1 receives 1, kernel next hops [('10.0.1.1', 'eth1')] |
| B3 traffic | PASS | 100% on eth1, 0% on eth2 (one link idle), 72.6 Gb/s |
| B4 ADD-PATH changes forwarding | PASS | leaf1 has 2 multipath paths, kernel via ['eth1', 'eth2'], 74% / 26% on eth1 / eth2 |
| B5 best-per-AS policy | PASS | leaf1 receives 1 path: both exits share neighbor AS 65099 |
| B6 failover comparison | PASS | see B6-failover.txt |
