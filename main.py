from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import random

# Conectar bot con el cliente
app = Client(
    "bot",
    api_id=14681595,
    api_hash="a86730aab5c59953c424abb4396d32d5",
    bot_token="8138537409:AAHGgzcTdoKEPQlMhbfjAVJuWkX8-M7s_wo"
)

# Comando /start
@app.on_message(filters.command("start"))
def start_command(client, message):
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Comandos", callback_data="help"),
         InlineKeyboardButton("ℹ️ Info", callback_data="info")],
        [InlineKeyboardButton("🔗 Soporte", url="https://t.me/tuusuario")]
    ])
    
    msg_start = f"""👋 **Bienvenido {first_name}** (@{username})

🤖 **Bot Multifuncional**
✨ Estoy aquí para ayudarte con diversas tareas.

Usa /help para ver todos los comandos disponibles."""
    
    message.reply(msg_start, reply_markup=keyboard)

# Comando /help
@app.on_message(filters.command("help"))
def help_command(client, message):
    help_text = """**📋 Lista de Comandos Disponibles:**

**👤 Básicos:**
/start - Iniciar el bot
/help - Mostrar esta ayuda
/info - Información del usuario
/id - Obtener tu ID

**🛠️ Utilidades:**
/time - Hora actual
/ping - Verificar latencia
/echo [texto] - Repetir texto
/stats - Estadísticas del bot

**🎮 Entretenimiento:**
/dado - Lanzar un dado
/coin - Lanzar una moneda
**✨ ¡Próximamente más funciones!**"""
    
    message.reply(help_text)

# Comando /info
@app.on_message(filters.command("info"))
def info_command(client, message):
    user = message.from_user
    chat = message.chat
    
    info_text = f"""**👤 Información del Usuario:**

**🆔 ID:** `{user.id}`
**👤 Nombre:** {user.first_name}
**📛 Apellido:** {user.last_name or 'No especificado'}
**📧 Username:** @{user.username or 'No tiene'}
**👥 Tipo de chat:** {chat.type}
**📅 Usuario desde:** {user.date.strftime('%d/%m/%Y')}"""
    
    message.reply(info_text)

# Comando /id
@app.on_message(filters.command("id"))
def id_command(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    message.reply(f"**🆔 Tus IDs:**\n**Usuario:** `{user_id}`\n**Chat:** `{chat_id}`")

# Comando /time
@app.on_message(filters.command("time"))
def time_command(client, message):
    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    message.reply(f"**🕐 Hora actual:**\n`{current_time}`")

# Comando /ping
@app.on_message(filters.command("ping"))
def ping_command(client, message):
    start_time = datetime.datetime.now()
    msg = message.reply("🏓 **Pong!**")
    end_time = datetime.datetime.now()
    ping_time = (end_time - start_time).microseconds / 1000
    
    msg.edit(f"🏓 **Pong!**\n**⏱️ Latencia:** `{ping_time:.2f} ms`")

# Comando /echo
@app.on_message(filters.command("echo"))
def echo_command(client, message):
    if len(message.command) > 1:
        text = " ".join(message.command[1:])
        message.reply(f"**Eco:** {text}")
    else:
        message.reply("❌ **Uso:** `/echo [texto]`")

# Comando /dado
@app.on_message(filters.command("dado"))
def dice_command(client, message):
    dice_result = random.randint(1, 6)
    message.reply(f"🎲 **Dado lanzado:** `{dice_result}`")

# Comando /coin
@app.on_message(filters.command("coin"))
def coin_command(client, message):
    result = random.choice(["🌕 Cara", "🌑 Cruz"])
    message.reply(f"🪙 **Moneda lanzada:** `{result}`")

# Comando /stats
@app.on_message(filters.command("stats"))
def stats_command(client, message):
    stats_text = """**📊 Estadísticas del Bot:**

**🟢 Estado:** Online
**⚙️ Funciones:** 10+ comandos
**📅 Última actualización:** Ahora
**👨‍💻 Desarrollador:** Tu nombre
**🔧 Framework:** Pyrogram"""
    
    message.reply(stats_text)

# Manejar mensajes de texto que no son comandos - SOLUCIÓN 1
@app.on_message(filters.private & filters.text)
def handle_text_messages(client, message):
    # Verificar manualmente si no es un comando
    if message.text.startswith('/'):
        return  # Ignorar comandos
    
    text = message.text.lower()
    
    # Respuestas automáticas
    if "hola" in text or "hi" in text:
        message.reply(f"👋 ¡Hola {message.from_user.first_name}! ¿En qué puedo ayudarte?")
    
    elif "gracias" in text:
        message.reply("😊 ¡De nada! ¿Necesitas algo más?")
    
    elif "bot" in text:
        message.reply("🤖 ¡Sí, soy un bot! Usa /help para ver lo que puedo hacer.")
    
    elif "adiós" in text or "chao" in text:
        message.reply("👋 ¡Hasta luego! Fue un gusto ayudarte.")

# Manejar callbacks de botones
@app.on_callback_query()
def handle_callbacks(client, callback_query):
    data = callback_query.data
    
    if data == "help":
        help_text = """**📋 Comandos Disponibles:**

/start - Iniciar bot
/help - Ver comandos
/info - Tu información
/id - Tu ID
/time - Hora actual
/ping - Latencia
/echo - Repetir texto
/dado - Lanzar dado
/coin - Lanzar moneda
/stats - Estadísticas"""
        
        callback_query.edit_message_text(help_text)
    
    elif data == "info":
        user = callback_query.from_user
        info_text = f"""**ℹ️ Información:**

**🆔 ID:** `{user.id}`
**👤 Nombre:** {user.first_name}
**📛 Apellido:** {user.last_name or 'No especificado'}
**📧 Username:** @{user.username or 'No tiene'}"""
        
        callback_query.edit_message_text(info_text)

# Manejar nuevos miembros
@app.on_message(filters.new_chat_members)
def welcome_new_members(client, message):
    for user in message.new_chat_members:
        if user.is_self:
            message.reply("🤖 ¡Gracias por añadirme al grupo! Usa /help para ver mis comandos.")
        else:
            message.reply(f"👋 ¡Bienvenido/a {user.first_name} al grupo!")

print('👾 Bot Online 👾')
app.run()