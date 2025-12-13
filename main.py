import os
import asyncio
import shutil
import sys
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import aiohttp
import zipfile
import io
import json
import re
import uuid
import time
import pathlib
import mimetypes
import humanize
from typing import Optional, Tuple, Dict, Any, List
import logging
from datetime import datetime, timedelta
import hashlib
from functools import wraps

# ==============================================
# CONFIGURACIÓN AVANZADA DE LOGGING
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_activity.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURACIÓN PRINCIPAL
# ==============================================

API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"

# ID del administrador principal (tú)
ADMIN_ID = 7970466590

# Variables de control
USER_ACTIVITY_LOG = {}  # Diccionario para registrar actividad de usuarios
MAX_USER_LOG_ENTRIES = 50  # Máximo de entradas por usuario

logger.info(f"✅ Sistema inicializado | Admin ID: {ADMIN_ID}")

# Verificar credenciales
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Faltan credenciales. Configura las variables de entorno.")
    sys.exit(1)

# Crear cliente Pyrogram
app = Client(
    "github_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

# Directorios del sistema
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_downloads")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Asegurar que existen los directorios necesarios
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ==============================================
# SISTEMA DE NOTIFICACIONES AL ADMIN
# ==============================================

async def notify_admin_activity(client: Client, user_info: Dict, action: str, details: str = ""):
    """
    Notifica al administrador sobre la actividad de otros usuarios
    """
    try:
        if user_info.get("id") == ADMIN_ID:
            return  # No notificar sobre la actividad del admin
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Formato del mensaje de notificación
        notification_text = f"""
🔔 **Actividad de Usuario Detectada**

👤 **Usuario:** {user_info.get('first_name', 'Desconocido')}
🆔 **ID:** `{user_info.get('id', 'N/A')}`
📝 **Acción:** {action}
🕐 **Hora:** {timestamp}

📋 **Detalles:**
{details if details else 'Sin detalles adicionales'}
        """
        
        # Enviar notificación al admin
        await client.send_message(
            chat_id=ADMIN_ID,
            text=notification_text,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        logger.info(f"📢 Notificación enviada al admin | Usuario: {user_info.get('id')} | Acción: {action}")
        
    except Exception as e:
        logger.error(f"❌ Error enviando notificación al admin: {e}")

def log_user_activity(user_id: int, action: str, details: str = ""):
    """
    Registra la actividad del usuario en el log interno
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if user_id not in USER_ACTIVITY_LOG:
            USER_ACTIVITY_LOG[user_id] = []
        
        log_entry = {
            "timestamp": timestamp,
            "action": action,
            "details": details
        }
        
        USER_ACTIVITY_LOG[user_id].append(log_entry)
        
        # Mantener solo las últimas entradas
        if len(USER_ACTIVITY_LOG[user_id]) > MAX_USER_LOG_ENTRIES:
            USER_ACTIVITY_LOG[user_id] = USER_ACTIVITY_LOG[user_id][-MAX_USER_LOG_ENTRIES:]
        
        # También guardar en archivo
        with open(os.path.join(LOGS_DIR, "user_activity.log"), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] UserID:{user_id} | Action:{action} | Details:{details}\n")
            
    except Exception as e:
        logger.error(f"Error registrando actividad del usuario: {e}")

# ==============================================
# DECORADORES UTILITARIOS
# ==============================================

def track_user_activity(action_name: str):
    """
    Decorador para rastrear actividad de usuarios
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message, *args, **kwargs):
            user_info = {
                "id": message.from_user.id if message.from_user else None,
                "username": message.from_user.username if message.from_user else None,
                "first_name": message.from_user.first_name if message.from_user else None,
                "last_name": message.from_user.last_name if message.from_user else None
            }
            
            # Registrar actividad
            log_user_activity(user_info["id"], action_name, message.text[:200] if message.text else "")
            
            # Notificar al admin si no es él
            if user_info["id"] != ADMIN_ID:
                details = f"Comando: {message.text[:100] if message.text else 'N/A'}"
                await notify_admin_activity(client, user_info, action_name, details)
            
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator

# ==============================================
# FUNCIONES PARA GITHUB (MEJORADAS)
# ==============================================

async def download_github_repo(repo_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Descarga un repositorio de GitHub como archivo ZIP
    Versión mejorada con manejo de errores y caché
    """
    try:
        if not repo_url or "github.com" not in repo_url:
            return None, "❌ URL de GitHub no válida"
        
        repo_url = repo_url.strip().rstrip('/')
        
        # Expresiones regulares mejoradas
        patterns = [
            r"github\.com/([^/]+)/([^/?#]+)",
            r"github\.com/([^/]+)/([^/]+)/tree/([^/]+)",
            r"github\.com/([^/]+)/([^/]+)\.git"
        ]
        
        username = repo_name = branch = None
        
        for pattern in patterns:
            match = re.search(pattern, repo_url)
            if match:
                username = match.group(1)
                repo_name = match.group(2)
                if len(match.groups()) > 2:
                    branch = match.group(3)
                break
        
        if not username or not repo_name:
            return None, "❌ No se pudo extraer información del repositorio"
        
        repo_name = re.sub(r'\.git$', '', repo_name)
        branch = branch or "main"
        
        # URL de descarga
        download_url = f"https://github.com/{username}/{repo_name}/archive/refs/heads/{branch}.zip"
        
        # Configurar timeout
        timeout = aiohttp.ClientTimeout(total=300, connect=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; GitHubDownloaderBot/2.0)',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            async with session.get(download_url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Verificar tamaño
                    if len(content) > 50 * 1024 * 1024:  # 50MB
                        return None, f"❌ Archivo demasiado grande ({len(content)/1024/1024:.1f}MB)"
                    
                    return content, None
                
                elif response.status == 404:
                    # Intentar con master como alternativa
                    alt_url = download_url.replace("/main.zip", "/master.zip")
                    async with session.get(alt_url, headers=headers) as response2:
                        if response2.status == 200:
                            content = await response2.read()
                            return content, None
                        return None, "❌ Repositorio o rama no encontrada"
                
                else:
                    return None, f"❌ Error HTTP {response.status}: {await response.text()[:100]}"
                    
    except asyncio.TimeoutError:
        return None, "⏰ Tiempo de espera agotado"
    except aiohttp.ClientError as e:
        return None, f"🌐 Error de conexión: {str(e)}"
    except Exception as e:
        logger.error(f"Error descargando repositorio: {e}")
        return None, f"⚠️ Error interno: {str(e)[:100]}"

async def search_github_repos(query: str, page: int = 1, per_page: int = 5) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Busca repositorios en GitHub usando la API
    Versión mejorada con caché y manejo de errores
    """
    try:
        if not query or len(query.strip()) < 2:
            return None, "🔍 La búsqueda debe tener al menos 2 caracteres"
        
        query = query.strip()
        encoded_query = aiohttp.helpers.quote(query, safe='')
        
        # URL de la API de GitHub
        url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&page={page}&per_page={per_page}"
        
        headers = {
            'User-Agent': 'GitHubDownloaderBot/3.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 403:
                    return None, "⏳ Límite de API alcanzado. Intenta más tarde"
                elif response.status == 422:
                    return None, "❌ Consulta de búsqueda no válida"
                elif response.status != 200:
                    return None, f"⚠️ Error API: {response.status}"
                
                data = await response.json()
                
                if "items" not in data or not data["items"]:
                    return None, "🔍 No se encontraron repositorios"
                
                # Procesar resultados
                repos = []
                for item in data["items"]:
                    description = item.get("description") or "Sin descripción"
                    if len(description) > 150:
                        description = description[:147] + "..."
                    
                    repo_info = {
                        "name": item.get("name", "Desconocido"),
                        "full_name": item.get("full_name", "Desconocido"),
                        "description": description,
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "language": item.get("language") or "No especificado",
                        "updated_at": item.get("updated_at", ""),
                        "owner": item.get("owner", {}).get("login", "Desconocido"),
                        "topics": item.get("topics", [])[:5]  # Primeros 5 temas
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
        return None, f"🌐 Error de conexión: {str(e)}"
    except Exception as e:
        logger.error(f"Error en búsqueda GitHub: {e}")
        return None, f"⚠️ Error interno: {str(e)[:100]}"

# ==============================================
# COMANDOS DEL BOT (INTERFAZ MEJORADA)
# ==============================================

@app.on_message(filters.command("start"))
@track_user_activity("Comando /start")
async def start_command(client: Client, message: Message):
    """
    Comando de inicio con interfaz mejorada
    """
    user = message.from_user
    
    welcome_text = f"""
🌟 **¡Hola {user.first_name}!** 🌟

🤖 **GitHub Downloader Pro** 
*Tu asistente para descargas de GitHub*

✨ **Funciones principales:**
• 📥 **Descarga rápida** de repositorios
• 🔍 **Búsqueda avanzada** en GitHub
• 📦 **Envío directo** como archivo ZIP
• ⚡ **Procesamiento optimizado**

🚀 **Comienza ahora:**
1. Envía un enlace de GitHub
2. Usa `/search <término>`
3. Usa `/download <URL>`

💡 **Consejo rápido:** Puedes pegar cualquier enlace de GitHub directamente.
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar Repositorios", callback_data="search_menu")],
        [InlineKeyboardButton("📥 Descargar Guía", callback_data="download_guide")],
        [InlineKeyboardButton("📚 Comandos", callback_data="show_commands"),
         InlineKeyboardButton("ℹ️ Información", callback_data="about_bot")],
        [InlineKeyboardButton("🌐 Visitar GitHub", url="https://github.com")]
    ])
    
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("search"))
@track_user_activity("Comando /search")
async def search_command(client: Client, message: Message):
    """
    Comando de búsqueda mejorado
    """
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        help_text = """
🔍 **Sistema de Búsqueda Avanzado**

📝 **Uso:** `/search <término de búsqueda>`

📚 **Ejemplos:**
• `/search python telegram bot`
• `/search machine learning tutorial`
• `/search user:microsoft windows`
• `/search language:javascript game`

🎯 **Operadores útiles:**
• `user:` - Buscar por usuario/organización
• `language:` - Filtrar por lenguaje
• `stars:` - Filtrar por estrellas
• `fork:` - Incluir forks

💡 **Sugerencias:**
• Usa términos específicos
• Combina operadores
• Revisa la ortografía
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Ejemplo: Python Bot", callback_data="search_example_python")],
            [InlineKeyboardButton("✨ Ejemplo: Machine Learning", callback_data="search_example_ml")]
        ])
        
        await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    query = args[1]
    
    if len(query) < 2:
        await message.reply_text("❌ El término de búsqueda debe tener al menos 2 caracteres.")
        return
    
    # Mensaje de procesamiento elegante
    processing_msg = await message.reply_text(f"""
🔎 **Procesando búsqueda...**

📋 **Término:** `{query[:50]}{'...' if len(query) > 50 else ''}`
⏳ **Estado:** Analizando resultados...
    """, parse_mode=enums.ParseMode.MARKDOWN)
    
    results, error = await search_github_repos(query)
    
    if error:
        await processing_msg.edit_text(f"⚠️ **Resultado de búsqueda**\n\n❌ **Error:** {error}")
        return
    
    # Crear identificador único para esta búsqueda
    search_id = str(uuid.uuid4())[:8]
    
    # Botones de resultados
    keyboard_buttons = []
    
    for i, repo in enumerate(results["repos"], 1):
        repo_display_name = repo['name'][:20] + ('...' if len(repo['name']) > 20 else '')
        button_text = f"{i}. {repo_display_name} ⭐{repo['stars']}"
        callback_data = f"repo_select_{search_id}_{i-1}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Botones de navegación
    nav_buttons = []
    if results["has_prev"]:
        nav_buttons.append(InlineKeyboardButton("◀️ Anterior", 
            callback_data=f"search_prev_{search_id}_{results['page']}"))
    
    if results["has_next"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ▶️", 
            callback_data=f"search_next_{search_id}_{results['page']}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Botones adicionales
    keyboard_buttons.append([
        InlineKeyboardButton("🔄 Nueva Búsqueda", callback_data="new_search"),
        InlineKeyboardButton("📋 Ayuda", callback_data="search_help")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    # Texto de resultados formateado
    results_text = f"""
✅ **Búsqueda completada**

🔍 **Término:** `{query}`
📊 **Resultados:** {results['total_count']} repositorios encontrados
📄 **Página:** {results['page']}

🎯 **Top {len(results['repos'])} resultados:**
    """
    
    await processing_msg.edit_text(results_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("download"))
@track_user_activity("Comando /download")
async def download_command(client: Client, message: Message):
    """
    Comando de descarga mejorado
    """
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        help_text = """
📥 **Sistema de Descarga Directa**

🔗 **Uso:** `/download <URL de GitHub>`

🌐 **Formatos aceptados:**
• `https://github.com/usuario/repositorio`
• `https://github.com/usuario/repositorio/tree/rama`
• `https://github.com/usuario/repositorio.git`

⚡ **Ejemplos rápidos:**
• `/download https://github.com/octocat/Spoon-Knife`
• `/download https://github.com/python/cpython`

⚠️ **Limitaciones:**
• Máximo 50MB por archivo
• Solo repositorios públicos
• Sin límites de tasa básicos
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Ejemplo rápido", callback_data="quick_example_download")],
            [InlineKeyboardButton("🔍 Buscar primero", callback_data="search_menu")]
        ])
        
        await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    repo_url = args[1].strip()
    
    # Validar URL
    if not re.match(r'^https?://(www\.)?github\.com/[^/]+/[^/]+', repo_url):
        await message.reply_text("""
❌ **URL no válida**

ℹ️ **Formato correcto:**
`https://github.com/usuario/nombre-repositorio`

💡 **Verifica que:**
1. Comience con https://github.com/
2. Incluya nombre de usuario
3. Incluya nombre del repositorio
        """, parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    # Proceso de descarga con pasos
    steps = [
        "🔄 Validando URL...",
        "🌐 Conectando con GitHub...",
        "📦 Preparando descarga...",
        "⏬ Descargando contenido..."
    ]
    
    current_step = await message.reply_text("🚀 **Iniciando descarga...**\n\n" + steps[0])
    
    for i, step in enumerate(steps[1:], 1):
        await asyncio.sleep(0.5)
        await current_step.edit_text(f"🚀 **Progreso de descarga**\n\n✅ {steps[i-1]}\n▶️ {step}")
    
    # Realizar descarga
    zip_content, error = await download_github_repo(repo_url)
    
    if error:
        await current_step.edit_text(f"""
❌ **Descarga fallida**

🔗 **URL:** {repo_url[:50]}...
📋 **Error:** {error}

💡 **Soluciones posibles:**
• Verifica que el repositorio sea público
• Intenta con otra rama
• Verifica tu conexión
        """)
        return
    
    # Extraer información
    match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
    if match:
        username, repo_name = match.groups()
        repo_name = re.sub(r'\.git$', '', repo_name)
        repo_name = repo_name.split('/')[0] if '/' in repo_name else repo_name
    else:
        username, repo_name = "Desconocido", "repositorio"
    
    filename = f"{repo_name}.zip"
    file_size_mb = len(zip_content) / 1024 / 1024
    
    # Actualizar estado
    await current_step.edit_text(f"""
✅ **Descarga completada**

📦 **Repositorio:** {repo_name}
👤 **Usuario:** {username}
💾 **Tamaño:** {file_size_mb:.2f} MB
📤 **Enviando archivo...**
    """)
    
    try:
        # Enviar archivo
        await message.reply_document(
            document=io.BytesIO(zip_content),
            file_name=filename,
            caption=f"""
📦 **{repo_name}** | Por {username}

🔗 **URL:** {repo_url}
💾 **Tamaño:** {file_size_mb:.2f} MB
📅 **Descargado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

✅ *Descarga completada exitosamente*
            """,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Eliminar mensaje de progreso
        await current_step.delete()
        
    except Exception as e:
        logger.error(f"Error enviando documento: {e}")
        await current_step.edit_text(f"""
❌ **Error al enviar archivo**

📋 **Detalles:** {str(e)[:100]}

💡 **Posible causa:**
• El archivo es demasiado grande
• Problemas de conexión
• Límites de Telegram
        """)

@app.on_message(filters.command("help"))
@track_user_activity("Comando /help")
async def help_command(client: Client, message: Message):
    """
    Comando de ayuda completo y mejorado
    """
    help_text = """
🆘 **Centro de Ayuda - GitHub Downloader Pro**

📚 **Secciones disponibles:**

1️⃣ **🔄 COMANDOS BÁSICOS**
• `/start` - Iniciar el bot y ver menú principal
• `/help` - Mostrar este mensaje de ayuda
• `/info` - Información del bot y estadísticas

2️⃣ **🔍 COMANDOS DE BÚSQUEDA**
• `/search <término>` - Buscar repositorios
• `/search user:<usuario>` - Buscar por usuario
• `/search language:<lenguaje>` - Filtrar por lenguaje

3️⃣ **📥 COMANDOS DE DESCARGA**
• `/download <URL>` - Descargar repositorio
• `/download <URL>/tree/<rama>` - Descargar rama específica

4️⃣ **⚙️ FUNCIONES AVANZADAS**
• Detección automática de URLs GitHub
• Soporte para múltiples formatos de URL
• Procesamiento en segundo plano

⚠️ **LIMITACIONES Y NOTAS:**
• Límite de 50MB por archivo (Telegram)
• Solo repositorios públicos
• Máximo 30 segundos por descarga
• Sin almacenamiento permanente

❓ **¿NECESITAS MÁS AYUDA?**
Contacta al administrador o revisa los ejemplos.
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver Ejemplos", callback_data="show_examples"),
         InlineKeyboardButton("🚀 Probar Ahora", callback_data="quick_start")],
        [InlineKeyboardButton("📊 Ver Estadísticas", callback_data="show_stats"),
         InlineKeyboardButton("🌐 Documentación", url="https://docs.github.com")],
        [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("info"))
@track_user_activity("Comando /info")
async def info_command(client: Client, message: Message):
    """
    Comando de información del bot
    """
    try:
        bot_info = await client.get_me()
        
        # Obtener estadísticas básicas
        total_users = len(USER_ACTIVITY_LOG)
        today = datetime.now().strftime("%Y-%m-%d")
        today_activities = sum(len(logs) for logs in USER_ACTIVITY_LOG.values())
        
        info_text = f"""
🤖 **Información del Bot**

**📛 Nombre:** {bot_info.first_name}
**👤 Username:** @{bot_info.username}
**🆔 ID:** `{bot_info.id}`

**📊 Estadísticas:**
• 👥 Usarios únicos: {total_users}
• 📈 Actividades hoy: {today_activities}
• 💾 Directorio temporal: {TEMP_DIR}

**⚙️ Configuración:**
• Admin ID: `{ADMIN_ID}`
• Versión: 3.0 Pro
• Estado: ✅ Operativo

**🕐 Última actualización:**
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💡 *Este bot está diseñado para descargas rápidas y seguras de GitHub*
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_info")],
            [InlineKeyboardButton("📊 Ver Logs", callback_data="view_logs"),
             InlineKeyboardButton("🏠 Inicio", callback_data="main_menu")]
        ])
        
        await message.reply_text(info_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error en comando info: {e}")
        await message.reply_text("❌ Error obteniendo información del bot.")

# ==============================================
# DETECCIÓN AUTOMÁTICA DE URLS GITHUB
# ==============================================

@app.on_message(filters.regex(r'https?://(www\.)?github\.com/[^\s]+'))
@track_user_activity("URL GitHub detectada")
async def handle_github_url(client: Client, message: Message):
    """
    Detecta automáticamente URLs de GitHub en los mensajes
    """
    urls = re.findall(r'https?://(www\.)?github\.com/[^\s]+', message.text)
    
    if not urls:
        return
    
    repo_url = urls[0]
    
    # Extraer información básica
    match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
    
    if match:
        username, repo_name = match.groups()
        repo_name = re.sub(r'\.git$', '', repo_name)
        repo_name = repo_name.split('/')[0] if '/' in repo_name else repo_name
    else:
        username, repo_name = "Desconocido", "Repositorio"
    
    # Interfaz de opciones elegante
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Descargar ZIP", callback_data=f"url_dl_{repo_url}"),
         InlineKeyboardButton("🔍 Ver Detalles", callback_data=f"url_info_{repo_url}")],
        [InlineKeyboardButton("🌐 Abrir en GitHub", url=repo_url),
         InlineKeyboardButton("🗑️ Descartar", callback_data="dismiss")]
    ])
    
    await message.reply_text(
        f"""
🔗 **URL de GitHub detectada**

📦 **Repositorio:** `{repo_name}`
👤 **Usuario:** `{username}`
🔍 **URL:** {repo_url[:50]}...

💡 **¿Qué deseas hacer?**
        """,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ==============================================
# COMANDOS DE ADMINISTRADOR
# ==============================================

@app.on_message(filters.command("admin") & filters.user(ADMIN_ID))
async def admin_command(client: Client, message: Message):
    """
    Panel de administración exclusivo para el admin
    """
    # Obtener estadísticas
    total_users = len(USER_ACTIVITY_LOG)
    
    # Actividad reciente (últimas 24 horas)
    recent_activities = 0
    for user_logs in USER_ACTIVITY_LOG.values():
        for log in user_logs[-10:]:  # Últimas 10 entradas por usuario
            try:
                log_time = datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - log_time).total_seconds() <= 86400:  # 24 horas
                    recent_activities += 1
            except:
                continue
    
    admin_text = f"""
🔧 **Panel de Administración**

📊 **Estadísticas del sistema:**
• 👥 Usuarios únicos: {total_users}
• 📈 Actividad (24h): {recent_activities}
• 💾 Espacio temporal: {TEMP_DIR}

👤 **Tu información:**
• ID: `{message.from_user.id}`
• Nombre: {message.from_user.first_name}

⚙️ **Opciones disponibles:**
        """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Ver Actividad", callback_data="admin_view_activity"),
         InlineKeyboardButton("🧹 Limpiar Cache", callback_data="admin_clear_cache")],
        [InlineKeyboardButton("📋 Ver Logs", callback_data="admin_view_logs"),
         InlineKeyboardButton("🔄 Reiniciar", callback_data="admin_restart")],
        [InlineKeyboardButton("🏠 Volver", callback_data="main_menu")]
    ])
    
    await message.reply_text(admin_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# MANEJADOR DE CALLBACKS MEJORADO
# ==============================================

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query: CallbackQuery):
    """
    Maneja todas las interacciones con botones inline
    """
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    
    try:
        # REGISTRAR ACTIVIDAD EN CALLBACKS TAMBIÉN
        log_user_activity(user_id, f"Callback: {data[:30]}")
        
        # NOTIFICAR AL ADMIN SI NO ES ÉL
        if user_id != ADMIN_ID:
            user_info = {
                "id": callback_query.from_user.id,
                "username": callback_query.from_user.username,
                "first_name": callback_query.from_user.first_name
            }
            await notify_admin_activity(client, user_info, f"Botón: {data[:30]}")
        
        # MENÚ PRINCIPAL
        if data == "main_menu":
            await start_command(client, message)
        
        # BÚSQUEDA
        elif data == "search_menu":
            await message.edit_text("""
🔍 **Menú de Búsqueda**

💡 **Selecciona una opción:**
• Buscar repositorios
• Ver ejemplos
• Ayuda de búsqueda
            """, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Nueva Búsqueda", callback_data="new_search")],
                [InlineKeyboardButton("📚 Ver Ejemplos", callback_data="search_examples")],
                [InlineKeyboardButton("❓ Ayuda Búsqueda", callback_data="search_help")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
            ]))
        
        # DESCARGAS
        elif data.startswith("url_dl_"):
            repo_url = data[7:]  # Remover "url_dl_"
            
            processing_msg = await message.reply_text("⏳ Preparando descarga...")
            
            zip_content, error = await download_github_repo(repo_url)
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                # Extraer información para el nombre del archivo
                match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
                if match:
                    username, repo_name = match.groups()
                    repo_name = re.sub(r'\.git$', '', repo_name)
                    filename = f"{repo_name}.zip"
                else:
                    filename = "repositorio.zip"
                
                await callback_query.message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name=filename,
                    caption=f"📦 Descargado desde: {repo_url}"
                )
                await processing_msg.delete()
        
        # INFORMACIÓN DE REPOSITORIO
        elif data.startswith("url_info_"):
            repo_url = data[9:]  # Remover "url_info_"
            
            match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
            if match:
                username, repo_name = match.groups()
                info_text = f"""
📋 **Información del Repositorio**

📦 **Nombre:** {repo_name}
👤 **Usuario:** {username}
🔗 **URL:** {repo_url}

💡 **Opciones disponibles:**
                """
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Descargar", callback_data=f"url_dl_{repo_url}")],
                    [InlineKeyboardButton("🌐 Abrir en GitHub", url=repo_url)],
                    [InlineKeyboardButton("🔙 Volver", callback_data="dismiss")]
                ])
                
                await message.edit_text(info_text, reply_markup=keyboard)
        
        # DESCARTAR MENSAJE
        elif data == "dismiss":
            await message.delete()
        
        # EJEMPLOS DE BÚSQUEDA
        elif data == "search_example_python":
            await search_command(client, message)
            await message.reply_text("💡 Ejemplo: `/search python telegram bot`")
        
        elif data == "search_example_ml":
            await message.reply_text("💡 Ejemplo: `/search machine learning tensorflow`")
        
        # AYUDA DE BÚSQUEDA
        elif data == "search_help":
            await message.edit_text("""
❓ **Ayuda de Búsqueda**

🔍 **Operadores útiles:**
• `user:github` - Repos de GitHub org
• `language:python` - Solo Python
• `stars:>1000` - Más de 1000 estrellas
• `topic:machine-learning` - Por tema

💡 **Consejos:**
• Usa comillas para frases exactas
• Combina operadores
• Especifica para mejores resultados
            """, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Probar Búsqueda", callback_data="new_search")],
                [InlineKeyboardButton("🏠 Menú Principal", callback_data="main_menu")]
            ]))
        
        # ACTUALIZAR INFORMACIÓN
        elif data == "refresh_info":
            await info_command(client, message)
        
        # VISTA DE LOGS (SOLO ADMIN)
        elif data == "admin_view_logs" and user_id == ADMIN_ID:
            try:
                log_file = os.path.join(LOGS_DIR, "user_activity.log")
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-20:]  # Últimas 20 líneas
                    
                    log_text = "".join(lines)
                    if len(log_text) > 3000:
                        log_text = "...\n" + log_text[-3000:]
                    
                    await message.reply_text(f"""
📋 **Últimas actividades registradas:**                    """)
                else:
                    await message.reply_text("📭 No hay logs disponibles aún.")
            except Exception as e:
                await message.reply_text(f"❌ Error leyendo logs: {str(e)}")
        
        # LIMPIAR CACHE (SOLO ADMIN)
        elif data == "admin_clear_cache" and user_id == ADMIN_ID:
            USER_ACTIVITY_LOG.clear()
            await message.reply_text("✅ Cache de actividades limpiada exitosamente.")
        
        # RESPUESTA POR DEFECTO PARA BOTONES NO MANEJADOS
        else:
            await callback_query.answer("ℹ️ Función en desarrollo...", show_alert=True)
        
        # CONFIRMAR RECEPCIÓN DEL CALLBACK
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error en callback handler: {e}")
        await callback_query.answer("❌ Error procesando la solicitud", show_alert=True)

# ==============================================
# FUNCIÓN DE LIMPIEZA AUTOMÁTICA
# ==============================================

async def auto_cleanup():
    """
    Limpia automáticamente archivos temporales antiguos
    """
    try:
        current_time = time.time()
        max_age = 3600  # 1 hora en segundos
        
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age:
                    os.remove(filepath)
                    logger.info(f"🧹 Archivo temporal eliminado: {filename}")
    
    except Exception as e:
        logger.error(f"Error en limpieza automática: {e}")

# ==============================================
# INICIO Y EJECUCIÓN PRINCIPAL
# ==============================================

async def main():
    """
    Función principal de ejecución del bot
    """
    logger.info("🚀 Iniciando GitHub Downloader Pro...")
    logger.info(f"📁 Directorio base: {BASE_DIR}")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    
    try:
        # Iniciar cliente
        await app.start()
        
        # Obtener información del bot
        bot_info = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{bot_info.username}")
        
        # Programar limpieza automática cada 30 minutos
        async def scheduled_cleanup():
            while True:
                await asyncio.sleep(1800)  # 30 minutos
                await auto_cleanup()
        
        # Iniciar tarea de limpieza en segundo plano
        asyncio.create_task(scheduled_cleanup())
        
        # Mantener el bot en ejecución
        logger.info("🤖 Bot en ejecución. Presiona Ctrl+C para detener.")
        
        # Mantener el proceso activo
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")
    finally:
        # Limpieza final
        logger.info("🧹 Realizando limpieza final...")
        await app.stop()
        logger.info("👋 Bot detenido exitosamente")

# ==============================================
# PUNTO DE ENTRADA
# ==============================================

if __name__ == "__main__":
    # Configurar event loop para asyncio
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Ejecutar bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Programa terminado por el usuario")
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        sys.exit(1)
