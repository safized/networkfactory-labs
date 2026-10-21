#!/usr/bin/env bash
# Measure traffic loss from h1 to h2 while a link fails.
# Sends 100 pings per second for 20 seconds; fail a link from another terminal during the run.
# Usage: ./failover-test.sh <a|b>
set -euo pipefail
lab=$1
docker exec "clab-addpath-$lab-h1" ping -c 2000 -i 0.01 -q 10.99.0.10 | tail -2
echo "Each lost packet is about 10 ms of outage."
