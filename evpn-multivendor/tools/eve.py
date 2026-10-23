"""EVE-NG REST API helpers: log in with ~/.config/eve/labops.env and map node names to console ports."""
import http.cookiejar, json, os, ssl, urllib.request
from pathlib import Path

LAB = os.environ.get('EVE_LAB', 'NetworkFactory/CUMULUS-EVPN.unl')


def _env():
    env = {}
    for line in Path(os.path.expanduser('~/.config/eve/labops.env')).read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"\'')
    return env


def _host():
    """EVE-NG address from EVE_HOST, or from EVE_URL in ~/.config/eve/labops.env."""
    if os.environ.get('EVE_HOST'):
        return os.environ['EVE_HOST']
    try:
        return _env()['EVE_URL'].split('://')[-1].split('/')[0].split(':')[0]
    except (OSError, KeyError):
        raise SystemExit('Set EVE_HOST, or EVE_URL in ~/.config/eve/labops.env')


HOST = _host()


class Eve:
    def __init__(self):
        e = _env()
        self.url = e.get('EVE_URL', f'https://{HOST}').replace('http://', 'https://')
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        self.op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                              urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('POST', '/api/auth/login', {'username': e['EVE_USER'], 'password': e['EVE_PASS'], 'html5': '-1'})

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={'Content-Type': 'application/json'})
        try:
            return json.loads(self.op.open(req).read())
        except urllib.error.HTTPError as err:
            return json.loads(err.read())

    def nodes(self):
        return self.call('GET', f'/api/labs/{LAB}/nodes')['data']

    def ports(self):
        """{node name: console port} for running nodes."""
        return {n['name']: int(n['url'].rsplit(':', 1)[1]) for n in self.nodes().values() if n['status'] >= 2}
