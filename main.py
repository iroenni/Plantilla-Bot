from pyrogram import Client, filters
from pyrogram.types import Message

# Configuración del bot
app = Client(
    "mi_bot_saludo",
    api_id=14681595,
    api_hash="a86730aab5c59953c424abb4396d32d5",
    bot_token="8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
)

# Comando /start - Saludo básico
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "Soy un bot simple que saluda.\n"
        "¡Encantado de conocerte! 😊"
    )

# Comando /hola - Saludo alternativo
@app.on_message(filters.command("hola"))
async def hola_command(client: Client, message: Message):
    user = message.from_user
    await message.reply_text(
        f"¡Hola {user.first_name}! 👋\n"
        "¿Cómo estás hoy? 🌟"
    )

# Responder a "hola" en texto plano
@app.on_message(filters.text & filters.private)
async def responder_hola(client: Client, message: Message):
    texto = message.text.lower()
    user = message.from_user
    
    if texto in ["hola", "hi", "hello", "buenas", "saludos"]:
        await message.reply_text(f"¡Hola {user.first_name}! 😄")
    
    elif texto in ["¿cómo estás?", "como estas", "qué tal", "que tal"]:
        await message.reply_text(
            f"¡Muy bien {user.first_name}! 😊\n"
            "¿Y tú, cómo te encuentras?"
        )
    
    elif texto in ["adiós", "chao", "bye", "hasta luego"]:
        await message.reply_text(f"¡Adiós {user.first_name}! 👋\n¡Que tengas un buen día! ✨")

# Comando /ayuda - Información
@app.on_message(filters.command("ayuda"))
async def ayuda_command(client: Client, message: Message):
    ayuda_texto = (
        "🤖 **Bot de Saludo Simple**\n\n"
        "**Comandos disponibles:**\n"
        "/start - Iniciar el bot\n"
        "/hola - Saludar\n"
        "/ayuda - Mostrar esta ayuda\n\n"
        "**También puedes saludarme escribiendo:**\n"
        "hola, hi, hello, buenas\n\n"
        "¡Soy un bot muy simple y simpático! 😊"
    )
    await message.reply_text(ayuda_texto)

# Mensaje cuando se agrega el bot a un grupo
@app.on_message(filters.new_chat_members)
async def welcome_group(client: Client, message: Message):
    for user in message.new_chat_members:
        if user.is_self:
            await message.reply_text(
                "👋 ¡Hola a todos!\n"
                "Soy un bot de saludos.\n"
                "Escribe /hola para que te salude 😊"
            )

# Ejecutar el bot
print("🤖 Bot de Saludo iniciando...")
app.run()