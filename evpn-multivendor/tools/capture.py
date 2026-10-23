"""Packet capture on an EVE-NG link from this machine: tcpdump runs on the EVE host (tcpdump-lab, no root),
the pcap streams back over SSH.

EVE names the host side of every node interface vun0010001<node id, 3 hex><interface index, 2 hex>.
"""
import shlex, subprocess, time
from pathlib import Path

SSH = ['ssh', '-i', str(Path.home() / '.ssh/eve_lab'), '-o', 'BatchMode=yes', 'labops@192.168.1.112']


def tap(node_id, iface):
    return f'vun0010001{node_id:03x}{iface:02x}'


class Capture:
    """with Capture(tap(3, 4), 'out.pcap', 'udp port 4789'): ...run traffic..."""
    def __init__(self, ifname, out, bpf='', seconds=60):
        self.cmd = SSH + [f'timeout {seconds} /usr/local/bin/tcpdump-lab -U -s 0 -i {ifname} -w - {shlex.quote(bpf) if bpf else ""}']
        self.out = Path(out)

    def __enter__(self):
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.out, 'wb')
        self.p = subprocess.Popen(self.cmd, stdout=self.f, stderr=subprocess.DEVNULL)
        time.sleep(2)                                   # let tcpdump attach before traffic starts
        return self

    def __exit__(self, *exc):
        time.sleep(1.5)
        self.p.terminate(); self.p.wait(); self.f.close()
