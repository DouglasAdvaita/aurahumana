"""Ayuda local para las cuentas RAVE guardadas en Neon.

No forma parte de la aplicacion: es una herramienta de escritorio para
destrabar una cuenta cuando no se puede entrar desde la web.

Lee DATABASE_URL del entorno o del archivo .env de esta carpeta
(nunca imprime la clave). No requiere instalar nada nuevo.

Uso:
    python cuentas_neon.py listar
    python cuentas_neon.py nueva-clave correo@dominio.com
    python cuentas_neon.py borrar correo@dominio.com

- listar: muestra solo los correos registrados y las fechas (sin claves).
- nueva-clave: pide una contrasena nueva, cierra las sesiones abiertas y
  entrega un codigo de recuperacion nuevo (se muestra una sola vez).
- borrar: elimina la cuenta y todo lo que tenga guardado en la nube.

Nota: los mensajes van sin tildes a proposito, para que se lean bien en la
consola de Windows.
"""
import getpass
import os
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent


def cargar_dsn():
    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if dsn:
        return dsn
    env = CARPETA / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            if clave.strip() == "DATABASE_URL":
                return valor.strip().strip('"').strip("'")
    return ""


def conectar_rapido(dsn):
    """Fuerza IPv4 y limite de espera: en Windows la resolucion IPv6 de Neon
    tarda hasta medio minuto por cada conexion."""
    import socket
    from urllib.parse import urlparse

    u = urlparse(dsn)
    if not u.hostname or "hostaddr=" in dsn:
        return dsn
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 5432, socket.AF_INET, socket.SOCK_STREAM)
        ip = infos[0][4][0]
    except Exception:
        return dsn
    sep = "&" if "?" in dsn else "?"
    return dsn + sep + "hostaddr=" + ip + "&connect_timeout=10"


def tapar(email):
    """Muestra el correo sin exponerlo entero."""
    email = email or ""
    if "@" not in email:
        return "***"
    usuario, dominio = email.split("@", 1)
    return usuario[:3] + "***@" + dominio


def pedir_password():
    p1 = getpass.getpass("Contrasena nueva (minimo 8 caracteres): ")
    if len(p1) < 8:
        print("Muy corta: la contrasena tiene que tener al menos 8 caracteres.")
        return None
    p2 = getpass.getpass("Repetila para confirmar: ")
    if p1 != p2:
        print("No coinciden. No se cambio nada.")
        return None
    return p1


def main():
    dsn = cargar_dsn()
    if not dsn:
        print("Falta DATABASE_URL.\n")
        print("Agrega una linea al archivo .env de esta carpeta:")
        print("  DATABASE_URL=postgresql://usuario:clave@host/base?sslmode=require\n")
        print("La sacas de Neon: panel del proyecto, Connection string.")
        print("Ese archivo no se publica (esta excluido del repositorio).")
        return 2
    os.environ["DATABASE_URL"] = conectar_rapido(dsn)

    import auth_db
    from nube_db import _conn

    if not auth_db.disponible():
        print("No pude leer DATABASE_URL.")
        return 2

    accion = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    correo = auth_db._norm_email(sys.argv[2]) if len(sys.argv) > 2 else ""

    if accion in ("listar", "lista"):
        auth_db.init_db()
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute(
                "SELECT c.email, c.created_at, "
                "(SELECT count(*) FROM perfiles_cuenta p WHERE p.cuenta_id = c.id) "
                "FROM cuentas c ORDER BY c.created_at"
            )
            filas = cur.fetchall()
        finally:
            c.close()
        if not filas:
            print("No hay ninguna cuenta registrada en esta base.")
            return 0
        print("Cuentas registradas: %d\n" % len(filas))
        for email, creada, cuantos in filas:
            fecha = str(creada)[:16] if creada else ""
            print("  %s   (alta %s, %d persona/s en la nube)" % (email, fecha, cuantos))
        return 0

    if accion in ("nuevo-codigo", "nuevo_codigo", "codigo"):
        auth_db.init_db()
        c = _conn()
        try:
            cur = c.cursor()
            if correo:
                cur.execute("SELECT id, email, created_at FROM cuentas WHERE email=%s", (correo,))
            else:
                cur.execute("SELECT id, email, created_at FROM cuentas ORDER BY created_at")
            filas = cur.fetchall()
            if not filas:
                print("No hay ninguna cuenta con ese correo.")
                return 1
            if len(filas) > 1 and not correo:
                filas = [filas[-1]]
                print("Hay varias cuentas: uso la mas reciente (%s, alta %s)."
                      % (tapar(filas[0][1]), str(filas[0][2])[:16]))
            cuenta_id, email, _ = filas[0]
            codigo = auth_db._codigo_legible()
            cur.execute(
                "UPDATE cuentas SET cod_rec_hash=%s, updated_at=now() WHERE id=%s",
                (auth_db.hash_pass(codigo.replace("-", "").upper()), cuenta_id),
            )
            c.commit()
        finally:
            c.close()
        print("\nCuenta: %s" % tapar(email))
        print("Codigo de recuperacion nuevo: %s" % codigo)
        print("Anotalo ahora: no se vuelve a mostrar. La contrasena no cambia.")
        return 0

    # Tambien se puede elegir la cuenta por fecha de alta (sin escribir el correo):
    #   python cuentas_neon.py nueva-clave 2026-10-30
    fecha = ""
    if correo and "@" not in correo and correo[:4].isdigit():
        fecha, correo = correo, ""

    if not correo and not fecha:
        print(__doc__)
        return 2

    if accion in ("nueva-clave", "nueva_clave", "clave"):
        auth_db.init_db()
        c = _conn()
        try:
            cur = c.cursor()
            if fecha:
                cur.execute("SELECT id, email, created_at FROM cuentas "
                            "WHERE created_at::date = %s::date", (fecha,))
                filas = cur.fetchall()
                if not filas:
                    print("No hay ninguna cuenta con alta el %s." % fecha)
                    return 1
                if len(filas) > 1:
                    print("Hay %d cuentas con esa fecha. Indica el correo." % len(filas))
                    return 1
                cuenta_id, email, _ = filas[0]
                print("Cuenta con alta %s: %s" % (fecha, tapar(email)))
            else:
                cur.execute("SELECT id, email FROM cuentas WHERE email=%s", (correo,))
                r = cur.fetchone()
                if not r:
                    print('No existe una cuenta con el correo "%s".' % correo)
                    print("Proba con: python cuentas_neon.py listar")
                    return 1
                cuenta_id = r[0]
            try:
                pw = pedir_password()
            except (EOFError, KeyboardInterrupt):
                print("\nEscribila en una terminal propia, no desde un script.")
                return 1
            if not pw:
                return 1
            codigo = auth_db._codigo_legible()
            cur.execute(
                "UPDATE cuentas SET pass_hash=%s, cod_rec_hash=%s, updated_at=now() WHERE id=%s",
                (auth_db.hash_pass(pw), auth_db.hash_pass(codigo.replace("-", "").upper()), cuenta_id),
            )
            cur.execute("DELETE FROM sesiones WHERE cuenta_id=%s", (cuenta_id,))
            c.commit()
        finally:
            c.close()
        print("\nContrasena cambiada. Ya podes entrar en /cuenta con ese correo.")
        print("Se cerraron las sesiones que estuvieran abiertas.\n")
        print("Codigo de recuperacion nuevo: %s" % codigo)
        print("Anotalo ahora: no se puede volver a mostrar.")
        return 0

    if accion in ("borrar", "eliminar"):
        print('Vas a borrar la cuenta "%s" y todo lo que tenga en la nube.' % correo)
        if input("Escribi BORRAR para confirmar: ").strip() != "BORRAR":
            print("Cancelado. No se borro nada.")
            return 1
        auth_db.init_db()
        c = _conn()
        try:
            cur = c.cursor()
            cur.execute("DELETE FROM cuentas WHERE email=%s", (correo,))
            cuantas = cur.rowcount
            c.commit()
        finally:
            c.close()
        print("Cuenta borrada." if cuantas else "No existia esa cuenta.")
        return 0 if cuantas else 1

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
