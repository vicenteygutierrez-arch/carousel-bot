import os, json, tempfile, subprocess
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
import db
from carousel import generar_desde_texto, generar_desde_foto, PLATFORMS
from transcribe import transcribir_audio

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
STAN_STORE_URL = os.environ.get("STAN_STORE_URL", "")
RENDER_SCRIPT = Path(__file__).parent / "render_pillow.py"

ASK_EMAIL, ASK_BRAND_NAME, ASK_BRAND_COLOR, ASK_BRAND_HANDLE = range(4)
COLORES = {"🔵 Azul": "#1E40AF", "⚫ Negro": "#18181B", "🟣 Morado": "#7C3AED", "🟠 Naranja": "#EA580C", "🔴 Rojo": "#DC2626", "🟢 Verde": "#16A34A", "🩷 Rosa": "#DB2777", "🟤 Café": "#92400E"}

def teclado_plataformas():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📸 Instagram", callback_data="plat_instagram"), InlineKeyboardButton("💼 LinkedIn", callback_data="plat_linkedin"), InlineKeyboardButton("📘 Facebook", callback_data="plat_facebook")]])

def teclado_colores():
    botones = [InlineKeyboardButton(n, callback_data=f"color_{h}") for n, h in COLORES.items()]
    filas = [botones[i:i+2] for i in range(0, len(botones), 2)]
    filas.append([InlineKeyboardButton("✏️ Hex", callback_data="color_custom")])
    return InlineKeyboardMarkup(filas)

async def enviar_carrusel(update, datos, brand_color, platform):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        slides_path = tmp_path / "slides.json"
        slides_path.write_text(json.dumps(datos, ensure_ascii=False))
        out_dir = tmp_path / "slides"
        r = subprocess.run(["python3", str(RENDER_SCRIPT), "--input", str(slides_path), "--out", str(out_dir), "--primary", brand_color], capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(r.stderr[-300:])
        imagenes = sorted(out_dir.glob("slide_*.png"))
        media = [InputMediaPhoto(media=open(img, "rb")) for img in imagenes]
        await update.effective_message.reply_media_group(media=media)
    caption = datos.get("caption", "")
    hashtags = " ".join(datos.get("hashtags", []))
    await update.effective_message.reply_text(f"📝 *Pie:*\n{caption}\n\n#️⃣ *Tags:*\n{hashtags}", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    db.create_user(tid, update.effective_user.username)
    user = db.get_user(tid)
    if user["active"] and user["onboarded"]:
        await update.message.reply_text(f"👋 ¡Hola!\n\nTexto, voz o foto\n_Uso: {user['carousels_used']}/{user['carousels_limit']}_", parse_mode="Markdown")
        return ConversationHandler.END
    if user["active"] and not user["onboarded"]:
        await update.message.reply_text("¿Tu marca?")
        return ASK_BRAND_NAME
    await update.message.reply_text("¿Ya compraste? `/activar`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Comprar €9", url=STAN_STORE_URL)]]))
    return ConversationHandler.END

async def cmd_activar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✉️ Tu email:")
    return ASK_EMAIL

async def recibir_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    tid = update.effective_user.id
    db.activate_user(tid, email)
    await update.message.reply_text("✅ Listo. ¿Tu marca?", parse_mode="Markdown")
    return ASK_BRAND_NAME

async def recibir_nombre_marca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brand_name"] = update.message.text.strip()
    await update.message.reply_text("🎨 Color?", reply_markup=teclado_colores())
    return ASK_BRAND_COLOR

async def recibir_color_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "color_custom":
        await query.edit_message_text("✏️ #hex:")
        return ASK_BRAND_COLOR
    context.user_data["brand_color"] = query.data.replace("color_", "")
    await query.edit_message_text("📱 @usuario?")
    return ASK_BRAND_HANDLE

async def recibir_color_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not texto.startswith("#"): 
        await update.message.reply_text("❌ #hex")
        return ASK_BRAND_COLOR
    context.user_data["brand_color"] = texto
    await update.message.reply_text("📱 @?")
    return ASK_BRAND_HANDLE

async def recibir_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    handle = update.message.text.strip().lstrip("@")
    db.update_brand(tid, color=context.user_data.get("brand_color", "#1E3A5F"), name=context.user_data.get("brand_name", "Mi Marca"), handle=handle)
    await update.message.reply_text("🎉 ¡Listo!\n\nTexto, voz o foto", parse_mode="Markdown")
    return ConversationHandler.END

async def _check_usuario(update):
    tid = update.effective_user.id
    ok, razon = db.can_create(tid)
    if not ok:
        if razon == "not_active":
            await update.effective_message.reply_text("🔒 Compra primero", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("€9", url=STAN_STORE_URL)]]))
    return ok, razon

async def seleccionar_plataforma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plataforma = query.data.replace("plat_", "")
    tid = update.effective_user.id
    user = db.get_user(tid)
    tipo = context.user_data.get("pending_type", "text")
    contenido = context.user_data.get("pending_content", "")
    foto_bytes = context.user_data.get("pending_photo")
    msg = await query.edit_message_text("⏳")
    try:
        datos = generar_desde_foto(foto_bytes, contenido, plataforma) if tipo == "photo" and foto_bytes else generar_desde_texto(contenido, plataforma)
        await enviar_carrusel(update, datos, user["brand_color"], plataforma)
        db.increment_usage(tid, contenido or "foto", plataforma)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ {e}")

async def procesar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok: return
    context.user_data["pending_content"] = update.message.text
    context.user_data["pending_type"] = "text"
    await update.message.reply_text("📱?", reply_markup=teclado_plataformas())

async def procesar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok: return
    msg = await update.message.reply_text("🎤")
    try:
        voice = update.message.voice or update.message.audio
        archivo = await voice.get_file()
        audio_bytes = await archivo.download_as_bytearray()
        texto = transcribir_audio(bytes(audio_bytes))
        if not texto:
            await msg.edit_text("❌")
            return
        context.user_data["pending_content"] = texto
        context.user_data["pending_type"] = "text"
        await msg.edit_text(f"📱?", reply_markup=teclado_plataformas())
    except Exception as e:
        await msg.edit_text(f"❌")

async def procesar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, _ = await _check_usuario(update)
    if not ok: return
    msg = await update.message.reply_text("📷")
    try:
        foto = update.message.photo[-1]
        archivo = await foto.get_file()
        foto_bytes = await archivo.download_as_bytearray()
        context.user_data["pending_photo"] = bytes(foto_bytes)
        context.user_data["pending_content"] = update.message.caption or ""
        context.user_data["pending_type"] = "photo"
        await msg.edit_text("📷 📱?", reply_markup=teclado_plataformas())
    except Exception as e:
        await msg.edit_text(f"❌")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("activar", cmd_activar)],
        states={
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_email)],
            ASK_BRAND_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre_marca)],
            ASK_BRAND_COLOR: [CallbackQueryHandler(recibir_color_boton, pattern="^color_"), MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_color_texto)],
            ASK_BRAND_HANDLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_handle)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(seleccionar_plataforma, pattern="^plat_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_texto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, procesar_audio))
    app.add_handler(MessageHandler(filters.PHOTO, procesar_foto))
    print("🚀 CarouselBot.")
    app.run_polling()

if __name__ == "__main__":
    main()
