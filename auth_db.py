"""Fase 2 RAVE: cuentas con email + contrasena y perfiles por cuenta.

Sin dependencias nuevas: usa hashlib/scrypt de la stdlib y psycopg2 (ya instalado).
"""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nube_db import _conn as _conn_base
from nube_db import disponible as _disponible

DIAS_SESION = 30
_ITER = 200000


def disponible():
    return _disponible()


def init_db():
    sql = Path(__file__).with_name("schema_fase2.sql").read_text(encoding="utf-8")
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute(sql)
        c.commit()
    finally:
        c.close()


def hash_pass(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def check_pass(pw: str, stored: str) -> bool:
    try:
        algo, it, salt_hex, hash_hex = (stored or "").split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()[:180]


def _codigo_legible() -> str:
    # 4 grupos de 4 caracteres sin ambiguos, ej. K7QF-2M9X-P4RT-8WZ3
    abc = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    grupos = ["".join(secrets.choice(abc) for _ in range(4)) for _ in range(4)]
    return "-".join(grupos)


# ---------- cuentas ----------
def crear_cuenta(email: str, pw: str):
    """Devuelve (cuenta_id, codigo_recuperacion). Lanza ValueError si ya existe."""
    email = _norm_email(email)
    if len(pw or "") < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Correo inválido")
    codigo = _codigo_legible()
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT id FROM cuentas WHERE email=%s", (email,))
        if cur.fetchone():
            raise ValueError("Ese correo ya tiene cuenta")
        cur.execute("INSERT INTO cuentas(email,pass_hash,cod_rec_hash) VALUES(%s,%s,%s) RETURNING id",
                    (email, hash_pass(pw), hash_pass(codigo.replace("-", "").upper())))
        cuenta_id = cur.fetchone()[0]
        c.commit()
        return cuenta_id, codigo
    finally:
        c.close()


def login(email: str, pw: str):
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT id, pass_hash FROM cuentas WHERE email=%s", (_norm_email(email),))
        r = cur.fetchone()
        if not r or not check_pass(pw or "", r[1]):
            return None
        return r[0]
    finally:
        c.close()


def recuperar(email: str, codigo: str, nueva: str):
    """Cambia la contraseña usando el código de recuperación. True si salió bien."""
    if len(nueva or "") < 8:
        return False
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT id, cod_rec_hash FROM cuentas WHERE email=%s", (_norm_email(email),))
        r = cur.fetchone()
        if not r or not r[1]:
            return False
        if not check_pass((codigo or "").replace("-", "").replace(" ", "").upper(), r[1]):
            return False
        cur.execute("UPDATE cuentas SET pass_hash=%s, updated_at=now() WHERE id=%s",
                    (hash_pass(nueva), r[0]))
        cur.execute("DELETE FROM sesiones WHERE cuenta_id=%s", (r[0],))
        c.commit()
        return True
    finally:
        c.close()


def cambiar_email(email: str, codigo: str, nuevo: str):
    """Cambia el correo de la cuenta usando el código de recuperación."""
    nuevo = _norm_email(nuevo)
    if "@" not in nuevo or "." not in nuevo.split("@")[-1]:
        raise ValueError("Correo nuevo inválido")
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT id, cod_rec_hash FROM cuentas WHERE email=%s", (_norm_email(email),))
        r = cur.fetchone()
        if not r or not r[1]:
            return False
        if not check_pass((codigo or "").replace("-", "").replace(" ", "").upper(), r[1]):
            return False
        cur.execute("SELECT id FROM cuentas WHERE email=%s", (nuevo,))
        if cur.fetchone():
            raise ValueError("Ese correo ya tiene cuenta")
        cur.execute("UPDATE cuentas SET email=%s, updated_at=now() WHERE id=%s", (nuevo, r[0]))
        c.commit()
        return True
    finally:
        c.close()


# ---------- sesiones ----------
def crear_sesion(cuenta_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(days=DIAS_SESION)
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("DELETE FROM sesiones WHERE expira < now()")
        cur.execute("INSERT INTO sesiones(token,cuenta_id,expira) VALUES(%s,%s,%s)",
                    (token, cuenta_id, expira))
        c.commit()
        return token
    finally:
        c.close()


def cuenta_de_token(token: str):
    if not token:
        return None
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT c.id, c.email FROM sesiones s JOIN cuentas c ON c.id=s.cuenta_id "
                    "WHERE s.token=%s AND s.expira > now()", (token,))
        r = cur.fetchone()
        return {"id": r[0], "email": r[1]} if r else None
    finally:
        c.close()


def cerrar_sesion(token: str):
    if not token:
        return
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("DELETE FROM sesiones WHERE token=%s", (token,))
        c.commit()
    finally:
        c.close()


# ---------- perfiles de la cuenta ----------
def subir_perfil(cuenta_id: int, perfil: dict):
    vis = perfil.get("visibilidad") or "privado"
    if vis not in ("privado", "publico"):
        vis = "privado"
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO perfiles_cuenta(cuenta_id,nombre,fecha,hora,lugar,lat,lon,tz,tz_name,datos_json,visibilidad) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(cuenta_id,nombre) DO UPDATE SET fecha=EXCLUDED.fecha, hora=EXCLUDED.hora, "
            "lugar=EXCLUDED.lugar, lat=EXCLUDED.lat, lon=EXCLUDED.lon, tz=EXCLUDED.tz, "
            "tz_name=EXCLUDED.tz_name, datos_json=EXCLUDED.datos_json, "
            "visibilidad=EXCLUDED.visibilidad, updated_at=now()",
            (cuenta_id, perfil.get("nombre", "")[:120], perfil.get("fecha", ""), perfil.get("hora", ""),
             perfil.get("lugar", ""), perfil.get("lat"), perfil.get("lon"), perfil.get("tz"),
             perfil.get("tz_name", ""), json.dumps(perfil.get("datos_json") or {}), vis))
        c.commit()
    finally:
        c.close()


def perfiles_de(cuenta_id: int):
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("SELECT nombre,fecha,hora,lugar,lat,lon,tz,tz_name,datos_json,visibilidad,updated_at "
                    "FROM perfiles_cuenta WHERE cuenta_id=%s ORDER BY nombre", (cuenta_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        c.close()


def borrar_perfil(cuenta_id: int, nombre: str):
    c = _conn_base()
    try:
        cur = c.cursor()
        cur.execute("DELETE FROM perfiles_cuenta WHERE cuenta_id=%s AND nombre=%s", (cuenta_id, nombre))
        n = cur.rowcount
        c.commit()
        return n
    finally:
        c.close()
