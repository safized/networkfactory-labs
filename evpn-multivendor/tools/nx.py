"""NX-OS consoles: first boot (abort POAP, set the admin password, skip the setup dialog), login, run commands.

Usage: python3 nx.py PORT 'command' ['command' ...]      show commands, or config lines after 'configure terminal'
"""
import sys
from eve import HOST
from console import Console
from cumulus_first_boot import LAB_PASS

PROMPT = r'\n[\w-]+(\([\w-]+\))?# $'
IMAGE = 'nxos64-cs.10.4.2.F.bin'


def login(host, port):
    c = Console(host, port)
    c.send('\x03', end=''); c.drain(0.5)
    c.send('')
    while True:
        n, _ = c.expect([r'\(yes/skip/no\)\[no\]: $',
                         r'enforce secure password standard.*: $',
                         r'Enter the password for "admin": $',
                         r'Confirm the password for "admin": $',
                         r'basic configuration dialog \(yes/no\): $',
                         r'login: $',
                         r'Password: ?$',
                         r'loader > *$',
                         PROMPT], 900)
        if n == 0:
            c.send('yes')
        elif n == 1:
            c.send('yes')
        elif n in (2, 3):
            c.send(LAB_PASS)
        elif n == 4:
            c.send('no')
        elif n == 5:
            c.send('admin')
        elif n == 6:
            c.send(LAB_PASS)
        elif n == 7:                                      # NX-OSv without a saved boot variable stops here
            c.send('boot ' + IMAGE)
        else:
            break
    c.cmd('terminal length 0', PROMPT)
    c.cmd('terminal width 511', PROMPT)
    return c


if __name__ == '__main__':
    c = login(HOST, int(sys.argv[1]))
    for line in sys.argv[2:]:
        print(f'### {line}')
        print(c.cmd(line, PROMPT, timeout=300))
    c.close()
