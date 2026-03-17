import os
import threading
import asyncio
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Importiere die AION-Chat-Funktion. 
# Annahme: aion.py wird so angepasst, dass eine Funktion `run_aion_turn` existiert.
try:
    from aion import run_aion_turn 
except ImportError:
    # Fallback, falls die Funktion noch nicht existiert
    def run_aion_turn(user_input: str):
        return f"AION (simuliert): '{user_input}' wurde empfangen, aber die Kernlogik ist nicht verbunden."

TELEGRAM_TOKEN_PATH = os.path.expanduser('~/.aion_telegram_token')
CHAT_ID_PATH = os.path.expanduser('~/.aion_telegram_chatid')

chat_id = None

def load_token_and_chatid():
    global chat_id
    token = ''
    if os.path.isfile(TELEGRAM_TOKEN_PATH):
        token = open(TELEGRAM_TOKEN_PATH).read().strip()
    if os.path.isfile(CHAT_ID_PATH):
        chat_id = open(CHAT_ID_PATH).read().strip()
    return token

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_id
    chat_id = update.effective_chat.id
    with open(CHAT_ID_PATH, 'w') as f:
        f.write(str(chat_id))
    await update.message.reply_text('AION Telegram-Bot aktiviert und mit Kernlogik verbunden!')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_id
    chat_id = update.effective_chat.id
    with open(CHAT_ID_PATH, 'w') as f:
        f.write(str(chat_id))
    
    user_text = update.message.text
    
    # Rufe die AION-Kernlogik auf
    aion_response = await asyncio.to_thread(run_aion_turn, user_text)
    
    # Sende die Antwort von AION zurück an den Nutzer
    await update.message.reply_text(aion_response)

def telegram_loop():
    token = load_token_and_chatid()
    if not token:
        print('Telegram-Token fehlt!')
        return
        
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Telegram Bot Polling gestartet...")
    app.run_polling()

def start_telegram_bot():
    # Starte den Bot in einem separaten Thread, um die Hauptanwendung nicht zu blockieren
    t = threading.Thread(target=telegram_loop, daemon=True)
    t.start()

def send_telegram_message(message: str):
    token = load_token_and_chatid()
    if not token or not chat_id:
        return {'ok': False, 'error': 'Token oder Chat-ID fehlt'}
    try:
        # Synchrone Ausführung in einem Thread, um den Haupt-Event-Loop nicht zu blockieren
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot = Bot(token)
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
        loop.close()
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def register(api):
    # Diese Funktion wird von AION aufgerufen, um das Plugin zu registrieren
    api.register_tool(
        'send_telegram_message',
        'Sendet eine Nachricht an die gespeicherte Telegram-Chat-ID.',
        lambda params: send_telegram_message(params.get('message', '')), 
        {'type': 'object', 'properties': {'message': {'type': 'string'}}, 'required': ['message']}
    )
    start_telegram_bot()