# NetworkFactory labs

Reproducible labs that accompany the writing on [networkfactory.net](https://networkfactory.net).
Most labs run on a laptop with containerlab and open-source routing software; the multi-vendor labs run on EVE-NG
with vendor images you supply. Every lab has a step-by-step guide, packet captures and an automated check.

| Lab | What it shows |
|---|---|
| [bgp-add-path](bgp-add-path/) | When BGP ADD-PATH changes forwarding (off-path route reflector) and when it only adds visibility (eBGP fabric) |
| [bgp-unnumbered-asn](bgp-unnumbered-asn/) | BGP unnumbered on the wire and in the kernel, and three ASN plans for a rail-optimized fabric after failures |
| [evpn-multivendor](evpn-multivendor/) | One EVPN-VXLAN tenant across NX-OS and Cumulus Linux: ARP suppression, symmetric IRB, host mobility, and two mistakes that break it quietly (EVE-NG) |

## Disclaimer

These labs are a personal, educational project, not a product or a service. Code and configurations are provided as is,
without warranty of any kind, under the [MIT License](LICENSE). They are written for lab environments: validate anything
against the documentation of your release, and follow your own change process, before production use. Views are my own and
not those of any employer. Product names are trademarks of their respective owners. Full text: [networkfactory.net/legal](https://networkfactory.net/legal/).
