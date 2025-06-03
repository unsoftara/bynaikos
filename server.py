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
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
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
API_ID = "25142891"
API_HASH = "80993bef31f6c8d9ed40d97589407c11"
SESSION_STRING = "1ApWapzMBu0Bepyw_xn-29h8anJZojALZTy4mLYK6rZGVk8UAEh6qr_L4blqeJ_82XObCcu8jBofOL9KZJg7j0l3oqcvkYDD7I5pC4jq87PzWLAPUqLA0hKdmX88TbBjaP-GXkIKUq20PR9W8c1aSfOs_OzywOsS955xie7SUUDS3VNmQekMDW3mr2wk2Ad8u7tnzndUS-4v2Cgjq_AWmjrpsd_Us3uOR_nTkqjYV8911LHAjyl9UleI8mBF8NWdJEir0YXE0h_yfchFyVDFP387vwTIq7kTxGU-dr8vY7SUp_vmCjnNXRgqEYmzgkn-sNVide5VqnhVHs9hS-dia32-jGq2TEWo="
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

# Функция для извлечения EXIF-данных
def get_exif_data(image_file):
    try:
        image = Image.open(image_file)
        exif_data_raw = image._getexif()
        if not exif_data_raw:
            return {"status": "error", "message": "Метаданные не найдены."}

        exif_data = {}
        for tag_id, value in exif_data_raw.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                gps_data = {}
                for t in value:
                    sub_tag = GPSTAGS.get(t, t)
                    gps_data[sub_tag] = value[t]
                exif_data["GPSInfo"] = gps_data
            else:
                exif_data[tag] = value

        formatted_data = ["METADATA EXTRACTION RESULTS", "├ Date: 12:50 PM +04, June 03, 2025"]
        for tag, value in exif_data.items():
            if tag == "GPSInfo":
                formatted_data.append("├ GPSInfo:")
                for sub_tag, sub_value in value.items():
                    formatted_data.append(f"│   └ {sub_tag}: {sub_value}")
            else:
                formatted_data.append(f"├ {tag}: {value}")
        formatted_data.append("└ Status: EXTRACTION COMPLETE")
        return {"status": "success", "data": "\n".join(formatted_data)}
    except Exception as e:
        logger.error(f"Error extracting EXIF data: {e}", exc_info=True)
        return {"status": "error", "message": f"ERROR: Failed to extract metadata - {str(e)}"}

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
    data = request.get_json()
    key = data.get('key')
    badge_id = data.get('badgeId')

    if not key:
        return jsonify({'status': 'error', 'message': 'ERROR: KEY REQUIRED'}), 400

    if key == 'metadata13':
        users = read_users()
        for user in users:
            if user['badgeId'] == badge_id:
                user.setdefault('features', [])
                if 'metadata' not in user['features']:
                    user['features'].append('metadata')
                    write_users(users)
                    return jsonify({'status': 'success', 'message': 'METADATA FEATURE UNLOCKED.'})
                return jsonify({'status': 'success', 'message': 'METADATA FEATURE ALREADY UNLOCKED.'})
        return jsonify({'status': 'error', 'message': 'ERROR: USER NOT FOUND'}), 404

    initialize_keys_file()
    agent_keys = read_agent_keys()
    if key in agent_keys:
        return jsonify({'status': 'error', 'message': 'ERROR: KEY ALREADY EXISTS'}), 400
    agent_keys.append(key)
    write_agent_keys(agent_keys)
    return jsonify({'status': 'success', 'message': 'AGENT KEY GENERATED SUCCESSFULLY.', 'key': key})

@app.route('/api/get-user-features', methods=['POST'])
def get_user_features():
    data = request.get_json()
    badge_id = data.get('badgeId')

    if not badge_id:
        return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID REQUIRED'}), 400

    users = read_users()
    for user in users:
        if user['badgeId'] == badge_id:
            features = user.get('features', [])
            return jsonify({'status': 'success', 'features': features})
    return jsonify({'status': 'error', 'message': 'ERROR: USER NOT FOUND'}), 404

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
    users.append({'badgeId': badge_id, 'password': hashed_password, 'agentKey': agent_key, 'features': []})
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

    future = asyncio.run_coroutine_threadsafe(send_phone_number(phone_number), loop)
    result = future.result()
    logger.info(f"Phone lookup result: {result}")
    return jsonify(result)

@app.route('/api/extract-metadata', methods=['POST'])
def extract_metadata():
    badge_id = request.form.get('badgeId')
    if not badge_id:
        return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID REQUIRED'}), 400

    users = read_users()
    user = next((u for u in users if u['badgeId'] == badge_id), None)
    if not user or 'metadata' not in user.get('features', []):
        return jsonify({'status': 'error', 'message': 'ERROR: METADATA FEATURE NOT UNLOCKED'}), 403

    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': 'ERROR: IMAGE FILE REQUIRED'}), 400

    image_file = request.files['image']
    if not image_file.filename.lower().endswith(('.jpg', '.jpeg')):
        return jsonify({'status': 'error', 'message': 'ERROR: ONLY JPEG/JPG FILES ARE SUPPORTED'}), 400

    try:
        result = get_exif_data(image_file)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in extract_metadata endpoint: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f"ERROR: SERVER ERROR - {str(e)}"}), 500

if __name__ == '__main__':
    initialize_users_file()
    initialize_keys_file()
    # Запуск Telethon в отдельном потоке
    def run_telethon():
        loop.run_forever()

    telethon_thread = threading.Thread(target=run_telethon, daemon=True)
    telethon_thread.start()

    # Запуск Flask
    app.run(host='0.0.0.0', port=5000, debug=True)
