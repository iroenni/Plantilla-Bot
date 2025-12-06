import asyncio
import datetime
import logging
from typing import Dict, List
import aiosqlite
import aiohttp
import pytz
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from pyrogram.enums import ParseMode

# Configuración básica
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración del bot
API_ID = 14681595
API_HASH = "a86730aab5c59953c424abb4396d32d5"
BOT_TOKEN = "8138537409:AAGMLe6R1nk8wHmfE2AZVSdG4_AQ8aaISSA"
OWNER_ID = 7970466590  # Tu ID de usuario

# Inicializar cliente
app = Client("monitoring_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Base de datos
DB_NAME = "monitoring.db"

# Estados de monitoreo
MONITORING_JOBS = {}
MONITORING_TASKS = {}

class Database:
    """Clase para manejar la base de datos SQLite"""
    
    @staticmethod
    async def init_db():
        """Inicializar la base de datos"""
        async with aiosqlite.connect(DB_NAME) as db:
            # Tabla de sitios web
            await db.execute('''
                CREATE TABLE IF NOT EXISTS websites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    interval INTEGER DEFAULT 60,
                    status TEXT DEFAULT 'unknown',
                    last_check DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    enabled INTEGER DEFAULT 1
                )
            ''')
            
            # Tabla de historial de checks
            await db.execute('''
                CREATE TABLE IF NOT EXISTS checks_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    website_id INTEGER NOT NULL,
                    status_code INTEGER,
                    response_time REAL,
                    is_up INTEGER DEFAULT 0,
                    error_message TEXT,
                    checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (website_id) REFERENCES websites (id)
                )
            ''')
            
            # Tabla de notificaciones
            await db.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    website_id INTEGER,
                    notification_type TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de usuarios
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT DEFAULT 'es',
                    notifications_enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
            logger.info("Base de datos inicializada")

    @staticmethod
    async def add_user(user_id: int, username: str, first_name: str, last_name: str = None):
        """Agregar usuario a la base de datos"""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                '''INSERT OR IGNORE INTO users 
                   (user_id, username, first_name, last_name) 
                   VALUES (?, ?, ?, ?)''',
                (user_id, username, first_name, last_name)
            )
            await db.commit()

    @staticmethod
    async def add_website(user_id: int, name: str, url: str, interval: int = 60):
        """Agregar sitio web para monitoreo"""
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                '''INSERT INTO websites (name, url, user_id, interval) 
                   VALUES (?, ?, ?, ?)''',
                (name, url, user_id, interval)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def get_websites(user_id: int = None):
        """Obtener todos los sitios web o de un usuario específico"""
        async with aiosqlite.connect(DB_NAME) as db:
            if user_id:
                cursor = await db.execute(
                    '''SELECT * FROM websites WHERE user_id = ? ORDER BY created_at DESC''',
                    (user_id,)
                )
            else:
                cursor = await db.execute('''SELECT * FROM websites ORDER BY created_at DESC''')
            
            columns = [description[0] for description in cursor.description]
            websites = await cursor.fetchall()
            return [dict(zip(columns, website)) for website in websites]

    @staticmethod
    async def get_website(website_id: int):
        """Obtener un sitio web por ID"""
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                '''SELECT * FROM websites WHERE id = ?''',
                (website_id,)
            )
            website = await cursor.fetchone()
            if website:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, website))
            return None

    @staticmethod
    async def update_website_status(website_id: int, status: str, last_check: datetime):
        """Actualizar estado del sitio web"""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                '''UPDATE websites SET status = ?, last_check = ? WHERE id = ?''',
                (status, last_check, website_id)
            )
            await db.commit()

    @staticmethod
    async def add_check_history(website_id: int, status_code: int, response_time: float, is_up: bool, error_message: str = None):
        """Agregar historial de check"""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                '''INSERT INTO checks_history 
                   (website_id, status_code, response_time, is_up, error_message) 
                   VALUES (?, ?, ?, ?, ?)''',
                (website_id, status_code, response_time, is_up, error_message)
            )
            await db.commit()

    @staticmethod
    async def get_website_stats(website_id: int):
        """Obtener estadísticas del sitio web"""
        async with aiosqlite.connect(DB_NAME) as db:
            # Obtener uptime de las últimas 24 horas
            cursor = await db.execute('''
                SELECT 
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN is_up = 1 THEN 1 ELSE 0 END) as successful_checks,
                    AVG(response_time) as avg_response_time
                FROM checks_history 
                WHERE website_id = ? AND checked_at > datetime('now', '-24 hours')
            ''', (website_id,))
            stats = await cursor.fetchone()
            
            if stats and stats[0] > 0:
                uptime = (stats[1] / stats[0]) * 100
                return {
                    'total_checks': stats[0],
                    'successful_checks': stats[1],
                    'uptime_24h': round(uptime, 2),
                    'avg_response_time': round(stats[2] or 0, 2)
                }
            return None

    @staticmethod
    async def delete_website(website_id: int):
        """Eliminar sitio web"""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''DELETE FROM websites WHERE id = ?''', (website_id,))
            await db.commit()
            return True

    @staticmethod
    async def toggle_website(website_id: int, enabled: bool):
        """Activar/desactivar sitio web"""
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                '''UPDATE websites SET enabled = ? WHERE id = ?''',
                (1 if enabled else 0, website_id)
            )
            await db.commit()

class WebsiteMonitor:
    """Clase para monitorear sitios web"""
    
    def __init__(self):
        self.session = None
        
    async def get_session(self):
        """Obtener sesión aiohttp"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
        
    async def check_website(self, website: Dict) -> Dict:
        """Verificar un sitio web"""
        session = await self.get_session()
        start_time = datetime.datetime.now()
        
        try:
            async with session.get(
                website['url'],
                allow_redirects=True,
                ssl=False
            ) as response:
                response_time = (datetime.datetime.now() - start_time).total_seconds()
                
                is_up = response.status < 400
                status = "up" if is_up else "down"
                
                return {
                    'status': status,
                    'status_code': response.status,
                    'response_time': response_time,
                    'is_up': is_up,
                    'error_message': None
                }
                
        except Exception as e:
            response_time = (datetime.datetime.now() - start_time).total_seconds()
            return {
                'status': 'down',
                'status_code': 0,
                'response_time': response_time,
                'is_up': False,
                'error_message': str(e)
            }
    
    async def check_all_websites(self):
        """Verificar todos los sitios web activos"""
        websites = await Database.get_websites()
        active_websites = [w for w in websites if w['enabled'] == 1]
        
        for website in active_websites:
            try:
                result = await self.check_website(website)
                now = datetime.datetime.now()
                
                # Actualizar base de datos
                await Database.update_website_status(website['id'], result['status'], now)
                await Database.add_check_history(
                    website['id'],
                    result['status_code'],
                    result['response_time'],
                    result['is_up'],
                    result['error_message']
                )
                
                # Enviar notificación si el estado cambió
                if website['status'] != result['status']:
                    await self.send_status_notification(website, result)
                    
            except Exception as e:
                logger.error(f"Error checking website {website['url']}: {e}")
    
    async def send_status_notification(self, website: Dict, result: Dict):
        """Enviar notificación de cambio de estado"""
        user_id = website['user_id']
        
        status_emoji = "🟢" if result['is_up'] else "🔴"
        status_text = "ONLINE" if result['is_up'] else "OFFLINE"
        
        message = (
            f"🚨 **Cambio de Estado Detectado**\n\n"
            f"**Sitio:** {website['name']}\n"
            f"**URL:** {website['url']}\n"
            f"**Estado:** {status_emoji} {status_text}\n"
            f"**Código HTTP:** {result['status_code']}\n"
            f"**Tiempo de respuesta:** {result['response_time']:.2f}s\n"
        )
        
        if result['error_message']:
            message += f"**Error:** {result['error_message']}\n"
        
        message += f"\n🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            await app.send_message(user_id, message)
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

# Inicializar monitor
monitor = WebsiteMonitor()

# Comandos del bot
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Comando /start"""
    user = message.from_user
    await Database.add_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Agregar Sitio", callback_data="add_site"),
         InlineKeyboardButton("📊 Mis Sitios", callback_data="list_sites")],
        [InlineKeyboardButton("⚙️ Configuración", callback_data="settings"),
         InlineKeyboardButton("📈 Estadísticas", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help"),
         InlineKeyboardButton("👨‍💻 Soporte", url="https://t.me/tuusuario")]
    ])
    
    welcome_text = (
        f"👋 **Bienvenido {user.first_name}!**\n\n"
        "🤖 **Bot de Monitoreo Web Uptime**\n"
        "Monitorea el estado de tus sitios web 24/7\n\n"
        "✨ **Características:**\n"
        "• Monitoreo en tiempo real\n"
        "• Notificaciones instantáneas\n"
        "• Historial y estadísticas\n"
        "• Panel de control interactivo\n\n"
        "Usa los botones para comenzar!"
    )
    
    await message.reply_text(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("add"))
async def add_site_command(client: Client, message: Message):
    """Agregar sitio web para monitoreo"""
    args = message.text.split()
    
    if len(args) < 3:
        await message.reply_text(
            "📝 **Uso:** `/add <nombre> <url>`\n\n"
            "**Ejemplo:**\n"
            "`/add MiSitio https://ejemplo.com`\n"
            "`/add API https://api.ejemplo.com/health`"
        )
        return
    
    name = args[1]
    url = args[2] if args[2].startswith(('http://', 'https://')) else f'https://{args[2]}'
    
    # Validar URL básica
    if not url.startswith(('http://', 'https://')):
        await message.reply_text("❌ URL inválida. Debe comenzar con http:// o https://")
        return
    
    try:
        website_id = await Database.add_website(message.from_user.id, name, url)
        
        await message.reply_text(
            f"✅ **Sitio agregado exitosamente!**\n\n"
            f"**Nombre:** {name}\n"
            f"**URL:** {url}\n"
            f"**ID:** `{website_id}`\n\n"
            "El monitoreo comenzará automáticamente en 1 minuto."
        )
        
        # Iniciar monitoreo para este sitio
        await start_monitoring_website(website_id)
        
    except Exception as e:
        await message.reply_text(f"❌ Error al agregar sitio: {str(e)}")

@app.on_message(filters.command("sites"))
async def list_sites_command(client: Client, message: Message):
    """Listar sitios web del usuario"""
    websites = await Database.get_websites(message.from_user.id)
    
    if not websites:
        await message.reply_text(
            "📭 **No tienes sitios monitoreados**\n\n"
            "Usa /add para agregar tu primer sitio web."
        )
        return
    
    text = "📊 **Tus Sitios Monitoreados:**\n\n"
    
    for site in websites:
        status_emoji = {
            'up': '🟢',
            'down': '🔴',
            'unknown': '⚫'
        }.get(site['status'], '⚫')
        
        enabled_emoji = '✅' if site['enabled'] else '⏸️'
        
        text += (
            f"{status_emoji} **{site['name']}** {enabled_emoji}\n"
            f"🔗 {site['url']}\n"
            f"🆔 ID: `{site['id']}` | ⏱️ {site['interval']}s\n"
        )
        
        if site['last_check']:
            last_check = datetime.datetime.fromisoformat(site['last_check'])
            text += f"🕐 Última verificación: {last_check.strftime('%H:%M:%S')}\n"
        
        text += "─" * 30 + "\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualizar", callback_data="list_sites"),
         InlineKeyboardButton("➕ Agregar Más", callback_data="add_site")],
        [InlineKeyboardButton("📈 Ver Detalles", callback_data="view_details")]
    ])
    
    await message.reply_text(text[:4000], reply_markup=keyboard)

@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    """Estadísticas generales"""
    websites = await Database.get_websites(message.from_user.id)
    
    if not websites:
        await message.reply_text("No tienes sitios monitoreados aún.")
        return
    
    total_sites = len(websites)
    up_sites = len([s for s in websites if s['status'] == 'up'])
    down_sites = len([s for s in websites if s['status'] == 'down'])
    enabled_sites = len([s for s in websites if s['enabled'] == 1])
    
    text = (
        "📈 **Estadísticas de Monitoreo**\n\n"
        f"**Sitios Totales:** {total_sites}\n"
        f"**🟢 Online:** {up_sites}\n"
        f"**🔴 Offline:** {down_sites}\n"
        f"**✅ Activos:** {enabled_sites}\n"
        f"**⏸️ Pausados:** {total_sites - enabled_sites}\n\n"
    )
    
    # Calcular uptime general
    total_uptime = 0
    sites_with_stats = 0
    
    for site in websites:
        stats = await Database.get_website_stats(site['id'])
        if stats:
            total_uptime += stats['uptime_24h']
            sites_with_stats += 1
    
    if sites_with_stats > 0:
        avg_uptime = total_uptime / sites_with_stats
        text += f"**📊 Uptime promedio (24h):** {avg_uptime:.2f}%\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualizar", callback_data="stats"),
         InlineKeyboardButton("📊 Detalles por Sitio", callback_data="site_stats")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)

@app.on_message(filters.command("check"))
async def check_now_command(client: Client, message: Message):
    """Forzar verificación de todos los sitios"""
    await message.reply_text("🔄 Verificando todos los sitios...")
    
    try:
        await monitor.check_all_websites()
        await message.reply_text("✅ Verificación completada!")
    except Exception as e:
        await message.reply_text(f"❌ Error durante la verificación: {str(e)}")

@app.on_message(filters.command("pause"))
async def pause_command(client: Client, message: Message):
    """Pausar monitoreo de un sitio"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text(
            "⏸️ **Uso:** `/pause <id_del_sitio>`\n\n"
            "Obtén el ID con el comando /sites"
        )
        return
    
    try:
        site_id = int(args[1])
        website = await Database.get_website(site_id)
        
        if not website:
            await message.reply_text("❌ Sitio no encontrado.")
            return
        
        if website['user_id'] != message.from_user.id:
            await message.reply_text("❌ Solo puedes pausar tus propios sitios.")
            return
        
        await Database.toggle_website(site_id, False)
        await stop_monitoring_website(site_id)
        
        await message.reply_text(
            f"⏸️ **Monitoreo pausado**\n\n"
            f"**Sitio:** {website['name']}\n"
            f"**ID:** {site_id}\n\n"
            "Usa /resume para reactivar."
        )
        
    except ValueError:
        await message.reply_text("❌ ID inválido.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("resume"))
async def resume_command(client: Client, message: Message):
    """Reanudar monitoreo de un sitio"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text(
            "▶️ **Uso:** `/resume <id_del_sitio>`\n\n"
            "Obtén el ID con el comando /sites"
        )
        return
    
    try:
        site_id = int(args[1])
        website = await Database.get_website(site_id)
        
        if not website:
            await message.reply_text("❌ Sitio no encontrado.")
            return
        
        if website['user_id'] != message.from_user.id:
            await message.reply_text("❌ Solo puedes reanudar tus propios sitios.")
            return
        
        await Database.toggle_website(site_id, True)
        await start_monitoring_website(site_id)
        
        await message.reply_text(
            f"▶️ **Monitoreo reanudado**\n\n"
            f"**Sitio:** {website['name']}\n"
            f"**ID:** {site_id}\n\n"
            "El sitio será verificado en el próximo ciclo."
        )
        
    except ValueError:
        await message.reply_text("❌ ID inválido.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete"))
async def delete_command(client: Client, message: Message):
    """Eliminar un sitio"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text(
            "🗑️ **Uso:** `/delete <id_del_sitio>`\n\n"
            "⚠️ **Esta acción no se puede deshacer!**"
        )
        return
    
    try:
        site_id = int(args[1])
        website = await Database.get_website(site_id)
        
        if not website:
            await message.reply_text("❌ Sitio no encontrado.")
            return
        
        if website['user_id'] != message.from_user.id:
            await message.reply_text("❌ Solo puedes eliminar tus propios sitios.")
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, eliminar", callback_data=f"confirm_delete_{site_id}"),
             InlineKeyboardButton("❌ Cancelar", callback_data="cancel_delete")]
        ])
        
        await message.reply_text(
            f"⚠️ **¿Eliminar sitio?**\n\n"
            f"**Nombre:** {website['name']}\n"
            f"**URL:** {website['url']}\n"
            f"**ID:** {site_id}\n\n"
            "Esta acción eliminará todos los datos del sitio.",
            reply_markup=keyboard
        )
        
    except ValueError:
        await message.reply_text("❌ ID inválido.")

@app.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    """Estado general del sistema"""
    websites = await Database.get_websites()
    
    total_sites = len(websites)
    up_sites = len([s for s in websites if s['status'] == 'up'])
    down_sites = len([s for s in websites if s['status'] == 'down'])
    
    text = (
        "🤖 **Estado del Sistema**\n\n"
        f"**Bot:** 🟢 Online\n"
        f"**Monitoreando:** {total_sites} sitios\n"
        f"**🟢 Online:** {up_sites}\n"
        f"**🔴 Offline:** {down_sites}\n"
        f"**📊 Uptime general:** {(up_sites/total_sites*100 if total_sites > 0 else 0):.1f}%\n\n"
        f"🕐 **Hora del servidor:** {datetime.datetime.now().strftime('%H:%M:%S')}\n"
        f"📅 **Fecha:** {datetime.datetime.now().strftime('%Y-%m-%d')}"
    )
    
    await message.reply_text(text)

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Mostrar ayuda"""
    help_text = """
📚 **Comandos Disponibles:**

**👤 Básicos:**
/start - Iniciar bot
/help - Mostrar esta ayuda
/status - Estado del sistema

**🌐 Monitoreo:**
/add <nombre> <url> - Agregar sitio
/sites - Listar sitios
/check - Verificar ahora
/stats - Estadísticas

**⚙️ Gestión:**
/pause <id> - Pausar monitoreo
/resume <id> - Reanudar monitoreo
/delete <id> - Eliminar sitio
/info <id> - Información del sitio

**📊 Reportes:**
/report - Reporte diario
/history <id> - Historial del sitio

**👑 Dueño:**
/allstats - Estadísticas globales
/broadcast <msg> - Mensaje a usuarios
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Agregar Sitio", callback_data="add_site"),
         InlineKeyboardButton("📊 Mis Sitios", callback_data="list_sites")],
        [InlineKeyboardButton("📈 Estadísticas", callback_data="stats"),
         InlineKeyboardButton("⚙️ Configuración", callback_data="settings")]
    ])
    
    await message.reply_text(help_text, reply_markup=keyboard)

# Manejo de callbacks (botones)
@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Manejar botones inline"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "add_site":
        await callback_query.message.reply_text(
            "📝 **Agregar Nuevo Sitio**\n\n"
            "Envía el comando:\n"
            "`/add <nombre> <url>`\n\n"
            "**Ejemplo:**\n"
            "`/add MiSitio https://ejemplo.com`"
        )
        await callback_query.answer()
        
    elif data == "list_sites":
        websites = await Database.get_websites(user_id)
        
        if not websites:
            await callback_query.message.edit_text(
                "📭 **No tienes sitios monitoreados**\n\n"
                "Usa el botón 'Agregar Sitio' para comenzar."
            )
            return
        
        text = "📊 **Tus Sitios Monitoreados:**\n\n"
        buttons = []
        
        for site in websites[:10]:  # Máximo 10 por página
            status_emoji = '🟢' if site['status'] == 'up' else '🔴'
            enabled_emoji = '✅' if site['enabled'] else '⏸️'
            
            text += f"{status_emoji} **{site['name']}** {enabled_emoji}\n"
            text += f"🔗 {site['url'][:30]}...\n"
            text += f"🆔 ID: `{site['id']}`\n"
            text += "─" * 30 + "\n"
            
            buttons.append([
                InlineKeyboardButton(
                    f"{site['name']} ({site['id']})",
                    callback_data=f"site_info_{site['id']}"
                )
            ])
        
        buttons.append([
            InlineKeyboardButton("🔄 Actualizar", callback_data="list_sites"),
            InlineKeyboardButton("➕ Agregar", callback_data="add_site")
        ])
        
        keyboard = InlineKeyboardMarkup(buttons)
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer()
    
    elif data.startswith("site_info_"):
        site_id = int(data.split("_")[2])
        website = await Database.get_website(site_id)
        
        if not website or website['user_id'] != user_id:
            await callback_query.answer("Sitio no encontrado", show_alert=True)
            return
        
        stats = await Database.get_website_stats(site_id)
        
        status_emoji = '🟢' if website['status'] == 'up' else '🔴'
        enabled_emoji = '✅ Activo' if website['enabled'] else '⏸️ Pausado'
        
        text = (
            f"🔍 **Información del Sitio**\n\n"
            f"**Nombre:** {website['name']}\n"
            f"**URL:** {website['url']}\n"
            f"**Estado:** {status_emoji} {website['status'].upper()}\n"
            f"**Monitoreo:** {enabled_emoji}\n"
            f"**Intervalo:** {website['interval']} segundos\n"
            f"**ID:** `{site_id}`\n\n"
        )
        
        if stats:
            text += (
                f"📊 **Estadísticas (24h):**\n"
                f"• Uptime: {stats['uptime_24h']}%\n"
                f"• Checks: {stats['total_checks']}\n"
                f"• Respuesta: {stats['avg_response_time']}s\n"
            )
        
        if website['last_check']:
            last_check = datetime.datetime.fromisoformat(website['last_check'])
            text += f"\n🕐 **Última verificación:** {last_check.strftime('%H:%M:%S')}"
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⏸️ Pausar", callback_data=f"pause_{site_id}") 
                if website['enabled'] else 
                InlineKeyboardButton("▶️ Reanudar", callback_data=f"resume_{site_id}"),
                InlineKeyboardButton("🗑️ Eliminar", callback_data=f"delete_{site_id}")
            ],
            [InlineKeyboardButton("📈 Historial", callback_data=f"history_{site_id}"),
             InlineKeyboardButton("🔙 Volver", callback_data="list_sites")]
        ])
        
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer()
    
    elif data.startswith("pause_"):
        site_id = int(data.split("_")[1])
        await Database.toggle_website(site_id, False)
        await stop_monitoring_website(site_id)
        await callback_query.answer("✅ Monitoreo pausado")
        await callback_query.message.reply_text(f"⏸️ Monitoreo pausado para el sitio ID: {site_id}")
    
    elif data.startswith("resume_"):
        site_id = int(data.split("_")[1])
        await Database.toggle_website(site_id, True)
        await start_monitoring_website(site_id)
        await callback_query.answer("✅ Monitoreo reanudado")
        await callback_query.message.reply_text(f"▶️ Monitoreo reanudado para el sitio ID: {site_id}")
    
    elif data.startswith("delete_"):
        site_id = int(data.split("_")[1])
        await Database.delete_website(site_id)
        await stop_monitoring_website(site_id)
        await callback_query.answer("✅ Sitio eliminado")
        await callback_query.message.reply_text(f"🗑️ Sitio eliminado ID: {site_id}")
    
    elif data == "stats":
        websites = await Database.get_websites(user_id)
        
        if not websites:
            await callback_query.message.edit_text(
                "📭 **No tienes sitios monitoreados**\n\n"
                "Agrega sitios para ver estadísticas."
            )
            return
        
        total_sites = len(websites)
        up_sites = len([s for s in websites if s['status'] == 'up'])
        down_sites = len([s for s in websites if s['status'] == 'down'])
        
        text = (
            f"📈 **Tus Estadísticas**\n\n"
            f"**Sitios Totales:** {total_sites}\n"
            f"**🟢 Online:** {up_sites}\n"
            f"**🔴 Offline:** {down_sites}\n"
            f"**📊 Uptime:** {(up_sites/total_sites*100 if total_sites > 0 else 0):.1f}%\n\n"
        )
        
        # Estadísticas detalladas
        for site in websites[:5]:  # Mostrar primeros 5
            stats = await Database.get_website_stats(site['id'])
            if stats:
                text += f"**{site['name']}:** {stats['uptime_24h']}% uptime\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Actualizar", callback_data="stats"),
             InlineKeyboardButton("📊 Detalles", callback_data="list_sites")],
            [InlineKeyboardButton("🔙 Inicio", callback_data="start")]
        ])
        
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer()
    
    elif data == "settings":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Notificaciones", callback_data="notifications"),
             InlineKeyboardButton("⏱️ Intervalos", callback_data="intervals")],
            [InlineKeyboardButton("📧 Contacto", callback_data="contact"),
             InlineKeyboardButton("🔙 Volver", callback_data="start")]
        ])
        
        await callback_query.message.edit_text(
            "⚙️ **Configuración**\n\n"
            "Configura las opciones del bot:",
            reply_markup=keyboard
        )
        await callback_query.answer()
    
    elif data == "start":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar Sitio", callback_data="add_site"),
             InlineKeyboardButton("📊 Mis Sitios", callback_data="list_sites")],
            [InlineKeyboardButton("⚙️ Configuración", callback_data="settings"),
             InlineKeyboardButton("📈 Estadísticas", callback_data="stats")]
        ])
        
        await callback_query.message.edit_text(
            "🤖 **Bot de Monitoreo Web**\n\n"
            "Selecciona una opción:",
            reply_markup=keyboard
        )
        await callback_query.answer()

# Funciones de monitoreo
async def start_monitoring_website(website_id: int):
    """Iniciar monitoreo para un sitio web específico"""
    website = await Database.get_website(website_id)
    if not website or website['enabled'] != 1:
        return
    
    async def monitor_job():
        while True:
            try:
                result = await monitor.check_website(website)
                now = datetime.datetime.now()
                
                await Database.update_website_status(
                    website_id, 
                    result['status'], 
                    now
                )
                
                await Database.add_check_history(
                    website_id,
                    result['status_code'],
                    result['response_time'],
                    result['is_up'],
                    result['error_message']
                )
                
                # Notificar cambio de estado
                current_status = website.get('status', 'unknown')
                if current_status != result['status']:
                    await monitor.send_status_notification(website, result)
                
                # Actualizar estado en cache
                website['status'] = result['status']
                
            except Exception as e:
                logger.error(f"Error in monitoring job for {website_id}: {e}")
            
            await asyncio.sleep(website['interval'])
    
    task = asyncio.create_task(monitor_job())
    MONITORING_TASKS[website_id] = task
    logger.info(f"Started monitoring for website {website_id}")

async def stop_monitoring_website(website_id: int):
    """Detener monitoreo para un sitio web"""
    if website_id in MONITORING_TASKS:
        MONITORING_TASKS[website_id].cancel()
        del MONITORING_TASKS[website_id]
        logger.info(f"Stopped monitoring for website {website_id}")

async def start_all_monitoring():
    """Iniciar monitoreo para todos los sitios activos"""
    websites = await Database.get_websites()
    for website in websites:
        if website['enabled'] == 1:
            await start_monitoring_website(website['id'])

async def periodic_summary():
    """Enviar resumen periódico a los usuarios"""
    while True:
        try:
            # Enviar resumen cada 24 horas
            await asyncio.sleep(24 * 60 * 60)
            
            # Aquí puedes agregar lógica para enviar resúmenes
            # a los usuarios sobre el estado de sus sitios
            
            logger.info("Periodic summary check completed")
            
        except Exception as e:
            logger.error(f"Error in periodic summary: {e}")

# Inicialización
async def main():
    """Función principal"""
    # Inicializar base de datos
    await Database.init_db()
    
    # Iniciar monitoreo para sitios existentes
    await start_all_monitoring()
    
    # Iniciar resúmenes periódicos
    asyncio.create_task(periodic_summary())
    
    logger.info("🤖 Bot de Monitoreo Web iniciado!")
    
    # Ejecutar el bot
    await app.start()
    logger.info("✅ Bot conectado a Telegram")
    
    # Mantener el bot corriendo
    await asyncio.Event().wait()

# Ejecutar
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")