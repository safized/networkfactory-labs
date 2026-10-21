#!/usr/bin/env bash
# Show the transmit rate of two interfaces on one node, once per second.
# Usage: ./watch-links.sh <container> <ifc> <ifc>
#   Phase A: ./watch-links.sh clab-addpath-a-spine1 eth2 eth3   (spine toward border1, border2)
#   Phase B: ./watch-links.sh clab-addpath-b-leaf1  eth1 eth2   (leaf toward border1, border2)
set -euo pipefail
node=$1; a=$2; b=$3
tx() { sudo docker exec "$node" cat "/sys/class/net/$1/statistics/tx_bytes"; }
pa=$(tx "$a"); pb=$(tx "$b")
printf '%-8s %14s %14s\n' time "$a Mb/s" "$b Mb/s"
while sleep 1; do
  na=$(tx "$a"); nb=$(tx "$b")
  printf '%-8s %14d %14d\n' "$(date +%T)" $(( (na - pa) * 8 / 1000000 )) $(( (nb - pb) * 8 / 1000000 ))
  pa=$na; pb=$nb
done
