from pyrogram import Client, filters

#Conectar bot con el cliente
app = Client(
"bot",
api_id=14681595, #Ingresa tu api_id
api_hash="a86730aab5c59953c424abb4396d32d5", #Ingresa tu api_hash
bot_token="8138537409:AAHGgzcTdoKEPQlMhbfjAVJuWkX8-M7s_wo") #Ingresa el token de tu bot
 
@app.on_message()
def commands(client, message):
    text = message.text
    username = message.from_user.username

    if '/start' in text:
        msg_start = f'🔰Bienvenido {username}'
        message.reply(msg_start)
        
print('👾Bot Online👾')
app.run()