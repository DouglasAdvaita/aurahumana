"""Envío del código de recuperación por correo (Gmail + contraseña de aplicación).

Variables de entorno (en local van en .env, en Render en el dashboard):
    SMTP_HOST  (por defecto smtp.gmail.com)
    SMTP_PORT  (por defecto 587)
    SMTP_USER  (tu Gmail completo)
    SMTP_PASS  (contraseña de aplicación de 16 letras, sin espacios)
    SMTP_FROM  (opcional, por defecto SMTP_USER)

Si falta SMTP_USER o SMTP_PASS, enviar_codigo() devuelve False sin romper nada.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def _cfg():
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": (os.environ.get("SMTP_USER") or "").strip(),
        "pwd": (os.environ.get("SMTP_PASS") or "").replace(" ", ""),
        "sender": (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip(),
    }


def disponible() -> bool:
    c = _cfg()
    return bool(c["user"] and c["pwd"])


def enviar_codigo(destinatario: str, codigo: str) -> bool:
    """Manda el código de recuperación al correo. True si salió, False si no."""
    c = _cfg()
    if not c["user"] or not c["pwd"] or not destinatario:
        return False
    msg = EmailMessage()
    msg["Subject"] = "AlmaVista: tu código de recuperación"
    msg["From"] = c["sender"] or c["user"]
    msg["To"] = destinatario
    msg.set_content(
        "Hola,\n\n"
        "Este es tu código de recuperación de AlmaVista. Guardalo en un lugar seguro:\n\n"
        f"    {codigo}\n\n"
        "Con este código podés cambiar tu contraseña desde la app\n"
        "(Perfil > Olvidé mi contraseña) si algún día la olvidás.\n\n"
        "Si no creaste ninguna cuenta, ignorá este correo.\n"
    )
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
            s.starttls(context=ctx)
            s.login(c["user"], c["pwd"])
            s.send_message(msg)
        return True
    except Exception:
        return False
