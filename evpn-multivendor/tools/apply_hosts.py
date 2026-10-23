"""Address every host from configs/hosts/<NAME>.sh over its console."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eve import Eve
from host import shell, PROMPT

CFG = Path(__file__).parent.parent / 'configs' / 'hosts'
ports = Eve().ports()
for f in sorted(CFG.glob('*.sh')):
    c = shell(f.stem, ports[f.stem])
    for line in f.read_text().split('\n'):
        if line.strip():
            c.cmd(line, PROMPT)
    print(f.stem, c.cmd('ip -br -4 addr show eth0; ip route show default', PROMPT).strip().replace('\n', ' | '))
    c.close()
