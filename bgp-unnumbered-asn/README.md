# Lab: BGP unnumbered and ASN plans for AI fabrics

Two spines and four leaves in a rail-optimized layout (2 scalable units x 2 rails), running FRR with
**BGP unnumbered**: no IPv4 address on any fabric link. The same fabric is deployed with three ASN plans
to show what each one does after a failure.

```
            spine1                spine2          every leaf: eth1 to spine1, eth2 to spine2
   leaf1   leaf2   leaf3   leaf4                  leaf1 = SU1 rail 1, leaf2 = SU1 rail 2
                                                  leaf3 = SU2 rail 1, leaf4 = SU2 rail 2
```

| Plan | ASNs | What it shows |
|---|---|---|
| `rfc7938` | spines share 65000; leaves 65101, 65102, 65111, 65112 | The recommended plan. After one failure the spine withdraws cleanly; after a double failure there is no path |
| `per-rail` | leaves of the same rail share an ASN (65201, 65202) | Same-rail leaves in different units **cannot reach each other**: loop prevention drops the route. `allowas-in` brings it back by disabling that protection |
| `unique-spines` | spines 65001 and 65002 | Needs multipath-relax for ECMP; after a failure the spine learns **valley paths** through the leaves, which keep a double failure reachable through a leaf |

**Validated:** FRR 10.2.1, containerlab 0.81.1, Ubuntu 24.04: 15/15 checks with `verify.py`.
Outputs are in [`results/`](results/), packet captures in [`captures/`](captures/), screenshots in [`images/`](images/).

## Run it

```bash
docker pull quay.io/frrouting/frr:10.2.1 && docker pull nicolaka/netshoot
python3 generate.py          # configurations for all three plans, derived from position
python3 verify.py            # deploys each plan in turn, checks it, captures, tears down (about 6 minutes)
```

To explore one plan by hand:

```bash
cd plans/rfc7938 && containerlab deploy -t topology.clab.yml
docker exec -it clab-unnum-rfc7938-leaf1 vtysh
#   show bgp ipv4 unicast summary          neighbors are interfaces, not addresses
#   show bgp neighbors eth1                look for "Extended nexthop: advertised and received"
#   show bgp ipv4 unicast 10.255.2.1/32    next hops are fe80:: link-local addresses
docker exec clab-unnum-rfc7938-leaf1 ip route show 10.255.2.1      # nexthop via inet6 fe80::... dev eth1
docker exec clab-unnum-rfc7938-leaf1 ip neigh show                 # 169.254.0.1 PERMANENT entries
containerlab destroy -t topology.clab.yml --cleanup
```

## What to look for

1. **Discovery:** router advertisements (`captures/u-router-advertisements.pcap`) carry each side's link-local address and MAC.
2. **Capability:** the OPEN messages carry *Extended Next Hop Encoding* (capability 5, RFC 8950): IPv4 unicast, next hop AFI IPv6.
3. **Routes:** UPDATEs carry IPv4 prefixes inside `MP_REACH_NLRI` with an IPv6 link-local next hop.
4. **Kernel:** FRR 10.2.1 on a current kernel installs the IPv4 route **with the IPv6 next hop directly** (`via inet6 fe80::...`).
   Older stacks used a placeholder next hop, `169.254.0.1 onlink`, with a permanent neighbor entry; FRR still creates those entries.
5. **ASN plans:** compare `results/per-rail/R2-leaf1-table.txt` (route received, not installed) and
   `results/unique-spines/V2-*.txt` (valley path on spine1) with `results/rfc7938/A1-*.txt`.

A note on churn: `verify.py` counts BGP messages after one link failure. In a six-switch fabric both spine plans
produce the same few updates; path hunting needs many alternative paths, so it grows with fabric size (RFC 7938, section 5.1).

## Files

- `generate.py`: the source of truth and the configuration generator (the automation example in the article)
- `verify.py`: deploy, check, capture, tear down
- `shots.py`: screenshot panels from `results/` and `captures/decoded/` (tshark decodes)

*Configurations are for a lab. Validate them against the documentation of your release before production.*
