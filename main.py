import os
import asyncio
import shutil
import tempfile
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import aiohttp
import zipfile
import io
import json
import re
import uuid
from typing import Optional, Tuple, Dict, Any
import logging
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================
# ⚠️⚠️⚠️ ADVERTENCIA DE SEGURIDAD ⚠️⚠️⚠️
# ==============================================
# NUNCA expongas tus credenciales en el código
# Usa variables de entorno o un archivo de configuración
# ==============================================

# Configuración del bot (DEBES USAR VARIABLES DE ENTORNO)
API_ID = os.getenv("API_ID") or 14681595  # ⚠️ Cambia esto
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"  # ⚠️ Cambia esto
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"  # ⚠️ Cambia esto

# Verificar credenciales
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Faltan credenciales. Configura las variables de entorno.")
    exit(1)

app = Client(
    "github_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Directorio temporal para descargas
TEMP_DIR = tempfile.mkdtemp(prefix="github_downloader_")
os.makedirs(TEMP_DIR, exist_ok=True)

# Almacenamiento temporal para resultados de búsqueda
search_cache: Dict[str, Dict[str, Any]] = {}

# Configuración
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB en bytes
SEARCH_CACHE_TIMEOUT = 1800  # 30 minutos en segundos
DOWNLOAD_TIMEOUT = 300  # 5 minutos

class GitHubAPIError(Exception):
    """Excepción personalizada para errores de la API de GitHub"""
    pass

class DownloadError(Exception):
    """Excepción personalizada para errores de descarga"""
    pass

def cleanup_old_temp_files():
    """Eliminar archivos temporales antiguos"""
    try:
        if os.path.exists(TEMP_DIR):
            # Eliminar archivos más antiguos de 1 hora
            now = time.time()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(filepath):
                    if now - os.path.getmtime(filepath) > 3600:
                        os.remove(filepath)
                        logger.info(f"🗑️ Eliminado archivo temporal: {filename}")
    except Exception as e:
        logger.error(f"Error limpiando archivos temporales: {e}")

async def download_github_repo(repo_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Descarga un repositorio de GitHub como ZIP
    """
    try:
        # Validar URL
        if not repo_url or "github.com" not in repo_url:
            return None, "URL no válida. Debe ser un repositorio de GitHub."

        # Limpiar URL
        repo_url = repo_url.strip().rstrip('/')
        
        # Convertir URL de GitHub a formato de descarga ZIP
        if "/archive/" in repo_url and repo_url.endswith(".zip"):
            download_url = repo_url
        else:
            # Extraer usuario y repositorio
            pattern = r"github\.com/([^/]+)/([^/?#]+)"
            match = re.search(pattern, repo_url)
            
            if not match:
                return None, "No se pudo extraer información del repositorio."
            
            user, repo = match.groups()
            repo = re.sub(r'\.git$', '', repo)
            
            # Determinar rama
            if "/tree/" in repo_url:
                branch_match = re.search(r'/tree/([^/]+)', repo_url)
                branch = branch_match.group(1) if branch_match else "main"
            else:
                branch = "main"
            
            download_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
        
        # Configurar timeout
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
        
        # Descargar contenido
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    # Intentar con master si main falla
                    if "/main.zip" in download_url:
                        alt_url = download_url.replace("/main.zip", "/master.zip")
                        async with session.get(alt_url) as response2:
                            if response2.status != 200:
                                return None, f"No se pudo descargar el repositorio. HTTP {response.status}"
                            content = await response2.read()
                    else:
                        return None, f"Error HTTP {response.status}: No se pudo descargar."
                else:
                    content = await response.read()
        
        # Verificar tamaño
        if len(content) > MAX_FILE_SIZE:
            return None, f"El archivo es demasiado grande ({len(content)/1024/1024:.1f}MB). Límite: 50MB."
        
        return content, None
        
    except asyncio.TimeoutError:
        return None, "Tiempo de espera agotado al descargar el repositorio."
    except aiohttp.ClientError as e:
        return None, f"Error de conexión: {str(e)}"
    except Exception as e:
        logger.error(f"Error en download_github_repo: {e}")
        return None, f"Error interno: {str(e)}"

def get_repo_info_from_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrae información del repositorio de la URL
    """
    try:
        pattern = r"github\.com/([^/]+)/([^/?#]+)"
        match = re.search(pattern, repo_url)
        
        if match:
            username = match.group(1)
            repo_name = match.group(2)
            # Limpiar .git y ramas
            repo_name = re.sub(r'\.git$', '', repo_name)
            if '/tree/' in repo_url:
                repo_name = repo_name.split('/')[0]
            return username, repo_name
        return None, None
    except Exception as e:
        logger.error(f"Error en get_repo_info_from_url: {e}")
        return None, None

async def search_github_repos(query: str, page: int = 1, per_page: int = 5) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Busca repositorios en GitHub usando la API
    """
    try:
        if not query or len(query.strip()) < 2:
            return None, "La búsqueda debe tener al menos 2 caracteres."
        
        query = query.strip()
        encoded_query = aiohttp.helpers.quote(query, safe='')
        url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&page={page}&per_page={per_page}"
        
        headers = {
            'User-Agent': 'GitHubDownloaderBot/2.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 403:
                    return None, "Límite de la API de GitHub alcanzado. Intenta más tarde."
                elif response.status == 422:
                    return None, "Consulta de búsqueda no válida."
                elif response.status != 200:
                    return None, f"Error en la API: {response.status}"
                
                data = await response.json()
                
                if "items" not in data:
                    return None, "No se encontraron resultados."
                
                repos = []
                for item in data["items"]:
                    repo_info = {
                        "name": item.get("name", "Desconocido"),
                        "full_name": item.get("full_name", "Desconocido"),
                        "description": item.get("description") or "Sin descripción",
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language") or "N/A",
                        "updated_at": item.get("updated_at", ""),
                        "owner": item.get("owner", {}).get("login", "Desconocido")
                    }
                    repos.append(repo_info)
                
                total_count = data.get("total_count", 0)
                return {
                    "repos": repos,
                    "total_count": total_count,
                    "page": page,
                    "query": query,
                    "has_next": len(repos) == per_page and (page * per_page) < total_count,
                    "has_prev": page > 1
                }, None
                
    except aiohttp.ClientError as e:
        logger.error(f"Error de conexión en search_github_repos: {e}")
        return None, "Error de conexión con GitHub."
    except Exception as e:
        logger.error(f"Error en search_github_repos: {e}")
        return None, f"Error interno: {str(e)}"

def format_repo_search_results(results: Dict) -> str:
    """
    Formatea los resultados de búsqueda para mostrar al usuario
    """
    repos = results["repos"]
    total_count = results["total_count"]
    page = results["page"]
    query = results.get("query", "")
    
    text = f"🔍 **Resultados para: `{query}`**\n\n"
    text += f"📊 **Encontrados:** {total_count} repositorios\n"
    text += f"📄 **Página:** {page}\n\n"
    
    for i, repo in enumerate(repos, 1):
        idx = (page - 1) * 5 + i
        text += f"**{idx}. {repo['full_name']}**\n"
        text += f"   ⭐ {repo['stars']} | 🍴 {repo['forks']} | 💻 {repo['language']}\n"
        text += f"   📝 {repo['description'][:100]}{'...' if len(repo['description']) > 100 else ''}\n"
        text += f"   👤 {repo['owner']}\n\n"
    
    text += "💡 **Selecciona un repositorio con los botones**"
    return text

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar repos", callback_data="search"),
         InlineKeyboardButton("📚 Ayuda", callback_data="help")],
        [InlineKeyboardButton("📥 Descargar", callback_data="download_menu"),
         InlineKeyboardButton("🌐 GitHub", url="https://github.com")]
    ])
    
    await message.reply_text(
        f"👋 ¡Hola {user.first_name}!\n\n"
        "🤖 **GitHub Downloader Bot**\n\n"
        "📥 **Puedo descargar repositorios de GitHub y enviártelos como ZIP.**\n\n"
        "🔍 **Características:**\n"
        "• Sistema de búsqueda de repositorios\n"
        "• Descarga de repos completos\n"
        "• Soporte para ramas específicas\n"
        "• Interfaz intuitiva con botones\n\n"
        "**Comandos principales:**\n"
        "`/search <término>` - Buscar repositorios\n"
        "`/download <url>` - Descargar repositorio\n"
        "`/help` - Mostrar ayuda completa\n"
        "`/example` - Ejemplos de uso\n\n"
        "¡Envía un enlace de GitHub o busca repositorios!",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Sistema de Búsqueda de Repositorios**\n\n"
            "📝 **Uso:** `/search <término de búsqueda>`\n\n"
            "**Ejemplos:**\n"
            "• `/search python bot`\n"
            "• `/search machine learning`\n"
            "• `/search user:microsoft windows`\n\n"
            "💡 **Consejos:**\n"
            "• Usa palabras clave específicas\n"
            "• Busca por lenguaje: `language:python`\n"
            "• Busca por usuario: `user:nombre`\n"
            "• Máximo 5 resultados por página",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    query = args[1]
    
    if len(query) < 2:
        await message.reply_text("❌ La búsqueda debe tener al menos 2 caracteres.")
        return
    
    # Mensaje de procesamiento
    processing_msg = await message.reply_text(f"🔍 **Buscando:** `{query}`...")
    
    # Realizar búsqueda
    results, error = await search_github_repos(query)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    # Generar ID único para esta búsqueda
    search_id = str(uuid.uuid4())[:8]
    search_cache[search_id] = {
        "results": results,
        "query": query,
        "user_id": message.from_user.id,
        "timestamp": datetime.now().timestamp()
    }
    
    # Crear botones para los resultados
    keyboard_buttons = []
    for i, repo in enumerate(results["repos"], 1):
        callback_data = f"select_{search_id}_{i-1}"
        button_text = f"{i}. {repo['name'][:15]}{'...' if len(repo['name']) > 15 else ''}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Botones de navegación
    nav_buttons = []
    if results["has_prev"]:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
    
    if results["has_next"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([
        InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search"),
        InlineKeyboardButton("📋 Ayuda", callback_data="help")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(
        format_repo_search_results(results),
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("download"))
async def download_command(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "📥 **Descargar Repositorio**\n\n"
            "📝 **Uso:** `/download <URL del repositorio>`\n\n"
            "**Ejemplos:**\n"
            "• `/download https://github.com/usuario/repo`\n"
            "• `/download https://github.com/usuario/repo/tree/main`\n"
            "• `/download https://github.com/usuario/repo.git`\n\n"
            "💡 **También puedes usar:**\n"
            "`/search <término>` para buscar repositorios\n\n"
            "⚠️ **Límite:** 50MB por archivo",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_url = args[1].strip()
    
    # Validar URL
    if not re.match(r'^https?://github\.com/[^/]+/[^/]+', repo_url):
        await message.reply_text(
            "❌ **URL no válida**\n\n"
            "Por favor, envía una URL de GitHub válida.\n"
            "**Formato:** `https://github.com/usuario/repositorio`\n\n"
            "💡 Usa `/search` para encontrar repositorios",
            parse_mode=enums.ParseMode.MARKDOWN
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
    filename = f"{repo_name or 'repositorio'}.zip"
    
    # Calcular tamaño
    file_size_mb = len(zip_content) / 1024 / 1024
    
    # Preparar para enviar
    await processing_msg.edit_text(f"✅ **Descarga completada!**\n📦 Tamaño: {file_size_mb:.1f}MB\n📤 Enviando...")
    
    try:
        # Enviar como documento
        await message.reply_document(
            document=io.BytesIO(zip_content),
            file_name=filename,
            caption=(
                f"📦 **{repo_name or 'Repositorio'}**\n"
                f"🔗 {repo_url}\n"
                f"📊 Tamaño: {file_size_mb:.1f}MB\n"
                f"👤 Usuario: {username or 'Desconocido'}\n\n"
                f"✅ Descargado por @{client.me.username}"
            ),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error enviando documento: {e}")
        await processing_msg.edit_text(f"❌ **Error al enviar:** {str(e)[:100]}")

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
🤖 **GitHub Downloader Bot - Ayuda**

📥 **¿Qué puedo hacer?**
• 🔍 **Buscar repositorios** en GitHub
• 📥 Descargar repositorios completos
• 📁 Enviarlos como archivo ZIP
• 🌿 Soporte para ramas específicas
• 📊 Información detallada del repositorio

🛠️ **Comandos:**
`/start` - Iniciar el bot
`/search <término>` - Buscar repositorios
`/download <url>` - Descargar repositorio
`/help` - Mostrar esta ayuda
`/example` - Ver ejemplos de uso
`/info` - Información del bot
`/clear_cache` - Limpiar caché de búsqueda

🔍 **Sistema de búsqueda:**
• Busca en todos los repos públicos de GitHub
• Ordena por popularidad (estrellas)
• Muestra descripción, lenguaje y estadísticas
• Navegación por páginas

🔗 **Formatos de URL aceptados:**
• `https://github.com/usuario/repo`
• `https://github.com/usuario/repo/tree/main`
• `https://github.com/usuario/repo/tree/develop`
• `https://github.com/usuario/repo.git`

⚠️ **Limitaciones:**
• Máximo 50MB por archivo (límite de Telegram)
• Solo repositorios públicos
• Límites de API de GitHub (10-30 búsquedas/min)
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example"),
         InlineKeyboardButton("📥 Ejemplo rápido", callback_data="quick_download")],
        [InlineKeyboardButton("📚 Comandos", callback_data="commands"),
         InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("example"))
async def example_command(client: Client, message: Message):
    examples = """
📚 **Ejemplos de uso:**

🔍 **Búsquedas:**
`/search python bot telegram`
`/search machine learning tensorflow`
`/search language:javascript game`
`/search user:microsoft windows`

📥 **Descargas:**
`/download https://github.com/octocat/Spoon-Knife`
`/download https://github.com/python/cpython`
`/download https://github.com/torvalds/linux/tree/master`

🔥 **Búsquedas populares:**
• `/search python`
• `/search javascript framework`
• `/search open source`
• `/search ai machine learning`

💡 **Consejo:** Usa la búsqueda para encontrar repositorios antes de descargarlos!
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar 'python bot'", callback_data="search_python"),
         InlineKeyboardButton("📥 Descargar ejemplo", callback_data="quick_download")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help"),
         InlineKeyboardButton("🏠 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(examples, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.regex(r'https?://github\.com/[^\s]+'))
async def handle_github_url(client: Client, message: Message):
    """Detecta automáticamente URLs de GitHub en mensajes"""
    urls = re.findall(r'https?://github\.com/[^\s]+', message.text)
    
    if urls:
        repo_url = urls[0]
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Descargar ZIP", callback_data=f"dl_{repo_url}"),
             InlineKeyboardButton("🔍 Ver detalles", callback_data=f"info_{repo_url}")],
            [InlineKeyboardButton("🌐 Abrir en GitHub", url=repo_url)]
        ])
        
        username, repo_name = get_repo_info_from_url(repo_url)
        
        await message.reply_text(
            f"🔍 **Repositorio detectado:**\n\n"
            f"**Nombre:** {repo_name or 'Desconocido'}\n"
            f"**Usuario:** {username or 'Desconocido'}\n"
            f"**URL:** {repo_url}\n\n"
            "¿Qué quieres hacer?",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user = callback_query.from_user
    message = callback_query.message
    
    try:
        # Limpiar caché expirada
        current_time = datetime.now().timestamp()
        expired_keys = [
            key for key, value in search_cache.items()
            if current_time - value.get("timestamp", 0) > SEARCH_CACHE_TIMEOUT
        ]
        for key in expired_keys:
            del search_cache[key]
        
        if data == "help":
            await help_command(client, message)
            await callback_query.answer()
            
        elif data == "example":
            await example_command(client, message)
            await callback_query.answer()
            
        elif data == "start":
            await start_command(client, message)
            await callback_query.answer()
            
        elif data == "search":
            await callback_query.message.reply_text(
                "🔍 **Nueva búsqueda**\n\n"
                "Envía tu término de búsqueda:\n\n"
                "**Ejemplos:**\n"
                "`python telegram bot`\n"
                "`machine learning`\n"
                "`web development`\n\n"
                "O usa: `/search <término>`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer()
            
        elif data == "download_menu":
            await callback_query.message.reply_text(
                "📥 **Descargar repositorio**\n\n"
                "Envía la URL del repositorio de GitHub:\n\n"
                "**Formato:**\n"
                "`https://github.com/usuario/repositorio`\n\n"
                "O usa: `/download <URL>`\n\n"
                "💡 **Consejo:** Usa primero `/search` para encontrar repositorios",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer()
            
        elif data == "search_example":
            processing_msg = await callback_query.message.reply_text("🔍 **Ejemplo:** Buscando `python bot`...")
            results, error = await search_github_repos("python bot")
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                search_id = str(uuid.uuid4())[:8]
                search_cache[search_id] = {
                    "results": results,
                    "query": "python bot",
                    "user_id": user.id,
                    "timestamp": current_time
                }
                
                keyboard_buttons = []
                for i, repo in enumerate(results["repos"], 1):
                    callback_data = f"select_{search_id}_{i-1}"
                    button_text = f"{i}. {repo['name'][:15]}"
                    keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                
                keyboard_buttons.append([InlineKeyboardButton("🔄 Buscar algo diferente", callback_data="search")])
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                
                await processing_msg.edit_text(
                    format_repo_search_results(results),
                    reply_markup=keyboard,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            await callback_query.answer()
            
        elif data.startswith(("prev_", "next_")):
            parts = data.split("_")
            action = parts[0]
            search_id = parts[1]
            current_page = int(parts[2])
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            
            if search_data["user_id"] != user.id:
                await callback_query.answer("❌ Esta búsqueda no es tuya")
                return
            
            new_page = current_page - 1 if action == "prev" else current_page + 1
            query = search_data["query"]
            
            results, error = await search_github_repos(query, new_page)
            
            if error:
                await callback_query.answer(f"Error: {error}")
                return
            
            search_cache[search_id]["results"] = results
            search_cache[search_id]["timestamp"] = current_time
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            nav_buttons = []
            if results["has_prev"]:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
            
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
            
            keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await message.edit_text(
                format_repo_search_results(results),
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer(f"Página {new_page}")
            
        elif data.startswith("select_"):
            parts = data.split("_")
            search_id = parts[1]
            repo_index = int(parts[2])
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            
            if search_data["user_id"] != user.id:
                await callback_query.answer("❌ Esta búsqueda no es tuya")
                return
            
            repos = search_data["results"]["repos"]
            
            if repo_index >= len(repos):
                await callback_query.answer("❌ Repositorio no encontrado")
                return
            
            repo = repos[repo_index]
            
            details_text = f"""
📦 **{repo['full_name']}**

📝 **Descripción:** {repo['description']}

📊 **Estadísticas:**
⭐ Estrellas: {repo['stars']}
🍴 Forks: {repo['forks']}
💻 Lenguaje: {repo['language']}
👤 Propietario: {repo['owner']}
🕐 Actualizado: {repo['updated_at'][:10]}

🔗 **URL:** {repo['url']}
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Descargar", callback_data=f"dl_{repo['url']}"),
                 InlineKeyboardButton("🌐 Ver en GitHub", url=repo['url'])],
                [InlineKeyboardButton("🔙 Volver a resultados", callback_data=f"back_{search_id}"),
                 InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")]
            ])
            
            await message.edit_text(details_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            await callback_query.answer(f"Seleccionado: {repo['name']}")
            
        elif data.startswith("back_"):
            search_id = data.split("_")[1]
            
            if search_id not in search_cache:
                await callback_query.answer("❌ La búsqueda ha expirado")
                return
            
            search_data = search_cache[search_id]
            results = search_data["results"]
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            nav_buttons = []
            if results["has_prev"]:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
            
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
            
            keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await message.edit_text(
                format_repo_search_results(results),
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer("Volviendo a resultados...")
            
        elif data.startswith("dl_"):
            repo_url = data[3:]
            
            processing_msg = await callback_query.message.reply_text("⏳ Descargando...")
            
            zip_content, error = await download_github_repo(repo_url)
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                username, repo_name = get_repo_info_from_url(repo_url)
                filename = f"{repo_name or 'repo'}.zip"
                file_size_mb = len(zip_content) / 1024 / 1024
                
                await callback_query.message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name=filename,
                    caption=(
                        f"📦 **{repo_name or 'Repositorio'}**\n"
                        f"🔗 {repo_url}\n"
                        f"📊 Tamaño: {file_size_mb:.1f}MB\n"
                        f"👤 Usuario: {username or 'Desconocido'}\n\n"
                        f"✅ Descargado por @{client.me.username}"
                    ),
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await processing_msg.delete()
            
            await callback_query.answer("✅ Descarga completada")
            
        elif data == "quick_download":
            example_url = "https://github.com/octocat/Spoon-Knife"
            
            msg = await callback_query.message.reply_text("⏳ Descargando ejemplo...")
            zip_content, error = await download_github_repo(example_url)
            
            if error:
                await msg.edit_text(f"❌ Error: {error}")
            else:
                await callback_query.message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name="Spoon-Knife.zip",
                    caption="🍴 **Spoon-Knife**\nRepositorio de prueba de GitHub\nDescargado por GitHub Downloader Bot",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await msg.delete()
            
            await callback_query.answer()
            
        elif data.startswith("search_similar_"):
            repo_url = data[15:]
            username, repo_name = get_repo_info_from_url(repo_url)
            
            if repo_name:
                await callback_query.message.reply_text(f"🔍 Buscando repositorios similares a `{repo_name}`...")
                await search_command(client, message)
                await callback_query.answer(f"Buscando: {repo_name}")
            else:
                await callback_query.answer("❌ No se pudo extraer nombre del repositorio")
                
    except Exception as e:
        logger.error(f"Error en handle_callback: {e}")
        await callback_query.answer("❌ Error interno del bot")

@app.on_message(filters.command("info"))
async def info_command(client: Client, message: Message):
    info_text = f"""
🤖 **GitHub Downloader Bot v2.0**
    
**Desarrollador:** [Tu Nombre]
**Username:** @{client.me.username}
**ID:** {client.me.id}
**Versión:** 2.0
    
**✨ Características:**
• 🔍 Sistema de búsqueda de repositorios
• 📥 Descarga de repos completos
• 📊 Estadísticas en tiempo real
• 🔄 Navegación por páginas
• 📋 Vista detallada de repos
    
**🛠️ Tecnologías:**
• Pyrogram para Telegram
• API de GitHub
• aiohttp para descargas asíncronas
• Manejo eficiente de memoria
    
**⚠️ Límites:** 
• 50MB por archivo (Telegram)
• 10-30 búsquedas/min (API GitHub)
• Solo repos públicos
    
**Comandos principales:**
`/search <término>` - Buscar repos
`/download <url>` - Descargar repo
`/help` - Ayuda completa
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example"),
         InlineKeyboardButton("📚 Ver ayuda", callback_data="help")],
        [InlineKeyboardButton("📖 Documentación", url="https://docs.github.com/rest")]
    ])
    
    await message.reply_text(info_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("clear_cache"))
async def clear_cache_command(client: Client, message: Message):
    """Comando para limpiar la caché de búsqueda"""
    global search_cache
    count = len(search_cache)
    search_cache.clear()
    cleanup_old_temp_files()
    await message.reply_text(f"✅ Caché limpiada. Se eliminaron {count} búsquedas y archivos temporales antiguos.")

@app.on_message(filters.command("cleanup"))
async def cleanup_command(client: Client, message: Message):
    """Comando para limpieza manual"""
    try:
        # Limpiar directorio temporal
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR)
        
        # Limpiar caché
        global search_cache
        count = len(search_cache)
        search_cache.clear()
        
        await message.reply_text(f"✅ Limpieza completa. Directorio temporal recreado y {count} búsquedas eliminadas.")
    except Exception as e:
        await message.reply_text(f"❌ Error en limpieza: {str(e)}")

async def periodic_cleanup():
    """Limpieza periódica automática"""
    while True:
        await asyncio.sleep(3600)  # 1 hora
        try:
            # Limpiar caché expirada
            current_time = datetime.now().timestamp()
            expired_keys = [
                key for key, value in search_cache.items()
                if current_time - value.get("timestamp", 0) > SEARCH_CACHE_TIMEOUT
            ]
            for key in expired_keys:
                del search_cache[key]
            
            # Limpiar archivos temporales
            cleanup_old_temp_files()
            
            logger.info(f"🔄 Limpieza periódica completada. Caché: {len(search_cache)} entradas")
        except Exception as e:
            logger.error(f"Error en limpieza periódica: {e}")

# Iniciar limpieza periódica
@app.on_raw_update()
async def on_start(client, update):
    if not hasattr(on_start, "started"):
        on_start.started = True
        asyncio.create_task(periodic_cleanup())
        logger.info("🤖 GitHub Downloader Bot iniciado correctamente!")

# Configurar manejo de excepciones global
async def main():
    try:
        logger.info("🚀 Iniciando GitHub Downloader Bot...")
        await app.start()
        
        # Información del bot
        me = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{me.username}")
        
        # Mantener el bot en ejecución
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
    finally:
        await app.stop()

if __name__ == "__main__":
    # Ejecutar el bot
    app.run()