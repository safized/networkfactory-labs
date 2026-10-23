"""Drive EVE-NG node consoles (telnet) from Python: wait for prompts, send commands, read output.

Standard library only. The telnet handling is deliberately minimal: refuse every option the
server proposes, strip control sequences, and treat the console as a plain byte stream.
"""
import re, socket, time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
ANSI = re.compile(rb'\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\r')


class Console:
    def __init__(self, host, port, timeout=10):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(0.3)
        self.buf = b''

    def _read(self):
        try:
            data = self.s.recv(65536)
        except socket.timeout:
            return False
        if not data:
            raise ConnectionError('console closed')
        out, i = bytearray(), 0
        while i < len(data):                       # answer telnet negotiation: we want nothing
            b = data[i]
            if b == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    reply = WONT if cmd in (DO, DONT) else DONT
                    self.s.sendall(bytes([IAC, reply, data[i + 2]]))
                    i += 3
                    continue
                if cmd == SB:
                    j = data.find(bytes([IAC, SE]), i)
                    i = j + 2 if j >= 0 else len(data)
                    continue
                i += 2
                continue
            out.append(b)
            i += 1
        self.buf += ANSI.sub(b'', bytes(out))
        return True

    def expect(self, patterns, timeout=60):
        """Wait until one of the regex patterns appears; return (index, text up to and including it)."""
        pats = [re.compile(p.encode() if isinstance(p, str) else p) for p in patterns]
        end = time.time() + timeout
        while time.time() < end:
            for n, p in enumerate(pats):
                m = p.search(self.buf)
                if m:
                    text = self.buf[:m.end()].decode(errors='replace')
                    self.buf = self.buf[m.end():]
                    return n, text
            self._read()
        raise TimeoutError(f'none of {patterns} within {timeout}s; last output: {self.buf[-400:].decode(errors="replace")!r}')

    def send(self, line='', end='\r'):
        self.s.sendall(line.encode() + end.encode())

    def drain(self, quiet=0.8):
        """Read until the console has been quiet for `quiet` seconds; return the text."""
        last = time.time()
        while time.time() - last < quiet:
            if self._read():
                last = time.time()
        text, self.buf = self.buf.decode(errors='replace'), b''
        return text

    def cmd(self, line, prompt, timeout=60):
        """Send one command and return its output (without the echoed command and the final prompt)."""
        self.drain(0.2)
        self.send(line)
        _, text = self.expect([prompt], timeout)
        body = text.split('\n', 1)[1] if '\n' in text else ''
        return body.rsplit('\n', 1)[0] if '\n' in body else ''

    def close(self):
        self.s.close()
