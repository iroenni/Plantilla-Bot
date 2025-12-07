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

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================
# ⚠️⚠️⚠️ ADVERTENCIA DE SEGURIDAD ⚠️⚠️⚠️
# ==============================================

# Configuración del bot (DEBES USAR VARIABLES DE ENTORNO)
API_ID = os.getenv("API_ID") or 14681595
API_HASH = os.getenv("API_HASH") or "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"

# Lista de administradores (IDs de usuario de Telegram)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
# O puedes usar el ID de tu usuario (obténlo con @userinfobot en Telegram)
DEFAULT_ADMIN_ID = 7970466590  # ⚠️ Cambia esto por tu ID real

if not ADMINS:
    ADMINS = [DEFAULT_ADMIN_ID]

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

# Directorio base del bot (directorio actual)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directorio temporal para descargas
TEMP_DIR = os.path.join(BASE_DIR, "temp_downloads")
os.makedirs(TEMP_DIR, exist_ok=True)

# Almacenamiento temporal para resultados de búsqueda
search_cache: Dict[str, Dict[str, Any]] = {}

# Configuración
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB en bytes
SEARCH_CACHE_TIMEOUT = 1800  # 30 minutos en segundos
DOWNLOAD_TIMEOUT = 300  # 5 minutos

# Decorador para verificar administrador
def admin_only(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        
        if user_id not in ADMINS:
            await message.reply_text(
                "❌ **Acceso denegado**\n\n"
                "Esta función solo está disponible para administradores del bot.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        return await func(client, message, *args, **kwargs)
    return wrapper

class GitHubAPIError(Exception):
    """Excepción personalizada para errores de la API de GitHub"""
    pass

class DownloadError(Exception):
    """Excepción personalizada para errores de descarga"""
    pass

class FileManager:
    """Clase para gestionar archivos y directorios"""
    
    SAFE_DIRECTORIES = [
        TEMP_DIR,
        BASE_DIR,
        os.path.join(BASE_DIR, "downloads"),
        os.path.join(BASE_DIR, "logs")
    ]
    
    RESTRICTED_PATHS = [
        "/",
        "/home",
        "/etc",
        "/var",
        "/usr",
        "/bin",
        "/sbin",
        "/root",
        os.path.expanduser("~")
    ]
    
    @staticmethod
    def is_safe_path(path: str) -> bool:
        """Verifica si una ruta está dentro de los directorios permitidos"""
        try:
            abs_path = os.path.abspath(path)
            
            # Verificar que no sea una ruta restringida
            for restricted in FileManager.RESTRICTED_PATHS:
                if abs_path.startswith(restricted) and restricted != BASE_DIR:
                    return False
            
            # Verificar que esté en un directorio seguro
            for safe_dir in FileManager.SAFE_DIRECTORIES:
                if abs_path.startswith(os.path.abspath(safe_dir)):
                    return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def get_file_info(path: str) -> Dict[str, Any]:
        """Obtiene información detallada de un archivo o directorio"""
        try:
            abs_path = os.path.abspath(path)
            stat_info = os.stat(abs_path)
            
            info = {
                "path": abs_path,
                "name": os.path.basename(abs_path),
                "size": stat_info.st_size,
                "size_human": humanize.naturalsize(stat_info.st_size),
                "modified": datetime.fromtimestamp(stat_info.st_mtime),
                "modified_str": datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "created": datetime.fromtimestamp(stat_info.st_ctime),
                "created_str": datetime.fromtimestamp(stat_info.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "is_dir": os.path.isdir(abs_path),
                "is_file": os.path.isfile(abs_path),
                "permissions": stat.filemode(stat_info.st_mode),
                "owner": stat_info.st_uid,
                "group": stat_info.st_gid,
                "inode": stat_info.st_ino
            }
            
            if info["is_file"]:
                # Obtener tipo MIME y extensión
                mime_type, _ = mimetypes.guess_type(abs_path)
                info["mime_type"] = mime_type or "application/octet-stream"
                info["extension"] = os.path.splitext(abs_path)[1].lower()
                
                # Calcular hash MD5 para archivos pequeños
                if info["size"] < 10 * 1024 * 1024:  # 10MB máximo para hash
                    try:
                        with open(abs_path, 'rb') as f:
                            info["md5"] = hashlib.md5(f.read()).hexdigest()
                    except:
                        info["md5"] = None
                else:
                    info["md5"] = None
            
            elif info["is_dir"]:
                # Contar archivos y directorios
                try:
                    items = os.listdir(abs_path)
                    files = [f for f in items if os.path.isfile(os.path.join(abs_path, f))]
                    dirs = [d for d in items if os.path.isdir(os.path.join(abs_path, d))]
                    info["file_count"] = len(files)
                    info["dir_count"] = len(dirs)
                    info["total_count"] = len(items)
                except:
                    info["file_count"] = 0
                    info["dir_count"] = 0
                    info["total_count"] = 0
            
            return info
        except Exception as e:
            logger.error(f"Error obteniendo info de archivo: {e}")
            return {}
    
    @staticmethod
    def list_directory(path: str, page: int = 1, items_per_page: int = 20) -> Dict[str, Any]:
        """Lista los contenidos de un directorio con paginación"""
        try:
            if not FileManager.is_safe_path(path):
                return {"error": "Ruta no permitida", "items": [], "total": 0}
            
            if not os.path.exists(path):
                return {"error": "La ruta no existe", "items": [], "total": 0}
            
            if not os.path.isdir(path):
                return {"error": "La ruta no es un directorio", "items": [], "total": 0}
            
            # Obtener todos los items
            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                items.append({
                    "name": item,
                    "path": item_path,
                    "is_dir": os.path.isdir(item_path),
                    "is_file": os.path.isfile(item_path),
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                    "size_human": humanize.naturalsize(os.path.getsize(item_path)) if os.path.isfile(item_path) else "0B",
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)),
                    "modified_str": datetime.fromtimestamp(os.path.getmtime(item_path)).strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Ordenar: directorios primero, luego archivos, alfabéticamente
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            
            total_items = len(items)
            
            # Paginación
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            paginated_items = items[start_idx:end_idx]
            
            return {
                "items": paginated_items,
                "total": total_items,
                "page": page,
                "items_per_page": items_per_page,
                "total_pages": (total_items + items_per_page - 1) // items_per_page,
                "current_path": path,
                "parent_path": os.path.dirname(path) if path != BASE_DIR else None
            }
        except Exception as e:
            logger.error(f"Error listando directorio: {e}")
            return {"error": str(e), "items": [], "total": 0}
    
    @staticmethod
    def search_files(root_path: str, pattern: str, search_type: str = "all") -> List[Dict[str, Any]]:
        """Busca archivos o directorios que coincidan con un patrón"""
        results = []
        
        if not FileManager.is_safe_path(root_path):
            return results
        
        try:
            pattern_lower = pattern.lower()
            
            for root, dirs, files in os.walk(root_path):
                # Buscar en directorios
                if search_type in ["all", "dirs"]:
                    for dir_name in dirs:
                        if pattern_lower in dir_name.lower():
                            dir_path = os.path.join(root, dir_name)
                            results.append({
                                "type": "directory",
                                "name": dir_name,
                                "path": dir_path,
                                "relative_path": os.path.relpath(dir_path, root_path)
                            })
                
                # Buscar en archivos
                if search_type in ["all", "files"]:
                    for file_name in files:
                        if pattern_lower in file_name.lower():
                            file_path = os.path.join(root, file_name)
                            results.append({
                                "type": "file",
                                "name": file_name,
                                "path": file_path,
                                "relative_path": os.path.relpath(file_path, root_path),
                                "size": os.path.getsize(file_path),
                                "size_human": humanize.naturalsize(os.path.getsize(file_path))
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
            return True, f"Directorio creado: {path}"
        except Exception as e:
            logger.error(f"Error creando directorio: {e}")
            return False, f"Error: {str(e)}"
    
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
                return True, f"Directorio eliminado: {os.path.basename(path)}"
            else:
                os.remove(path)
                return True, f"Archivo eliminado: {os.path.basename(path)}"
        except Exception as e:
            logger.error(f"Error eliminando ruta: {e}")
            return False, f"Error: {str(e)}"
    
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
            return True, f"Renombrado a: {new_name}"
        except Exception as e:
            logger.error(f"Error renombrando ruta: {e}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """Obtiene información del uso del disco"""
        try:
            # Uso del directorio base
            base_usage = shutil.disk_usage(BASE_DIR)
            
            # Tamaño del directorio temporal
            temp_size = 0
            if os.path.exists(TEMP_DIR):
                for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        temp_size += os.path.getsize(fp) if os.path.isfile(fp) else 0
            
            # Contar archivos en temp
            temp_count = 0
            if os.path.exists(TEMP_DIR):
                for _, _, filenames in os.walk(TEMP_DIR):
                    temp_count += len(filenames)
            
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
                "temp_count": temp_count,
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Error obteniendo uso de disco: {e}")
            return {}

async def download_github_repo(repo_url: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Descarga un repositorio de GitHub como ZIP"""
    try:
        if not repo_url or "github.com" not in repo_url:
            return None, "URL no válida. Debe ser un repositorio de GitHub."
        
        repo_url = repo_url.strip().rstrip('/')
        
        if "/archive/" in repo_url and repo_url.endswith(".zip"):
            download_url = repo_url
        else:
            pattern = r"github\.com/([^/]+)/([^/?#]+)"
            match = re.search(pattern, repo_url)
            
            if not match:
                return None, "No se pudo extraer información del repositorio."
            
            user, repo = match.groups()
            repo = re.sub(r'\.git$', '', repo)
            
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

# ==============================================
# COMANDOS DE ADMINISTRACIÓN (ROOT)
# ==============================================

@app.on_message(filters.command("root") & filters.private)
@admin_only
async def root_command(client: Client, message: Message):
    """Menú principal de administración"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Ver directorio actual", callback_data="root_list_current")],
        [InlineKeyboardButton("🔍 Buscar archivos", callback_data="root_search_menu"),
         InlineKeyboardButton("📊 Uso de disco", callback_data="root_disk_usage")],
        [InlineKeyboardButton("🧹 Limpiar temp", callback_data="root_cleanup_temp"),
         InlineKeyboardButton("📝 Ver logs", callback_data="root_view_logs")],
        [InlineKeyboardButton("🔄 Reiniciar bot", callback_data="root_restart_bot"),
         InlineKeyboardButton("🚫 Cerrar bot", callback_data="root_shutdown_bot")],
        [InlineKeyboardButton("🏠 Inicio", callback_data="start")]
    ])
    
    await message.reply_text(
        "🔧 **Panel de Administración Root**\n\n"
        "**Opciones disponibles:**\n"
        "• 📁 **Explorar directorios** - Navegar por el sistema de archivos\n"
        "• 🔍 **Buscar archivos** - Buscar archivos por nombre\n"
        "• 📊 **Uso de disco** - Ver espacio disponible y utilizado\n"
        "• 🧹 **Limpiar temporal** - Eliminar archivos temporales\n"
        "• 📝 **Ver logs** - Consultar registros del bot\n"
        "• 🔄 **Reiniciar bot** - Reiniciar la aplicación\n"
        "• 🚫 **Cerrar bot** - Apagar el bot\n\n"
        f"**Directorio base:** `{BASE_DIR}`\n"
        f"**Directorio temp:** `{TEMP_DIR}`\n"
        f"**Administradores:** {len(ADMINS)} usuario(s)",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.MARKDOWN
    )

@app.on_message(filters.command("ls") & filters.private)
@admin_only
async def ls_command(client: Client, message: Message):
    """Listar contenido de directorio"""
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1:
        path = args[1].strip()
    else:
        path = BASE_DIR
    
    await list_directory_command(client, message, path)

async def list_directory_command(client: Client, message: Message, path: str, page: int = 1):
    """Comando para listar directorio"""
    if not FileManager.is_safe_path(path):
        await message.reply_text(
            "❌ **Ruta no permitida**\n\n"
            "Solo puedes acceder a directorios dentro del área del bot.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    if not os.path.exists(path):
        await message.reply_text(
            f"❌ **La ruta no existe**\n\n`{path}`",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    if not os.path.isdir(path):
        # Mostrar información del archivo
        file_info = FileManager.get_file_info(path)
        
        if not file_info:
            await message.reply_text("❌ No se pudo obtener información del archivo")
            return
        
        text = f"📄 **Información del archivo**\n\n"
        text += f"**Nombre:** `{file_info['name']}`\n"
        text += f"**Ruta:** `{file_info['path']}`\n"
        text += f"**Tamaño:** {file_info['size_human']}\n"
        text += f"**Modificado:** {file_info['modified_str']}\n"
        text += f"**Creado:** {file_info['created_str']}\n"
        text += f"**Permisos:** {file_info['permissions']}\n"
        
        if 'mime_type' in file_info:
            text += f"**Tipo MIME:** {file_info['mime_type']}\n"
        
        if file_info['size'] < 5 * 1024 * 1024:  # 5MB
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Enviar archivo", callback_data=f"root_send_{path}")],
                [InlineKeyboardButton("📝 Renombrar", callback_data=f"root_rename_{path}"),
                 InlineKeyboardButton("🗑️ Eliminar", callback_data=f"root_delete_{path}")],
                [InlineKeyboardButton("📁 Directorio padre", callback_data=f"root_list_{os.path.dirname(path)}"),
                 InlineKeyboardButton("🔙 Volver", callback_data="root")]
            ])
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Renombrar", callback_data=f"root_rename_{path}"),
                 InlineKeyboardButton("🗑️ Eliminar", callback_data=f"root_delete_{path}")],
                [InlineKeyboardButton("📁 Directorio padre", callback_data=f"root_list_{os.path.dirname(path)}"),
                 InlineKeyboardButton("🔙 Volver", callback_data="root")]
            ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    # Listar directorio
    result = FileManager.list_directory(path, page)
    
    if "error" in result:
        await message.reply_text(f"❌ **Error:** {result['error']}")
        return
    
    text = f"📁 **Directorio:** `{result['current_path']}`\n\n"
    text += f"📊 **Total de items:** {result['total']}\n"
    text += f"📄 **Página {result['page']} de {result['total_pages']}**\n\n"
    
    if not result["items"]:
        text += "📭 **El directorio está vacío**\n"
    else:
        for i, item in enumerate(result["items"], 1):
            idx = (page - 1) * result["items_per_page"] + i
            icon = "📁" if item["is_dir"] else "📄"
            size = f" ({item['size_human']})" if item["is_file"] else ""
            text += f"{icon} **{idx}.** `{item['name']}`{size}\n"
    
    # Crear botones
    keyboard_buttons = []
    
    # Botones de navegación de página
    nav_buttons = []
    if result["page"] > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"root_list_{path}_{result['page']-1}"))
    
    if result["page"] < result["total_pages"]:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"root_list_{path}_{result['page']+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    # Botones de acciones
    action_buttons = []
    if result["parent_path"]:
        action_buttons.append(InlineKeyboardButton("📁 Subir", callback_data=f"root_list_{result['parent_path']}"))
    
    action_buttons.append(InlineKeyboardButton("➕ Nueva carpeta", callback_data=f"root_mkdir_{path}"))
    keyboard_buttons.append(action_buttons)
    
    # Botones de archivos/directorios (máximo 5 por página)
    for item in result["items"][:5]:
        btn_text = f"📁 {item['name']}" if item["is_dir"] else f"📄 {item['name']}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        callback_data = f"root_list_{item['path']}" if item["is_dir"] else f"root_info_{item['path']}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    # Botones de control
    keyboard_buttons.append([
        InlineKeyboardButton("🔍 Buscar aquí", callback_data=f"root_search_{path}"),
        InlineKeyboardButton("🏠 Inicio", callback_data="root")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("disk") & filters.private)
@admin_only
async def disk_command(client: Client, message: Message):
    """Mostrar uso del disco"""
    disk_info = FileManager.get_disk_usage()
    
    if not disk_info:
        await message.reply_text("❌ No se pudo obtener información del disco")
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
    text += f"• Tamaño: {disk_info['temp_size_human']}\n"
    text += f"• Archivos: {disk_info['temp_count']}\n\n"
    text += f"**Actualizado:** {disk_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Limpiar temporal", callback_data="root_cleanup_temp")],
        [InlineKeyboardButton("📊 Detalles completos", callback_data="root_disk_details"),
         InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("clean") & filters.private)
@admin_only
async def clean_command(client: Client, message: Message):
    """Limpiar archivos temporales"""
    try:
        if os.path.exists(TEMP_DIR):
            # Contar archivos antes de limpiar
            file_count = 0
            total_size = 0
            
            for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp) if os.path.isfile(fp) else 0
                    file_count += 1
            
            # Eliminar y recrear directorio
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR, exist_ok=True)
            
            await message.reply_text(
                f"✅ **Limpieza completada**\n\n"
                f"**Archivos eliminados:** {file_count}\n"
                f"**Espacio liberado:** {humanize.naturalsize(total_size)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await message.reply_text("✅ El directorio temporal ya está vacío")
    except Exception as e:
        logger.error(f"Error limpiando temporal: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("find") & filters.private)
@admin_only
async def find_command(client: Client, message: Message):
    """Buscar archivos"""
    args = message.text.split(maxsplit=2)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Buscar Archivos**\n\n"
            "**Uso:** `/find <patrón> [ruta]`\n\n"
            "**Ejemplos:**\n"
            "• `/find .py` - Buscar archivos .py\n"
            "• `/find config /app` - Buscar 'config' en /app\n"
            "• `/find log --type=dir` - Buscar directorios\n\n"
            "**Opciones:**\n"
            "• `--type=file` - Solo archivos\n"
            "• `--type=dir` - Solo directorios\n"
            "• `--type=all` - Ambos (predeterminado)",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    pattern = args[1]
    search_path = BASE_DIR
    search_type = "all"
    
    if len(args) > 2:
        remaining = args[2]
        if remaining.startswith("--type="):
            search_type = remaining.split("=")[1]
        else:
            search_path = remaining
    
    if not FileManager.is_safe_path(search_path):
        await message.reply_text("❌ Ruta no permitida")
        return
    
    processing_msg = await message.reply_text(f"🔍 Buscando `{pattern}` en `{search_path}`...")
    
    results = FileManager.search_files(search_path, pattern, search_type)
    
    if not results:
        await processing_msg.edit_text(f"❌ No se encontraron resultados para `{pattern}`")
        return
    
    text = f"🔍 **Resultados de búsqueda**\n\n"
    text += f"**Patrón:** `{pattern}`\n"
    text += f"**Ruta:** `{search_path}`\n"
    text += f"**Tipo:** `{search_type}`\n"
    text += f"**Encontrados:** {len(results)} items\n\n"
    
    for i, result in enumerate(results[:10], 1):
        icon = "📁" if result["type"] == "directory" else "📄"
        size = f" ({result['size_human']})" if result["type"] == "file" else ""
        text += f"{icon} **{i}.** `{result['relative_path']}`{size}\n"
    
    if len(results) > 10:
        text += f"\n... y {len(results) - 10} más\n"
    
    # Crear botones para los resultados
    keyboard_buttons = []
    for i, result in enumerate(results[:5], 1):
        btn_text = f"{i}. {os.path.basename(result['path'])}"
        if len(btn_text) > 20:
            btn_text = btn_text[:17] + "..."
        
        callback_data = f"root_list_{result['path']}" if result["type"] == "directory" else f"root_info_{result['path']}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    
    keyboard_buttons.append([
        InlineKeyboardButton("🔍 Nueva búsqueda", callback_data="root_search_menu"),
        InlineKeyboardButton("🔙 Volver", callback_data="root")
    ])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("tree") & filters.private)
@admin_only
async def tree_command(client: Client, message: Message):
    """Mostrar estructura de directorios en formato árbol"""
    args = message.text.split(maxsplit=1)
    path = args[1] if len(args) > 1 else BASE_DIR
    depth = 3  # Profundidad máxima por defecto
    
    if not FileManager.is_safe_path(path):
        await message.reply_text("❌ Ruta no permitida")
        return
    
    if not os.path.isdir(path):
        await message.reply_text("❌ La ruta no es un directorio")
        return
    
    async def build_tree(dir_path, current_depth=0, max_depth=3, prefix=""):
        """Función recursiva para construir el árbol"""
        if current_depth >= max_depth:
            return ""
        
        try:
            items = os.listdir(dir_path)
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))
            
            tree_str = ""
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                item_path = os.path.join(dir_path, item)
                is_dir = os.path.isdir(item_path)
                
                # Icono y prefijo
                connector = "└── " if is_last else "├── "
                icon = "📁" if is_dir else "📄"
                
                tree_str += f"{prefix}{connector}{icon} {item}\n"
                
                # Si es directorio y no demasiado profundo, procesar contenido
                if is_dir and current_depth < max_depth - 1:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    tree_str += await build_tree(item_path, current_depth + 1, max_depth, new_prefix)
            
            return tree_str
        except PermissionError:
            return f"{prefix}└── 🔒 [Acceso denegado]\n"
        except Exception:
            return f"{prefix}└── ❌ [Error]\n"
    
    processing_msg = await message.reply_text("🌳 Generando árbol de directorios...")
    
    tree_output = f"🌳 **Estructura de directorios**\n\n"
    tree_output += f"**Ruta:** `{path}`\n"
    tree_output += f"**Profundidad:** {depth} niveles\n\n"
    tree_output += "```\n"
    tree_output += os.path.basename(path.rstrip('/')) + "/\n"
    tree_output += await build_tree(path, 0, depth)
    tree_output += "```"
    
    # Limitar tamaño del mensaje
    if len(tree_output) > 4000:
        tree_output = tree_output[:4000] + "\n\n... (truncado por tamaño)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Explorar", callback_data=f"root_list_{path}")],
        [InlineKeyboardButton("🔍 Buscar aquí", callback_data=f"root_search_{path}"),
         InlineKeyboardButton("🔙 Volver", callback_data="root")]
    ])
    
    await processing_msg.edit_text(tree_output, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_command(client: Client, message: Message):
    """Estadísticas del bot y sistema"""
    # Obtener información del sistema
    disk_info = FileManager.get_disk_usage()
    
    # Contar archivos en temp
    temp_stats = {"files": 0, "size": 0}
    if os.path.exists(TEMP_DIR):
        for dirpath, dirnames, filenames in os.walk(TEMP_DIR):
            temp_stats["files"] += len(filenames)
            for f in filenames:
                fp = os.path.join(dirpath, f)
                temp_stats["size"] += os.path.getsize(fp) if os.path.isfile(fp) else 0
    
    # Obtener información del bot
    bot_info = await client.get_me()
    
    # Información de caché
    cache_size = len(search_cache)
    
    # Uso de memoria (aproximado)
    import psutil
    process = psutil.Process()
    mem_info = process.memory_info()
    
    text = "📊 **Estadísticas del Sistema**\n\n"
    
    text += "🤖 **Información del Bot:**\n"
    text += f"• **Nombre:** @{bot_info.username}\n"
    text += f"• **ID:** {bot_info.id}\n"
    text += f"• **Administradores:** {len(ADMINS)}\n"
    text += f"• **Caché de búsqueda:** {cache_size} entradas\n\n"
    
    text += "💾 **Uso de Disco:**\n"
    if disk_info:
        text += f"• **Total:** {disk_info['total_human']}\n"
        text += f"• **Usado:** {disk_info['used_human']} ({disk_info['percent_used']:.1f}%)\n"
        text += f"• **Libre:** {disk_info['free_human']}\n"
        text += f"• **Temp:** {humanize.naturalsize(temp_stats['size'])} ({temp_stats['files']} archivos)\n\n"
    
    text += "🧠 **Uso de Memoria:**\n"
    text += f"• **RSS:** {humanize.naturalsize(mem_info.rss)}\n"
    text += f"• **VMS:** {humanize.naturalsize(mem_info.vms)}\n\n"
    
    text += "📁 **Directorios:**\n"
    text += f"• **Base:** `{BASE_DIR}`\n"
    text += f"• **Temp:** `{TEMP_DIR}`\n"
    text += f"• **Seguros:** {len(FileManager.SAFE_DIRECTORIES)} directorios\n\n"
    
    text += f"🕐 **Actualizado:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Uso de disco", callback_data="root_disk_usage"),
         InlineKeyboardButton("🧹 Limpiar", callback_data="root_cleanup_temp")],
        [InlineKeyboardButton("📁 Explorar", callback_data="root_list_current"),
         InlineKeyboardButton("🔙 Panel", callback_data="root")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# ==============================================
# HANDLERS DE CALLBACKS PARA ADMINISTRACIÓN
# ==============================================

@app.on_callback_query(filters.regex(r"^root_"))
async def handle_root_callbacks(client: Client, callback_query: CallbackQuery):
    """Manejador de callbacks del panel root"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if user_id not in ADMINS:
        await callback_query.answer("❌ Acceso denegado", show_alert=True)
        return
    
    message = callback_query.message
    
    try:
        if data == "root":
            await root_command(client, message)
            
        elif data == "root_list_current":
            await list_directory_command(client, message, BASE_DIR)
            
        elif data.startswith("root_list_"):
            parts = data[10:].split("_", 2)  # root_list_path_page
            path = parts[0] if len(parts) > 0 else BASE_DIR
            
            # Si hay página
            if len(parts) == 2 and parts[1].isdigit():
                page = int(parts[1])
                await list_directory_command(client, message, path, page)
            else:
                await list_directory_command(client, message, path)
            
        elif data.startswith("root_info_"):
            path = data[10:]
            await list_directory_command(client, message, path)
            
        elif data == "root_disk_usage":
            await disk_command(client, message)
            
        elif data == "root_disk_details":
            disk_info = FileManager.get_disk_usage()
            
            if disk_info:
                text = "💾 **Detalles del Disco**\n\n"
                text += f"**Total bytes:** {disk_info['total']:,}\n"
                text += f"**Usado bytes:** {disk_info['used']:,}\n"
                text += f"**Libre bytes:** {disk_info['free']:,}\n"
                text += f"**Porcentaje:** {disk_info['percent_used']:.2f}%\n"
                text += f"**Temp bytes:** {disk_info['temp_size']:,}\n"
                text += f"**Archivos temp:** {disk_info['temp_count']}\n\n"
                text += f"**Timestamp:** {disk_info['timestamp']}"
                
                await message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
            else:
                await message.edit_text("❌ Error obteniendo detalles del disco")
            
        elif data == "root_cleanup_temp":
            await clean_command(client, message)
            
        elif data.startswith("root_send_"):
            path = data[10:]
            
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
                await message.reply_document(
                    document=path,
                    caption=f"📄 **Archivo del sistema**\n`{os.path.basename(path)}`\n\n"
                           f"**Ruta:** `{path}`\n"
                           f"**Tamaño:** {humanize.naturalsize(file_size)}",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply_text(f"❌ Error enviando archivo: {str(e)}")
            
        elif data.startswith("root_delete_"):
            path = data[12:]
            
            if not FileManager.is_safe_path(path):
                await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                return
            
            if not os.path.exists(path):
                await callback_query.answer("❌ La ruta no existe", show_alert=True)
                return
            
            # Pedir confirmación
            item_name = os.path.basename(path)
            is_dir = os.path.isdir(path)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"root_confirm_delete_{path}"),
                 InlineKeyboardButton("❌ Cancelar", callback_data=f"root_list_{os.path.dirname(path)}")]
            ])
            
            confirm_text = f"⚠️ **Confirmar eliminación**\n\n"
            if is_dir:
                confirm_text += f"¿Eliminar el directorio **{item_name}** y todo su contenido?\n\n"
                confirm_text += "**Esta acción no se puede deshacer.**"
            else:
                confirm_text += f"¿Eliminar el archivo **{item_name}**?\n\n"
                confirm_text += "**Esta acción no se puede deshacer.**"
            
            await message.edit_text(confirm_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
            
        elif data.startswith("root_confirm_delete_"):
            path = data[20:]
            
            success, message_text = FileManager.delete_path(path)
            
            if success:
                parent_dir = os.path.dirname(path)
                await list_directory_command(client, message, parent_dir)
                await callback_query.answer("✅ Eliminado correctamente")
            else:
                await message.edit_text(f"❌ {message_text}")
                await callback_query.answer("❌ Error")
            
        elif data.startswith("root_rename_"):
            path = data[12:]
            
            if not FileManager.is_safe_path(path):
                await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                return
            
            if not os.path.exists(path):
                await callback_query.answer("❌ La ruta no existe", show_alert=True)
                return
            
            item_name = os.path.basename(path)
            
            # Guardar la ruta en el estado del usuario
            await callback_query.answer("📝 Ingresa el nuevo nombre")
            
            # Enviar mensaje para pedir el nuevo nombre
            await message.reply_text(
                f"🔄 **Renombrar**\n\n"
                f"**Actual:** `{item_name}`\n\n"
                f"Por favor, envía el nuevo nombre:",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Usar una variable temporal para almacenar la ruta
            # En una implementación real, usarías una base de datos o diccionario
            # Para este ejemplo, usaremos un mensaje directo
            from_user = callback_query.from_user.id
            
            # Guardar en estado (simplificado)
            global rename_states
            if 'rename_states' not in globals():
                rename_states = {}
            rename_states[from_user] = path
            
        elif data.startswith("root_mkdir_"):
            parent_path = data[11:]
            
            if not FileManager.is_safe_path(parent_path):
                await callback_query.answer("❌ Ruta no permitida", show_alert=True)
                return
            
            await callback_query.answer("📁 Ingresa el nombre de la carpeta")
            
            await message.reply_text(
                f"➕ **Crear nueva carpeta**\n\n"
                f"**Ubicación:** `{parent_path}`\n\n"
                f"Por favor, envía el nombre de la nueva carpeta:",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Guardar en estado
            global mkdir_states
            if 'mkdir_states' not in globals():
                mkdir_states = {}
            mkdir_states[callback_query.from_user.id] = parent_path
            
        elif data == "root_search_menu":
            await message.edit_text(
                "🔍 **Buscar Archivos**\n\n"
                "Envía el patrón de búsqueda:\n\n"
                "**Ejemplos:**\n"
                "• `.py` - Archivos Python\n"
                "• `config` - Archivos de configuración\n"
                "• `log` - Archivos de log\n\n"
                "**O usa:** `/find <patrón> [ruta]`",
                parse_mode=enums.ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Buscar en base", callback_data=f"root_search_{BASE_DIR}"),
                     InlineKeyboardButton("🔍 Buscar en temp", callback_data=f"root_search_{TEMP_DIR}")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="root")]
                ])
            )
            
        elif data.startswith("root_search_"):
            path = data[12:]
            
            await callback_query.answer("🔍 Ingresa el patrón de búsqueda")
            
            await message.reply_text(
                f"🔍 **Buscar en directorio**\n\n"
                f"**Ruta:** `{path}`\n\n"
                f"Envía el patrón a buscar:",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Guardar en estado
            global search_states
            if 'search_states' not in globals():
                search_states = {}
            search_states[callback_query.from_user.id] = path
            
        elif data == "root_view_logs":
            log_file = os.path.join(BASE_DIR, "bot.log")
            
            if os.path.exists(log_file):
                try:
                    # Leer últimas líneas del log
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if lines:
                        last_lines = lines[-50:]  # Últimas 50 líneas
                        log_text = "".join(last_lines)
                        
                        if len(log_text) > 4000:
                            log_text = "...\n" + log_text[-4000:]
                        
                        text = f"📝 **Últimas líneas del log**\n\n"
                        text += f"**Archivo:** `{log_file}`\n"
                        text += f"**Total líneas:** {len(lines)}\n\n"
                        text += "```\n"
                        text += log_text
                        text += "\n```"
                        
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📤 Descargar log completo", callback_data="root_download_log")],
                            [InlineKeyboardButton("🗑️ Limpiar logs", callback_data="root_clear_logs"),
                             InlineKeyboardButton("🔙 Volver", callback_data="root")]
                        ])
                        
                        await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                    else:
                        await message.edit_text("📭 El archivo de log está vacío")
                except Exception as e:
                    await message.edit_text(f"❌ Error leyendo log: {str(e)}")
            else:
                await message.edit_text("📭 No se encontró archivo de log")
                
        elif data == "root_download_log":
            log_file = os.path.join(BASE_DIR, "bot.log")
            
            if os.path.exists(log_file):
                file_size = os.path.getsize(log_file)
                
                if file_size > MAX_FILE_SIZE:
                    await callback_query.answer(
                        f"❌ Log demasiado grande ({humanize.naturalsize(file_size)})",
                        show_alert=True
                    )
                    return
                
                await callback_query.answer("📤 Enviando archivo de log...")
                
                try:
                    await message.reply_document(
                        document=log_file,
                        caption="📝 **Archivo de log completo**",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                except Exception as e:
                    await message.reply_text(f"❌ Error enviando log: {str(e)}")
            else:
                await callback_query.answer("❌ No se encontró archivo de log", show_alert=True)
                
        elif data == "root_clear_logs":
            log_file = os.path.join(BASE_DIR, "bot.log")
            
            if os.path.exists(log_file):
                try:
                    # Crear backup del log actual
                    backup_file = f"{log_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(log_file, backup_file)
                    
                    # Limpiar log
                    with open(log_file, 'w') as f:
                        f.write(f"=== Log limpiado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    
                    await message.edit_text(
                        f"✅ **Log limpiado**\n\n"
                        f"Se creó un backup: `{os.path.basename(backup_file)}`",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                except Exception as e:
                    await message.edit_text(f"❌ Error limpiando log: {str(e)}")
            else:
                await message.edit_text("📭 No se encontró archivo de log")
                
        elif data == "root_restart_bot":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sí, reiniciar", callback_data="root_confirm_restart"),
                 InlineKeyboardButton("❌ Cancelar", callback_data="root")]
            ])
            
            await message.edit_text(
                "⚠️ **Confirmar reinicio**\n\n"
                "¿Estás seguro de que quieres reiniciar el bot?\n\n"
                "**Nota:** Esto puede tomar unos segundos.",
                reply_markup=keyboard
            )
            
        elif data == "root_confirm_restart":
            await message.edit_text("🔄 Reiniciando bot...")
            
            # En una implementación real, aquí reiniciarías el bot
            # Por ahora solo simulamos
            import sys
            os.execv(sys.executable, ['python'] + sys.argv)
            
        elif data == "root_shutdown_bot":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Sí, cerrar", callback_data="root_confirm_shutdown"),
                 InlineKeyboardButton("❌ Cancelar", callback_data="root")]
            ])
            
            await message.edit_text(
                "⚠️ **Confirmar cierre**\n\n"
                "¿Estás seguro de que quieres cerrar el bot?\n\n"
                "**Nota:** Tendrás que reiniciarlo manualmente.",
                reply_markup=keyboard
            )
            
        elif data == "root_confirm_shutdown":
            await message.edit_text("🛑 Cerrando bot...")
            
            # Cerrar el bot
            await client.stop()
            import sys
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Error en callback root: {e}")
        await callback_query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)

# ==============================================
# HANDLER PARA MENSAJES DE TEXTO (RENOMBRAR/CREAR)
# ==============================================

@app.on_message(filters.private & filters.text)
async def handle_text_messages(client: Client, message: Message):
    """Maneja mensajes de texto para operaciones root"""
    user_id = message.from_user.id
    
    if user_id not in ADMINS:
        return
    
    text = message.text.strip()
    
    # Verificar si estamos esperando un nombre para renombrar
    if 'rename_states' in globals() and user_id in rename_states:
        old_path = rename_states[user_id]
        parent_dir = os.path.dirname(old_path)
        new_path = os.path.join(parent_dir, text)
        
        success, msg = FileManager.rename_path(old_path, text)
        
        if success:
            await message.reply_text(f"✅ {msg}")
            await list_directory_command(client, message, parent_dir)
        else:
            await message.reply_text(f"❌ {msg}")
        
        del rename_states[user_id]
        return
    
    # Verificar si estamos esperando un nombre para nueva carpeta
    elif 'mkdir_states' in globals() and user_id in mkdir_states:
        parent_path = mkdir_states[user_id]
        new_dir = os.path.join(parent_path, text)
        
        success, msg = FileManager.create_directory(new_dir)
        
        if success:
            await message.reply_text(f"✅ {msg}")
            await list_directory_command(client, message, parent_path)
        else:
            await message.reply_text(f"❌ {msg}")
        
        del mkdir_states[user_id]
        return
    
    # Verificar si estamos esperando un patrón de búsqueda
    elif 'search_states' in globals() and user_id in search_states:
        search_path = search_states[user_id]
        
        # Realizar búsqueda
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
        
        del search_states[user_id]
        return

# ==============================================
# MANTENER EL RESTO DEL CÓDIGO ORIGINAL (con imports adicionales)
# ==============================================

# Importaciones adicionales necesarias
import humanize

# Resto de las funciones originales del bot...
# (download_github_repo, get_repo_info_from_url, search_github_repos, etc.)
# Se mantienen igual que en el código anterior

# ... [Aquí iría el resto del código original del bot GitHub Downloader] ...

# Solo necesitamos agregar el inicio de sesión
async def main():
    try:
        logger.info("🚀 Iniciando GitHub Downloader Bot con funciones Root...")
        await app.start()
        
        me = await app.get_me()
        logger.info(f"✅ Bot iniciado como: @{me.username}")
        
        # Crear archivo de log si no existe
        log_file = os.path.join(BASE_DIR, "bot.log")
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write(f"=== Bot iniciado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        
        # Mantener el bot en ejecución
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
    finally:
        await app.stop()

if __name__ == "__main__":
    # Instalar dependencias adicionales si no están instaladas
    try:
        import psutil
        import humanize
    except ImportError:
        logger.warning("Instalando dependencias adicionales...")
        import subprocess
        subprocess.run(["pip", "install", "psutil", "humanize"])
        import psutil
        import humanize
    
    # Crear directorios necesarios
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Configurar mimetypes
    mimetypes.init()
    
    app.run()