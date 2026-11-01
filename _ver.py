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

c = _conn(); cur = c.cursor()
cur.execute("SELECT id FROM cuentas WHERE email=%s", ('carterapersonalizada.uy@gmail.com',))
cid = cur.fetchone()[0]
cur.execute("SELECT nombre, visibilidad FROM perfiles_cuenta WHERE cuenta_id=%s AND visibilidad='publico' "
            "ORDER BY nombre LIMIT 3", (cid,))
print('cuenta 1 publicos (muestra):', cur.fetchall())
cur.execute("SELECT nombre FROM perfiles_cuenta WHERE cuenta_id=%s AND lower(nombre) IN ('jorge','fabiana')", (cid,))
print('cuenta 1 tiene:', cur.fetchall())
c.close()

tok = A.crear_sesion(cid)
try:
    cli = app.test_client(); cli.set_cookie('dh_sesion', tok)
    mis = cli.get('/api/buscar/mis').get_json().get('mis') or []
    print('mis publicas:', len(mis), mis[:3])
    j = cli.get('/api/buscar/candidatos?base=' + quote(mis[0])).get_json()
    cc = j.get('candidatos') or []
    print('base', mis[0], '-> candidatos', len(cc))
    print('primeros 6:', [(x['nombre'], x['personal'], x['comunes']) for x in cc[:6]])
    print('Jorge aparece:', any(x['nombre'] == 'Jorge' for x in cc),
          '| Fabiana aparece:', any(x['nombre'] == 'Fabiana' for x in cc))
finally:
    A.cerrar_sesion(tok)
