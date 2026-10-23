"""Apply configs/nxos/<NODE>.cfg over the console, line by line, and save it. Prints any line NX-OS rejects.

Usage: python3 tools/apply_nxos.py NODE=PORT [NODE=PORT ...]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eve import HOST
from nx import login, PROMPT

CFG = Path(__file__).parent.parent / 'configs' / 'nxos'

for arg in sys.argv[1:]:
    name, port = arg.split('=')
    c = login(HOST, int(port))
    c.cmd('configure terminal', PROMPT)
    errors = []
    for line in (CFG / f'{name}.cfg').read_text().split('\n'):
        if line.strip():
            out = c.cmd(line, PROMPT, timeout=120)
            if out.strip():
                errors.append(f'{line}\n  -> {out.strip()}')
    c.cmd('end', PROMPT)
    out = c.cmd('copy running-config startup-config', PROMPT, timeout=300)
    print(f'== {name}: {len(errors)} messages; save: {out.strip().splitlines()[-1] if out.strip() else ""}')
    for e in errors:
        print(e)
    c.close()
