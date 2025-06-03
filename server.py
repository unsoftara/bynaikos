import asyncio
import logging
import json
import os
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory
import bcrypt
import random
import string
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.messages import GetHistoryRequest, DeleteHistoryRequest
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.tl.types import KeyboardButtonCallback
from telethon.sessions import StringSession
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

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

# Функция для отправки запроса к Google каждые 10 секунд
def send_google_request():
    try:
        response = requests.get('https://www.google.com/')
        logger.info(f"Sent request to Google, status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending request to Google: {e}")
    # Планируем следующий запрос через 10 секунд
    threading.Timer(10.0, send_google_request).start()

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
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)['users']
    except Exception as e:
        logger.error(f"Error reading users file: {e}")
        return []

def write_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump({'users': users}, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing users file: {e}")

def read_agent_keys():
    try:
        with open(AGENT_KEYS_FILE, 'r') as f:
            return json.load(f)['keys']
    except Exception as e:
        logger.error(f"Error reading agent keys file: {e}")
        return []

def write_agent_keys(keys):
    try:
        with open(AGENT_KEYS_FILE, 'w') as f:
            json.dump({'keys': keys}, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing agent keys file: {e}")

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

        formatted_data = ["METADATA EXTRACTION RESULTS", "├ Date: 09:13 PM +04, June 03, 2025"]
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

# Telethon функции
async def get_n_latest_bot_messages(client, bot_username, count=3):
    """Получение последних сообщений от бота."""
    try:
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
    except Exception as e:
        logger.error(f"Error getting bot messages: {e}")
        return []

async def wait_for_specific_response(client, bot_username, keyword, timeout=15):
    """Ожидание сообщения с определённым ключевым словом."""
    logger.info(f"Waiting for message containing: {keyword}")
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        history = await client(GetHistoryRequest(
            peer=bot_username,
            limit=1,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        if not hasattr(history, 'messages') or not history.messages:
            await asyncio.sleep(1)
            continue
        message = history.messages[0]
        message_text = message.message or ""
        logger.info(f"Received message: {message_text[:100]}...")
        if keyword in message_text:
            logger.info("Received expected message")
            return message
        await asyncio.sleep(1)
    logger.warning("Timeout: expected message not received")
    return None

async def find_and_click_button(client, bot_username, button_position=3, timeout=15, retries=1):
    """Поиск и нажатие на кнопку по её позиции."""
    logger.info(f"Searching for button at position {button_position + 1} (index {button_position})")
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        history = await client(GetHistoryRequest(
            peer=bot_username,
            limit=2,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0
        ))
        if not hasattr(history, 'messages') or not history.messages:
            logger.info("No messages found in history.")
            await asyncio.sleep(1)
            continue

        for msg in history.messages:
            logger.info(f"Message ID {msg.id}: {msg.message[:100] if msg.message else 'No text'}...")

        message = history.messages[0]
        if hasattr(message, 'reply_markup') and message.reply_markup:
            buttons = [button for row in message.reply_markup.rows for button in row.buttons]
            logger.info(f"Found {len(buttons)} buttons: {[button.text for button in buttons]}")
            if len(buttons) > button_position:
                target_button = buttons[button_position]
                logger.info(f"Selected button: '{target_button.text}' at position {button_position + 1}")
                if isinstance(target_button, KeyboardButtonCallback):
                    for attempt in range(retries):
                        try:
                            await client(GetBotCallbackAnswerRequest(
                                peer=bot_username,
                                msg_id=message.id,
                                data=target_button.data
                            ))
                            logger.info("Callback query sent successfully.")
                            return True
                        except Exception as e:
                            logger.error(f"Attempt {attempt + 1}/{retries} - Error sending callback query: {e}")
                            if attempt < retries - 1:
                                logger.info("Retrying after 2 seconds...")
                                await asyncio.sleep(2)
                    logger.warning("Failed to send callback query after all retries.")
                    return False
                else:
                    logger.info("Button is not a callback button.")
                    return False
            else:
                logger.info(f"Not enough buttons: found {len(buttons)}, required {button_position + 1}")
        else:
            logger.info("No reply markup found in message.")
        await asyncio.sleep(1)
    logger.warning(f"Timeout: button at position {button_position + 1} not found within {timeout} seconds.")
    return False

async def send_phone_number(phone_number: str):
    """Отправка номера телефона боту и получение ответа."""
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

async def send_username(username: str):
    """Отправка username боту, нажатие на четвёртую кнопку и получение ответа."""
    try:
        await client.start()
        logger.info("Telethon client started")

        try:
            await client(DeleteHistoryRequest(
                peer=TARGET_BOT,
                max_id=0,
                just_clear=True,
                revoke=True
            ))
            logger.info(f"Chat history cleared with {TARGET_BOT}")
        except Exception as e:
            logger.error(f"Error clearing chat history: {e}")

        await client.send_message(TARGET_BOT, "/start")
        await asyncio.sleep(1)
        await client.send_message(TARGET_BOT, username)
        logger.info(f"Sent username {username} to {TARGET_BOT}")

        if await wait_for_specific_response(client, TARGET_BOT, "🔍 Обнаружен логин", timeout=20):
            if await find_and_click_button(client, TARGET_BOT, button_position=3, timeout=20, retries=1):
                logger.info("Waiting for bot response after button press...")
                await asyncio.sleep(15)
                messages = []
                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < 20:
                    messages = await get_n_latest_bot_messages(client, TARGET_BOT, count=5)
                    if messages and len(messages) >= 1:
                        response = messages[0].message
                        if "Телефон" in response or "История изменения имени" in response or "ID:" in response:
                            logger.info(f"Response from {TARGET_BOT}: {response}")
                            return {"status": "success", "result": response}
                    await asyncio.sleep(2)
                else:
                    logger.warning(f"No data response from {TARGET_BOT} within 20 seconds")
                    return {"status": "error", "message": f"No data response from {TARGET_BOT} within 20 seconds"}
            else:
                logger.warning("Failed to find or click the fourth button")
                messages = await get_n_latest_bot_messages(client, TARGET_BOT, count=5)
                for msg in messages:
                    logger.info(f"Fallback message: {msg.message[:100] if msg.message else 'No text'}...")
                if messages and len(messages) >= 1 and ("Телефон" in messages[0].message or "История изменения имени" in messages[0].message or "ID:" in messages[0].message):
                    logger.info(f"Response from {TARGET_BOT}: {messages[0].message}")
                    return {"status": "success", "result": messages[0].message}
                else:
                    logger.warning(f"No expected response from {TARGET_BOT}")
                    return {"status": "error", "message": f"No expected response from {TARGET_BOT}"}
        else:
            logger.warning(f"Expected '🔍 Обнаружен логин' message not received from {TARGET_BOT}")
            return {"status": "error", "message": f"Expected '🔍 Обнаружен логин' message not received"}
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
        logger.error(f"Error: {e}", exc_info=True)
        return {"status": "error", "message": f"Error: {str(e)}"}
    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info("Telethon client disconnected")

# Flask эндпоинты
@app.route('/')
def serve_index():
    """Сервировка HTML-файла."""
    return send_from_directory('.', 'global.html')

@app.route('/api/login', methods=['POST'])
def login():
    """Обработка логина пользователя."""
    data = request.get_json()
    badge_id = data.get('badgeId')
    password = data.get('password')

    if not badge_id or not password:
        return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID AND VERIFICATION CODE REQUIRED'}), 400

    users = read_users()
    for user in users:
        if user['badgeId'] == badge_id:
            if bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                return jsonify({'status': 'success', 'message': 'ACCESS GRANTED'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'ERROR: INVALID VERIFICATION CODE'}), 401
    return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID NOT FOUND'}), 404

@app.route('/api/verify-agent-key', methods=['POST'])
def verify_agent_key():
    """Проверка агентского ключа."""
    data = request.get_json()
    agent_key = data.get('agentKey')

    if not agent_key:
        return jsonify({'status': 'error', 'message': 'ERROR: AGENT KEY REQUIRED'}), 400

    agent_keys = read_agent_keys()
    for key in agent_keys:
        if key['key'] == agent_key and not key.get('used', False):
            key['used'] = True
            write_agent_keys(agent_keys)
            return jsonify({'status': 'success', 'message': 'AGENT KEY VERIFIED'}), 200
    return jsonify({'status': 'error', 'message': 'ERROR: INVALID OR USED AGENT KEY'}), 400

@app.route('/api/register', methods=['POST'])
def register():
    """Регистрация нового пользователя."""
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
    valid_key = False
    for key in agent_keys:
        if key['key'] == agent_key and key.get('used', False):
            valid_key = True
            break
    if not valid_key:
        return jsonify({'status': 'error', 'message': 'ERROR: INVALID OR UNVERIFIED AGENT KEY'}), 400

    users = read_users()
    for user in users:
        if user['badgeId'] == badge_id:
            return jsonify({'status': 'error', 'message': 'ERROR: BADGE ID ALREADY EXISTS'}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = {
        'badgeId': badge_id,
        'password': hashed_password,
        'features': []
    }
    users.append(new_user)
    write_users(users)
    return jsonify({'status': 'success', 'message': 'REGISTRATION SUCCESSFUL'}), 200

@app.route('/api/generate-agent-key', methods=['POST'])
def generate_agent_key():
    """Добавление нового ключа для пользователя."""
    data = request.get_json()
    new_key = data.get('key')
    badge_id = data.get('badgeId')

    if not new_key or not badge_id:
        return jsonify({'status': 'error', 'message': 'ERROR: Key and Badge ID required'}), 400

    users = read_users()
    user_exists = False
    for user in users:
        if user['badgeId'] == badge_id:
            user_exists = True
            if new_key == 'metadata_key':
                if 'metadata' not in user['features']:
                    user['features'].append('metadata')
                    write_users(users)
                    return jsonify({'status': 'success', 'message': 'Metadata feature unlocked successfully'}), 200
                else:
                    return jsonify({'status': 'error', 'message': 'Metadata feature already unlocked'}), 400
            else:
                return jsonify({'status': 'error', 'message': 'Invalid key'}), 400
    if not user_exists:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

@app.route('/api/get-user-features', methods=['POST'])
def get_user_features():
    """Получение доступных функций пользователя."""
    data = request.get_json()
    badge_id = data.get('badgeId')

    if not badge_id:
        return jsonify({'status': 'error', 'message': 'ERROR: Badge ID required'}), 400

    users = read_users()
    for user in users:
        if user['badgeId'] == badge_id:
            return jsonify({'status': 'success', 'features': user.get('features', [])}), 200
    return jsonify({'status': 'error', 'message': 'ERROR: User not found'}), 404

@app.route('/api/phone-lookup', methods=['POST'])
def phone_lookup():
    """Обработка запроса на поиск по номеру телефона."""
    data = request.get_json()
    phone_number = data.get('phoneNumber')

    if not phone_number:
        return jsonify({'status': 'error', 'message': 'ERROR: Phone number required'}), 400

    # Запуск асинхронной функции в синхронном контексте
    result = loop.run_until_complete(send_phone_number(phone_number))
    return jsonify(result), 200 if result['status'] == 'success' else 400

@app.route('/api/username-lookup', methods=['POST'])
def username_lookup():
    """Обработка запроса на поиск по имени пользователя Telegram."""
    data = request.get_json()
    username = data.get('username')

    if not username:
        return jsonify({'status': 'error', 'message': 'ERROR: Username required'}), 400

    # Запуск асинхронной функции в синхронном контексте
    result = loop.run_until_complete(send_username(username))
    return jsonify(result), 200 if result['status'] == 'success' else 400

@app.route('/api/extract-metadata', methods=['POST'])
def extract_metadata():
    """Извлечение метаданных из изображения."""
    if 'image' not in request.files or 'badgeId' not in request.form:
        return jsonify({'status': 'error', 'message': 'ERROR: Image and Badge ID required'}), 400

    image_file = request.files['image']
    badge_id = request.form['badgeId']

    users = read_users()
    user_has_feature = False
    for user in users:
        if user['badgeId'] == badge_id and 'metadata' in user.get('features', []):
            user_has_feature = True
            break
    if not user_has_feature:
        return jsonify({'status': 'error', 'message': 'ERROR: Metadata feature not unlocked or user not found'}), 403

    if not image_file.filename.lower().endswith(('.jpg', '.jpeg')):
        return jsonify({'status': 'error', 'message': 'ERROR: Only JPEG/JPG allowed'}), 400

    result = get_exif_data(image_file)
    return jsonify(result), 200 if result['status'] == 'success' else 400

# Запуск сервера и фонового запроса к Google
if __name__ == '__main__':
    initialize_users_file()
    initialize_keys_file()
    # Запускаем фоновую задачу для отправки запросов к Google
    send_google_request()
    app.run(debug=True, host='0.0.0.0', port=5000)
