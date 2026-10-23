"""Apply configs/cumulus/<NODE>.nvue to a node over its console: nv set ..., then nv config apply.

Usage: python3 tools/apply_cumulus.py NODE=PORT [NODE=PORT ...]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eve import HOST
from cumulus_first_boot import first_boot, PROMPT

CFG = Path(__file__).parent.parent / 'configs' / 'cumulus'

for arg in sys.argv[1:]:
    name, port = arg.split('=')
    c, _ = first_boot(HOST, name, int(port))
    c.cmd('export TERM=dumb; stty cols 250', PROMPT)
    errors = []
    for line in (CFG / f'{name}.nvue').read_text().split('\n'):
        if line.strip():
            out = c.cmd(line, PROMPT, timeout=60)
            if out.strip():
                errors.append(f'{line}\n  -> {out.strip()}')
    out = c.cmd('nv config apply -y 2>&1 | tail -5', PROMPT, timeout=300)
    print(f'== {name}: {len(errors)} messages; apply: {out.strip()}')
    for e in errors:
        print(e)
    c.close()
