"""Fase 3 RAVE: log de visitas en Neon (IP completa para pais posterior)."""
from pathlib import Path
from nube_db import _conn, disponible

def init_db():
    sql = Path(__file__).with_name("schema_fase3.sql").read_text(encoding="utf-8")
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute(sql)
        c.commit()
    finally:
        c.close()

def ip_real(request):
    # Render/Gunicorn: IP original en X-Forwarded-For.
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

def registrar(ip, path, user_agent, referer):
    if not disponible():
        return None
    try:
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO visitas(ip,path,user_agent,referer) VALUES(%s,%s,%s,%s) RETURNING id",
                (ip[:80], path[:200], user_agent[:300], referer[:300]),
            )
            vid = cur.fetchone()[0]
            c.commit()
            return vid
        finally:
            c.close()
    except Exception as e:
        # Primera visita tras el deploy: la tabla aun no existe -> crear y reintentar una vez.
        if 'visitas' in str(e).lower() or 'does not exist' in str(e):
            if _asegurar():
                try:
                    return registrar(ip, path, user_agent, referer)
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


def limpiar(dias=90):
    """Borra visitas viejas para no llenar Neon. Llamar de vez en cuando."""
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
            "SELECT id,created_at,ip,path,pais,duracion_seg,user_agent,referer "
            "FROM visitas ORDER BY id DESC LIMIT %s", (int(limit),)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        c.close()
