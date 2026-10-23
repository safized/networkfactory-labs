"""One handle on the running lab: run commands on any node by name, capture on any link, decode pcaps.

    lab = Lab()
    lab.sh('LEAF-3', 'sudo vtysh -c "show evpn vni"')       # Cumulus
    lab.sh('NX-LEAF-02', 'show nve peers')                  # NX-OS
    lab.sh('SERVER-6', 'ping -c 3 10.10.10.116')            # netshoot host
"""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eve import Eve, HOST
from capture import Capture, tap
import cumulus_first_boot as cfb
import nx as nxos
import host as hst

ROOT = Path(__file__).parent.parent


class Lab:
    def __init__(self):
        nodes = Eve().nodes()
        self.info = {n['name']: n for n in nodes.values()}
        self.id = {n['name']: int(k) for k, n in nodes.items()}
        self.port = {n['name']: int(n['url'].rsplit(':', 1)[1]) for n in nodes.values() if n['status'] >= 2}
        self.open = {}

    def _console(self, name):
        if name in self.open:
            return self.open[name]
        t = self.info[name]['template']
        if t == 'cumulus':
            c, _ = cfb.first_boot(HOST, name, self.port[name])
            c.cmd('export TERM=dumb PAGER=cat; stty cols 250 rows 0', cfb.PROMPT)
            c.drain(0.2); c.send('sudo -v')
            if c.expect([r'password for cumulus: $', cfb.PROMPT], 20)[0] == 0:
                c.send(cfb.LAB_PASS); c.expect([cfb.PROMPT], 20)
            prompt = cfb.PROMPT
        elif t == 'nxosv9k':
            c, prompt = nxos.login(HOST, self.port[name]), nxos.PROMPT
        else:
            c, prompt = hst.shell(name, self.port[name]), hst.PROMPT
        self.open[name] = (c, prompt)
        return self.open[name]

    def sh(self, name, *cmds, timeout=300):
        c, prompt = self._console(name)
        return '\n'.join(c.cmd(x, prompt, timeout=timeout).rstrip() for x in cmds)

    def show(self, name, *cmds, timeout=300):
        """Like sh(), but each output is headed '### NODE# command' so panels.block() can find it."""
        c, prompt = self._console(name)
        return '\n'.join(f'### {name}# {x}\n' + c.cmd(x, prompt, timeout=timeout).rstrip() for x in cmds)

    def tap(self, name, iface):
        return tap(self.id[name], iface)

    def capture(self, name, iface, out, bpf='', seconds=90):
        return Capture(self.tap(name, iface), out, bpf, seconds)


def tshark(pcap, *args):
    """Decode a pcap with tshark 4.6 from the netshoot image (no local install needed)."""
    p = Path(pcap).resolve()
    cmd = ['docker', 'run', '--rm', '-v', f'{p.parent}:/c', 'nicolaka/netshoot', 'tshark', '-r', f'/c/{p.name}', *args]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def first(pcap, display_filter):
    """Full decode (-V) of the first packet matching the filter. (tshark's -c counts packets read, not shown.)"""
    out = tshark(pcap, '-Y', display_filter, '-V')
    i = out.find('\nFrame ', 1)
    return out if i < 0 else out[:i]


def save(path, text):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + '\n')
    return path
