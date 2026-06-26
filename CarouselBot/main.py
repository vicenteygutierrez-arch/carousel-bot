"""
main.py — Punto de entrada. Corre el bot y el servidor webhook en paralelo.
"""
import threading
import os
from webhook_server import app as flask_app
import bot


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    print(f"🌐 Webhook server en puerto {os.environ.get('PORT', 8080)}")
    bot.main()
