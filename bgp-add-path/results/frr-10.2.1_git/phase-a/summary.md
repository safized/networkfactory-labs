| Step | Result | Detail |
|---|---|---|
| A1 sessions | PASS | spine1 has 3 established eBGP sessions |
| A2 spine paths | PASS | 2 BGP paths, multipath on 0, 1 kernel next hop |
| A3 traffic | PASS | 100% on eth2 (all on one uplink), 63.5 Gb/s |
| A4 multipath-relax | PASS | both paths multipath, 2 kernel next hops, 63% on eth2 (per-flow hashing) |
| A5 ADD-PATH in eBGP | PASS | leaf1 has 2 paths, BGP next hops ['10.0.1.1'], 1 kernel next hop: visibility, not forwarding |
| A6 failover | PASS | 6 pings lost (~60 ms) |
