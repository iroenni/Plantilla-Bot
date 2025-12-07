import os
import asyncio
import shutil
import tempfile
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import aiohttp
import zipfile
import io
import json

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

# Almacenamiento temporal para resultados de búsqueda
search_cache = {}

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

async def search_github_repos(query: str, page: int = 1, per_page: int = 5):
    """
    Busca repositorios en GitHub usando la API
    """
    try:
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&page={page}&per_page={per_page}"
        
        headers = {
            'User-Agent': 'GitHubDownloaderBot/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 403:
                    return None, "Límite de API alcanzado. Intenta más tarde."
                elif response.status != 200:
                    return None, f"Error en la API: {response.status}"
                
                data = await response.json()
                
                if "items" not in data:
                    return None, "No se encontraron resultados."
                
                repos = []
                for item in data["items"]:
                    repo_info = {
                        "name": item["name"],
                        "full_name": item["full_name"],
                        "description": item["description"] or "Sin descripción",
                        "url": item["html_url"],
                        "stars": item["stargazers_count"],
                        "forks": item["forks_count"],
                        "language": item["language"] or "N/A",
                        "updated_at": item["updated_at"],
                        "owner": item["owner"]["login"]
                    }
                    repos.append(repo_info)
                
                total_count = data.get("total_count", 0)
                return {"repos": repos, "total_count": total_count, "page": page}, None
                
    except Exception as e:
        return None, f"Error en la búsqueda: {str(e)}"

def format_repo_search_results(results: dict):
    """
    Formatea los resultados de búsqueda para mostrar al usuario
    """
    repos = results["repos"]
    total_count = results["total_count"]
    page = results["page"]
    
    text = f"🔍 **Resultados de búsqueda**\n"
    text += f"📊 Encontrados: {total_count} repositorios\n"
    text += f"📄 Página: {page}\n\n"
    
    for i, repo in enumerate(repos, 1):
        text += f"**{i}. {repo['full_name']}**\n"
        text += f"   ⭐ {repo['stars']} | 🍴 {repo['forks']} | 💻 {repo['language']}\n"
        text += f"   📝 {repo['description']}\n"
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
        "🤖 **Bot Descargador de GitHub**\n\n"
        "📥 **Puedo descargar repositorios de GitHub y enviártelos como ZIP.**\n\n"
        "🔍 **¡NUEVO!** Sistema de búsqueda de repositorios\n\n"
        "**Comandos disponibles:**\n"
        "/search [término] - Buscar repositorios\n"
        "/download [url] - Descargar repositorio\n"
        "/help - Mostrar ayuda\n"
        "/example - Ejemplos de uso\n\n"
        "¡Envía un enlace de GitHub o busca repositorios!",
        reply_markup=keyboard
    )

@app.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "🔍 **Sistema de Búsqueda de Repositorios**\n\n"
            "📝 **Uso:** `/search <término_de_búsqueda>`\n\n"
            "**Ejemplos:**\n"
            "`/search python bot`\n"
            "`/search machine learning`\n"
            "`/search openai`\n\n"
            "💡 **Consejos:**\n"
            "• Usa palabras clave específicas\n"
            "• Puedes buscar por lenguaje: `language:python`\n"
            "• Puedes buscar por usuario: `user:nombre`\n"
            "• Máximo 5 resultados por página"
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
    import uuid
    search_id = str(uuid.uuid4())[:8]
    search_cache[search_id] = {"results": results, "query": query, "user_id": message.from_user.id}
    
    # Crear botones para los resultados
    keyboard_buttons = []
    for i, repo in enumerate(results["repos"], 1):
        callback_data = f"select_{search_id}_{i-1}"  # Índice base 0
        button_text = f"{i}. {repo['name'][:15]}"
        keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Botones de navegación
    nav_buttons = []
    if results["page"] > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
    
    if results["total_count"] > results["page"] * 5:
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
    
    keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    await processing_msg.edit_text(
        format_repo_search_results(results),
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
            "💡 **También puedes usar:**\n"
            "`/search <término>` para buscar repositorios\n\n"
            "⚠️ **Límite:** 50MB por archivo (límite de Telegram)"
        )
        return

    repo_url = args[1]

    # Verificar que sea URL de GitHub
    if "github.com" not in repo_url:
        await message.reply_text(
            "❌ **URL no válida**\n\n"
            "Por favor, envía una URL de GitHub válida.\n"
            "Ejemplo: `https://github.com/usuario/repositorio`\n\n"
            "💡 Usa `/search` para encontrar repositorios"
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
            "💡 **Soluciones:**\n"
            "1. Descarga desde GitHub directamente\n"
            "2. Usa ramas más pequeñas\n"
            "3. Clona manualmente con git\n"
            "4. Usa `/search` para encontrar alternativas"
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
- 🔍 **Buscar repositorios** en GitHub
- 📥 Descargar repositorios completos
- Enviarlos como archivo ZIP a Telegram
- Soporte para ramas específicas
- Información detallada del repositorio

🛠️ **Comandos:**
/start - Iniciar el bot
/search [término] - Buscar repositorios
/download [url] - Descargar repositorio
/help - Esta ayuda
/example - Ver ejemplos
/info - Información del bot

🔍 **Sistema de búsqueda:**
• Busca en todos los repos públicos de GitHub
• Ordena por popularidad (estrellas)
• Muestra descripción, lenguaje y stats
• Navegación por páginas

🔗 **Formatos de URL aceptados:**
• https://github.com/usuario/repo
• https://github.com/usuario/repo/tree/main
• https://github.com/usuario/repo/tree/develop
• https://github.com/usuario/repo.git

⚠️ **Limitaciones:**
• Máximo 50MB por archivo
• Solo repositorios públicos
• Límites de API de GitHub (10-30 búsquedas/min)
• No requiere autenticación
"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Probar búsqueda", callback_data="search_example"),
         InlineKeyboardButton("📥 Descargar ejemplo", callback_data="download_example")],
        [InlineKeyboardButton("🌐 GitHub API", url="https://docs.github.com/en/rest")]
    ])

    await message.reply_text(help_text, reply_markup=keyboard)

@app.on_message(filters.command("example"))
async def example_command(client: Client, message: Message):
    examples = """
📚 **Ejemplos de uso:**

🔍 **Búsquedas:**
`/search python bot telegram`
`/search machine learning tensorflow`
`/search language:javascript game`
`/search user:microsoft`

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
         InlineKeyboardButton("📥 Ejemplo rápido", callback_data="quick_download")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help"),
         InlineKeyboardButton("🏠 Inicio", callback_data="start")]
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
             InlineKeyboardButton("🔍 Buscar similares", callback_data=f"search_similar_{repo_url}")],
            [InlineKeyboardButton("🌐 Ver en GitHub", url=repo_url)]
        ])

        username, repo_name = get_repo_info_from_url(repo_url)

        await message.reply_text(
            f"🔍 **Repositorio detectado:**\n\n"
            f"**Nombre:** {repo_name or 'Desconocido'}\n"
            f"**URL:** {repo_url}\n\n"
            "¿Qué quieres hacer?",
            reply_markup=keyboard
        )

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user = callback_query.from_user
    message = callback_query.message

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
            "O usa: `/search <término>`"
        )
        await callback_query.answer()
    
    elif data == "download_menu":
        await callback_query.message.reply_text(
            "📥 **Descargar repositorio**\n\n"
            "Envía la URL del repositorio de GitHub:\n\n"
            "**Formato:**\n"
            "`https://github.com/usuario/repositorio`\n\n"
            "O usa: `/download <URL>`\n\n"
            "💡 **Consejo:** Usa primero `/search` para encontrar repositorios"
        )
        await callback_query.answer()
    
    elif data == "search_example":
        # Ejemplo de búsqueda
        example_query = "python telegram bot"
        processing_msg = await callback_query.message.reply_text(f"🔍 **Ejemplo:** Buscando `{example_query}`...")
        
        results, error = await search_github_repos(example_query)
        
        if error:
            await processing_msg.edit_text(f"❌ Error: {error}")
        else:
            import uuid
            search_id = str(uuid.uuid4())[:8]
            search_cache[search_id] = {"results": results, "query": example_query, "user_id": user.id}
            
            keyboard_buttons = []
            for i, repo in enumerate(results["repos"], 1):
                callback_data = f"select_{search_id}_{i-1}"
                button_text = f"{i}. {repo['name'][:15]}"
                keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            keyboard_buttons.append([InlineKeyboardButton("🔄 Buscar algo diferente", callback_data="search")])
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            await processing_msg.edit_text(
                format_repo_search_results(results),
                reply_markup=keyboard
            )
        
        await callback_query.answer()
    
    elif data == "search_python":
        # Búsqueda predefinida de Python
        await search_command(client, message)
        await callback_query.answer("Envía: /search python bot")
    
    elif data.startswith("prev_") or data.startswith("next_"):
        # Navegación entre páginas
        parts = data.split("_")
        action = parts[0]
        search_id = parts[1]
        current_page = int(parts[2])
        
        # Verificar cache
        if search_id not in search_cache:
            await callback_query.answer("❌ La búsqueda ha expirado")
            return
        
        search_data = search_cache[search_id]
        
        if search_data["user_id"] != user.id:
            await callback_query.answer("❌ Esta búsqueda no es tuya")
            return
        
        # Calcular nueva página
        new_page = current_page - 1 if action == "prev" else current_page + 1
        
        # Realizar nueva búsqueda con la página actualizada
        query = search_data["query"]
        results, error = await search_github_repos(query, new_page)
        
        if error:
            await callback_query.answer(f"Error: {error}")
            return
        
        # Actualizar cache
        search_cache[search_id]["results"] = results
        
        # Recrear botones
        keyboard_buttons = []
        for i, repo in enumerate(results["repos"], 1):
            callback_data = f"select_{search_id}_{i-1}"
            button_text = f"{i}. {repo['name'][:15]}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Botones de navegación
        nav_buttons = []
        if results["page"] > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
        
        if results["total_count"] > results["page"] * 5:
            nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await message.edit_text(
            format_repo_search_results(results),
            reply_markup=keyboard
        )
        await callback_query.answer(f"Página {new_page}")
    
    elif data.startswith("select_"):
        # Seleccionar un repositorio de los resultados
        parts = data.split("_")
        search_id = parts[1]
        repo_index = int(parts[2])
        
        # Verificar cache
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
        
        # Mostrar detalles del repositorio
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
        
        await message.edit_text(details_text, reply_markup=keyboard)
        await callback_query.answer(f"Seleccionado: {repo['name']}")
    
    elif data.startswith("back_"):
        # Volver a resultados de búsqueda
        search_id = data.split("_")[1]
        
        if search_id not in search_cache:
            await callback_query.answer("❌ La búsqueda ha expirado")
            return
        
        search_data = search_cache[search_id]
        results = search_data["results"]
        
        # Recrear botones
        keyboard_buttons = []
        for i, repo in enumerate(results["repos"], 1):
            callback_data = f"select_{search_id}_{i-1}"
            button_text = f"{i}. {repo['name'][:15]}"
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Botones de navegación
        nav_buttons = []
        if results["page"] > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"prev_{search_id}_{results['page']}"))
        
        if results["total_count"] > results["page"] * 5:
            nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"next_{search_id}_{results['page']}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.append([InlineKeyboardButton("🔄 Nueva búsqueda", callback_data="search")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await message.edit_text(
            format_repo_search_results(results),
            reply_markup=keyboard
        )
        await callback_query.answer("Volviendo a resultados...")
    
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
                       f"📊 Tamaño: {file_size:.1f}MB\n\n"
                       f"✅ Descargado a través de @{client.me.username}"
            )
            await processing_msg.delete()

        await callback_query.answer("✅ Descarga completada")
    
    elif data == "quick_download":
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
    
    elif data.startswith("search_similar_"):
        # Buscar repositorios similares
        repo_url = data[15:]  # Quitar "search_similar_"
        username, repo_name = get_repo_info_from_url(repo_url)
        
        if repo_name:
            # Buscar por nombre de repositorio
            await callback_query.message.reply_text(f"🔍 Buscando repositorios similares a `{repo_name}`...")
            await search_command(client, message)
            await callback_query.answer(f"Buscando: {repo_name}")
        else:
            await callback_query.answer("❌ No se pudo extraer nombre del repositorio")

@app.on_message(filters.command("info"))
async def info_command(client: Client, message: Message):
    info_text = f"""
🤖 **GitHub Downloader Bot v2.0**
    
**Desarrollador:** Tu nombre
**Username:** @{client.me.username}
**ID:** {client.me.id}
    
**✨ Nuevas características:**
• 🔍 **Sistema de búsqueda** de repositorios
• 📊 Estadísticas en tiempo real
• 🔄 Navegación por páginas
• 📋 Vista detallada de repos
    
**Características:**
• Descarga repositorios públicos de GitHub
• Envía como archivo ZIP
• Detecta URLs automáticamente
• Interfaz con botones
• API de GitHub integrada
    
**Límites:** 
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
        [InlineKeyboardButton("🌐 GitHub API Docs", url="https://docs.github.com/en/rest")]
    ])

    await message.reply_text(info_text, reply_markup=keyboard)

@app.on_message(filters.command("clear_cache"))
async def clear_cache_command(client: Client, message: Message):
    """Comando para limpiar la caché de búsqueda"""
    global search_cache
    count = len(search_cache)
    search_cache.clear()
    await message.reply_text(f"✅ Caché limpiada. Se eliminaron {count} búsquedas.")

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

# Limpiar caché de búsqueda periódicamente
async def cleanup_search_cache():
    """Limpiar caché de búsqueda cada 30 minutos"""
    while True:
        await asyncio.sleep(1800)  # 30 minutos
        try:
            global search_cache
            old_size = len(search_cache)
            # Mantener solo las búsquedas de los últimos 30 minutos
            # (En una implementación real, agregarías timestamps a cada búsqueda)
            search_cache.clear()
            print(f"🗑️ Caché de búsqueda limpiada: {old_size} entradas")
        except Exception as e:
            print(f"Error limpiando caché: {e}")

# Iniciar limpieza automática
@app.on_raw_update()
async def on_start(client, update):
    if not hasattr(on_start, "started"):
        on_start.started = True
        asyncio.create_task(cleanup_temp_files())
        asyncio.create_task(cleanup_search_cache())
        print("🤖 Bot GitHub Downloader con Búsqueda iniciado!")

print("🚀 Iniciando GitHub Downloader Bot con Sistema de Búsqueda...")
app.run()