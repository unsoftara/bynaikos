import asyncio
import logging
import json
import os
from flask import Flask, request, jsonify, send_from_directory
import bcrypt
import random
import string
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.messages import GetHistoryRequest, DeleteHistoryRequest
from telethon.sessions import StringSession
import threading

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bini_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger('telethon').setLevel(logging.DEBUG)

# Конфигурация
API_ID = "27683579"
API_HASH = "a1d0fc7d0c9a41ff5e0ae6a6ed8e2dbb"
SESSION_STRING = "1ApWapzMBuyfIDoUMXoKtwxtY3P_OWmrt6xjAJv2fjWJmvQS8UZ06mrhvfJs3FtJibswJUTNmexVbV-pzsPsrcdkIEYYLtS_uJ3t-WOfYkcEOz_dh8Tpw6-y64jRtlJUm-x_X_wzAnUgkpd-aPblaD67Z09gNsp6amAEjUL144ShzkiBqs0LVvmdkAq06ZbDM4aAJMmRFGeadC08HlKOu1ht21NyvpjwcQYdg6v4D2THyhUlGO0EEMbx78UWG7mtHDQQ1hG7BS16gehRsTNurDjZ3sSf6di1CNeLAKK9VTMhWLQjwWCpJjof97PcDwHxh6YCPgN1X8uGITXOqzncEiAkv_t-zr18="
TARGET_BOT = "bini228777_bot"

# Инициализация Flask
app = Flask(__name__, static_folder='.', static_url_path='')
USERS_FILE = 'users.json'
AGENT_KEYS_FILE = 'agent_keys.json'

# Создаём событийный цикл для Telethon
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Инициализация клиента Telethon
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# Функции для работы с файлами
def initialize_users_file():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({'users': []}, f, indent=2)

def initialize_keys_file():
    if not os.path.exists(AGENT_KEYS_FILE):
        with open(AGENT_KEYS_FILE, 'w') as f:
            json.dump({'keys': []}, f, indent=2)

def read_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)['users']

def write_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump({'users': users}, f, indent=2)

def read_agent_keys():
    with open(AGENT_KEYS_FILE, 'r') as f:
        return json.load(f)['keys']

def write_agent_keys(keys):
    with open(AGENT_KEYS_FILE, 'w') as f:
        json.dump({'keys': keys}, f, indent=2)

def generate_key(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# Функции Telethon
async def get_n_latest_bot_messages(client, bot_username, count=2):
    logger.info(f"Fetching {count} latest messages from {bot_username}")
    history = await client(GetHistoryRequest(
        peer=bot_username,
        limit=count,
        offset_date=None,
        offset_id=0,
        max_id=0,
        min_id=0,
        add_offset=0,
        hash=0
    ))
    if not hasattr(history, 'messages') or not history.messages:
        logger.warning(f"No messages found in history for {bot_username}")
        return []
    for msg in history.messages:
        logger.info(f"Message: {msg.message[:100] if msg.message else 'No text'}...")
    return history.messages

async def send_phone_number(phone_number: str):
    try:
        logger.info(f"Starting phone lookup for: {phone_number}")
        await client.start()
        logger.info("Telethon client started successfully")

        bot_entity = await client.get_entity(TARGET_BOT)
        logger.info(f"Bot entity retrieved: {bot_entity.username}")

        await client(DeleteHistoryRequest(
            peer=TARGET_BOT,
            max_id=0,
            just_clear=True,
            revoke=True
        ))
        logger.info(f"Chat history cleared with {TARGET_BOT}")

        logger.info(f"Sending '/start' to {TARGET_BOT}")
        await client.send_message(TARGET_BOT, "/start")
        logger.info(f"Sent '/start' to {TARGET_BOT}")

        if not phone_number.startswith("+") or len(phone_number) < 12:
            logger.error("Invalid phone number format")
            return {"status": "error", "message": "Invalid phone number format. Must be like +7XXXXXXXXXX"}

        logger.info(f"Sending phone number {phone_number} to {TARGET_BOT}")
        await client.send_message(TARGET_BOT, phone_number)
        logger.info(f"Phone number {phone_number} sent to {TARGET_BOT}")

        await asyncio.sleep(15)
        messages = await get_n_latest_bot_messages(client, TARGET_BOT, count=5)
        if messages and len(messages) >= 1:
            response = messages[0].message or "No response"
            fio = "Not found"
            for line in response.split('\n'):
                if line.startswith('├ ФИО: '):
                    fio = line.replace('├ ФИО: ', '').strip()
                    break
            return {"status": "success", "fio": fio}
        else:
            logger.warning(f"No response or not enough messages from {TARGET_BOT}")
            return {"status": "error", "message": f"No response from {TARGET_BOT}"}

    except FloodWaitError as e:
        logger.error(f"Flood wait error: wait for {e.seconds} seconds")
        return {"status": "error", "message": f"Too many attempts. Wait {e.seconds} seconds"}
    except SessionPasswordNeededError:
        logger.error("Two-factor authentication required")
        return {"status": "error", "message": "Two-factor authentication required"}
    except PhoneCodeInvalidError:
        logger.error("Invalid authentication code")
        return {"status": "error", "message": "Invalid authentication code"}
    except Exception as e:
        logger.error(f"Error during phone lookup: {e}", exc_info=True)
        return {"status": "error", "message": f"Error: {str(e)}"}
    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info("Telethon client disconnected")

# Flask эндпоинты
@app.route('/')
def serve_index():
    return send_from_directory('.', 'global.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    badge_id = data.get('badgeId')
    password = data.get('password')

    if not badge_id or not password:
        return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID AND VERIFICATION CODE REQUIRED'}), 400

    users = read_users()
    for user in users:
        if user['badgeId'] == badge_id:
            if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                return jsonify({'status': 'success', 'message': 'ACCESS GRANTED. WELCOME, AGENT.'})
            else:
                return jsonify({'status': 'error', 'message': 'ACCESS DENIED: INVALID CREDENTIALS'}), 401
    return jsonify({'status': 'error', 'message': 'ACCESS DENIED: INVALID CREDENTIALS'}), 401

@app.route('/api/verify-agent-key', methods=['POST'])
def verify_agent_key():
    data = request.get_json()
    agent_key = data.get('agentKey')

    if not agent_key:
        return jsonify({'status': 'error', 'message': 'ERROR: AGENT KEY REQUIRED'}), 400

    agent_keys = read_agent_keys()
    if agent_key in agent_keys:
        return jsonify({'status': 'success', 'message': 'AGENT KEY VERIFIED. PROCEED TO REGISTRATION.'})
    else:
        return jsonify({'status': 'error', 'message': 'INVALID AGENT KEY. ACCESS DENIED.'}), 401

@app.route('/api/generate-agent-key', methods=['POST'])
def generate_agent_key():
    initialize_keys_file()
    agent_keys = read_agent_keys()
    new_key = generate_key()
    while new_key in agent_keys:
        new_key = generate_key()
    agent_keys.append(new_key)
    write_agent_keys(agent_keys)
    return jsonify({'status': 'success', 'message': 'AGENT KEY GENERATED SUCCESSFULLY.', 'key': new_key})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    badge_id = data.get('badgeId')
    password = data.get('password')
    confirm_password = data.get('confirmPassword')
    agent_key = data.get('agentKey')

    if not badge_id or not password or not confirm_password or not agent_key:
        return jsonify({'status': 'error', 'message': 'ERROR: ALL FIELDS ARE REQUIRED'}), 400

    if password != confirm_password:
        return jsonify({'status': 'error', 'message': 'ERROR: VERIFICATION CODES DO NOT MATCH'}), 400

    agent_keys = read_agent_keys()
    if agent_key not in agent_keys:
        return jsonify({'status': 'error', 'message': 'INVALID AGENT KEY. ACCESS DENIED.'}), 401

    users = read_users()
    if any(user['badgeId'] == badge_id for user in users):
        return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID ALREADY EXISTS'}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    users.append({'badgeId': badge_id, 'password': hashed_password, 'agentKey': agent_key})
    write_users(users)
    agent_keys.remove(agent_key)
    write_agent_keys(agent_keys)
    return jsonify({'status': 'success', 'message': 'REGISTRATION SUCCESSFUL!'})

@app.route('/api/phone-lookup', methods=['POST'])
def phone_lookup():
    data = request.get_json()
    phone_number = data.get('phoneNumber')
    logger.info(f"Received phone lookup request for: {phone_number}")
    if not phone_number:
        logger.error("Phone number not provided")
        return jsonify({'status': 'error', 'message': 'ERROR: PHONE NUMBER REQUIRED'}), 400

    # Запускаем асинхронную функцию в событийном цикле
    future = asyncio.run_coroutine_threadsafe(send_phone_number(phone_number), loop)
    result = future.result()  # Ждём результат
    logger.info(f"Phone lookup result: {result}")
    return jsonify(result)

# Запуск событийного цикла в отдельном потоке
def run_loop():
    loop.run_forever()

if __name__ == '__main__':
    initialize_users_file()
    initialize_keys_file()
    
    # Запускаем событийный цикл в отдельном потоке
    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()

    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
