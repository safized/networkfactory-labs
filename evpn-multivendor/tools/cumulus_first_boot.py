"""First login on fresh Cumulus VX 5.x nodes: cumulus/cumulus, forced password change, hostname check.

Usage: python3 cumulus_first_boot.py HOST NAME=PORT [NAME=PORT ...]
The lab password is a lab-only value documented in the README (LAB_PASS below).
"""
import sys
from console import Console

LAB_PASS = 'NetFactory#Lab1'
PROMPT = r'cumulus@[\w-]+:[^\n]*\$ $'


def first_boot(host, name, port):
    c = Console(host, port)
    c.send('\x03', end='')                            # clear anything half-typed or waiting
    c.drain(0.5)
    c.send('')
    n, _ = c.expect([r'login: $', PROMPT], 30)
    if n == 1:
        return c, 'already logged in'
    c.send('cumulus')
    c.expect([r'Password: $'], 15)
    c.send('cumulus')
    n, _ = c.expect([r'[Cc]urrent password: $', r'Login incorrect', PROMPT], 30)
    if n == 1:                                           # password was already changed earlier
        c.expect([r'login: $'], 15)
        c.send('cumulus'); c.expect([r'Password: $'], 15); c.send(LAB_PASS)
        c.expect([PROMPT], 30)
        return c, 'logged in with lab password'
    if n == 0:
        c.send('cumulus')
        c.expect([r'New password: $'], 15); c.send(LAB_PASS)
        c.expect([r'Retype new password: $'], 15); c.send(LAB_PASS)
        n, _ = c.expect([PROMPT, r'login: $'], 30)
        if n == 1:
            c.send('cumulus'); c.expect([r'Password: $'], 15); c.send(LAB_PASS)
            c.expect([PROMPT], 30)
        return c, 'password changed'
    return c, 'logged in'


if __name__ == '__main__':
    host = sys.argv[1]
    for arg in sys.argv[2:]:
        name, port = arg.split('=')
        c, how = first_boot(host, name, int(port))
        ver = c.cmd('grep VERSION_ID /etc/os-release; hostname', PROMPT)
        print(f'{name}: {how}; {ver.strip()}')
        c.close()
