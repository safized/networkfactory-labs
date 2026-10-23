# Lab: multi-vendor EVPN-VXLAN, one tenant across NX-OS and Cumulus Linux

Two leaf-spine fabrics from two vendors, joined by one link, carrying one tenant: a stretched VLAN, routed
subnets on both sides, the same anycast gateway everywhere. Every scenario is driven by script, captured on the
wire, and checked against what the control plane says should happen.

![Lab topology](diagrams/topology.png)

| | NX-OS fabric | Cumulus fabric |
|---|---|---|
| Software | NX-OSv 9000 10.4(2)F | Cumulus VX 5.4.0 |
| Underlay | eBGP over numbered /31 links | eBGP unnumbered (RFC 8950 next hops) |
| ASNs | spines 65200, leaves 65210-65212 | spines 65100, leaves 65103-65105 |
| VTEPs | 10.0.1.10-12 | 10.0.0.3-5 |
| Interconnect | LEAF-BORDER E1/1 | LEAF-3 swp4 |

The interconnect is a plain /31 with one eBGP session carrying IPv4 (loopbacks) and L2VPN EVPN. The spines and the
border leaf pass EVPN routes on with the next hop unchanged, so every leaf builds tunnels straight to every other
leaf, whichever vendor it is.

**Tenant TENANT1:** L3VNI 50001 (VLAN 3001), symmetric IRB, anycast gateway MAC `00:00:5e:00:01:01`, explicit
route targets `65000:<VNI>` on both vendors.

| VLAN | VNI | Subnet | Where | Hosts |
|---|---|---|---|---|
| 10 | 10010 | 10.10.10.0/24 | both fabrics | SERVER-6 (.106), SERVER-8 (.108), CLIENT-16 (.116) |
| 20 | 10020 | 10.20.20.0/24 | Cumulus only | SERVER-7 (.107), SERVER-9 (.109) |
| 30 | 10030 | 10.30.30.0/24 | NX-OS only | SERVER-11 (.111) |

Hosts are [netshoot](https://github.com/nicolaka/netshoot) containers.

## Scenarios

1. **One VLAN across two vendors**, and what ARP suppression really needs ([details](#scenario-1-one-vlan-across-two-vendors))
2. **Anycast gateway and symmetric IRB** between VLAN 20 and VLAN 30 (in progress)
3. **Host mobility**: a host moves from one vendor to the other (in progress)
4. **Break it**: underlay MTU and automatic route targets (in progress)

## Scenario 1: one VLAN across two vendors

SERVER-6 sits behind a Cumulus leaf, CLIENT-16 behind an NX-OS leaf, both in VLAN 10. They ping each other while
three captures run at once: on the inter-fabric link and on both access ports. The scenario runs three times.

```bash
python3 scenarios/s1_stretched_l2.py a   # CLIENT-16 silent, NX-OS suppress-arp off
python3 scenarios/s1_stretched_l2.py b   # CLIENT-16 pinged its gateway once, NX-OS suppress-arp off
python3 scenarios/s1_stretched_l2.py c   # suppress-arp on NX-OS too (TCAM carve + reload first)
```

![Scenario 1](diagrams/s1-arp-suppression.png)

**Phase a: the silent host.** Cumulus has ARP suppression on from the start, yet SERVER-6's ARP for CLIENT-16
crosses the link three times, once per NX-OS VTEP. Neither vendor has a MAC+IP route for 10.10.10.116, because
CLIENT-16 has never sent anything a leaf could learn its IP from. Suppression answers from the EVPN table; an
empty table means a flood.

![No MAC+IP route for CLIENT-16](images/s1a-silent-host.svg)
![One ARP broadcast, one VXLAN copy per remote VTEP](images/s1a-dci-flood.svg)
![The VXLAN headers of one flooded copy](images/s1a-vxlan-headers.svg)

**Phase b: the host has spoken once.** One ping from CLIENT-16 to its gateway, and NX-LEAF-02 advertises a type-2
MAC+IP route. LEAF-3 now answers SERVER-6's ARP itself, in 0.65 ms, and nothing crosses the link. The other
direction still floods: NX-LEAF-02 has no suppression, so CLIENT-16's ARP goes to all three Cumulus VTEPs.

![LEAF-3 learned 10.10.10.116 through EVPN](images/s1b-learned.svg)
![LEAF-3 answers locally](images/s1b-local-answer.svg)
![The Cumulus side is quiet, the NX-OS side floods](images/s1b-dci.svg)

**Phase c: suppression on both vendors.** NX-OS refuses `suppress-arp` until a TCAM region exists for it:

```
ERROR: Please configure TCAM region for Ingress ARP-Ether ACL before configuring ARP supression.
```

The lab borrows space from the IPv4 RACL region (it has no routed ACLs), carves `arp-ether 256 double-wide` and
reloads the three NX-OS leaves. After that, no ARP crosses the link in either direction.

![NX-LEAF-02's ARP suppression cache](images/s1c-suppression-cache.svg)
![Only the pings cross the link](images/s1c-dci.svg)

| Phase | ARP from SERVER-6 crossing the link | ARP from CLIENT-16 crossing the link |
|---|---|---|
| a: silent host, NX-OS suppression off | 3 | 1 (unicast re-check) |
| b: host spoke once, NX-OS suppression off | 0 | 6 (two ARPs x three Cumulus VTEPs) |
| c: suppression on both vendors | 0 | 0 |

**What to take away**

- ARP suppression is only as good as the MAC+IP table behind it. Silent hosts (a printer, a standby VM) are
  flooded the first time, whatever you configure.
- Configure suppression on every leaf. One vendor without it floods the whole VNI, across the interconnect, in
  copies: ingress replication sends one copy per remote VTEP.
- On Nexus 9000, `suppress-arp` needs a TCAM carve and a reload. Plan it into the first deployment, not a change
  window later.
- Observed on NX-OSv 9000 only: when NX-LEAF-02 floods an ARP into VXLAN, the inner Ethernet source is the switch's
  own MAC, while the ARP payload keeps the host's MAC. Hosts learn from the payload, so nothing breaks. This may be
  a quirk of the virtual platform; check it on hardware before relying on it either way.
- NX-OSv 9000 keeps no boot variable by default, so the first `reload` stops at `loader >`. The generated
  configuration sets `boot nxos bootflash:...`.

## Files

| Path | What it is |
|---|---|
| `generate.py` | The source of truth: every address, ASN, VNI and route target, and the generator for all configurations |
| `configs/` | Generated NVUE commands (Cumulus), NX-OS configurations, host addressing |
| `scenarios/` | One script per scenario: set up, capture, collect show commands |
| `shots.py` | Renders `results/` and `captures/decoded/` as the screenshot panels in `images/` |
| `tools/` | Console automation over EVE-NG (telnet), the EVE-NG REST API, remote packet capture |
| `diagrams/` | draw.io sources and exports |

## Build it on EVE-NG

You need EVE-NG with the Cumulus VX 5.4 and Nexus 9000v 10.4 images (not included: get them from NVIDIA and Cisco),
and the netshoot image adapted for EVE-NG (EVE needs an absolute path as the container command):

```bash
docker build -t netshoot-eve:latest -f tools/Dockerfile.netshoot-eve tools/
```

Lab credentials are lab-only values set by the first-boot scripts: `cumulus` / `NetFactory#Lab1` and
`admin` / `NetFactory#Lab1`. Change them if your lab is reachable from anything that matters.

*Configurations are for a lab. Validate them against the documentation of your release before production.*
