"""Fase 1 RAVE: helper Neon/Postgres aditivo (no toca CSV actual)."""
import os

def _dsn():
    return (os.environ.get("DATABASE_URL") or "").strip()

def disponible():
    return bool(_dsn())

def _conn():
    dsn = _dsn()
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL")
    try:
        import psycopg2
        return psycopg2.connect(dsn)
    except ImportError:
        pass
    try:
        import psycopg
        return psycopg.connect(dsn)
    except ImportError:
        raise RuntimeError("Falta driver: pip install psycopg2-binary")

def init_db():
    from pathlib import Path
    sql = Path(__file__).with_name("schema_fase1.sql").read_text(encoding="utf-8")
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute(sql)
        c.commit()
    finally:
        c.close()

def guardar_perfil(device_id, email, perfil: dict):
    """perfil: nombre, fecha, hora, lugar, lat, lon, tz, tz_name, datos_json(dict), visibilidad."""
    if not device_id:
        raise ValueError("Falta device_id")
    vis = perfil.get("visibilidad") or "privado"
    if vis not in ("privado", "publico"):
        vis = "privado"
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("INSERT INTO dispositivos(device_id,email) VALUES(%s,%s) "
                    "ON CONFLICT(device_id) DO UPDATE SET email=COALESCE(EXCLUDED.email,dispositivos.email), updated_at=now()",
                    (device_id, email))
        import json as _j
        cur.execute(
            "INSERT INTO perfiles_nube(device_id,nombre,fecha,hora,lugar,lat,lon,tz,tz_name,datos_json,visibilidad) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(device_id,nombre) DO UPDATE SET fecha=EXCLUDED.fecha, hora=EXCLUDED.hora, "
            "lugar=EXCLUDED.lugar, lat=EXCLUDED.lat, lon=EXCLUDED.lon, tz=EXCLUDED.tz, tz_name=EXCLUDED.tz_name, "
            "datos_json=EXCLUDED.datos_json, visibilidad=EXCLUDED.visibilidad, updated_at=now()",
            (device_id, perfil.get("nombre","")[:120], perfil.get("fecha",""), perfil.get("hora",""),
             perfil.get("lugar",""), perfil.get("lat"), perfil.get("lon"), perfil.get("tz"),
             perfil.get("tz_name",""), _j.dumps(perfil.get("datos_json") or {}), vis))
        c.commit()
    finally:
        c.close()

def mis_perfiles(device_id):
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("SELECT nombre,fecha,hora,lugar,lat,lon,tz,tz_name,datos_json,visibilidad,updated_at "
                    "FROM perfiles_nube WHERE device_id=%s ORDER BY updated_at DESC", (device_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        c.close()


def ping() -> bool:
    """Consulta minima para mantener Neon activo (evita suspend)."""
    if not disponible():
        return False
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        return True
    finally:
        c.close()
