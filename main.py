import os
import asyncio
import shutil
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import zipfile
import io

# Configuración del bot
app = Client(
    "github_downloader_bot",
    api_id=14681595,
    api_hash="a86730aab5c59953c424abb4396d32d5",
    bot_token="8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
)

# Directorio temporal para descargas
TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

async def download_github_repo(repo_url: str):
    """
    Descarga un repositorio de GitHub como ZIP
    """
    # Convertir URL de GitHub a formato de descarga ZIP
    if "github.com" not in repo_url:
        return None, "URL no válida. Debe ser un repositorio de GitHub."
    
    # Limpiar y formatear la URL
    repo_url = repo_url.strip()
    if repo_url.endswith('/'):
        repo_url = repo_url[:-1]
    
    # Convertir a URL de descarga ZIP
    if "/archive/" not in repo_url:
        # Si es URL normal de repo, convertir a descarga ZIP
        if "/tree/" in repo_url:
            # Si es una rama específica
            repo_url = repo_url.replace("/tree/", "/archive/") + ".zip"
        else:
            # Repo principal (rama master/main por defecto)
            if repo_url.endswith(".git"):
                repo_url = repo_url[:-4]
            repo_url = repo_url + "/archive/refs/heads/main.zip"
    
    # Si ya es URL de descarga pero sin .zip, agregarlo
    if not repo_url.endswith(".zip"):
        repo_url += ".zip"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(repo_url) as response:
                if response.status != 200:
                    # Intentar con master si main falla
                    if "/main.zip" in repo_url:
                        repo_url = repo_url.replace("/main.zip", "/master.zip")
                        async with session.get(repo_url) as response2:
                            if response2.status != 200:
                                return None, "No se pudo descargar el repositorio."
                            content = await response2.read()
                    else:
                        return None, f"Error {response.status}: No se pudo descargar."
                else:
                    content = await response.read()
        
        return content, None
        
    except Exception as e:
        return None, f"Error: {str(e)}"

def get_repo_info_from_url(repo_url: str):
    """
    Extrae información del repositorio de la URL
    """
    try:
        # Limpiar URL
        repo_url = repo_url.replace("https://github.com/", "")
        if "/tree/" in repo_url:
            repo_url = repo_url.split("/tree/")[0]
        
        parts = repo_url.split("/")
        if len(parts) >= 2:
            username = parts[0]
            repo_name = parts[1].replace(".git", "")
            return username, repo_name
        return None, None
    except:
        return None, None

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Ayuda", callback_data="help"),
         InlineKeyboardButton("🌐 Ejemplo", callback_data="example")],
        [InlineKeyboardButton("⚙️ GitHub", url="https://github.com")]
    ])
    
    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "🤖 **Bot Descargador de GitHub**\n\n"
        "📥 **Puedo descargar repositorios de GitHub y enviártelos como ZIP.**\n\n"
        "**Comandos disponibles:**\n"
        "/download [url] - Descargar repositorio\n"
        "/help - Mostrar ayuda\n"
        "/example - Ejemplos de uso\n\n"
        "¡Envía un enlace de GitHub para comenzar!",
        reply_markup=keyboard
    )

@app.on_message(filters.command("download"))
async def download_command(client: Client, message: Message):
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text(
            "📝 **Uso:** `/download <url_del_repositorio>`\n\n"
            "**Ejemplos:**\n"
            "`/download https://github.com/usuario/repo`\n"
            "`/download https://github.com/usuario/repo/tree/rama`\n\n"
            "⚠️ **Límite:** 20MB por archivo (límite de Telegram)"
        )
        return
    
    repo_url = args[1]
    
    # Verificar que sea URL de GitHub
    if "github.com" not in repo_url:
        await message.reply_text(
            "❌ **URL no válida**\n\n"
            "Por favor, envía una URL de GitHub válida.\n"
            "Ejemplo: `https://github.com/usuario/repositorio`"
        )
        return
    
    # Mensaje de procesamiento
    processing_msg = await message.reply_text("⏳ **Descargando repositorio...**")
    
    # Descargar el repositorio
    zip_content, error = await download_github_repo(repo_url)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    # Obtener nombre del archivo
    username, repo_name = get_repo_info_from_url(repo_url)
    if repo_name:
        filename = f"{repo_name}.zip"
    else:
        filename = "repositorio_github.zip"
    
    # Calcular tamaño
    file_size = len(zip_content) / 1024 / 1024  # Convertir a MB
    
    if file_size > 50:  # Límite de Telegram es ~50MB para bots
        await processing_msg.edit_text(
            f"❌ **Archivo demasiado grande**\n\n"
            f"Tamaño: {file_size:.1f}MB\n"
            f"Límite: 50MB\n\n"
            "💡 **Solución:**\n"
            "1. Descarga desde GitHub directamente\n"
            "2. Usa ramas más pequeñas\n"
            "3. Clona manualmente con git"
        )
        return
    
    # Preparar para enviar
    await processing_msg.edit_text(f"✅ **Descarga completada!**\n📦 Tamaño: {file_size:.1f}MB\n📤 Enviando...")
    
    try:
        # Enviar como documento
        await message.reply_document(
            document=io.BytesIO(zip_content),
            file_name=filename,
            caption=f"📦 **{repo_name if repo_name else 'Repositorio'}**\n"
                   f"🔗 {repo_url}\n"
                   f"📊 Tamaño: {file_size:.1f}MB\n\n"
                   f"✅ Descargado por @{client.me.username}"
        )
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ **Error al enviar:** {str(e)}")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
🤖 **Bot Descargador de GitHub - Ayuda**

📥 **¿Qué puedo hacer?**
- Descargar repositorios completos de GitHub
- Enviarlos como archivo ZIP a Telegram
- Soporte para ramas específicas
- Información del repositorio

🛠️ **Comandos:**
/start - Iniciar el bot
/download [url] - Descargar repositorio
/help - Esta ayuda
/example - Ver ejemplos

🔗 **Formatos de URL aceptados:**
• https://github.com/usuario/repo
• https://github.com/usuario/repo/tree/main
• https://github.com/usuario/repo/tree/develop
• https://github.com/usuario/repo.git

⚠️ **Limitaciones:**
• Máximo 50MB por archivo
• Solo repositorios públicos
• No requiere autenticación

💡 **Consejo:** Para repos grandes, usa el comando `git clone` manualmente.
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Probar ahora", callback_data="try_example"),
         InlineKeyboardButton("🌐 GitHub", url="https://github.com")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard)

@app.on_message(filters.command("example"))
async def example_command(client: Client, message: Message):
    examples = """
📚 **Ejemplos de uso:**

1. **Repositorio principal:**
   `/download https://github.com/octocat/Spoon-Knife`

2. **Rama específica:**
   `/download https://github.com/octocat/Spoon-Knife/tree/main`

3. **Con .git:**
   `/download https://github.com/octocat/Spoon-Knife.git`

4. **Proyectos populares:**
   • `/download https://github.com/torvalds/linux`
   • `/download https://github.com/python/cpython`
   • `/download https://github.com/vuejs/vue`

🔥 **Repos para probar:**
`/download https://github.com/octocat/Spoon-Knife`
(Repositorio de prueba oficial de GitHub)
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Descargar ejemplo", callback_data="download_example"),
         InlineKeyboardButton("❓ Ayuda", callback_data="help")]
    ])
    
    await message.reply_text(examples, reply_markup=keyboard)

@app.on_message(filters.regex(r'https?://github\.com/[^\s]+'))
async def handle_github_url(client: Client, message: Message):
    """
    Detecta automáticamente URLs de GitHub en mensajes
    """
    # Extraer URL del mensaje
    import re
    urls = re.findall(r'https?://github\.com/[^\s]+', message.text)
    
    if urls:
        repo_url = urls[0]
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Descargar ZIP", callback_data=f"dl_{repo_url}"),
             InlineKeyboardButton("🌐 Ver en GitHub", url=repo_url)]
        ])
        
        username, repo_name = get_repo_info_from_url(repo_url)
        
        await message.reply_text(
            f"🔍 **Repositorio detectado:**\n\n"
            f"**Nombre:** {repo_name or 'Desconocido'}\n"
            f"**URL:** {repo_url}\n\n"
            "¿Quieres descargarlo como ZIP?",
            reply_markup=keyboard
        )

@app.on_callback_query()
async def handle_callback(client, callback_query):
    data = callback_query.data
    user = callback_query.from_user
    
    if data == "help":
        await help_command(client, callback_query.message)
        await callback_query.answer()
        
    elif data == "example":
        await example_command(client, callback_query.message)
        await callback_query.answer()
        
    elif data == "try_example":
        await callback_query.message.reply_text(
            "📝 **Para probar, envía:**\n"
            "`/download https://github.com/octocat/Spoon-Knife`\n\n"
            "Este es un repositorio de prueba oficial de GitHub."
        )
        await callback_query.answer()
        
    elif data == "download_example":
        # Descargar repositorio de ejemplo
        example_url = "https://github.com/octocat/Spoon-Knife"
        
        msg = await callback_query.message.reply_text("⏳ Descargando ejemplo...")
        zip_content, error = await download_github_repo(example_url)
        
        if error:
            await msg.edit_text(f"❌ Error: {error}")
        else:
            await callback_query.message.reply_document(
                document=io.BytesIO(zip_content),
                file_name="Spoon-Knife.zip",
                caption="🍴 **Spoon-Knife**\nRepositorio de prueba de GitHub\nDescargado por @GitHubDownloaderBot"
            )
            await msg.delete()
        
        await callback_query.answer()
    
    elif data.startswith("dl_"):
        # Descargar desde callback
        repo_url = data[3:]  # Quitar "dl_" del inicio
        
        processing_msg = await callback_query.message.reply_text("⏳ Descargando...")
        
        zip_content, error = await download_github_repo(repo_url)
        
        if error:
            await processing_msg.edit_text(f"❌ Error: {error}")
        else:
            username, repo_name = get_repo_info_from_url(repo_url)
            filename = f"{repo_name or 'repo'}.zip"
            file_size = len(zip_content) / 1024 / 1024
            
            await callback_query.message.reply_document(
                document=io.BytesIO(zip_content),
                file_name=filename,
                caption=f"📦 **{repo_name or 'Repositorio'}**\n"
                       f"🔗 {repo_url}\n"
                       f"📊 Tamaño: {file_size:.1f}MB"
            )
            await processing_msg.delete()
        
        await callback_query.answer("✅ Descarga completada")

@app.on_message(filters.command("info"))
async def info_command(client: Client, message: Message):
    info_text = f"""
🤖 **GitHub Downloader Bot**
    
**Desarrollador:** Tu nombre
**Username:** @{client.me.username}
**ID:** {client.me.id}
    
**Características:**
• Descarga repositorios públicos de GitHub
• Envía como archivo ZIP
• Detecta URLs automáticamente
• Interfaz con botones
    
**Límites:** 50MB por archivo
    
**Código fuente:** [GitHub](https://github.com)
    """
    
    await message.reply_text(info_text)

# Limpiar archivos temporales periódicamente
async def cleanup_temp_files():
    """Limpiar archivos temporales cada hora"""
    while True:
        await asyncio.sleep(3600)  # 1 hora
        try:
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
                os.makedirs(TEMP_DIR)
                print("📁 Archivos temporales limpiados")
        except Exception as e:
            print(f"Error limpiando archivos: {e}")

# Iniciar limpieza automática
@app.on_raw_update()
async def on_start(client, update):
    if not hasattr(on_start, "started"):
        on_start.started = True
        asyncio.create_task(cleanup_temp_files())
        print("🤖 Bot GitHub Downloader iniciado!")

print("🚀 Iniciando GitHub Downloader Bot...")
app.run()