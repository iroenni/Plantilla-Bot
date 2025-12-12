
import os
import asyncio
import shutil
import tempfile
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
import stat
import hashlib
from functools import wraps
from enum import Enum

# ==============================================
# CONFIGURACIÓN DE LOGGING
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================
# CONFIGURACIÓN PRINCIPAL
# ==============================================

# Configuración del bot
API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"

# ✅ TU ID EXCLUSIVO DE ADMINISTRADOR
ADMIN_ID = 7970466590
ADMINS = [ADMIN_ID]  # Solo tú

logger.info(f"✅ Administrador exclusivo: {ADMIN_ID}")

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

# Directorio base del bot
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_downloads")
os.makedirs(TEMP_DIR, exist_ok=True)

# ==============================================
# SISTEMA DE ESTADOS PARA ROOT
# ==============================================

class UserState(Enum):
    """Estados posibles del usuario"""
    IDLE = "idle"
    WAITING_RENAME = "waiting_rename"
    WAITING_MKDIR = "waiting_mkdir"
    WAITING_SEARCH = "waiting_search"
    WAITING_DELETE_CONFIRM = "waiting_delete_confirm"

# Diccionario para almacenar estados de usuario
user_states = {}
# Diccionario para almacenar datos temporales por usuario
user_temp_data = {}

# Cache para búsquedas GitHub
search_cache: Dict[str, Dict[str, Any]] = {}

# Configuración
MAX_FILE_SIZE = 50 * 1024 * 1024
SEARCH_CACHE_TIMEOUT = 1800
DOWNLOAD_TIMEOUT = 300

# ==============================================
# DECORADORES Y CLASES UTILITARIAS
# ==============================================

def admin_only(func):
    """Decorador para restringir funciones solo al admin"""
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        if user_id != ADMIN_ID:
            await message.reply_text(
                "❌ **Acceso denegado**\n\n"
                "Esta función solo está disponible para el administrador del bot.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        return await func(client, message, *args, **kwargs)
    return wrapper

def set_user_state(user_id: int, state: UserState, data: Dict = None):
    """Establece el estado de un usuario"""
    user_states[user_id] = state
    if data:
        user_temp_data[user_id] = data
    logger.debug(f"Estado actualizado: {user_id} -> {state}")

def get_user_state(user_id: int) -> Optional[UserState]:
    """Obtiene el estado de un usuario"""
    return user_states.get(user_id)

def clear_user_state(user_id: int):
    """Limpia el estado de un usuario"""
    user_states.pop(user_id, None)
    user_temp_data.pop(user_id, None)
    logger.debug(f"Estado limpiado: {user_id}")

def get_user_temp_data(user_id: int, key: str = None):
    """Obtiene datos temporales de un usuario"""
    data = user_temp_data.get(user_id, {})
    if key:
        return data.get(key)
    return data

def set_user_temp_data(user_id: int, key: str, value: Any):
    """Establece datos temporales para un usuario"""
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {}
    user_temp_data[user_id][key] = value

class FileManager:
    """Gestor de archivos con seguridad"""
    
    SAFE_DIRECTORIES = [
        TEMP_DIR,
        BASE_DIR,
        os.path.join(BASE_DIR, "downloads"),
        os.path.join(BASE_DIR, "logs")
    ]
    
    RESTRICTED_PATHS = ["/", "/home", "/etc", "/var", "/usr", "/bin", "/sbin", "/root"]
    
    @staticmethod
    def is_safe_path(path: str) -> bool:
        """Verifica si una ruta es segura"""
        try:
            abs_path = os.path.abspath(path)
            for restricted in FileManager.RESTRICTED_PATHS:
                if abs_path.startswith(restricted):
                    return False
            for safe_dir in FileManager.SAFE_DIRECTORIES:
                if abs_path.startswith(os.path.abspath(safe_dir)):
                    return True
            return False
        except:
            return False
    
    @staticmethod
    def get_file_info(path: str) -> Dict[str, Any]:
        """Obtiene información de un archivo/directorio"""
        try:
            if not FileManager.is_safe_path(path):
                return {}
            
            abs_path = os.path.abspath(path)
            stat_info = os.stat(abs_path)
            
            info = {
                "path": abs_path,
                "name": os.path.basename(abs_path),
                "size": stat_info.st_size,
                "size_human": humanize.naturalsize(stat_info.st_size),
                "modified": datetime.fromtimestamp(stat_info.st_mtime),
                "modified_str": datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "is_dir": os.path.isdir(abs_path),
                "is_file": os.path.isfile(abs_path),
                "permissions": stat.filemode(stat_info.st_mode),
            }
            
            if info["is_dir"]:
                try:
                    items = os.listdir(abs_path)
                    info["item_count"] = len(items)
                except:
                    info["item_count"] = 0
            
            return info
        except Exception as e:
            logger.error(f"Error obteniendo info de archivo: {e}")
            return {}
    
    @staticmethod
    def list_directory(path: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Lista contenido de directorio con paginación"""
        try:
            if not FileManager.is_safe_path(path):
                return {"error": "Ruta no permitida", "items": [], "total": 0}
            
            if not os.path.exists(path):
                return {"error": "La ruta no existe", "items": [], "total": 0}
            
            if not os.path.isdir(path):
                return {"error": "No es un directorio", "items": [], "total": 0}
            
            # Obtener items
            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                try:
                    is_dir = os.path.isdir(item_path)
                    items.append({
                        "name": item,
                        "path": item_path,
                        "is_dir": is_dir,
                        "is_file": os.path.isfile(item_path),
                        "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                        "size_human": humanize.naturalsize(os.path.getsize(item_path)) if os.path.isfile(item_path) else "0B",
                        "modified": datetime.fromtimestamp(os.path.getmtime(item_path)),
                    })
                except:
                    continue
            
            # Ordenar
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            
            # Paginación
            total = len(items)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_items = items[start_idx:end_idx]
            total_pages = (total + per_page - 1) // per_page
            
            return {
                "items": paginated_items,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "current_path": path,
                "parent_path": os.path.dirname(path) if path != BASE_DIR else None
            }
        except Exception as e:
            logger.error(f"Error listando directorio: {e}")
            return {"error": str(e), "items": [], "total": 0}
    
    @staticmethod
    def search_files(path: str, pattern: str) -> List[Dict[str, Any]]:
        """Busca archivos que coincidan con un patrón"""
        results = []
        if not FileManager.is_safe_path(path):
            return results
        
        try:
            pattern_lower = pattern.lower()
            for root, dirs, files in os.walk(path):
                # Buscar en archivos
                for file in files:
                    if pattern_lower in file.lower():
                        file_path = os.path.join(root, file)
                        results.append({
                            "type": "file",
                            "name": file,
                            "path": file_path,
                            "relative_path": os.path.relpath(file_path, path),
                            "size": os.path.getsize(file_path),
                            "size_human": humanize.naturalsize(os.path.getsize(file_path))
                        })
                
                # Buscar en directorios
                for dir_name in dirs:
                    if pattern_lower in dir_name.lower():
                        dir_path = os.path.join(root, dir_name)
                        results.append({
                            "type": "directory",
                            "name": dir_name,
                            "path": dir_path,
                            "relative_path": os.path.relpath(dir_path, path)
                        })
        except Exception as e:
            logger.error(f"Error buscando archivos: {e}")
        
        return results
    
    @staticmethod
    def create_directory(path: str) -> Tuple[bool, str]:
        """Crea un directorio"""
        try:
            if not FileManager.is_safe_path(path):
                return False, "Ruta no permitida"
            
            if os.path.exists(path):
                return False, "El directorio ya existe"
            
            os.makedirs(path, exist_ok=True)
            return True, f"✅ Directorio creado: {os.path.basename(path)}"
        except Exception as e:
            logger.error(f"Error creando directorio: {e}")
            return False, f"❌ Error: {str(e)}"
    
    @staticmethod
    def delete_path(path: str) -> Tuple[bool, str]:
        """Elimina un archivo o directorio"""
        try:
            if not FileManager.is_safe_path(path):
                return False, "Ruta no permitida"
            
            if not os.path.exists(path):
                return False, "La ruta no existe"
            
            if os.path.isdir(path):
                shutil.rmtree(path)
                return True, f"✅ Directorio eliminado: {os.path.basename(path)}"
            else:
                os.remove(path)
                return True, f"✅ Archivo eliminado: {os.path.basename(path)}"
        except Exception as e:
            logger.error(f"Error eliminando ruta: {e}")
            return False, f"❌ Error: {str(e)}"
    
    @staticmethod
    def rename_path(old_path: str, new_name: str) -> Tuple[bool, str]:
        """Renombra un archivo o directorio"""
        try:
            if not FileManager.is_safe_path(old_path):
                return False, "Ruta no permitida"
            
            if not os.path.exists(old_path):
                return False, "La ruta no existe"
            
            parent_dir = os.path.dirname(old_path)
            new_path = os.path.join(parent_dir, new_name)
            
            if os.path.exists(new_path):
                return False, "Ya existe un elemento con ese nombre"
            
            os.rename(old_path, new_path)
            return True, f"✅ Renombrado a: {new_name}"
        except Exception as e:
            logger.error(f"Error renombrando ruta: {e}")
            return False, f"❌ Error: {str(e)}"
    
    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """Obtiene información del uso del disco"""
        try:
            base_usage = shutil.disk_usage(BASE_DIR)
            
            # Calcular tamaño del directorio temporal
            temp_size = 0
            if os.path.exists(TEMP_DIR):
                for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp):
                            temp_size += os.path.getsize(fp)
            
            return {
                "total": base_usage.total,
                "used": base_usage.used,
                "free": base_usage.free,
                "total_human": humanize.naturalsize(base_usage.total),
                "used_human": humanize.naturalsize(base_usage.used),
                "free_human": humanize.naturalsize(base_usage.free),
                "percent_used": (base_usage.used / base_usage.total * 100) if base_usage.total > 0 else 0,
                "temp_size": temp_size,
                "temp_size_human": humanize.naturalsize(temp_size),
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Error obteniendo uso de disco: {e}")
            return {}

# ==============================================
# FUNCIONES PARA GITHUB
# ==============================================

async def download_github_repo(repo_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Descarga un repositorio de GitHub como ZIP"""
    try:
        if not repo_url or "github.com" not in repo_url:
            return None, "URL no válida"
        
        repo_url = repo_url.strip().rstrip('/')
        
        # Extraer usuario y repositorio
        pattern = r"github\.com/([^/]+)/([^/?#]+)"
        match = re.search(pattern, repo_url)
        
        if not match:
            return None, "No se pudo extraer información"
        
        user, repo = match.groups()
        repo = re.sub(r'\.git$', '', repo)
        
        # Determinar rama
        if "/tree/" in repo_url:
            branch_match = re.search(r'/tree/([^/]+)', repo_url)
            branch = branch_match.group(1) if branch_match else "main"
        else:
            branch = "main"
        
        download_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
        
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    # Intentar con master
                    if "/main.zip" in download_url:
                        alt_url = download_url.replace("/main.zip", "/master.zip")
                        async with session.get(alt_url) as response2:
                            if response2.status != 200:
                                return None, f"Error HTTP {response.status}"
                            content = await response2.read()
                    else:
                        return None, f"Error HTTP {response.status}"
                else:
                    content = await response.read()
        
        if len(content) > MAX_FILE_SIZE:
            return None, f"Archivo demasiado grande ({len(content)/1024/1024:.1f}MB)"
        
        return content, None
        
    except asyncio.TimeoutError:
        return None, "Tiempo de espera agotado"
    except aiohttp.ClientError as e:
        return None, f"Error de conexión: {str(e)}"
    except Exception as e:
        logger.error(f"Error en download_github_repo: {e}")
        return None, f"Error interno: {str(e)}"

def get_repo_info_from_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extrae información del repositorio de la URL"""
    try:
        pattern = r"github\.com/([^/]+)/([^/?#]+)"
        match = re.search(pattern, repo_url)
        
        if match:
            username = match.group(1)
            repo_name = match.group(2)
            repo_name = re.sub(r'\.git$', '', repo_name)
            if '/tree/' in repo_url:
                repo_name = repo_name.split('/')[0]
            return username, repo_name
        return None, None
    except Exception as e:
        logger.error(f"Error en get_repo_info_from_url: {e}")
        return None, None

async def search_github_repos(query: str, page: int = 1, per_page: int = 5) -> Tuple[Optional[Dict], Optional[str]]:
    """Busca repositorios en GitHub usando la API"""
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
                    return None, "Límite de API alcanzado"
                elif response.status == 422:
                    return None, "Consulta no válida"
                elif response.status != 200:
                    return None, f"Error API: {response.status}"
                
                data = await response.json()
                
                if "items" not in data:
                    return None, "No se encontraron resultados"
                
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
        return None, "Error de conexión"
    except Exception as e:
        logger.error(f"Error en search_github_repos: {e}")
        return None, f"Error interno: {str(e)}"

def format_repo_search_results(results: Dict) -> str:
    """Formatea resultados de búsqueda"""
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

# ==============================================
# COMANDOS PRINCIPALES DEL BOT
# ==============================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Comando de inicio"""
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
        "📥 **Puedo descargar repositorios de GitHub**\n"
        "🔍 **Buscar repositorios públicos**\n"
        "📁 **Enviar como archivo ZIP**\n\n"
        "**Comandos principales:**\n"
        "`/search <término>` - Buscar repositorios\n"
        "`/download <url>` - Descargar repositorio\n"
        "`/help` - Ayuda completa\n\n"
        "¡Envía un enlace de GitHub o busca repositorios!",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    """Buscar repositorios en GitHub"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Sistema de Búsqueda**\n\n"
            "**Uso:** `/search <término>`\n\n"
            "**Ejemplos:**\n"
            "• `/search python bot`\n"
            "• `/search machine learning`\n"
            "• `/search user:microsoft`\n\n"
            "💡 **Consejos:**\n"
            "• Usa palabras clave específicas\n"
            "• Máximo 5 resultados por página",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    query = args[1]
    
    if len(query) < 2:
        await message.reply_text("❌ La búsqueda debe tener al menos 2 caracteres.")
        return
    
    processing_msg = await message.reply_text(f"🔍 **Buscando:** `{query}`...")
    
    results, error = await search_github_repos(query)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    # Guardar en cache
    search_id = str(uuid.uuid4())[:8]
    search_cache[search_id] = {
        "results": results,
        "query": query,
        "user_id": message.from_user.id,
        "timestamp": datetime.now().timestamp()
    }
    
    # Crear botones
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
    """Descargar repositorio de GitHub"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "📥 **Descargar Repositorio**\n\n"
            "**Uso:** `/download <URL>`\n\n"
            "**Ejemplos:**\n"
            "• `/download https://github.com/usuario/repo`\n"
            "• `/download https://github.com/usuario/repo/tree/main`\n\n"
            "⚠️ **Límite:** 50MB por archivo",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    repo_url = args[1].strip()
    
    if not re.match(r'^https?://github\.com/[^/]+/[^/]+', repo_url):
        await message.reply_text(
            "❌ **URL no válida**\n\n"
            "Formato: `https://github.com/usuario/repositorio`",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    processing_msg = await message.reply_text("⏳ **Descargando...**")
    
    zip_content, error = await download_github_repo(repo_url)
    
    if error:
        await processing_msg.edit_text(f"❌ **Error:** {error}")
        return
    
    username, repo_name = get_repo_info_from_url(repo_url)
    filename = f"{repo_name or 'repositorio'}.zip"
    file_size_mb = len(zip_content) / 1024 / 1024
    
    await processing_msg.edit_text(f"✅ **Descargado!**\n📦 Tamaño: {file_size_mb:.1f}MB\n📤 Enviando...")
    
    try:
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
    """Comando de ayuda"""
    help_text = """
🤖 **GitHub Downloader Bot - Ayuda**

📥 **Funciones:**
• 🔍 Buscar repositorios en GitHub
• 📥 Descargar repositorios completos
• 📁 Enviar como archivo ZIP
• 🌿 Soporte para ramas específicas

🛠️ **Comandos:**
`/start` - Iniciar bot
`/search <término>` - Buscar repositorios
`/download <url>` - Descargar repositorio
`/help` - Mostrar esta ayuda
`/example` - Ejemplos de uso
`/info` - Información del bot

🔍 **Formatos de URL:**
• `https://github.com/usuario/repo`
• `https://github.com/usuario/repo/tree/main`
• `https://github.com/usuario/repo.git`

⚠️ **Límites:**
• 50MB por archivo (Telegram)
• Solo repositorios públicos
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example"),
         InlineKeyboardButton("📥 Ejemplo rápido", callback_data="quick_download")],
        [InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/rest")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("example"))
async def example_command(client: Client, message: Message):
    """Ejemplos de uso"""
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
    """Detecta URLs de GitHub automáticamente"""
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

# ==============================================
# SISTEMA ROOT INTERNO - SOLO PARA ADMIN
# ==============================================

@app.on_message(filters.command("root") & filters.private)
@admin_only
async def root_command(client: Client, message: Message):
    """Panel de administración root"""
    # Limpiar estado anterior
    clear_user_state(message.from_user.id)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Explorar archivos", callback_data="root_explore")],
        [InlineKeyboardButton("🔍 Buscar archivos", callback_data="root_search_menu"),
         InlineKeyboardButton("📊 Uso de disco", callback_data="root_disk")],
        [InlineKeyboardButton("🧹 Limpiar temporal", callback_data="root_cleanup"),
         InlineKeyboardButton("📝 Ver logs", callback_data="root_logs")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="root_stats"),
         InlineKeyboardButton("🏠 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(
        "🔧 **Panel de Administración Root**\n\n"
        "**Opciones disponibles:**\n"
        "• 📁 **Explorar archivos** - Navegar por directorios\n"
        "• 🔍 **Buscar archivos** - Buscar por nombre\n"
        "• 📊 **Uso de disco** - Ver espacio disponible\n"
        "• 🧹 **Limpiar temporal** - Eliminar archivos temporales\n"
        "• 📝 **Ver logs** - Consultar registros del bot\n"
        "• 📊 **Estadísticas** - Información del sistema\n\n"
        f"**Directorio base:** `{BASE_DIR}`\n"
        f"**Admin ID:** `{ADMIN_ID}`\n"
        f"**Estado:** `{get_user_state(message.from_user.id) or UserState.IDLE.value}`",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

async def show_directory(client: Client, message: Message, path: str = None, page: int = 1):
    """Muestra contenido de un directorio"""
    if path is None:
        path = BASE_DIR
    
    result = FileManager.list_directory(path, page)
    
    if "error" in result:
        await message.reply_text(f"❌ **Error:** {result['error']}")
        return
    
    text = f"📁 **Directorio:** `{result['current_path']}`\n\n"
    text += f"📊 **Total items:** {result['total']}\n"
    text += f"📄 **Página {result['page']} de {result['total_pages']}**\n\n"
    
    if not result["items"]:
        text += "📭 **El directorio está vacío**\n"
    else:
        for i, item in enumerate(result["items"], 1):
            idx = (page - 1) * result["per_page"] + i
            icon = "📁" if item["is_dir"] else "📄"
            size = f" ({item['size_human']})" if item["is_file"] else ""
            text += f"{icon} **{idx}.** `{item['name']}`{size}\n"
    
    # Botones de navegación
    keyboard_buttons = []
    
    # Botones de página
    nav_buttons = []
    if result["page"] > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", 
            callback_data=f"root_dir_{path}_{result['page']-1}"))
    
    if result["page"] < result["total_pages"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", 
            callback_data=f"root_dir_{path}_{result['page']+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Botones de acciones
    action_buttons = []
    if result["parent_path"]:
        action_buttons.append(InlineKeyboardButton("📁 Subir", 
            callback_data=f"root_dir_{result['parent_path']}_1"))
    
    action_buttons.append(InlineKeyboardButton("➕ Nueva carpeta", 
        callback_data=f"root_mkdir_{path}"))
    keyboard_buttons.append(action_buttons)
    
    # Botones para items (máximo 5)
    for item in result["items"][:5]:
        btn_text = f"📁 {item['name']}" if item["is_dir"] else f"📄 {item['name']}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        if item["is_dir"]:
            callback_data = f"root_dir_{item['path']}_1"
        else:
            callback_data = f"root_file_{item['path']}"
        
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    # Botones de control
    keyboard_buttons.append([
        InlineKeyboardButton("🔍 Buscar aquí", callback_data=f"root_search_in_{path}"),
        InlineKeyboardButton("🔙 Volver", callback_data="root")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    if message.id:
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex(r"^root_dir_"))
async def handle_root_dir(client: Client, callback_query: CallbackQuery):
    """Maneja navegación por directorios"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    data = callback_query.data
    parts = data.split("_")
    path = "_".join(parts[2:-1])  # Recuperar path con posibles _
    page = int(parts[-1])
    
    await show_directory(client, callback_query.message, path, page)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_file_"))
async def handle_root_file(client: Client, callback_query: CallbackQuery):
    """Maneja selección de archivo"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[10:]  # Quitar "root_file_"
    
    file_info = FileManager.get_file_info(path)
    
    if not file_info:
        await callback_query.answer("❌ No se pudo obtener información", show_alert=True)
        return
    
    text = f"📄 **Información del archivo**\n\n"
    text += f"**Nombre:** `{file_info['name']}`\n"
    text += f"**Ruta:** `{file_info['path']}`\n"
    text += f"**Tamaño:** {file_info['size_human']}\n"
    text += f"**Modificado:** {file_info['modified_str']}\n"
    text += f"**Permisos:** {file_info['permissions']}\n"
    
    if file_info['is_dir']:
        text += f"**Items dentro:** {file_info.get('item_count', 0)}\n"
    
    keyboard_buttons = []
    
    if file_info['is_file'] and file_info['size'] < 5 * 1024 * 1024:  # 5MB
        keyboard_buttons.append([
            InlineKeyboardButton("📤 Descargar archivo", callback_data=f"root_download_{path}")
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton("📝 Renombrar", callback_data=f"root_rename_{path}"),
        InlineKeyboardButton("🗑️ Eliminar", callback_data=f"root_delete_{path}")
    ])
    
    parent_dir = os.path.dirname(path)
    keyboard_buttons.append([
        InlineKeyboardButton("📁 Directorio padre", callback_data=f"root_dir_{parent_dir}_1"),
        InlineKeyboardButton("🔙 Volver", callback_data="root_explore")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_explore$"))
async def handle_root_explore(client: Client, callback_query: CallbackQuery):
    """Inicia explorador de archivos"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    await show_directory(client, callback_query.message)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_mkdir_"))
async def handle_root_mkdir(client: Client, callback_query: CallbackQuery):
    """Solicita nombre para nueva carpeta"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    parent_path = callback_query.data[11:]  # Quitar "root_mkdir_"
    
    # Guardar estado
    set_user_state(callback_query.from_user.id, UserState.WAITING_MKDIR)
    set_user_temp_data(callback_query.from_user.id, "parent_path", parent_path)
    
    await callback_query.message.reply_text(
        f"📁 **Crear nueva carpeta**\n\n"
        f"**Ubicación:** `{parent_path}`\n\n"
        f"Por favor, envía el nombre de la nueva carpeta:",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    await callback_query.answer("📝 Envía el nombre de la carpeta")

@app.on_callback_query(filters.regex(r"^root_rename_"))
async def handle_root_rename(client: Client, callback_query: CallbackQuery):
    """Solicita nuevo nombre para archivo/directorio"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[12:]  # Quitar "root_rename_"
    
    # Guardar estado
    set_user_state(callback_query.from_user.id, UserState.WAITING_RENAME)
    set_user_temp_data(callback_query.from_user.id, "path", path)
    
    await callback_query.message.reply_text(
        f"📝 **Renombrar**\n\n"
        f"**Actual:** `{os.path.basename(path)}`\n\n"
        f"Por favor, envía el nuevo nombre:",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    await callback_query.answer("📝 Envía el nuevo nombre")

@app.on_callback_query(filters.regex(r"^root_delete_"))
async def handle_root_delete(client: Client, callback_query: CallbackQuery):
    """Solicita confirmación para eliminar"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[12:]  # Quitar "root_delete_"
    
    # Guardar estado
    set_user_state(callback_query.from_user.id, UserState.WAITING_DELETE_CONFIRM)
    set_user_temp_data(callback_query.from_user.id, "path", path)
    
    item_name = os.path.basename(path)
    is_dir = os.path.isdir(path)
    
    text = f"⚠️ **Confirmar eliminación**\n\n"
    if is_dir:
        text += f"¿Eliminar el directorio **{item_name}** y todo su contenido?\n\n"
    else:
        text += f"¿Eliminar el archivo **{item_name}**?\n\n"
    
    text += "**Esta acción no se puede deshacer.**"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"root_confirm_delete_{path}"),
         InlineKeyboardButton("❌ Cancelar", callback_data="root_explore")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_confirm_delete_"))
async def handle_root_confirm_delete(client: Client, callback_query: CallbackQuery):
    """Elimina archivo/directorio confirmado"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[20:]  # Quitar "root_confirm_delete_"
    
    success, message_text = FileManager.delete_path(path)
    
    if success:
        parent_dir = os.path.dirname(path)
        await show_directory(client, callback_query.message, parent_dir)
        await callback_query.answer("✅ Eliminado correctamente")
    else:
        await callback_query.message.edit_text(f"❌ {message_text}")
        await callback_query.answer("❌ Error")
    
    # Limpiar estado
    clear_user_state(callback_query.from_user.id)

@app.on_callback_query(filters.regex(r"^root_download_"))
async def handle_root_download(client: Client, callback_query: CallbackQuery):
    """Descarga archivo seleccionado"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[14:]  # Quitar "root_download_"
    
    if not FileManager.is_safe_path(path):
        await callback_query.answer("❌ Ruta no permitida", show_alert=True)
        return
    
    if not os.path.isfile(path):
        await callback_query.answer("❌ No es un archivo válido", show_alert=True)
        return
    
    file_size = os.path.getsize(path)
    
    if file_size > MAX_FILE_SIZE:
        await callback_query.answer(
            f"❌ Archivo demasiado grande ({humanize.naturalsize(file_size)})",
            show_alert=True
        )
        return
    
    await callback_query.answer("📤 Enviando archivo...")
    
    try:
        await callback_query.message.reply_document(
            document=path,
            caption=f"📄 **Archivo del sistema**\n`{os.path.basename(path)}`\n\n"
                   f"**Ruta:** `{path}`\n"
                   f"**Tamaño:** {humanize.naturalsize(file_size)}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except Exception as e:
        await callback_query.message.reply_text(f"❌ Error enviando archivo: {str(e)}")

@app.on_callback_query(filters.regex(r"^root_search_menu$"))
async def handle_root_search_menu(client: Client, callback_query: CallbackQuery):
    """Muestra menú de búsqueda"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar en base", callback_data=f"root_search_in_{BASE_DIR}"),
         InlineKeyboardButton("🔍 Buscar en temp", callback_data=f"root_search_in_{TEMP_DIR}")],
        [InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await callback_query.message.edit_text(
        "🔍 **Buscar Archivos**\n\n"
        "Selecciona donde buscar:\n\n"
        "**Base:** Directorio principal del bot\n"
        "**Temp:** Archivos temporales",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_search_in_"))
async def handle_root_search_in(client: Client, callback_query: CallbackQuery):
    """Solicita patrón de búsqueda"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    path = callback_query.data[15:]  # Quitar "root_search_in_"
    
    # Guardar estado
    set_user_state(callback_query.from_user.id, UserState.WAITING_SEARCH)
    set_user_temp_data(callback_query.from_user.id, "search_path", path)
    
    await callback_query.message.reply_text(
        f"🔍 **Buscar en directorio**\n\n"
        f"**Ruta:** `{path}`\n\n"
        f"Envía el patrón a buscar:",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    await callback_query.answer("🔍 Envía el patrón de búsqueda")

@app.on_callback_query(filters.regex(r"^root_disk$"))
async def handle_root_disk(client: Client, callback_query: CallbackQuery):
    """Muestra uso del disco"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    disk_info = FileManager.get_disk_usage()
    
    if not disk_info:
        await callback_query.answer("❌ Error obteniendo información", show_alert=True)
        return
    
    # Crear barra de progreso
    percent = disk_info["percent_used"]
    bar_length = 20
    filled_length = int(bar_length * percent / 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    text = "💾 **Información del Disco**\n\n"
    text += f"**Espacio total:** {disk_info['total_human']}\n"
    text += f"**Espacio usado:** {disk_info['used_human']}\n"
    text += f"**Espacio libre:** {disk_info['free_human']}\n"
    text += f"**Porcentaje usado:** {percent:.1f}%\n\n"
    text += f"`[{bar}] {percent:.1f}%`\n\n"
    text += f"**Directorio temporal:**\n"
    text += f"• Tamaño: {disk_info['temp_size_human']}\n\n"
    text += f"**Actualizado:** {disk_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Limpiar temporal", callback_data="root_cleanup")],
        [InlineKeyboardButton("📊 Detalles", callback_data="root_disk_details"),
         InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_cleanup$"))
async def handle_root_cleanup(client: Client, callback_query: CallbackQuery):
    """Limpia archivos temporales"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    try:
        if os.path.exists(TEMP_DIR):
            # Contar antes de limpiar
            file_count = 0
            total_size = 0
            
            for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp) if os.path.isfile(fp) else 0
                    file_count += 1
            
            # Eliminar y recrear
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR, exist_ok=True)
            
            await callback_query.message.edit_text(
                f"✅ **Limpieza completada**\n\n"
                f"**Archivos eliminados:** {file_count}\n"
                f"**Espacio liberado:** {humanize.naturalsize(total_size)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await callback_query.message.edit_text("✅ El directorio temporal ya está vacío")
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Error: {str(e)}")
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_logs$"))
async def handle_root_logs(client: Client, callback_query: CallbackQuery):
    """Muestra logs del bot"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    log_file = os.path.join(BASE_DIR, "bot.log")
    
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if lines:
                last_lines = lines[-20:]  # Últimas 20 líneas
                log_text = "".join(last_lines)
                
                if len(log_text) > 3000:
                    log_text = "...\n" + log_text[-3000:]
                
                text = f"📝 **Últimas líneas del log**\n\n"
                text += f"**Archivo:** `{log_file}`\n"
                text += f"**Total líneas:** {len(lines)}\n\n"
                text += "```\n"
                text += log_text
                text += "\n```"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ Limpiar logs", callback_data="root_clear_logs")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="root")]
                ])
                
                await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            else:
                await callback_query.message.edit_text("📭 El archivo de log está vacío")
        except Exception as e:
            await callback_query.message.edit_text(f"❌ Error leyendo log: {str(e)}")
    else:
        await callback_query.message.edit_text("📭 No se encontró archivo de log")
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^root_stats$"))
async def handle_root_stats(client: Client, callback_query: CallbackQuery):
    """Muestra estadísticas del sistema"""
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    disk_info = FileManager.get_disk_usage()
    
    # Información de caché
    cache_size = len(search_cache)
    
    # Obtener información del bot
    bot_info = await client.get_me()
    
    text = "📊 **Estadísticas del Sistema**\n\n"
    
    text += "🤖 **Información del Bot:**\n"
    text += f"• **Nombre:** @{bot_info.username}\n"
    text += f"• **ID:** {bot_info.id}\n"
    text += f"• **Admin ID:** {ADMIN_ID}\n"
    text += f"• **Caché de búsqueda:** {cache_size} entradas\n\n"
    
    text += "💾 **Uso de Disco:**\n"
    if disk_info:
        text += f"• **Total:** {disk_info['total_human']}\n"
        text += f"• **Usado:** {disk_info['used_human']} ({disk_info['percent_used']:.1f}%)\n"
        text += f"• **Libre:** {disk_info['free_human']}\n"
        text += f"• **Temp:** {disk_info['temp_size_human']}\n\n"
    
    text += "📁 **Directorios:**\n"
    text += f"• **Base:** `{BASE_DIR}`\n"
    text += f"• **Temp:** `{TEMP_DIR}`\n\n"
    
    text += f"🕐 **Actualizado:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Uso de disco", callback_data="root_disk"),
         InlineKeyboardButton("🧹 Limpiar", callback_data="root_cleanup")],
        [InlineKeyboardButton("📁 Explorar", callback_data="root_explore"),
         InlineKeyboardButton("🔙 Panel", callback_data="root")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await callback_query.answer()

# ==============================================
# MANEJADOR DE MENSAJES DE TEXTO (PARA ESTADOS)
# ==============================================

@app.on_message(filters.private & filters.text)
async def handle_text_messages(client: Client, message: Message):
    """Maneja mensajes de texto según el estado del usuario"""
    user_id = message.from_user.id
    user_state = get_user_state(user_id)
    text = message.text.strip()
    
    # Solo procesar si es admin y tiene un estado activo
    if user_id != ADMIN_ID or not user_state:
        return
    
    logger.info(f"Procesando mensaje para usuario {user_id} con estado {user_state}")
    
    if user_state == UserState.WAITING_MKDIR:
        parent_path = get_user_temp_data(user_id, "parent_path")
        
        if parent_path:
            new_dir = os.path.join(parent_path, text)
            success, msg = FileManager.create_directory(new_dir)
            
            await message.reply_text(msg)
            
            if success:
                # Mostrar el directorio padre actualizado
                await show_directory(client, message, parent_path)
        
        # Limpiar estado
        clear_user_state(user_id)
    
    elif user_state == UserState.WAITING_RENAME:
        old_path = get_user_temp_data(user_id, "path")
        
        if old_path:
            success, msg = FileManager.rename_path(old_path, text)
            
            await message.reply_text(msg)
            
            if success:
                # Mostrar el directorio padre actualizado
                parent_dir = os.path.dirname(old_path)
                await show_directory(client, message, parent_dir)
        
        # Limpiar estado
        clear_user_state(user_id)
    
    elif user_state == UserState.WAITING_SEARCH:
        search_path = get_user_temp_data(user_id, "search_path")
        
        if search_path:
            results = FileManager.search_files(search_path, text)
            
            if not results:
                await message.reply_text(f"❌ No se encontraron resultados para `{text}`")
            else:
                response = f"🔍 **Resultados para `{text}` en `{search_path}`**\n\n"
                response += f"**Encontrados:** {len(results)} items\n\n"
                
                for i, result in enumerate(results[:10], 1):
                    icon = "📁" if result["type"] == "directory" else "📄"
                    size = f" ({result['size_human']})" if result["type"] == "file" else ""
                    response += f"{icon} **{i}.** `{result['relative_path']}`{size}\n"
                
                if len(results) > 10:
                    response += f"\n... y {len(results) - 10} más"
                
                await message.reply_text(response, parse_mode=enums.ParseMode.MARKDOWN)
        
        # Limpiar estado
        clear_user_state(user_id)
    
    elif user_state == UserState.WAITING_DELETE_CONFIRM:
        # El usuario ya confirmó con botones, este estado no debería activarse aquí
        clear_user_state(user_id)
        await message.reply_text("⚠️ Operación cancelada o ya completada")

# ==============================================
# MANEJADOR DE CALLBACKS GENERALES
# ==============================================

@app.on_callback_query()
async def handle_general_callbacks(client: Client, callback_query: CallbackQuery):
    """Maneja callbacks generales (no root)"""
    data = callback_query.data
    user_id = callback_query.from_user.id
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
        
        # CALLBACKS DE BÚSQUEDA GITHUB
        if data == "search":
            await message.reply_text(
                "🔍 **Nueva búsqueda**\n\nEnvía tu término de búsqueda:\n\n"
                "Ejemplo: `/search python bot`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await callback_query.answer()
        
        elif data == "help":
            await help_command(client, message)
            await callback_query.answer()
        
        elif data == "start":
            await start_command(client, message)
            await callback_query.answer()
        
        elif data == "search_example":
            processing_msg = await message.reply_text("🔍 **Ejemplo:** Buscando `python bot`...")
            results, error = await search_github_repos("python bot")
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                search_id = str(uuid.uuid4())[:8]
                search_cache[search_id] = {
                    "results": results,
                    "query": "python bot",
                    "user_id": user_id,
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
            
            if search_data["user_id"] != user_id:
                await callback_query.answer("❌ Esta búsqueda no es tuya")
                return
            
            new_page = current_page - 1 if action == "prev" else current_page + 1
            query = search_data["query"]
            
            results, error = await search_github_repos(query, new_page)
            
            if error:
                await callback_query.answer(f"Error: {error}")
                return
            
            search_cache[search_id]["results"] = results
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            nav_buttons = []
            if results["has_prev"]:
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", 
                    callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", 
                    callback_data=f"next_{search_id}_{results['page']}"))
            
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
            
            if search_data["user_id"] != user_id:
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
        
        elif data.startswith("dl_"):
            repo_url = data[3:]
            
            processing_msg = await message.reply_text("⏳ Descargando...")
            
            zip_content, error = await download_github_repo(repo_url)
            
            if error:
                await processing_msg.edit_text(f"❌ Error: {error}")
            else:
                username, repo_name = get_repo_info_from_url(repo_url)
                filename = f"{repo_name or 'repo'}.zip"
                file_size_mb = len(zip_content) / 1024 / 1024
                
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
            
            await callback_query.answer("✅ Descarga completada")
        
        elif data == "quick_download":
            example_url = "https://github.com/octocat/Spoon-Knife"
            
            msg = await message.reply_text("⏳ Descargando ejemplo...")
            zip_content, error = await download_github_repo(example_url)
            
            if error:
                await msg.edit_text(f"❌ Error: {error}")
            else:
                await message.reply_document(
                    document=io.BytesIO(zip_content),
                    file_name="Spoon-Knife.zip",
                    caption="🍴 **Spoon-Knife**\nRepositorio de prueba de GitHub",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await msg.delete()
            
            await callback_query.answer()
        
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
                nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", 
                    callback_data=f"prev_{search_id}_{results['page']}"))
            
            if results["has_next"]:
                nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", 
                    callback_data=f"next_{search_id}_{results['page']}"))
            
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
        
    except Exception as e:
        logger.error(f"Error en callback general: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==============================================
# INICIO DEL BOT
# ==============================================

async def main():
    """Función principal"""
    try:
        logger.info("🚀 Iniciando GitHub Downloader Bot...")
        
        # Crear directorios necesarios
        os.makedirs(TEMP_DIR, exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
        
        # Crear archivo de log si no existe
        log_file = os.path.join(BASE_DIR, "bot.log")
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write(f"=== Bot iniciado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                f.write(f"=== Admin ID: {ADMIN_ID} ===\n")
        
        # Iniciar el bot
        await app.start()
        
        me = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{me.username}")
        logger.info(f"✅ ID del bot: