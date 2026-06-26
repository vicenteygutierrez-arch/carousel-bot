"""email_sender.py — Envío de códigos de verificación por Gmail SMTP."""
import os, smtplib, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

def generar_codigo() -> str:
    return str(random.randint(100000, 999999))

def enviar_codigo(email_destino: str, codigo: str) -> bool:
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("[EMAIL] No configuradas")
        return False
    asunto = "🎠 Tu código de activación — CarouselBot"
    cuerpo = f"<h2>CarouselBot 🎠</h2><p>Código: <strong>{codigo}</strong></p><p>Válido 10 minutos</p><p>/codigo {codigo}</p>"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"CarouselBot <{GMAIL_USER}>"
    msg["To"] = email_destino
    msg.attach(MIMEText(cuerpo, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, email_destino, msg.as_string())
        print(f"[EMAIL] Enviado a {email_destino}")
        return True
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        return False
