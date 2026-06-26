"""
bot.py — Bot de Telegram multi-cliente para generación de carruseles.
Producto comercial: €9/mes via Stan.store.
"""
import os
import json
import tempfile
import subprocess
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

import db
from carousel import generar_desde_texto, generar_desde_foto, PLATFORMS
from transcribe import transcribir_audio

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_ID       = int(os.environ.get("ADMIN_TELEGRAM_ID", "0"))
STAN_STORE_URL = os.environ.get("STAN_STORE_URL", "https://stan.store/tu-producto")
RENDER_SCRIPT  = Path(__file__).parent / "render_pillow.py"

ASK_EMAIL, ASK_BRAND_NAME, ASK_BRAND_COLOR, ASK_BRAND_HANDLE = range(4)

COLORES = {
    "🔵 Azul":    "#1E40AF",
    "⚫ Negro":   "#18181B",
    "🟣 Morado":  "#7C3AED",
    "🟠 Naranja": "#EA580C",
    "🔴 Rojo":    "#DC2626",
    "🟢 Verde":   "#16A34A",
    "🩷 Rosa":    "#DB2777",
    "🟤 Café":    "#92400E",
}


def teclado_plataformas():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📸 Instagram", callback_data="plat_instagram"),
        InlineKeyboardButton("💼 LinkedIn",  callback_data="plat_linkedin"),
        InlineKeyboardButton("📘 Facebook",  callback_data="plat_facebook"),
    ]])


def teclado_colores():
    botones = [InlineKeyboardButton(n, callback_data=f"color_{h}") for n, h in COLORES.items()]
    filas   = [botones[i:i+2] for i in range(0, len(botones), 2)]
    filas.append([InlineKeyboardButton("✏️ Escribir mi color (hex)", callback_data="color_custom")])
    return InlineKeyboardMarkup(filas)


async def enviar_carrusel(update: Update, datos: dict, brand_color: str, platform: str):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path   = Path(tmp)
        slides_path = tmp_path / "slides.json"
        slides_path.write_text(json.dumps(datos, ensure_ascii=False))

        out_dir = tmp_path / "slides"
        r = subprocess.run(
            ["python3", str(RENDER_SCRIPT),
             "--input", str(slides_path),
             "--out",   str(out_dir),
             "--primary", brand_color],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:])

        imagenes = sorted(out_dir.glob("slide_*.png"))
        media    = [InputMediaPhoto(media=open(img, "rb")) for img in imagenes]
        await update.effective_message.reply_media_group(media=media)

    caption  = datos.get("caption", "")
    hashtags = " ".join(datos.get("hashtags", []))
    await update.effective_message.reply_text(
        f"📝 *Pie de foto:*\n{caption}\n\n#️⃣ *Hashtags:*\n{hashtags}",
        parse_mode="Markdown"
    )


# ── Start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    name = update.effective_user.first_name
    db.create_user(tid, update.effective_user.username)
    user = db.get_user(tid)

    if user["active"] and user["onboarded"]:
        await update.message.reply_text(
            f"👋 ¡Hola, {name}!\n\n"
            "Mándame cualquier cosa para crear tu carrusel:\n"
            "• ✍️ *Texto o tema* — ej: 'beneficios del ayuno intermitente'\n"
            "• 🎤 *Mensaje de voz* — explícame la idea hablando\n"
            "• 📷 *Foto* — la analizo y creo el carrusel\n\n"
            f"_Carruseles este mes: {user['carousels_used']}/{user['carousels_limit']}_",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if user["active"] and not user["onboarded"]:
        await update.message.reply_text("¡Ya tienes acceso! ¿Cómo se llama tu marca o proyecto?")
        return ASK_BRAND_NAME

    await update.message.reply_text(
        "👋 *Bienvenido a CarouselBot* 🎠\n\n"
        "Crea carruseles profesionales para Instagram, LinkedIn y Facebook "
        "desde tu celular — con texto, voz o fotos.\n\n"
        "✨ *€9/mes — 100 carruseles mensuales*\n\n"
        "¿Ya compraste? Escribe /activar\n"
        "¿Quieres suscribirte? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🛒 Suscribirme por €9/mes", url=STAN_STORE_URL)
        ]])
    )
    return ConversationHandler.END


# ── Activación ───────────────────────────────────────────────────────────────

async def cmd_activar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✉️ Escribe el *email* con el que compraste en Stan.store:", parse_mode="Markdown")
    return ASK_EMAIL


async def recibir_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    tid   = update.effective_user.id

    if "@" not in email:
        await update.message.reply_text("❌ Email inválido, intenta de nuevo:")
        return ASK_EMAIL

    if db.check_pending_activation(email):
        db.activate_user(tid, email)
        await update.message.reply_text(
            "✅ *¡Acceso activado!*\n\nConfiguremos tu marca. ¿Cómo se llama?",
            parse_mode="Markdown"
        )
        return ASK_BRAND_NAME

    await update.message.reply_text(
        "❌ No encontré compra para ese email.\n"
        "Usa el mismo email con el que compraste en Stan.store. "
        "Si acabas de comprar espera un minuto e intenta de nuevo."
    )
    return ConversationHandler.END


# ── Onboarding de marca ──────────────────────────────────────────────────────

async def recibir_nombre_marca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brand_name"] = update.message.text.strip()
    await update.message.reply_text("🎨 Elige el color principal de tu marca:", reply_markup=teclado_colores())
    return ASK_BRAND_COLOR


async def recibir_color_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "color_custom":
        await query.edit_message_text("✏️ Escribe tu color en hex (ej: #FF5733):")
        return ASK_BRAND_COLOR
    context.user_data["brand_color"] = query.data.replace("color_", "")
    await query.edit_message_text("✅ Color guardado.\n\n📱 ¿Cuál es tu @usuario en redes? (sin el @)")
    return ASK_BRAND_HANDLE


async def recibir_color_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not texto.startswith("#"):
        await update.message.reply_text("❌ Escribe el color en formato hex, ej: #FF5733")
        return ASK_BRAND_COLOR
    context.user_data["brand_color"] = texto
    await update.message.reply_text("✅ Color guardado.\n\n📱 ¿Cuál es tu @usuario en redes? (sin el @)")
    return ASK_BRAND_HANDLE


async def recibir_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid    = update.effective_user.id
    handle = update.message.text.strip().lstrip("@")
    db.update_brand(
        tid,
        color=context.user_data.get("brand_color", "#1E3A5F"),
        name=context.user_data.get("brand_name", "Mi Marca"),
        handle=handle
    )
    await update.message.reply_text(
        "🎉 *¡Marca configurada!*\n\n"
        "Ahora crea tu primer carrusel enviándome:\n"
        "• ✍️ Un *texto o tema*\n"
        "• 🎤 Un *mensaje de voz*\n"
        "• 📷 Una *foto*\n\n"
        "¡Empieza cuando quieras!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── Generación ───────────────────────────────────────────────────────────────

async def _check_usuario(update: Update) -> tuple:
    tid = update.effective_user.id
    ok, razon = db.can_create(tid)
    if not ok:
        if razon == "not_active":
            await update.effective_message.reply_text(
                "🔒 Necesitas suscribirte primero.\nEscribe /activar si ya compraste.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛒 Suscribirme €9/mes", url=STAN_STORE_URL)
                ]])
            )
        elif razon == "not_onboarded":
            await update.effective_message.reply_text("⚙️ Primero configura tu marca con /start")
        elif razon == "limit_reached":
            await update.effective_message.reply_text(
                "📊 Alcanzaste el límite de 100 carruseles este mes. Se renueva el próximo mes."
            )
    return ok, razon


async def seleccionar_plataforma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    plataforma = query.data.replace("plat_", "")
    tid        = update.effective_user.id
    user       = db.get_user(tid)
    tipo       = context.user_data.get("pending_type", "text")
    contenido  = context.user_data.get("pending_content", "")
    foto_bytes = context.user_data.get("pending_photo")

    msg = await query.edit_message_text("⏳ Generando tu carrusel con IA...")
    try:
        if tipo == "photo" and foto_bytes:
            await msg.edit_text("🔍 Analizando tu imagen con IA...")
            datos = generar_desde_foto(foto_bytes, contenido, plataforma)
        else:
            await msg.edit_text("🔍 Investigando el tema...")
            datos = generar_desde_texto(contenido, plataforma)

        await msg.edit_text("🎨 Renderizando las imágenes...")
        await enviar_carrusel(update, datos, user["brand_color"], plataforma)
        db.increment_usage(tid, contenido or "foto", plataforma)
        user = db.get_user(tid)
        await msg.delete()
        await update.effective_message.reply_text(
            f"✅ *Carrusel listo* para {PLATFORMS[plataforma]['name']}!\n"
            f"_Carruseles este mes: {user['carousels_used']}/{user['carousels_limit']}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}\n\nIntenta de nuevo.")


async def procesar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok:
        return
    context.user_data["pending_content"] = update.message.text
    context.user_data["pending_type"]    = "text"
    await update.message.reply_text("📱 ¿Para qué plataforma?", reply_markup=teclado_plataformas())


async def procesar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok:
        return
    msg = await update.message.reply_text("🎤 Transcribiendo tu audio...")
    try:
        voice      = update.message.voice or update.message.audio
        archivo    = await voice.get_file()
        audio_bytes = await archivo.download_as_bytearray()
        texto      = transcribir_audio(bytes(audio_bytes))
        if not texto:
            await msg.edit_text("❌ No pude entender el audio. Intenta de nuevo.")
            return
        context.user_data["pending_content"] = texto
        context.user_data["pending_type"]    = "text"
        await msg.edit_text(
            f"🎤 Escuché: _{texto}_\n\n📱 ¿Para qué plataforma?",
            parse_mode="Markdown",
            reply_markup=teclado_plataformas()
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error con el audio: {e}")


async def procesar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok:
        return
    msg = await update.message.reply_text("📷 Recibiendo imagen...")
    try:
        foto       = update.message.photo[-1]
        archivo    = await foto.get_file()
        foto_bytes = await archivo.download_as_bytearray()
        context.user_data["pending_photo"]   = bytes(foto_bytes)
        context.user_data["pending_content"] = update.message.caption or ""
        context.user_data["pending_type"]    = "photo"
        await msg.edit_text("📷 Imagen recibida. ¿Para qué plataforma?", reply_markup=teclado_plataformas())
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


# ── Comandos utiles ──────────────────────────────────────────────────────────

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Usa /start para comenzar.")
        return
    estado = "✅ Activo" if user["active"] else "🔒 Sin suscripción"
    await update.message.reply_text(
        f"📊 *Tu cuenta*\n\nEstado: {estado}\nMarca: {user['brand_name'] or '—'}\n"
        f"Color: {user['brand_color']}\nCarruseles este mes: {user['carousels_used']}/{user['carousels_limit']}",
        parse_mode="Markdown"
    )


async def cmd_configurar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user or not user["active"]:
        await update.message.reply_text("🔒 Activa tu suscripción primero con /activar")
        return ConversationHandler.END
    await update.message.reply_text("¿Cómo quieres que se llame tu marca?")
    return ASK_BRAND_NAME


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    users = db.list_users(10)
    lineas = [
        "📊 *Panel Admin*\n",
        f"👥 Usuarios: {stats['total_users']}",
        f"✅ Activos: {stats['active_users']}",
        f"🎠 Carruseles: {stats['total_carousels']}\n",
        "*Últimos 10:*"
    ]
    for u in users:
        lineas.append(f"{'✅' if u['active'] else '⏳'} @{u['username'] or '?'} — {u['carousels_used']}/{u['carousels_limit']}")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",      start),
            CommandHandler("activar",    cmd_activar),
            CommandHandler("configurar", cmd_configurar),
        ],
        states={
            ASK_EMAIL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_email)],
            ASK_BRAND_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre_marca)],
            ASK_BRAND_COLOR: [
                CallbackQueryHandler(recibir_color_boton, pattern="^color_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_color_texto),
            ],
            ASK_BRAND_HANDLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_handle)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(seleccionar_plataforma, pattern="^plat_"))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,  procesar_texto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO,    procesar_audio))
    app.add_handler(MessageHandler(filters.PHOTO,                    procesar_foto))

    print("🚀 CarouselBot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
