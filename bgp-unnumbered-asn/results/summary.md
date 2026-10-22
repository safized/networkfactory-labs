| Step | Result | Detail |
|---|---|---|
| U1 sessions | PASS | every leaf has 2 unnumbered sessions, every spine 4 |
| U3 extended next hop | PASS | IPv4 routes may carry an IPv6 next hop (RFC 8950) |
| U4 kernel next hops | PASS | IPv4 route with two IPv6 link-local next hops; 169.254.0.1 neighbor entries kept for compatibility |
| U5 reachability | PASS | leaf1 reaches every other leaf loopback; traceroute shows spine loopbacks |
| A1 shared spine ASN, single failure | PASS | spine1 withdraws leaf3 instead of learning it through another leaf (0 paths) |
| A2 shared spine ASN, double failure | PASS | leaf1 cannot reach leaf3: no valley path to fall back on |
| R1 sessions | PASS | all sessions up: nothing looks wrong |
| R2 same-rail leaf missing | PASS | leaf1 receives leaf3 (same rail, other unit) but rejects it: its own ASN is in the path |
| R3 same-rail unreachable | PASS | leaf1 reaches leaf2 and leaf4, not leaf3 |
| R4 allowas-in | PASS | allowas-in brings the route back by accepting its own ASN in paths |
| V1 sessions | PASS | all sessions up |
| V1 ECMP needs multipath-relax | PASS | two different AS paths (65001 65111, 65002 65111): ECMP only because multipath-relax is on |
| V2 valley path on the spine | PASS | spine1 learns leaf3 back through a leaf: ['65101 65002 65111', '65102 65002 65111', '65112 65002 65111'] |
| V3 double failure | PASS | leaf1 still reaches leaf3, through spine1, a leaf and spine2 |
| V4 churn | PASS | messages to leaf1 after one failure: 3 with unique spine ASNs vs 3 with a shared one |
