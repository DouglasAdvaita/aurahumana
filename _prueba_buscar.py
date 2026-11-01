import os, re, socket
from pathlib import Path
from urllib.parse import urlparse, quote

t = Path('.env').read_text(encoding='utf-8', errors='replace')
m = re.search(r'^DATABASE_URL\s*=\s*(.+)\s*$', t, re.M)
dsn = m.group(1).strip().strip('"').strip("'") if m else ''
u = urlparse(dsn)
try:
    ip = socket.getaddrinfo(u.hostname, u.port or 5432, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    dsn = dsn + ('&' if '?' in dsn else '?') + 'hostaddr=' + ip + '&connect_timeout=10'
except Exception:
    pass
os.environ['DATABASE_URL'] = dsn

import auth_db as A
from nube_db import _conn
from app import app

def sesion(email):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT id FROM cuentas WHERE email=%s", (email,))
    cid = cur.fetchone()[0]; c.close()
    return A.crear_sesion(cid)

casos = [('jorgetuso@gmail.com', 'Fabiana', 'Jorge'),
         ('carteraperonalizada.uy@gmail.com', 'Jorge', 'Fabiana')]
for email, base, buscar in casos:
    tok = sesion(email)
    try:
        cli = app.test_client(); cli.set_cookie('dh_sesion', tok)
        r = cli.get('/api/buscar/candidatos?base=' + quote(base) + '&q=' + quote(buscar))
        j = r.get_json()
        cc = j.get('candidatos') or []
        print(email, '| base', base, '| busca', buscar, '| status', r.status_code, '->', len(cc))
        for x in cc[:3]:
            print('    ', x['nombre'], '| comunes', x['comunes'], '| tipo', x['tipo'],
                  '| foto', (x['foto'] or '(sin)')[:30])
        r2 = cli.get('/api/buscar/candidatos?base=' + quote(base))
        j2 = r2.get_json()
        print('    afinidad por canales:', len(j2.get('candidatos') or []),
              '| afines:', len(j2.get('afinidad') or []))
    finally:
        A.cerrar_sesion(tok)
