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
    bot_token="8138537409:AAHGgzcTdoKEPQlMhbfjAVJuWkX8-M7s_wo"
)

# Variables de configuración
auto_messages_active = True
auto_interval = 1800  # 30 minutos en segundos
YOUR_USER_ID = 7970466590  # Cambia esto por tu ID real

# Lista de mensajes automáticos
AUTO_MESSAGES = [
    "🤖 **Recordatorio automático**\n¡El bot sigue activo y funcionando!",
    "⏰ **Mensaje programado**\nTodo funciona correctamente",
    "🔔 **Notificación**\nEl bot está online y listo para ayudarte",
    "💫 **Actualización**\nTodas las funciones están operativas",
    "📊 **Reporte**\nEstado: ✅ Todo en orden"
]

# Diccionario para almacenar el estado del menú de cada usuario
user_menus = {}

async def send_auto_messages():
    """Función para enviar mensajes automáticos cada cierto tiempo"""
    while True:
        try:
            # Esperar el intervalo configurado
            await asyncio.sleep(auto_interval)
            
            if auto_messages_active:
                # Seleccionar mensaje aleatorio
                message = random.choice(AUTO_MESSAGES)
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                full_message = f"{message}\n\n🕐 **Hora:** {current_time}\n**⏰ Intervalo:** {auto_interval//60} minutos"
                
                # Enviar mensaje al usuario
                await app.send_message(YOUR_USER_ID, full_message)
                print(f"📨 Mensaje automático enviado a {YOUR_USER_ID}")
                
        except Exception as e:
            print(f"❌ Error enviando mensaje automático: {e}")

def get_main_menu(user_id):
    """Menú principal"""
    buttons = []
    
    # Si es el dueño, mostrar botones especiales
    if user_id == YOUR_USER_ID:
        auto_status = "🟢 ON" if auto_messages_active else "🔴 OFF"
        buttons.append([InlineKeyboardButton(f"🔔 Auto Mensajes ({auto_status})", callback_data="auto_menu")])
    
    buttons.extend([
        [InlineKeyboardButton("📋 Comandos Rápidos", callback_data="quick_commands")],
        [InlineKeyboardButton("🛠️ Utilidades", callback_data="utilities_menu")],
        [InlineKeyboardButton("🎮 Entretenimiento", callback_data="entertainment_menu")],
        [InlineKeyboardButton("ℹ️ Información", callback_data="info_menu")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="stats_menu")]
    ])
    
    return InlineKeyboardMarkup(buttons)

def get_auto_menu():
    """Menú de configuración automática"""
    auto_status = "🟢 ACTIVADOS" if auto_messages_active else "🔴 DESACTIVADOS"
    interval_minutes = auto_interval // 60
    
    buttons = [
        [InlineKeyboardButton(f"Estado: {auto_status}", callback_data="toggle_auto")],
        [InlineKeyboardButton(f"⏰ Intervalo: {interval_minutes}min", callback_data="interval_menu")],
        [InlineKeyboardButton("📝 Personalizar Mensajes", callback_data="custom_messages")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def get_interval_menu():
    """Menú para configurar intervalo"""
    buttons = [
        [InlineKeyboardButton("⏱️ 15 minutos", callback_data="set_interval_900")],
        [InlineKeyboardButton("⏱️ 30 minutos", callback_data="set_interval_1800")],
        [InlineKeyboardButton("⏱️ 1 hora", callback_data="set_interval_3600")],
        [InlineKeyboardButton("⏱️ 2 horas", callback_data="set_interval_7200")],
        [InlineKeyboardButton("⏱️ 6 horas", callback_data="set_interval_21600")],
        [InlineKeyboardButton("⏱️ 12 horas", callback_data="set_interval_43200")],
        [InlineKeyboardButton("🔙 Atrás", callback_data="auto_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def get_quick_commands_menu():
    """Menú de comandos rápidos"""
    buttons = [
        [InlineKeyboardButton("🆔 Obtener mi ID", callback_data="get_my_id")],
        [InlineKeyboardButton("🕐 Hora actual", callback_data="get_time")],
        [InlineKeyboardButton("🏓 Test de latencia", callback_data="ping_test")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def get_utilities_menu():
    """Menú de utilidades"""
    buttons = [
        [InlineKeyboardButton("📡 Información del Chat", callback_data="chat_info")],
        [InlineKeyboardButton("👤 Mi Información", callback_data="my_info")],
        [InlineKeyboardButton("🔄 Echo (Repetir texto)", callback_data="echo_command")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def get_entertainment_menu():
    """Menú de entretenimiento"""
    buttons = [
        [InlineKeyboardButton("🎲 Lanzar Dado", callback_data="roll_dice")],
        [InlineKeyboardButton("🪙 Lanzar Moneda", callback_data="flip_coin")],
        [InlineKeyboardButton("🔢 Número Aleatorio", callback_data="random_number")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def get_info_menu():
    """Menú de información"""
    buttons = [
        [InlineKeyboardButton("🤖 Acerca del Bot", callback_data="about_bot")],
        [InlineKeyboardButton("📚 Ayuda Completa", callback_data="full_help")],
        [InlineKeyboardButton("🆘 Soporte", callback_data="support_info")],
        [InlineKeyboardButton("🔙 Menú Principal", callback_data="main_menu")]
    ]
    
    return InlineKeyboardMarkup(buttons)

def format_interval(seconds):
    """Formatear intervalo a texto legible"""
    if seconds < 60:
        return f"{seconds} segundos"
    elif seconds < 3600:
        return f"{seconds//60} minutos"
    else:
        return f"{seconds//3600} horas"

# ========== COMANDOS PRINCIPALES ==========

@app.on_message(filters.command("start"))
def start_command(client, message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    welcome_text = f"""👋 **Bienvenido {first_name}**

🤖 **Bot Multifuncional con Menús Interactivos**

✨ **Características:**
• 🎯 Navegación por menús
• 🔔 Mensajes automáticos
• 🛠️ Herramientas útiles
• 🎮 Entretenimiento

📱 **Usa los botones para navegar**"""
    
    message.reply(welcome_text, reply_markup=get_main_menu(user_id))

@app.on_message(filters.command("menu"))
def menu_command(client, message):
    """Comando para abrir el menú principal"""
    user_id = message.from_user.id
    message.reply("**📱 Menú Principal**", reply_markup=get_main_menu(user_id))

# ========== MANEJO DE CALLBACKS ==========

@app.on_callback_query()
async def handle_callbacks(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    
    try:
        # Menú Principal
        if data == "main_menu":
            await message.edit_text("**📱 Menú Principal**", reply_markup=get_main_menu(user_id))
        
        # Comandos Rápidos
        elif data == "quick_commands":
            await message.edit_text("**📋 Comandos Rápidos**\n\nSelecciona una opción:", reply_markup=get_quick_commands_menu())
        
        elif data == "get_my_id":
            await message.edit_text(f"**🆔 Tu ID:** `{user_id}`", reply_markup=get_quick_commands_menu())
        
        elif data == "get_time":
            current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            await message.edit_text(f"**🕐 Hora actual:**\n`{current_time}`", reply_markup=get_quick_commands_menu())
        
        elif data == "ping_test":
            start_time = datetime.datetime.now()
            ping_msg = await message.edit_text("🏓 **Calculando latencia...**")
            end_time = datetime.datetime.now()
            ping_time = (end_time - start_time).microseconds / 1000
            await ping_msg.edit_text(f"🏓 **Pong!**\n**⏱️ Latencia:** `{ping_time:.2f} ms`", reply_markup=get_quick_commands_menu())
        
        # Utilidades
        elif data == "utilities_menu":
            await message.edit_text("**🛠️ Menú de Utilidades**\n\nSelecciona una herramienta:", reply_markup=get_utilities_menu())
        
        elif data == "my_info":
            user = callback_query.from_user
            info_text = f"""**👤 Tu Información:**

**🆔 ID:** `{user.id}`
**👤 Nombre:** {user.first_name}
**📛 Apellido:** {user.last_name or 'No especificado'}
**📧 Username:** @{user.username or 'No tiene'}
**📅 Usuario desde:** {user.date.strftime('%d/%m/%Y')}"""
            await message.edit_text(info_text, reply_markup=get_utilities_menu())
        
        elif data == "chat_info":
            chat = message.chat
            chat_info = f"""**💬 Información del Chat:**

**🆔 ID:** `{chat.id}`
**📛 Tipo:** {chat.type}
**👤 Título:** {chat.title or 'Chat privado'}
**👥 Miembros:** {chat.members_count if hasattr(chat, 'members_count') else 'N/A'}"""
            await message.edit_text(chat_info, reply_markup=get_utilities_menu())
        
        elif data == "echo_command":
            await callback_query.answer("ℹ️ Usa el comando /echo [texto] en el chat", show_alert=True)
        
        # Entretenimiento
        elif data == "entertainment_menu":
            await message.edit_text("**🎮 Menú de Entretenimiento**\n\nSelecciona un juego:", reply_markup=get_entertainment_menu())
        
        elif data == "roll_dice":
            dice_result = random.randint(1, 6)
            await message.edit_text(f"🎲 **Dado lanzado:** `{dice_result}`", reply_markup=get_entertainment_menu())
        
        elif data == "flip_coin":
            result = random.choice(["🌕 Cara", "🌑 Cruz"])
            await message.edit_text(f"🪙 **Moneda lanzada:** `{result}`", reply_markup=get_entertainment_menu())
        
        elif data == "random_number":
            number = random.randint(1, 100)
            await message.edit_text(f"🔢 **Número aleatorio:** `{number}`", reply_markup=get_entertainment_menu())
        
        # Información
        elif data == "info_menu":
            await message.edit_text("**ℹ️ Menú de Información**\n\nSelecciona una opción:", reply_markup=get_info_menu())
        
        elif data == "about_bot":
            about_text = """**🤖 Acerca de este Bot**

**✨ Características:**
• Menús interactivos
• Mensajes automáticos
• Herramientas útiles
• Entretenimiento

**🔧 Tecnología:**
• Framework: Pyrogram
• Lenguaje: Python
• Estado: 🟢 Online"""
            await message.edit_text(about_text, reply_markup=get_info_menu())
        
        elif data == "full_help":
            help_text = """**📚 Ayuda Completa**

**Navegación:**
• Usa /menu para abrir el menú
• Navega con los botones
• Todos los comandos están en los menús

**Funciones disponibles:**
• Información de usuario/chat
• Herramientas útiles
• Juegos y entretenimiento
• Mensajes automáticos (solo dueño)"""
            await message.edit_text(help_text, reply_markup=get_info_menu())
        
        elif data == "support_info":
            await message.edit_text("**🆘 Soporte**\n\n📧 Contacta al desarrollador para soporte técnico.", reply_markup=get_info_menu())
        
        # Estadísticas
        elif data == "stats_menu":
            auto_status = "🟢 Activados" if auto_messages_active else "🔴 Desactivados"
            stats_text = f"""**📊 Estadísticas del Bot**

**🟢 Estado:** Online
**🔔 Auto Mensajes:** {auto_status}
**⏰ Intervalo:** {format_interval(auto_interval)}
**🛠️ Funciones:** 15+ herramientas
**📱 Menús:** 6 categorías"""
            await message.edit_text(stats_text, reply_markup=get_main_menu(user_id))
        
        # MENÚS DE CONFIGURACIÓN AUTOMÁTICA (solo dueño)
        elif data == "auto_menu":
            if user_id == YOUR_USER_ID:
                auto_status = "🟢 ACTIVADOS" if auto_messages_active else "🔴 DESACTIVADOS"
                interval_text = format_interval(auto_interval)
                auto_text = f"""**🔔 Configuración de Auto Mensajes**

**Estado:** {auto_status}
**Intervalo actual:** {interval_text}

**Opciones disponibles:**"""
                await message.edit_text(auto_text, reply_markup=get_auto_menu())
            else:
                await callback_query.answer("❌ Solo el dueño puede acceder a esta configuración", show_alert=True)
        
        elif data == "toggle_auto":
            if user_id == YOUR_USER_ID:
                global auto_messages_active
                auto_messages_active = not auto_messages_active
                status = "🟢 ACTIVADOS" if auto_messages_active else "🔴 DESACTIVADOS"
                await message.edit_text(f"**✅ Estado actualizado**\n\nAuto mensajes: {status}", reply_markup=get_auto_menu())
            else:
                await callback_query.answer("❌ Solo el dueño puede cambiar esta configuración", show_alert=True)
        
        elif data == "interval_menu":
            if user_id == YOUR_USER_ID:
                await message.edit_text("**⏰ Configurar Intervalo**\n\nSelecciona el tiempo entre mensajes:", reply_markup=get_interval_menu())
            else:
                await callback_query.answer("❌ Solo el dueño puede cambiar el intervalo", show_alert=True)
        
        elif data.startswith("set_interval_"):
            if user_id == YOUR_USER_ID:
                try:
                    new_interval = int(data.split("_")[2])
                    global auto_interval
                    auto_interval = new_interval
                    interval_text = format_interval(new_interval)
                    await message.edit_text(f"**✅ Intervalo actualizado**\n\nNuevo intervalo: {interval_text}", reply_markup=get_auto_menu())
                except Exception as e:
                    await callback_query.answer("❌ Error al cambiar el intervalo", show_alert=True)
            else:
                await callback_query.answer("❌ Solo el dueño puede cambiar el intervalo", show_alert=True)
        
        elif data == "custom_messages":
            if user_id == YOUR_USER_ID:
                await callback_query.answer("ℹ️ Esta función estará disponible en la próxima actualización", show_alert=True)
            else:
                await callback_query.answer("❌ Solo el dueño puede acceder a esta configuración", show_alert=True)
        
        await callback_query.answer()
        
    except Exception as e:
        print(f"Error en callback: {e}")
        await callback_query.answer("❌ Error al procesar la solicitud", show_alert=True)

# ========== COMANDOS DE TEXTO (para compatibilidad) ==========

@app.on_message(filters.command("help"))
def help_command(client, message):
    """Redirigir al menú de ayuda"""
    message.reply("**📱 Usa el menú interactivo para navegar**", reply_markup=get_main_menu(message.from_user.id))

@app.on_message(filters.command("id"))
def id_command(client, message):
    """Comando rápido de ID"""
    message.reply(f"**🆔 Tu ID:** `{message.from_user.id}`")

@app.on_message(filters.command("time"))
def time_command(client, message):
    """Comando rápido de hora"""
    current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    message.reply(f"**🕐 Hora actual:**\n`{current_time}`")

# ========== INICIALIZACIÓN ==========

@app.on_message(filters.command("init"))
def init_bot(client, message):
    if message.from_user.id == YOUR_USER_ID:
        message.reply("🤖 **Bot inicializado**\n✅ Sistema de menús activado\n🔔 Mensajes automáticos configurados", reply_markup=get_main_menu(message.from_user.id))

# Ejecutar cuando el bot se inicia
print('👾 Iniciando Bot con Sistema de Menús... 👾')
# Iniciar la tarea de mensajes automáticos
asyncio.create_task(send_auto_messages())
app.run()