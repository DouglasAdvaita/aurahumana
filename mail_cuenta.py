"""Envío del código de recuperación por correo.

Dos caminos, en este orden:
1. Brevo por API (recomendado): BREVO_API_KEY + BREVO_FROM (remitente verificado).
2. Gmail por SMTP: SMTP_USER + SMTP_PASS (contraseña de aplicación).
   También sirve el relay SMTP de Brevo: SMTP_HOST=smtp-relay.brevo.com,
   SMTP_USER=tu correo de Brevo, SMTP_PASS=la clave SMTP.

Variables de entorno (en local van en .env, en Render en el dashboard):
    BREVO_API_KEY, BREVO_FROM, BREVO_FROM_NAME (opcional)
    SMTP_HOST (por defecto smtp.gmail.com), SMTP_PORT (587),
    SMTP_USER, SMTP_PASS, SMTP_FROM (opcional)

Si no hay ninguna configurada, enviar_codigo() devuelve False sin romper nada.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

ASUNTO = "AlmaVista: tu código de recuperación"


def _texto(codigo: str) -> str:
    return (
        "Hola,\n\n"
        "Ya está creada tu cuenta de AlmaVista. Este es tu código de recuperación:\n\n"
        f"    {codigo}\n\n"
        "Guardalo: con este código podés elegir una contraseña nueva desde la app\n"
        "(Cuenta > Olvidé mi contraseña) si algún día la olvidás.\n\n"
        "Si no creaste ninguna cuenta, ignorá este correo y no compartas el código.\n"
    )


def _smtp_cfg():
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": (os.environ.get("SMTP_USER") or "").strip(),
        "pwd": (os.environ.get("SMTP_PASS") or "").replace(" ", ""),
        "sender": (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip(),
    }


def _brevo_cfg():
    remitente = (os.environ.get("BREVO_FROM") or "").strip()
    return {
        "key": (os.environ.get("BREVO_API_KEY") or "").strip(),
        "from": remitente,
        "name": (os.environ.get("BREVO_FROM_NAME") or "AlmaVista").strip(),
    }


def disponible() -> bool:
    b = _brevo_cfg()
    if b["key"] and b["from"]:
        return True
    c = _smtp_cfg()
    return bool(c["user"] and c["pwd"])


def _enviar_brevo(destinatario: str, codigo: str) -> bool:
    b = _brevo_cfg()
    if not b["key"] or not b["from"] or not destinatario:
        return False
    datos = {
        "sender": {"name": b["name"], "email": b["from"]},
        "to": [{"email": destinatario}],
        "subject": ASUNTO,
        "textContent": _texto(codigo),
    }
    pedido = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(datos).encode("utf-8"),
        headers={
            "api-key": b["key"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=15) as r:
            estado = getattr(r, "status", None) or r.getcode()
            return 200 <= int(estado) < 300
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        print(f"[mail] Brevo rechazó el envío ({e.code}): {detalle}")
        return False
    except Exception as e:
        # Solo el motivo, nunca la clave.
        print(f"[mail] Brevo no respondió: {type(e).__name__}: {e}"[:300])
        return False


def _enviar_smtp(destinatario: str, codigo: str) -> bool:
    c = _smtp_cfg()
    if not c["user"] or not c["pwd"] or not destinatario:
        return False
    msg = EmailMessage()
    msg["Subject"] = ASUNTO
    msg["From"] = c["sender"] or c["user"]
    msg["To"] = destinatario
    msg.set_content(_texto(codigo))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(c["host"], c["port"], timeout=15) as s:
            s.starttls(context=ctx)
            s.login(c["user"], c["pwd"])
            s.send_message(msg)
        return True
    except Exception as e:
        # Solo el motivo, nunca las credenciales: queda en el log de Render.
        print(f"[mail] no se pudo enviar a {destinatario}: {type(e).__name__}: {e}"[:300])
        return False


def enviar_codigo(destinatario: str, codigo: str) -> bool:
    """Manda el código de recuperación al correo. True si salió, False si no."""
    if _brevo_cfg()["key"]:
        return _enviar_brevo(destinatario, codigo)
    return _enviar_smtp(destinatario, codigo)
