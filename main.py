import os
import asyncio
import aiohttp
import re
import io
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime

# Configuración básica
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Credenciales
API_ID = 14681595
API_HASH = "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
ADMIN_ID = 7970466590

# Cliente Pyrogram
app = Client("github_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Diccionario para seguimiento
user_activity = {}

# ================= FUNCIONES PRINCIPALES =================

async def notify_admin(user_info: dict, action: str):
    """Notifica al admin sobre actividad"""
    try:
        if user_info.get("id") == ADMIN_ID:
            return
        
        msg = f"""🔔 **ACTIVIDAD DETECTADA**
👤 Usuario: {user_info.get('first_name', 'N/A')}
🆔 ID: `{user_info['id']}`
📝 Acción: {action}
🕐 Hora: {datetime.now().strftime('%H:%M:%S')}"""
        
        await app.send_message(ADMIN_ID, msg, parse_mode=enums.ParseMode.MARKDOWN)
    except:
        pass

async def download_repo(repo_url: str):
    """Descarga repositorio de GitHub"""
    try:
        # Extraer info de la URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return None, "URL inválida"
        
        user, repo = match.groups()
        repo = re.sub(r'\.git$', '', repo)
        
        # Determinar rama
        branch = "main"
        if "/tree/" in repo_url:
            branch_match = re.search(r'/tree/([^/]+)', repo_url)
            if branch_match:
                branch = branch_match.group(1)
        
        # URL de descarga
        url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    if len(content) > 50 * 1024 * 1024:
                        return None, "Archivo muy grande (>50MB)"
                    return content, None
                else:
                    return None, f"Error {response.status}"
    except Exception as e:
        return None, f"Error: {str(e)[:100]}"

async def search_repos(query: str, page: int = 1):
    """Busca repositorios en GitHub"""
    try:
        url = f"https://api.github.com/search/repositories?q={query}&page={page}&per_page=5"
        headers = {'User-Agent': 'GitHubBot'}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("items", []), None
                return None, f"Error API: {response.status}"
    except:
        return None, "Error de conexión"

# ================= COMANDOS DEL BOT =================

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    """Comando /start"""
    user = message.from_user
    if user.id != ADMIN_ID:
        await notify_admin({"id": user.id, "first_name": user.first_name}, "/start")
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar", callback_data="search")],
        [InlineKeyboardButton("📥 Descargar", callback_data="download")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help")]
    ])
    
    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "🤖 **GitHub Downloader Bot**\n"
        "Descarga repositorios de GitHub fácilmente.\n\n"
        "📌 **Comandos:**\n"
        "• /start - Iniciar bot\n"
        "• /search <término> - Buscar repos\n"
        "• /download <url> - Descargar repo\n"
        "• /help - Ayuda completa",
        reply_markup=kb
    )

@app.on_message(filters.command("search"))
async def search_cmd(client: Client, message: Message):
    """Comando /search"""
    user = message.from_user
    if user.id != ADMIN_ID:
        await notify_admin({"id": user.id, "first_name": user.first_name}, f"/search: {message.text[:50]}")
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("⚠️ **Uso:** `/search <término>`\nEjemplo: `/search python bot`")
        return
    
    query = args[1]
    await message.reply_text(f"🔍 Buscando: `{query}`...")
    
    repos, error = await search_repos(query)
    
    if error:
        await message.reply_text(f"❌ {error}")
        return
    
    if not repos:
        await message.reply_text("📭 No se encontraron resultados.")
        return
    
    # Mostrar primeros 5 resultados
    text = f"✅ **Resultados para:** `{query}`\n\n"
    for i, repo in enumerate(repos[:5], 1):
        text += f"{i}. **{repo['name']}** ⭐{repo.get('stargazers_count', 0)}\n"
        text += f"   {repo.get('description', 'Sin descripción')[:80]}...\n"
        text += f"   👤 {repo['owner']['login']}\n\n"
    
    kb_buttons = []
    for i, repo in enumerate(repos[:3]):
        kb_buttons.append([InlineKeyboardButton(
            f"📦 {repo['name'][:15]}",
            callback_data=f"dl_{repo['html_url']}"
        )])
    
    kb_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
    
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb_buttons))

@app.on_message(filters.command("download"))
async def download_cmd(client: Client, message: Message):
    """Comando /download"""
    user = message.from_user
    if user.id != ADMIN_ID:
        await notify_admin({"id": user.id, "first_name": user.first_name}, f"/download: {message.text[:50]}")
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("⚠️ **Uso:** `/download <url>`\nEjemplo: `/download https://github.com/user/repo`")
        return
    
    url = args[1].strip()
    if "github.com" not in url:
        await message.reply_text("❌ URL de GitHub no válida.")
        return
    
    msg = await message.reply_text("⏳ Descargando...")
    
    content, error = await download_repo(url)
    
    if error:
        await msg.edit_text(f"❌ {error}")
        return
    
    # Extraer nombre del archivo
    match = re.search(r'github\.com/([^/]+)/([^/]+)', url)
    filename = f"{match.group(2)}.zip" if match else "repo.zip"
    
    await message.reply_document(
        document=io.BytesIO(content),
        file_name=filename,
        caption=f"📦 Descargado de GitHub\n🔗 {url[:50]}..."
    )
    await msg.delete()

@app.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    """Comando /help"""
    text = """
🆘 **AYUDA - GitHub Downloader Bot**

📚 **Comandos disponibles:**
• /start - Iniciar bot
• /search <término> - Buscar repositorios
• /download <url> - Descargar repositorio
• /help - Mostrar esta ayuda

🔍 **Ejemplos:**
`/search python telegram bot`
`/download https://github.com/octocat/Spoon-Knife`

💡 **Consejos:**
• También puedes pegar URLs directamente
• Límite: 50MB por archivo
• Solo repos públicos
"""
    await message.reply_text(text)

# ================= DETECCIÓN DE URLS =================

@app.on_message(filters.regex(r'https?://github\.com/[^\s]+'))
async def url_detector(client: Client, message: Message):
    """Detecta URLs de GitHub"""
    user = message.from_user
    if user.id != ADMIN_ID:
        await notify_admin({"id": user.id, "first_name": user.first_name}, "URL detectada")
    
    url = re.search(r'https?://github\.com/[^\s]+', message.text).group()
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Descargar", callback_data=f"dl_{url}")],
        [InlineKeyboardButton("🌐 Abrir", url=url)]
    ])
    
    await message.reply_text(
        f"🔗 **URL detectada:**\n{url}\n\n¿Descargar repositorio?",
        reply_markup=kb
    )

# ================= MANEJADOR DE CALLBACKS =================

@app.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    """Maneja botones inline"""
    data = callback.data
    user = callback.from_user
    
    if user.id != ADMIN_ID:
        await notify_admin({"id": user.id, "first_name": user.first_name}, f"Botón: {data[:20]}")
    
    if data == "search":
        await callback.message.reply_text("🔍 **Buscar repositorios**\n\nEnvía: `/search <término>`")
    
    elif data == "download":
        await callback.message.reply_text("📥 **Descargar repositorio**\n\nEnvía: `/download <url>`")
    
    elif data == "help":
        await help_cmd(client, callback.message)
    
    elif data.startswith("dl_"):
        url = data[3:]
        await callback.message.reply_text(f"⏳ Descargando: {url[:50]}...")
        
        content, error = await download_repo(url)
        
        if error:
            await callback.message.reply_text(f"❌ {error}")
        else:
            match = re.search(r'github\.com/([^/]+)/([^/]+)', url)
            filename = f"{match.group(2)}.zip" if match else "repo.zip"
            
            await callback.message.reply_document(
                document=io.BytesIO(content),
                file_name=filename,
                caption=f"✅ Descargado de GitHub"
            )
    
    await callback.answer()

# ================= INICIO DEL BOT =================

async def main():
    """Función principal"""
    await app.start()
    bot = await app.get_me()
    logger.info(f"✅ Bot iniciado: @{bot.username}")
    
    # Mantener activo
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot detenido")
    except Exception as e:
        print(f"❌ Error: {e}")