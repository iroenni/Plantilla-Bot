from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import random
import asyncio
import time

# Conectar bot con el cliente
app = Client(
    "bot",
    api_id=14681595,
    api_hash="a86730aab5c59953c424abb4396d32d5",
    bot_token="8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
)

# Variable para controlar el envío automático
auto_messages_active = True
# Reemplaza con tu ID de usuario (puedes obtenerlo con /id)
YOUR_USER_ID = 7970466590  # Cambia esto por tu ID real

# Lista de mensajes automáticos
AUTO_MESSAGES = [
    "🤖 **Recordatorio automático**\n¡El bot sigue activo y funcionando!",
    "⏰ **Mensaje programado**\nTodo funciona correctamente",
    "🔔 **Notificación**\nEl bot está online y listo para ayudarte",
    "💫 **Actualización**\nTodas las funciones están operativas",
    "📊 **Reporte**\nEstado: ✅ Todo en orden"
]

async def send_auto_messages():
    """Función para enviar mensajes automáticos cada cierto tiempo"""
    while auto_messages_active:
        try:
            # Esperar 30 minutos (1800 segundos)
            await asyncio.sleep(1800)
            
            if auto_messages_active:
                # Seleccionar mensaje aleatorio
                message = random.choice(AUTO_MESSAGES)
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                full_message = f"{message}\n\n🕐 **Hora:** {current_time}"
                
                # Enviar mensaje al usuario
                await app.send_message(YOUR_USER_ID, full_message)
                print(f"📨 Mensaje automático enviado a {YOUR_USER_ID}")
                
        except Exception as e:
            print(f"❌ Error enviando mensaje automático: {e}")

# Comando para activar/desactivar mensajes automáticos
@app.on_message(filters.command("auto"))
def auto_command(client, message):
    global auto_messages_active
    
    if message.from_user.id != YOUR_USER_ID:
        message.reply("❌ **Solo el dueño puede usar este comando**")
        return
    
    if len(message.command) > 1:
        action = message.command[1].lower()
        if action in ["on", "activar", "start"]:
            auto_messages_active = True
            message.reply("✅ **Mensajes automáticos ACTIVADOS**\nSe enviarán cada 30 minutos")
        elif action in ["off", "desactivar", "stop"]:
            auto_messages_active = False
            message.reply("❌ **Mensajes automáticos DESACTIVADOS**")
        else:
            message.reply("❌ **Uso:** `/auto on` o `/auto off`")
    else:
        status = "🟢 ACTIVADOS" if auto_messages_active else "🔴 DESACTIVADOS"
        message.reply(f"**Estado de mensajes automáticos:** {status}")

# Comando para configurar el intervalo
@app.on_message(filters.command("interval"))
def interval_command(client, message):
    if message.from_user.id != YOUR_USER_ID:
        message.reply("❌ **Solo el dueño puede usar este comando**")
        return
    
    message.reply("🕐 **Configuración de intervalo**\nActualmente fijo en 30 minutos\n*Próximamente: intervalo personalizable*")

# Comando /start
@app.on_message(filters.command("start"))
def start_command(client, message):
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Verificar si es el dueño
    owner_buttons = []
    if message.from_user.id == YOUR_USER_ID:
        owner_buttons = [
            [InlineKeyboardButton("🔔 Auto Mensajes", callback_data="auto_settings"),
            InlineKeyboardButton("🕐 Intervalo", callback_data="interval_settings")]
        ]
    
    keyboard_buttons = [
        [InlineKeyboardButton("📋 Comandos", callback_data="help"),
         InlineKeyboardButton("ℹ️ Info", callback_data="info")],
        [InlineKeyboardButton("🔗 Soporte", url="https://t.me/tuusuario")]
    ]
    
    # Combinar botones
    if owner_buttons:
        keyboard_buttons = owner_buttons + keyboard_buttons
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    msg_start = f"""👋 **Bienvenido {first_name}** (@{username})

🤖 **Bot Multifuncional**
✨ Estoy aquí para ayudarte con diversas tareas.

{"🔔 **Modo Dueño Activado**" if message.from_user.id == YOUR_USER_ID else ""}

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

**🔔 Dueño:**
/auto [on/off] - Activar/desactivar mensajes automáticos
/interval - Configurar intervalo

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
**📅 Usuario desde:** {user.date.strftime('%d/%m/%Y')}
{"**👑 Rol:** Dueño del Bot" if user.id == YOUR_USER_ID else ""}"""
    
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
    auto_status = "🟢 Activados" if auto_messages_active else "🔴 Desactivados"
    stats_text = f"""**📊 Estadísticas del Bot:**

**🟢 Estado:** Online
**⚙️ Funciones:** 10+ comandos
**🔔 Auto Mensajes:** {auto_status}
**📅 Última actualización:** Ahora
**👨‍💻 Desarrollador:** Tu nombre
**🔧 Framework:** Pyrogram"""
    
    message.reply(stats_text)

# Manejar mensajes de texto que no son comandos
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
    user = callback_query.from_user
    
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
        info_text = f"""**ℹ️ Información:**

**🆔 ID:** `{user.id}`
**👤 Nombre:** {user.first_name}
**📛 Apellido:** {user.last_name or 'No especificado'}
**📧 Username:** @{user.username or 'No tiene'}"""
        
        callback_query.edit_message_text(info_text)
    
    elif data == "auto_settings" and user.id == YOUR_USER_ID:
        status = "🟢 ACTIVADOS" if auto_messages_active else "🔴 DESACTIVADOS"
        auto_text = f"""**🔔 Configuración de Auto Mensajes**

**Estado:** {status}
**Intervalo:** 30 minutos

**Comandos:**
/auto on - Activar
/auto off - Desactivar
/interval - Configurar tiempo"""
        
        callback_query.edit_message_text(auto_text)
    
    elif data == "interval_settings" and user.id == YOUR_USER_ID:
        callback_query.edit_message_text("🕐 **Configuración de Intervalo**\n\nActualmente el intervalo está fijo en 30 minutos.\n*En futuras actualizaciones podrás personalizarlo*")

# Manejar nuevos miembros
@app.on_message(filters.new_chat_members)
def welcome_new_members(client, message):
    for user in message.new_chat_members:
        if user.is_self:
            message.reply("🤖 ¡Gracias por añadirme al grupo! Usa /help para ver mis comandos.")
        else:
            message.reply(f"👋 ¡Bienvenido/a {user.first_name} al grupo!")

# Iniciar el bot y la tarea automática
@app.on_message(filters.command("init"))
def init_bot(client, message):
    if message.from_user.id == YOUR_USER_ID:
        message.reply("🤖 **Bot inicializado**\n✅ Mensajes automáticos activados")
        print("Bot iniciado con mensajes automáticos")

# Ejecutar cuando el bot se inicia
@app.on_raw_update()
async def on_start(client, update):
    # Solo ejecutar una vez cuando el bot inicia
    if not hasattr(on_start, "started"):
        on_start.started = True
        print("👾 Bot Online 👾")
        # Iniciar la tarea de mensajes automáticos
        asyncio.create_task(send_auto_messages())

print('👾 Iniciando Bot... 👾')
app.run()