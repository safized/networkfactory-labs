# Equivalent configuration: Cumulus Linux NVUE and Cisco NX-OS

The lab runs FRR directly. Cumulus Linux uses FRR underneath, so every `vtysh` command in the lab
also works on a Cumulus switch. The lines below show how the same features are set with NVUE and on NX-OS.

> **Not lab-tested here.** Check each line against the documentation of the release you run
> (Cumulus Linux 5.x user guide, "BGP" section; NX-OS Unicast Routing Configuration Guide, "Advanced BGP")
> before using it, and run the lab on that platform before presenting it as validated.

| Feature | FRR / `vtysh` (lab) | Cumulus Linux NVUE | Cisco NX-OS |
|---|---|---|---|
| ECMP across neighbors in different ASes | `bgp bestpath as-path multipath-relax` | `nv set vrf default router bgp path-selection multipath aspath-ignore on` (enabled by default on Cumulus) | `router bgp <asn>` → `bestpath as-path multipath-relax` |
| eBGP / iBGP multipath | `maximum-paths 8` / `maximum-paths ibgp 8` | `nv set vrf default router bgp address-family ipv4-unicast multipaths ebgp 8` / `... multipaths ibgp 8` | `address-family ipv4 unicast` → `maximum-paths 8` / `maximum-paths ibgp 8` |
| Route reflector client | `neighbor X route-reflector-client` | `nv set vrf default router bgp neighbor X address-family ipv4-unicast route-reflector-client on` | `neighbor X` → `address-family ipv4 unicast` → `route-reflector-client` |
| Next-hop-self into iBGP | `neighbor X next-hop-self` | `nv set vrf default router bgp neighbor X address-family ipv4-unicast nexthop-setting self` | `neighbor X` → `address-family ipv4 unicast` → `next-hop-self` |
| ADD-PATH: send all paths | `neighbor X addpath-tx-all-paths` | `nv set vrf default router bgp neighbor X address-family ipv4-unicast add-path-tx all-paths` | See below |
| ADD-PATH: send best per neighboring AS | `neighbor X addpath-tx-bestpath-per-AS` | `nv set vrf default router bgp neighbor X address-family ipv4-unicast add-path-tx best-per-as` | Route-map selection, see below |
| ADD-PATH: receive | On by default | On by default | `capability additional-paths receive` |

## NX-OS ADD-PATH, route reflector side

NX-OS separates the capability (send, receive) from the selection (which paths), which is chosen with a route map:

```
route-map ADDPATH-ALL permit 10
  set path-selection all advertise

router bgp 65000
  address-family ipv4 unicast
    maximum-paths ibgp 8
    additional-paths send
    additional-paths receive
    additional-paths selection route-map ADDPATH-ALL
  neighbor 10.255.0.11
    remote-as 65000
    update-source loopback0
    address-family ipv4 unicast
      route-reflector-client
```

On the client, enable receive (`additional-paths receive` under the address family, or
`capability additional-paths receive` under the neighbor's address family) and `maximum-paths ibgp`.
Verify with `show bgp ipv4 unicast neighbors <peer>` (look for the additional-paths capability) and
`show bgp ipv4 unicast 10.99.0.0/24` (look for several paths with path IDs).

## Running the lab on these platforms

- **Cumulus VX:** NVIDIA publishes Cumulus VX images; containerlab can run Cumulus Linux nodes. Replace the
  FRR nodes with Cumulus VX and apply the NVUE lines above.
- **NX-OS:** the Nexus 9000v image (from your Cisco account) runs in containerlab through vrnetlab. Allow about
  8 GB RAM and several minutes of boot time per node; four nodes need a 32 GB host.

FRR is the fastest way to a working demonstration; the behavior is protocol behavior and carries across platforms.
