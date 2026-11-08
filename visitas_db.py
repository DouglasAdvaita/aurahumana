"""Fase 3 RAVE: log de visitas en Neon (IP completa para pais posterior)."""
from pathlib import Path
from nube_db import _conn, disponible

def init_db():
    sql = Path(__file__).with_name("schema_fase3.sql").read_text(encoding="utf-8")
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute(sql)
        # Migraciones suaves (columnas nuevas sin romper despliegues viejos).
        try:
            cur.execute("ALTER TABLE visitas ADD COLUMN IF NOT EXISTS es_propia BOOLEAN DEFAULT FALSE")
        except Exception:
            pass
        try:
            cur.execute("""CREATE TABLE IF NOT EXISTS descargas_apk (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                ip TEXT,
                apk TEXT,
                user_agent TEXT
            )""")
        except Exception:
            pass
        c.commit()
    finally:
        c.close()

def ip_real(request):
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return (xff or request.remote_addr or "")[:80]

def _asegurar():
    global _OK
    try:
        _OK
    except NameError:
        globals()['_OK'] = False
    if _OK:
        return True
    try:
        init_db()
        globals()['_OK'] = True
        return True
    except Exception:
        return False

def registrar(ip, path, user_agent, referer, es_propia=False):
    if not disponible():
        return None
    try:
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO visitas(ip,path,user_agent,referer,es_propia) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (ip[:80], path[:200], user_agent[:300], referer[:300], bool(es_propia)),
            )
            vid = cur.fetchone()[0]
            c.commit()
            return vid
        finally:
            c.close()
    except Exception as e:
        if 'visitas' in str(e).lower() or 'does not exist' in str(e) or 'column' in str(e).lower():
            if _asegurar():
                try:
                    return registrar(ip, path, user_agent, referer, es_propia)
                except Exception:
                    return None
        return None

def cerrar(vid, segundos, ip=None):
    if not disponible() or not vid:
        return False
    try:
        segundos = max(0, min(int(segundos or 0), 86400))
    except (ValueError, TypeError):
        return False
    try:
        c = _conn()
        try:
            cur = c.cursor()
            if ip:
                cur.execute(
                    "UPDATE visitas SET duracion_seg=%s, updated_at=now() WHERE id=%s AND ip=%s",
                    (segundos, vid, ip[:80]),
                )
            else:
                cur.execute(
                    "UPDATE visitas SET duracion_seg=%s, updated_at=now() WHERE id=%s",
                    (segundos, vid),
                )
            ok = cur.rowcount > 0
            c.commit()
            return ok
        finally:
            c.close()
    except Exception:
        return False


def registrar_descarga(ip, apk, user_agent):
    if not disponible():
        return None
    try:
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO descargas_apk(ip,apk,user_agent) VALUES(%s,%s,%s) RETURNING id",
                (ip[:80], apk[:200], user_agent[:300]),
            )
            did = cur.fetchone()[0]
            c.commit()
            return did
        finally:
            c.close()
    except Exception as e:
        if 'descargas_apk' in str(e).lower() or 'does not exist' in str(e):
            try:
                init_db()
            except Exception:
                pass
            try:
                c = _conn()
                cur = c.cursor()
                cur.execute(
                    "INSERT INTO descargas_apk(ip,apk,user_agent) VALUES(%s,%s,%s) RETURNING id",
                    (ip[:80], apk[:200], user_agent[:300]),
                )
                did = cur.fetchone()[0]
                c.commit()
                c.close()
                return did
            except Exception:
                return None
        return None

def descargas_totales():
    if not disponible():
        return 0
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT count(*) FROM descargas_apk")
        r = cur.fetchone()
        c.close()
        return r[0] if r and r[0] is not None else 0
    except Exception:
        return 0

def descargas_por_dia(dias=14):
    if not disponible():
        return []
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            "SELECT created_at::date AS d, count(*) FROM descargas_apk "
            "WHERE created_at > now() - (%s || ' days')::interval GROUP BY d ORDER BY d DESC LIMIT %s",
            (str(int(dias)), int(dias)),
        )
        rows = [(r[0].strftime('%d/%m') if hasattr(r[0], 'strftime') else str(r[0])[:10], r[1]) for r in cur.fetchall()]
        c.close()
        return rows
    except Exception:
        return []

def limpiar(dias=90):
    try:
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute("DELETE FROM visitas WHERE created_at < now() - (%s || ' days')::interval", (str(int(dias)),))
            n = cur.rowcount
            c.commit()
            return n
        finally:
            c.close()
    except Exception:
        return 0

def ultimas(limit=200):
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute(
            "SELECT id,created_at,ip,path,pais,duracion_seg,user_agent,referer,es_propia "
            "FROM visitas ORDER BY id DESC LIMIT %s", (int(limit),)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        c.close()
