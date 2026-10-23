"""Run commands on a netshoot host over its EVE-NG console.

Usage: python3 host.py NAME 'command' ['command' ...]
"""
import sys
from console import Console
from eve import Eve, HOST

PROMPT = r'\n[\w-]+:[^\n]*# $'


def shell(name, port=None):
    c = Console(HOST, port or Eve().ports()[name])
    c.send('\x03', end=''); c.drain(0.5)
    c.send('trap - DEBUG; unset PROMPT_COMMAND; export PS1="\\h:\\w# " TERM=dumb COLUMNS=250'); c.expect([PROMPT], 20)
    return c


if __name__ == '__main__':
    c = shell(sys.argv[1])
    for line in sys.argv[2:]:
        print(f'### {line}')
        print(c.cmd(line, PROMPT, timeout=300))
    c.close()
