# Lab: BGP ADD-PATH, where it changes forwarding and where it only changes what you see

A two-phase lab on FRR (the routing suite inside Cumulus Linux and SONiC), run with containerlab.

| Phase | Design | Question it answers |
|---|---|---|
| **A** | eBGP fabric, one ASN per switch | Does ADD-PATH give a leaf more paths? (It gives visibility, not forwarding. Multipath-relax is what creates ECMP.) |
| **B** | iBGP with an off-path route reflector | What does a route reflector hide, and how does ADD-PATH bring the paths back? (Here it changes forwarding: two links instead of one.) |

![Phase A](images/phase-a-ebgp.svg)
![Phase B](images/phase-b-ibgp-rr.svg)

**Time:** about 90 minutes by hand, or 10 minutes with `verify.py`. **Resources:** 4 vCPU, 4 GB RAM is plenty (seven small containers).

**Validated:** FRR 10.2.1 with containerlab 0.81.1 on Ubuntu 24.04, both phases 6/6 with `verify.py`. Raw outputs are in [`results/`](results/).
**Standards:** ADD-PATH is RFC 7911; route reflection is RFC 4456.

> Commands and expected behavior below are written for FRR 10.x. Outputs differ slightly between releases. **Capture your real outputs**; they become the screenshots for the article and the talk.

---

## 0. Prepare (once)

```bash
sudo apt-get update && sudo apt-get install -y docker.io      # Docker (Ubuntu)
sudo usermod -aG docker $USER                                   # Docker without sudo
bash -c "$(curl -sL https://get.containerlab.dev)"              # containerlab
sudo usermod -aG clab_admins $USER                              # containerlab without sudo
# log out and back in, then:
docker pull quay.io/frrouting/frr:10.2.1
docker pull nicolaka/netshoot:latest
```

Regenerate configurations at any time with `python3 generate.py` (all addressing lives there).

Shortcuts used below (bash):
```bash
v() { docker exec "clab-addpath-$1-$2" vtysh -c "$3"; }      # v a spine1 "show bgp summary"
x() { lab=$1 node=$2; shift 2; docker exec "clab-addpath-$lab-$node" "$@"; }
```

### Automated run (recommended before every presentation)

`verify.py` runs every step below, asserts the expected state, measures traffic and failover, and saves all outputs to `results/<frr-version>/`. Standard library only, no virtual environment needed.

```bash
cd phase-a-ebgp && containerlab deploy -t topology.clab.yml && cd ..
python3 verify.py a
cd phase-a-ebgp && containerlab destroy -t topology.clab.yml --cleanup && cd ..
cd phase-b-ibgp-rr && containerlab deploy -t topology.clab.yml && cd ..
python3 verify.py b --failover
cd phase-b-ibgp-rr && containerlab destroy -t topology.clab.yml --cleanup && cd ..
```

Each phase must start from a fresh deploy, because the steps change the configuration. The manual walkthrough below is the same sequence, for presenting live.

---

## Phase A: eBGP fabric

```bash
cd phase-a-ebgp && containerlab deploy -t topology.clab.yml && cd ..
```

### A1. Baseline: every session up
```bash
v a spine1 "show bgp ipv4 unicast summary"
```
Look for: three neighbors, each with a prefix count (not `Active`/`Connect`). **Capture.**

### A2. What the spine knows
```bash
v a spine1 "show bgp ipv4 unicast 10.99.0.0/24"
x a spine1 ip route show 10.99.0.0/24
```
Look for: **two paths**, AS paths `65021 65099` and `65022 65099`, one marked `best`, **neither marked `multipath`**. The kernel route has **one** next hop.

Why: the two paths come from different neighboring ASes. By default BGP only load-shares across paths whose AS paths are identical. **Capture.**

### A3. Put traffic on it
Terminal 1:
```bash
x a h2 iperf3 -s -D
./watch-links.sh clab-addpath-a-spine1 eth2 eth3
```
Terminal 2:
```bash
x a h1 iperf3 -c 10.99.0.10 -P 8 -t 60
```
Look for: all traffic on one spine link (toward the best path's border), the other near zero. **Capture the watch output.**

### A4. Turn on multipath-relax (the knob that actually creates ECMP here)
```bash
docker exec -it clab-addpath-a-spine1 vtysh
configure terminal
router bgp 65000
 bgp bestpath as-path multipath-relax
end
show bgp ipv4 unicast 10.99.0.0/24
```
Look for: both paths now marked `multipath`; `ip route show 10.99.0.0/24` shows **two next hops**. Re-run the iperf3 test: traffic now spreads over eth2 and eth3, per flow, so not perfectly even. **Capture both.**

Talking point: unequal shares with 8 flows are the hash collisions from the [ECMP article](https://networkfactory.net/articles/one-link-fails-every-job-slows/).

### A5. Turn on ADD-PATH from the spine to the leaf
```bash
docker exec -it clab-addpath-a-spine1 vtysh
configure terminal
router bgp 65000
 address-family ipv4 unicast
  neighbor 10.0.1.0 addpath-tx-all-paths
end
clear bgp ipv4 unicast 10.0.1.0
```
The capability is negotiated when the session opens, so the session is reset. Then:
```bash
v a spine1 "show bgp neighbors 10.0.1.0"        # find the AddPath capability lines
v a leaf1  "show bgp ipv4 unicast 10.99.0.0/24"
x a leaf1  ip route show 10.99.0.0/24
```
Look for: leaf1 now has **two paths** (AS paths `65000 65021 65099` and `65000 65022 65099`, each with an Addpath ID), **both with next hop 10.0.1.1**. The kernel route still has **one** next hop. **Capture all three.**

**The finding:** in an eBGP fabric the spine rewrites the next hop, so extra paths collapse onto the same next hop at the leaf. ADD-PATH adds visibility (the leaf can see both exits and both AS paths) but does not change forwarding. The spine's multipath does the balancing.

### A6 (optional). Failure
Terminal 1: `./failover-test.sh a`. Terminal 2, during the run:
```bash
x a border1 ip link set eth2 down     # border1 loses the gateway
sleep 5; x a border1 ip link set eth2 up
```
Record the packet loss. Repeat with and without multipath-relax.

```bash
cd phase-a-ebgp && containerlab destroy -t topology.clab.yml --cleanup && cd ..
```

---

## Phase B: iBGP with an off-path route reflector

```bash
cd phase-b-ibgp-rr && containerlab deploy -t topology.clab.yml && cd ..
```

### B1. Baseline: underlay and sessions
```bash
v b leaf1 "show ip ospf neighbor"             # rr1, border1, border2 in Full state
v b rr1   "show bgp ipv4 unicast summary"     # three clients established
v b border1 "show bgp ipv4 unicast summary"   # rr1 and dcgw established
```
**Capture.**

### B2. What the route reflector knows, and what it says
```bash
v b rr1   "show bgp ipv4 unicast 10.99.0.0/24"
v b leaf1 "show bgp ipv4 unicast 10.99.0.0/24"
x b leaf1 ip route show 10.99.0.0/24
```
Look for:
- rr1 has **two paths**, next hops 10.255.0.21 (border1) and 10.255.0.22 (border2), one marked best. With equal IGP cost the tie is broken by the originator's router ID, so expect border1.
- leaf1 has **one path**, next hop 10.255.0.21. The kernel route uses **eth1 only**.

The route reflector knows two exits and tells the leaf about one: a reflector advertises only its best path. **Capture.**

### B3. Traffic
```bash
x b h2 iperf3 -s -D
./watch-links.sh clab-addpath-b-leaf1 eth1 eth2     # terminal 1
x b h1 iperf3 -c 10.99.0.10 -P 8 -t 60              # terminal 2
```
Look for: everything on eth1, nothing on eth2, although border2 and its link are healthy. **Capture.**

### B4. Turn on ADD-PATH on the route reflector
```bash
docker exec -it clab-addpath-b-rr1 vtysh
configure terminal
router bgp 65000
 address-family ipv4 unicast
  neighbor 10.255.0.11 addpath-tx-all-paths
end
clear bgp ipv4 unicast 10.255.0.11
```
Then:
```bash
v b leaf1 "show bgp ipv4 unicast 10.99.0.0/24"
x b leaf1 ip route show 10.99.0.0/24
```
Look for: leaf1 now has **two paths**, both `multipath`, next hops 10.255.0.21 and 10.255.0.22. The kernel route has **two next hops, via eth1 and eth2**. Re-run iperf3: traffic is on both links. **Capture all of it; this is the money shot.**

### B5. Selection policy: all paths, or best per AS?
```bash
docker exec -it clab-addpath-b-rr1 vtysh
configure terminal
router bgp 65000
 address-family ipv4 unicast
  no neighbor 10.255.0.11 addpath-tx-all-paths
  neighbor 10.255.0.11 addpath-tx-bestpath-per-AS
end
clear bgp ipv4 unicast 10.255.0.11
```
Look for: leaf1 is back to **one path**. Ask the audience why before revealing it: both paths come from the same neighboring AS (65099), so "best per AS" sends one. The selection policy is a design decision, not a default. Switch back to `addpath-tx-all-paths` afterwards.

### B6. Does ADD-PATH speed up failover? (measured: no, and it can loop)
`python3 verify.py b --failover` fails border1's gateway link three times in each of three cases, with a ping flow (100 per second) that hashes through border1:

| Case | Pings lost (10 ms each) | TTL exceeded |
|---|---|---|
| No ADD-PATH | 15, 15, 15 | 0 |
| ADD-PATH to leaf1 | 14, 15, 14 | 0 |
| ADD-PATH to leaf1 and both borders | 15, 14, 15 | **6, 6, 6** |

What it shows:
- **Convergence did not improve.** Each case loses about 150 ms, the time for border1's withdrawal to travel through rr1 to leaf1. Holding more paths does not shorten that journey.
- **Backup paths at the borders created a transient loop.** Only border1 lacks a backup by default (the reflector never sends border1 its own path back, and its best path comes from border1). With ADD-PATH toward the borders, border1 gets border2's exit, but the only way to reach border2 is back through leaf1, which still sends the flow to border1 until the withdrawal arrives. The packets bounce until their TTL expires: `Time to live exceeded` from 10.0.1.3.
- **Compare phase A:** about 50 ms there, because the spine peers directly with both borders and already holds both paths; a reflector adds a hop of propagation.

Design lesson: a backup path speeds up failover only if it is reachable without going back through the router that is still sending you the traffic, for example over a direct link between the borders. Otherwise, protect the ingress: fast detection (BFD), and next-hop tracking so the leaf drops a path the moment its exit fails.

```bash
cd phase-b-ibgp-rr && containerlab destroy -t topology.clab.yml --cleanup && cd ..
```

---

## What to take away

| Design | Who decides the split | Does ADD-PATH change forwarding? | The knob that matters |
|---|---|---|---|
| eBGP fabric, next hop rewritten | Each hop, using its own multipath | No: paths collapse onto one next hop | `bgp bestpath as-path multipath-relax` on every tier |
| iBGP with an in-path reflector (the spine) | The reflector, which forwards traffic too | Little: the spine balances anyway | iBGP multipath on the reflector |
| iBGP with an off-path reflector | The receiver of the routes | **Yes**: hidden exits become usable next hops | ADD-PATH on the reflector, `maximum-paths ibgp` on clients |
| Overlays with encapsulation (EVPN, MPLS, SRv6) | The ingress, which tunnels to the next hop | **Yes**: next hops are tunnel endpoints | ADD-PATH, plus a selection policy you chose on purpose |

Costs to mention: more paths means more memory and more update processing on every receiver, and the selection policy (all, best-per-AS, best N) decides how much you pay.

## Presenting it (15 minutes)

1. **The puzzle (1 min):** two healthy exits, one carrying all the traffic. Show B3.
2. **The cause (2 min):** a route reflector advertises only its best path. Show B2.
3. **The fix (3 min):** ADD-PATH, live. Show B4, traffic on both links.
4. **The twist (4 min):** run the same feature in an eBGP fabric and nothing changes in forwarding. Show A5. Why: next-hop rewrite. What actually works there: multipath-relax (A4).
5. **The policy (2 min):** best-per-AS sends one path here. Show B5.
6. **The myth (2 min):** "ADD-PATH gives you fast failover." Show B6: same 150 ms, and a loop when backups sit behind the ingress.
7. **The decision table (2 min):** the table above, and the costs.

Equivalent configuration for Cumulus Linux NVUE and Cisco NX-OS is in [EQUIVALENTS.md](EQUIVALENTS.md).

*Configurations are for a lab. Validate behavior against the documentation of the release you run before production.*
