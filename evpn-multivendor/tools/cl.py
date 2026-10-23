"""Run shell commands on a Cumulus node over its EVE-NG console.

Usage: python3 cl.py PORT 'command' ['command' ...]
"""
import sys
from console import Console
from cumulus_first_boot import first_boot, PROMPT, LAB_PASS

if __name__ == '__main__':
    port = int(sys.argv[1])
    c, _ = first_boot('192.168.1.112', '', port)
    c.cmd('export TERM=dumb PAGER=cat SYSTEMD_PAGER=; stty cols 250 rows 0', PROMPT)
    c.drain(0.2); c.send('sudo -v')                      # cache sudo credentials once
    if c.expect([r'password for cumulus: $', PROMPT], 20)[0] == 0:
        c.send(LAB_PASS); c.expect([PROMPT], 20)
    for line in sys.argv[2:]:
        print(f'### {line}')
        print(c.cmd(line, PROMPT, timeout=240))
    c.close()
