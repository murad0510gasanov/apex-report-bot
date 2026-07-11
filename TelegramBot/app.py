# app.py — APEX REPORT (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)
import os
import sys
import json
import asyncio
import re
import random
import time
from datetime import datetime, timedelta
from aiohttp import web
import aiohttp

try:
    from telethon import TelegramClient, events, errors
    from telethon.tl.types import KeyboardButtonCallback
    from telethon.tl.functions.account import ReportPeerRequest
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.types import InputReportReasonSpam
    from telethon.errors import FloodWaitError, UsernameNotOccupiedError, ChannelPrivateError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# ===== ТВОИ ДАННЫЕ =====
API_ID = 21826549
API_HASH = 'c1a19f792cfd9e397200d16c7e448160'
BOT_TOKEN = '8870668741:AAHL2cO1BWoHau-bVmBLziMadDj94SnU7IA'
CHANNEL_ID = -1004489395750
SUBSCRIPTION_BOT_TOKEN = '8238807176:AAFBRezNnlRiJ3oE-D81aOQGJ8NvJzBGBiU'
DEVELOPER_LINK = 'https://t.me/cazlen'
BOT_NAME = 'APEX REPORT'
ADMIN_IDS = [8701448954]

# ===== ПУТИ =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
os.makedirs(SESSIONS_DIR, exist_ok=True)

AU_DIR = os.path.join(SESSIONS_DIR, 'au')
US_DIR = os.path.join(SESSIONS_DIR, 'us')
INTERNAL_DIR = os.path.join(SESSIONS_DIR, 'internal')

for d in [AU_DIR, US_DIR, INTERNAL_DIR]:
    os.makedirs(d, exist_ok=True)

LOG_FILE = os.path.join(BASE_DIR, 'bot_analytics.json')
SUBS_FILE = os.path.join(BASE_DIR, 'subscriptions.json')
REQUESTS_FILE = os.path.join(BASE_DIR, 'requests.json')

_subs_cache = {}
_subs_cache_time = 0
pending_requests = {}  # ГЛОБАЛЬНЫЙ СЛОВАРЬ ДЛЯ ЗАЯВОК

# ===== РАБОТА С ДАННЫМИ =====
def load_data():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"reports": [], "users": [], "notifications": []}

def save_data(data):
    for attempt in range(5):
        try:
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return
        except:
            time.sleep(0.5)
            continue

def load_subs():
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_subs(subs):
    with open(SUBS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subs, f, indent=2, ensure_ascii=False)

def load_requests():
    if os.path.exists(REQUESTS_FILE):
        try:
            with open(REQUESTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_requests(requests):
    with open(REQUESTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(requests, f, indent=2, ensure_ascii=False)

def has_subscription(user_id):
    global _subs_cache, _subs_cache_time
    if time.time() - _subs_cache_time > 30:
        _subs_cache = load_subs()
        _subs_cache_time = time.time()
    user_id_str = str(user_id)
    if user_id_str not in _subs_cache:
        return False
    expiry = _subs_cache[user_id_str].get('expiry')
    if not expiry:
        return False
    try:
        expiry_dt = datetime.fromisoformat(expiry)
        return expiry_dt > datetime.now()
    except:
        return False

def generate_phone():
    return f"+7{random.randint(1000000000, 9999999999)}"

# ===== ПОДКЛЮЧЕНИЕ =====
async def try_connect(session_path, timeout=20, retries=3):
    session_name = os.path.basename(session_path)
    for attempt in range(retries):
        client = None
        try:
            if attempt > 0:
                print(f"[{session_name}] ⏳ Повторная попытка {attempt+1}/{retries}...")
                await asyncio.sleep(2)
            client = TelegramClient(session_path, API_ID, API_HASH)
            await asyncio.wait_for(client.start(), timeout=timeout)
            await asyncio.wait_for(client.get_me(), timeout=timeout)
            print(f"[{session_name}] ✅ Подключена")
            return client
        except asyncio.TimeoutError:
            if client:
                await client.disconnect()
            print(f"[{session_name}] ⏰ Таймаут")
            if attempt == retries - 1:
                return None
        except FloodWaitError as e:
            if client:
                await client.disconnect()
            print(f"[{session_name}] ⏳ FloodWait {e.seconds} сек")
            await asyncio.sleep(min(e.seconds, 30))
            if attempt == retries - 1:
                return None
        except Exception as e:
            if client:
                await client.disconnect()
            print(f"[{session_name}] ❌ Ошибка: {str(e)[:50]}")
            if attempt == retries - 1:
                return None
    return None

def get_all_sessions():
    sessions = []
    if os.path.exists(SESSIONS_DIR):
        for root, dirs, files in os.walk(SESSIONS_DIR):
            for f in files:
                if f.endswith('.session'):
                    sessions.append(os.path.join(root, f))
    return sessions

async def get_live_session():
    all_sessions = get_all_sessions()
    if not all_sessions:
        return None
    for session_path in all_sessions:
        client = await try_connect(session_path, timeout=10, retries=1)
        if client:
            return client
    return None

# ===== AI-АНАЛИЗ ЧЕРЕЗ POLLINATIONS AI =====
async def analyze_with_ai(texts, target, single=False):
    if single:
        messages_text = texts[0] if texts else "Пустое сообщение"
        prompt = f"""Analyze this single message from Telegram and determine if it violates Telegram's Terms of Service.

Message: {messages_text}

Return JSON with:
- violation: type (drugs/spam/porn/violence/scam/personal/bullying) or null if none
- severity: high/medium/low or null
- explanation: short explanation in Russian

Format: {{"violation": "spam", "severity": "medium", "explanation": "Спам-сообщение..."}}"""
    else:
        messages_text = "\n".join(texts[:50])
        prompt = f"""Analyze these messages from a Telegram channel and determine if they violate Telegram's Terms of Service.

Channel: {target}
Messages:
{messages_text}

Return JSON with:
- violation: type (drugs/spam/porn/violence/scam/personal/bullying) or null if none
- severity: high/medium/low or null
- explanation: short explanation in Russian
- links: array of links to violating messages (if any)

Format:
{{
    "violation": "drugs",
    "severity": "high",
    "explanation": "Канал рекламирует продажу кокаина...",
    "links": ["https://t.me/test_channel/2", "https://t.me/test_channel/3"]
}}"""

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.pollinations.ai/v1/chat/completions"
            payload = {
                "model": "openai",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "stream": False
            }
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result_text = data['choices'][0]['message']['content']
                    if result_text.startswith('```json'):
                        result_text = result_text.replace('```json', '').replace('```', '').strip()
                    elif result_text.startswith('```'):
                        result_text = result_text.replace('```', '').strip()
                    try:
                        return json.loads(result_text)
                    except:
                        return {"error": "Ошибка парсинга JSON от AI", "raw": result_text}
                else:
                    return {"error": f"Ошибка AI: {resp.status}"}
    except Exception as e:
        return {"error": f"Ошибка AI: {str(e)[:100]}"}

# ===== ГЕНЕРАЦИЯ ТЕКСТА ЖАЛОБЫ =====
async def generate_complaint_text(target, violation, description, links):
    if not links:
        links = ["No specific links provided"]
    
    prompt = f"""Generate a short, formal complaint to Telegram moderators about a channel that violates Terms of Service.

Channel: {target}
Violation type: {violation}
User description: {description}
Links to violating messages:
{chr(10).join(links)}

Write a formal complaint without any urgent words. Use only English. Keep it concise (maximum 100 words)."""

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.pollinations.ai/v1/chat/completions"
            payload = {
                "model": "openai",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "stream": False
            }
            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    return f"I would like to report a Telegram channel involved in {violation}.\n\nChannel: {target}\n\n{description}\n\nReported messages:\n{chr(10).join(links)}\n\nPlease review this content and take appropriate action.\n\nThank you."
    except:
        return f"I would like to report a Telegram channel involved in {violation}.\n\nChannel: {target}\n\n{description}\n\nReported messages:\n{chr(10).join(links)}\n\nPlease review this content and take appropriate action.\n\nThank you."

# ===== ОПЕРАТОР =====
async def send_operator_report(user_id, username, edit_callback=None):
    try:
        client = await get_live_session()
        if not client:
            result = "❌ Нет живых сессий"
            if edit_callback:
                await edit_callback(result)
            return result

        username = username.replace('https://t.me/', '').replace('@', '')
        
        try:
            entity = await client.get_entity(f"@{username}")
        except UsernameNotOccupiedError:
            await client.disconnect()
            result = f"❌ Оператор @{username} не найден"
            if edit_callback:
                await edit_callback(result)
            return result
        except Exception as e:
            await client.disconnect()
            result = f"❌ Ошибка: {str(e)[:50]}"
            if edit_callback:
                await edit_callback(result)
            return result

        try:
            await client(ReportPeerRequest(
                peer=entity,
                reason=InputReportReasonSpam(),
                message="Spam and violation of Telegram Terms of Service"
            ))
            result = f"✅ Жалоба на @{username} отправлена"
            
            try:
                async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
                    channel = await temp_client.get_entity(CHANNEL_ID)
                    await temp_client.send_message(channel, f"✅ Оператор @{username} — жалоба отправлена")
            except:
                pass
                
        except FloodWaitError as e:
            result = f"⏳ FloodWait {e.seconds} сек"
        except Exception as e:
            result = f"❌ Ошибка: {str(e)[:50]}"
        finally:
            await client.disconnect()

    except Exception as e:
        result = f"❌ Ошибка: {str(e)[:50]}"

    if edit_callback:
        await edit_callback(result)
    return result

# ===== ТЕЛЕТОН =====
async def send_telethon_report(user_id, target, edit_callback=None):
    all_sessions = get_all_sessions()
    if not all_sessions:
        if edit_callback:
            await edit_callback("❌ Нет сессий")
        return "❌ Нет сессий"
    if not target:
        if edit_callback:
            await edit_callback("❌ Неверная ссылка")
        return "❌ Неверная ссылка"

    message_link_pattern = r'https://t\.me/([^/]+)/(\d+)'
    match = re.search(message_link_pattern, target)
    if match:
        chat_username = match.group(1)
        is_message = True
    else:
        is_message = False
        if 't.me/' in target:
            target = target.replace('https://t.me/', '')
            if '/' in target:
                target = target.split('/')[0]
        if not target.startswith('@'):
            target = '@' + target

    total = len(all_sessions)
    errors = 0
    success_count = 0

    print(f"\n📤 Telethon — отправка на {target}")
    print(f"📁 Всего сессий: {total}")

    async def send_one(session_path, index):
        nonlocal errors, success_count
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=20, retries=3)
        if not client:
            errors += 1
            print(f"[{session_name}] ❌ Не удалось подключиться")
            return

        try:
            if is_message:
                try:
                    chat = await client.get_entity(chat_username)
                    await client(ReportPeerRequest(peer=chat, reason=InputReportReasonSpam(), message=""))
                    success_count += 1
                    print(f"[{session_name}] ✅ Успешно")
                except UsernameNotOccupiedError:
                    errors += 1
                    print(f"[{session_name}] ❌ Канал не найден")
                except FloodWaitError as e:
                    errors += 1
                    print(f"[{session_name}] ⏳ FloodWait {e.seconds} сек")
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception as e:
                    errors += 1
                    print(f"[{session_name}] ❌ {str(e)[:50]}")
            else:
                try:
                    entity = await client.get_entity(target)
                    await client(ReportPeerRequest(peer=entity, reason=InputReportReasonSpam(), message=""))
                    success_count += 1
                    print(f"[{session_name}] ✅ Успешно")
                except UsernameNotOccupiedError:
                    errors += 1
                    print(f"[{session_name}] ❌ Цель не найдена")
                except FloodWaitError as e:
                    errors += 1
                    print(f"[{session_name}] ⏳ FloodWait {e.seconds} сек")
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception as e:
                    errors += 1
                    print(f"[{session_name}] ❌ {str(e)[:50]}")
        finally:
            await client.disconnect()

    tasks = [send_one(session_path, i+1) for i, session_path in enumerate(all_sessions)]
    await asyncio.gather(*tasks)

    print(f"\n📊 Результат: {success_count}/{total} успешно, {errors} ошибок")

    result = f"✅ Telethon — ОТПРАВЛЕНО ({success_count}/{total})"
    if errors > 0:
        result += f"\n⚠️ Ошибок: {errors}"

    try:
        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
            channel = await temp_client.get_entity(CHANNEL_ID)
            await temp_client.send_message(channel, f"✅ Telethon репорт на {target}\nУспешно: {success_count}/{total}\nОшибок: {errors}")
    except:
        pass

    if edit_callback:
        await edit_callback(result)
    return result

# ===== МИКС =====
async def send_mix_report(user_id, target, text, edit_callback=None):
    all_sessions = []
    if os.path.exists(AU_DIR):
        for f in os.listdir(AU_DIR):
            if f.endswith('.session'):
                all_sessions.append(os.path.join(AU_DIR, f))
    if os.path.exists(US_DIR):
        for f in os.listdir(US_DIR):
            if f.endswith('.session'):
                all_sessions.append(os.path.join(US_DIR, f))

    if not all_sessions:
        if edit_callback:
            await edit_callback("❌ Нет сессий для микса (AU + US)")
        return "❌ Нет сессий для микса"

    total = len(all_sessions)
    au_sessions = [s for s in all_sessions if 'au' in s]
    us_sessions = [s for s in all_sessions if 'us' in s]
    current = 0

    print(f"\n📤 Микс — отправка на {target}")
    print(f"📁 Сессий AU: {len(au_sessions)}, US: {len(us_sessions)}")

    for session_path in au_sessions:
        current += 1
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=15, retries=2)
        if not client:
            print(f"[AU] {session_name} ❌ Не удалось подключиться")
            continue
        try:
            print(f"[AU] {session_name} ⏳ Отправка... ({current}/{total})")
            await client.send_message('@AUReportBot', '/start')
            await asyncio.sleep(2)
            await client.send_message('@AUReportBot', target)
            await asyncio.sleep(2)
            async for msg in client.iter_messages('@AUReportBot', limit=5):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Other' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            await client.send_message('@AUReportBot', text)
            await asyncio.sleep(2)
            async for msg in client.iter_messages('@AUReportBot', limit=5):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Proceed without' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            async for msg in client.iter_messages('@AUReportBot', limit=3):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Confirm' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            print(f"[AU] {session_name} ✅ Отправлено")
        except Exception as e:
            print(f"[AU] {session_name} ❌ {str(e)[:50]}")
        finally:
            await client.disconnect()

    for session_path in us_sessions:
        current += 1
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=15, retries=2)
        if not client:
            print(f"[US] {session_name} ❌ Не удалось подключиться")
            continue
        try:
            print(f"[US] {session_name} ⏳ Отправка... ({current}/{total})")
            await client.send_message('@TIDABot', '/start')
            await asyncio.sleep(2)
            await client.send_message('@TIDABot', target)
            await asyncio.sleep(2)
            async for msg in client.iter_messages('@TIDABot', limit=5):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Non-consensual' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            await client.send_message('@TIDABot', text)
            await asyncio.sleep(2)
            async for msg in client.iter_messages('@TIDABot', limit=5):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Proceed without' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            async for msg in client.iter_messages('@TIDABot', limit=3):
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text and 'Confirm' in btn.text:
                                await btn.click()
                                await asyncio.sleep(1)
                                break
                        else:
                            continue
                        break
                    break
            print(f"[US] {session_name} ✅ Отправлено")
        except Exception as e:
            print(f"[US] {session_name} ❌ {str(e)[:50]}")
        finally:
            await client.disconnect()

    print(f"\n📊 Микс — отправлено {current}/{total} сессий")

    try:
        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
            channel = await temp_client.get_entity(CHANNEL_ID)
            await temp_client.send_message(channel, f"✅ Микс-жалоба отправлена на {target}")
    except:
        pass

    if edit_callback:
        await edit_callback("✅ Микс-жалоба отправлена!")
    return "✅ Микс-жалоба отправлена!"

# ===== AI-АНАЛИЗ (ИСПРАВЛЕННЫЙ) =====
class AIAnalyzer:
    def __init__(self):
        self.last_result = None
        self.keywords = {
            "drugs": ["наркотик", "кокаин", "героин", "спайс", "соль", "шишки", "закладка", "продажа", "продам", "drugs", "cocaine", "heroin"],
            "personal": ["паспорт", "фио", "адрес", "телефон", "личные данные", "passport", "address", "phone"],
            "porn": ["порно", "секс", "18+", "голый", "porn", "sex", "nude"],
            "violence": ["насилие", "убить", "оружие", "угроза", "violence", "kill", "weapon"],
            "spam": ["спам", "реклама", "подпишись", "spam", "ad", "promo"],
            "scam": ["лохотрон", "пирамида", "инвестиции", "scam", "fraud"],
            "bullying": ["буллинг", "травля", "оскорбление", "bullying", "harassment"]
        }

    def fallback_analyze(self, text):
        text_lower = text.lower()
        results = {}
        for category, words in self.keywords.items():
            count = 0
            for word in words:
                if word in text_lower:
                    count += 1
            results[category] = min(count * 25, 100)
        return results

    def get_violation(self, results):
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        for cat, percent in sorted_results:
            if percent >= 30:
                return cat, percent
        return None, 0

    async def analyze_target(self, target, user_id, bot_instance):
        client = await get_live_session()
        if not client:
            return None, "❌ Нет живых сессий"

        messages = []
        target_type = "unknown"
        chat_username = ""
        message_ids = []

        try:
            if 't.me/joinchat' in target or 't.me/+' in target:
                try:
                    await client.join_channel(target)
                    print(f"[JOIN] Присоединился по ссылке")
                    await asyncio.sleep(3)
                except Exception as e:
                    await client.disconnect()
                    return None, f"❌ Не удалось присоединиться по ссылке: {str(e)[:50]}"

            if 't.me/' in target:
                if 'joinchat' not in target and '+' not in target:
                    chat_username = target.replace('https://t.me/', '').split('/')[0]
                    entity = await client.get_entity(f"@{chat_username}")
                    target_type = "канал"
                else:
                    entity = await client.get_entity(target)
                    chat_username = getattr(entity, 'username', 'unknown')
                    target_type = "канал"
            elif target.startswith('@'):
                chat_username = target.replace('@', '')
                entity = await client.get_entity(target)
                target_type = "бот" if entity.bot else "пользователь"
            else:
                await client.disconnect()
                return None, "❌ Неверная ссылка"

            try:
                await client(JoinChannelRequest(entity))
                print(f"[JOIN] Подписался на {chat_username}")
                await asyncio.sleep(3)
            except ChannelPrivateError:
                try:
                    await client.send_message(entity, "Заявка на вступление")
                    print(f"[JOIN] Отправлена заявка в {chat_username}")
                    pending_requests[user_id] = {
                        "target": target,
                        "entity": entity,
                        "chat_username": chat_username,
                        "user_id": user_id,
                        "bot_instance": bot_instance,
                        "status": "waiting",
                        "client_filename": client.session.filename
                    }
                    await client.disconnect()
                    return None, f"🔒 Канал {chat_username} закрытый. Отправлена заявка. Я уведомлю вас, когда заявку одобрят."
                except Exception as e:
                    await client.disconnect()
                    return None, f"❌ Ошибка при отправке заявки: {str(e)[:50]}"
            except Exception as e:
                try:
                    await client.send_message(entity, "Заявка на вступление")
                    print(f"[JOIN] Отправлена заявка в {chat_username}")
                    pending_requests[user_id] = {
                        "target": target,
                        "entity": entity,
                        "chat_username": chat_username,
                        "user_id": user_id,
                        "bot_instance": bot_instance,
                        "status": "waiting",
                        "client_filename": client.session.filename
                    }
                    await client.disconnect()
                    return None, f"🔒 Канал {chat_username} закрытый. Отправлена заявка. Я уведомлю вас, когда заявку одобрят."
                except:
                    await client.disconnect()
                    return None, f"❌ Не удалось подписаться или отправить заявку: {str(e)[:50]}"

            if target_type == "бот":
                try:
                    await client.send_message(entity, '/start')
                    await asyncio.sleep(2)
                except:
                    pass

            msgs = await client.get_messages(entity, limit=50)
            for m in msgs:
                if m and m.text:
                    messages.append(m.text)
                    message_ids.append(m.id)

        except Exception as e:
            await client.disconnect()
            return None, f"❌ Ошибка: {str(e)[:50]}"

        await client.disconnect()

        if not messages:
            return None, "❌ Нет сообщений"

        result = await analyze_with_ai(messages, target)
        
        if result.get("error"):
            print(f"[AI] Ошибка: {result['error']}, используем фолбэк")
            results = self.fallback_analyze(" ".join(messages))
            violation, percent = self.get_violation(results)
            if violation:
                result = {
                    "violation": violation,
                    "severity": "medium",
                    "explanation": f"Найдено нарушение типа {violation} по ключевым словам",
                    "links": []
                }
                if chat_username:
                    for idx, msg_id in enumerate(message_ids[:5]):
                        result["links"].append(f"https://t.me/{chat_username}/{msg_id}")
            else:
                result = {"violation": None, "severity": None, "explanation": "Нарушений не найдено.", "links": []}

        if result.get("violation") and not result.get("links") and chat_username:
            result["links"] = [f"https://t.me/{chat_username}/{msg_id}" for msg_id in message_ids[:5]]

        self.last_result = result

        if result.get("violation"):
            try:
                async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
                    channel = await temp_client.get_entity(CHANNEL_ID)
                    report_text = (
                        f"🔍 AI Анализ: {target}\n"
                        f"Тип: {target_type.upper()}\n"
                        f"⚠️ Нарушение: {result['violation'].upper()} ({result.get('severity', 'medium').upper()})\n"
                        f"📝 Объяснение: {result.get('explanation', '')}\n"
                        f"📊 Сообщений: {len(messages)}\n"
                    )
                    if result.get("links"):
                        report_text += f"🔗 Ссылки на нарушения:\n" + "\n".join(result["links"])
                    else:
                        report_text += "❌ Найдено нарушение!"
                    await temp_client.send_message(channel, report_text)
            except:
                pass

        return result, None

    async def check_pending_requests(self, bot_instance):
        while True:
            try:
                await asyncio.sleep(10)
                for user_id, req in list(pending_requests.items()):
                    if req.get("status") != "waiting":
                        continue
                    
                    client = await try_connect(req["client_filename"], timeout=10, retries=1)
                    if not client:
                        continue
                    
                    try:
                        msgs = await client.get_messages(req["entity"], limit=1)
                        if msgs:
                            req["status"] = "approved"
                            print(f"[JOIN] Заявка для {req['chat_username']} одобрена!")
                            
                            messages = []
                            message_ids = []
                            all_msgs = await client.get_messages(req["entity"], limit=50)
                            for m in all_msgs:
                                if m and m.text:
                                    messages.append(m.text)
                                    message_ids.append(m.id)
                            
                            if messages:
                                result = await analyze_with_ai(messages, req["target"])
                                if result.get("error"):
                                    results = self.fallback_analyze(" ".join(messages))
                                    violation, percent = self.get_violation(results)
                                    if violation:
                                        result = {
                                            "violation": violation,
                                            "severity": "medium",
                                            "explanation": f"Найдено нарушение типа {violation} по ключевым словам",
                                            "links": []
                                        }
                                        if req["chat_username"]:
                                            for idx, msg_id in enumerate(message_ids[:5]):
                                                result["links"].append(f"https://t.me/{req['chat_username']}/{msg_id}")
                                    else:
                                        result = {"violation": None, "severity": None, "explanation": "Нарушений не найдено.", "links": []}
                                
                                if result.get("violation") and not result.get("links") and req["chat_username"]:
                                    result["links"] = [f"https://t.me/{req['chat_username']}/{msg_id}" for msg_id in message_ids[:5]]
                                
                                if result.get("violation"):
                                    report = f"🔍 AI-АНАЛИЗ\n\nЦель: {req['target']}\nТип: КАНАЛ\nНарушение: {result['violation'].upper()} ({result.get('severity', 'medium').upper()})\nОбъяснение: {result.get('explanation', '')}\n"
                                    if result.get("links"):
                                        report += "\n🔗 Ссылки на нарушения:\n" + "\n".join(result["links"])
                                    
                                    buttons = [
                                        [KeyboardButtonCallback("🚀 Отправить жалобу", f"send_ai_report_{user_id}")],
                                        [KeyboardButtonCallback("🔙 Назад", "back_to_start")]
                                    ]
                                    try:
                                        await bot_instance.send_message(user_id, report, buttons=buttons)
                                    except:
                                        pass
                                else:
                                    try:
                                        await bot_instance.send_message(user_id, f"🔍 AI-АНАЛИЗ\n\nЦель: {req['target']}\n✅ Нарушений не найдено.")
                                    except:
                                        pass
                            
                            await client.disconnect()
                            pending_requests.pop(user_id, None)
                        else:
                            await client.disconnect()
                    except:
                        await client.disconnect()
            except:
                continue

    async def analyze_single_message(self, message_text, link):
        result = await analyze_with_ai([message_text], link, single=True)
        if result.get("error"):
            results = self.fallback_analyze(message_text)
            violation, percent = self.get_violation(results)
            if violation:
                result = {
                    "violation": violation,
                    "severity": "medium",
                    "explanation": f"Найдено нарушение типа {violation} по ключевым словам",
                    "links": [link]
                }
            else:
                result = {"violation": None, "severity": None, "explanation": "Нарушений не найдено.", "links": []}
        if result.get("violation") and not result.get("links"):
            result["links"] = [link]
        self.last_result = result
        return result

# ===== HTTP-СЕРВЕР ДЛЯ RENDER =====
async def health_check(request):
    return web.Response(text="I'm alive!")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=10000)
    await site.start()
    print("[HTTP] Сервер запущен на порту 10000")
    await asyncio.Event().wait()

# ===== БОТ ДЛЯ ПОДПИСОК =====
async def run_subscription_bot():
    try:
        print("[SUB-BOT] Запуск...")
        bot = TelegramClient('subscription_bot', API_ID, API_HASH)
        await bot.start(bot_token=SUBSCRIPTION_BOT_TOKEN)
        print("[SUB-BOT] Бот для подписок запущен")
        user_states = {}
        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            if event.sender_id not in ADMIN_IDS:
                await event.reply("⛔ Доступ запрещён")
                return
            await event.delete()
            buttons = [
                [KeyboardButtonCallback("📋 Список", b"sub_list")],
                [KeyboardButtonCallback("📥 Заявки", b"sub_requests")],
                [KeyboardButtonCallback("➕ Выдать", b"sub_give")],
                [KeyboardButtonCallback("🗑️ Удалить", b"sub_remove")]
            ]
            await event.reply("🔑 БОТ ПОДПИСОК", buttons=buttons)
        @bot.on(events.CallbackQuery)
        async def handle_sub_callbacks(event):
            if event.sender_id not in ADMIN_IDS:
                await event.answer("⛔ Доступ запрещён")
                return
            await event.answer()
            user_id = event.sender_id
            data = event.data.decode('utf-8')
            if data == "sub_list":
                subs = load_subs()
                if not subs:
                    await event.edit("📋 Нет подписчиков.")
                    return
                text = "📋 СПИСОК:\n\n"
                for uid, data in subs.items():
                    status = "✅" if has_subscription(int(uid)) else "❌"
                    text += f"{status} {uid} до {data.get('expiry', '—')[:10]}\n"
                await event.edit(text, buttons=[[KeyboardButtonCallback("🔙 Назад", b"sub_back")]])
                return
            if data == "sub_requests":
                reqs = load_requests()
                if not reqs:
                    await event.edit("📥 Нет заявок.")
                    return
                text = "📥 ЗАЯВКИ:\n\n"
                for r in reqs:
                    text += f"🆔 {r.get('user_id')} — {r.get('time')}\n"
                await event.edit(text, buttons=[[KeyboardButtonCallback("🔙 Назад", b"sub_back")]])
                return
            if data == "sub_give":
                user_states[user_id] = 'waiting_give'
                await event.edit("➕ ВЫДАТЬ\n\nОтправь: ID дни\nПример: 123456789 7",
                    buttons=[[KeyboardButtonCallback("🔙 Отмена", b"sub_back")]])
                return
            if data == "sub_remove":
                user_states[user_id] = 'waiting_remove'
                await event.edit("🗑️ УДАЛИТЬ\n\nОтправь ID\nПример: 123456789",
                    buttons=[[KeyboardButtonCallback("🔙 Отмена", b"sub_back")]])
                return
            if data == "sub_back":
                user_states.pop(user_id, None)
                buttons = [
                    [KeyboardButtonCallback("📋 Список", b"sub_list")],
                    [KeyboardButtonCallback("📥 Заявки", b"sub_requests")],
                    [KeyboardButtonCallback("➕ Выдать", b"sub_give")],
                    [KeyboardButtonCallback("🗑️ Удалить", b"sub_remove")]
                ]
                await event.edit("🔑 БОТ ПОДПИСОК", buttons=buttons)
                return
        @bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel_sub(event):
            if event.sender_id not in ADMIN_IDS:
                return
            user_states.pop(event.sender_id, None)
            await event.reply("❌ Отменено")
        @bot.on(events.NewMessage)
        async def handle_sub_messages(event):
            if event.sender_id not in ADMIN_IDS:
                return
            user_id = event.sender_id
            state = user_states.get(user_id)
            if not state:
                return
            await event.delete()
            text = event.message.text.strip()
            if state == 'waiting_give':
                parts = text.split()
                if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                    await event.reply("❌ Формат: ID дни")
                    return
                uid, days = parts[0], int(parts[1])
                subs = load_subs()
                expiry = datetime.now() + timedelta(days=days)
                subs[uid] = {'expiry': expiry.isoformat()}
                save_subs(subs)
                requests = load_requests()
                requests = [r for r in requests if r.get('user_id') != int(uid)]
                save_requests(requests)
                await event.reply(f"✅ Выдана {uid} на {days} дн.")
                user_states.pop(user_id, None)
            elif state == 'waiting_remove':
                if not text.isdigit():
                    await event.reply("❌ Введи ID")
                    return
                uid = text
                subs = load_subs()
                if uid in subs:
                    del subs[uid]
                    save_subs(subs)
                    await event.reply(f"✅ Удалена {uid}")
                else:
                    await event.reply(f"❌ {uid} не найден")
                user_states.pop(user_id, None)
        print("[SUB-BOT] Готов")
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"[SUB-BOT] Ошибка: {e}")

# ===== ГЛАВНЫЙ БОТ =====
async def main_bot():
    try:
        bot = TelegramClient('bot_session', API_ID, API_HASH)
        await bot.start(bot_token=BOT_TOKEN)
        print("Bot connected")
        user_states = {}
        user_data = {}
        active_messages = {}
        analyzer = AIAnalyzer()
        
        asyncio.create_task(analyzer.check_pending_requests(bot))
        
        async def update_message(event, text, buttons=None):
            user_id = event.sender_id
            try:
                if user_id in active_messages:
                    await active_messages[user_id].edit(text, buttons=buttons)
                else:
                    active_messages[user_id] = await event.reply(text, buttons=buttons)
            except:
                active_messages[user_id] = await event.reply(text, buttons=buttons)
        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.delete()
            user_id = event.sender_id
            data = load_data()
            if user_id not in data.get('users', []):
                data.setdefault('users', []).append(user_id)
                save_data(data)
            if has_subscription(user_id):
                buttons = [
                    [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                    [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")],
                    [KeyboardButtonCallback("📜 Моя история", b"history")]
                ]
                await update_message(event, f"📌 {BOT_NAME}", buttons)
            else:
                await update_message(event, f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}")
        @bot.on(events.CallbackQuery)
        async def handle_callbacks(event):
            await event.answer()
            user_id = event.sender_id
            data = event.data.decode('utf-8')
            try:
                await event.message.delete()
            except:
                pass
            async def upd(text, buttons=None):
                await update_message(event, text, buttons)
            if data == "main_menu":
                if not has_subscription(user_id):
                    await upd(f"🔒 ДОСТУП ОГРАНИЧЕН\n\nКупить: {DEVELOPER_LINK}", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                buttons = [
                    [KeyboardButtonCallback("📤 Микс", b"mix_menu")],
                    [KeyboardButtonCallback("⚡ Telethon", b"telethon_report")],
                    [KeyboardButtonCallback("🔍 AI-анализ", b"ai_analyze")],
                    [KeyboardButtonCallback("👤 Оператор", b"operator")],
                    [KeyboardButtonCallback("🔙 Назад", b"back_to_start")]
                ]
                await upd("📋 МЕНЮ", buttons)
                return
            if data == "profile":
                user_entity = await event.client.get_entity(user_id)
                username = f"@{user_entity.username}" if user_entity.username else "—"
                user_reports = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                status = "⭐" if has_subscription(user_id) else "🏠"
                await upd(f"👤 ПРОФИЛЬ\n\nID: {user_id}\nЮзернейм: {username}\nСтатус: {status}\nЖалоб: {len(user_reports)}", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                return
            if data == "developer":
                await upd(f"👨‍💻 РАЗРАБОТЧИК\n\n{DEVELOPER_LINK}", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                return
            if data == "history":
                history = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                if not history:
                    await upd("📜 ИСТОРИЯ\n\nНет записей.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                text = "📜 ИСТОРИЯ\n\n"
                for i, r in enumerate(history[-10:], 1):
                    status = "✅" if "успешно" in r.get('destination', '').lower() else "⏳"
                    text += f"{i}. {r.get('target', '')} - {status} - {r.get('type', '')}\n"
                buttons = [
                    [KeyboardButtonCallback("🔙 Назад", b"back_to_start")]
                ]
                await upd(text, buttons)
                return
            if data == "back_to_start":
                if has_subscription(user_id):
                    buttons = [
                        [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                        [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")],
                        [KeyboardButtonCallback("📜 Моя история", b"history")]
                    ]
                    await upd(f"📌 {BOT_NAME}", buttons)
                else:
                    await upd(f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}")
                return
            if data == "mix_menu":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_mix_target'
                await upd("📤 МИКС\n\nОтправь ссылку\n@username или https://t.me/...", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data == "telethon_report":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_telethon_target'
                await upd("⚡ TELEHON\n\nОтправь ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data == "operator":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_operator_target'
                await upd("👤 ОПЕРАТОР\n\nОтправь юзернейм\n@username или https://t.me/...", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data == "ai_analyze":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_ai_target'
                await upd("🔍 AI-АНАЛИЗ\n\nОтправь ссылку\n@channel или https://t.me/...", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data == "mix_drugs_yes":
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['drugs'] = 'yes'
                user_states[user_id] = 'waiting_mix_description'
                await upd("📝 ОПИСАНИЕ\n\nТип; Причина; Ссылки\nПример: Канал; продажа; https://t.me/x/12", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data == "mix_drugs_no":
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['drugs'] = 'no'
                user_states[user_id] = 'waiting_mix_description'
                await upd("📝 ОПИСАНИЕ\n\nТип; Причина; Ссылки\nПример: Канал; продажа; https://t.me/x/12", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if data.startswith("send_ai_report_"):
                try:
                    target_user_id = int(data.split("_")[3])
                except:
                    target_user_id = user_id
                if not analyzer.last_result or not analyzer.last_result.get("violation"):
                    await upd("❌ Нет нарушений для отправки.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    return
                violation = analyzer.last_result.get("violation")
                target = user_data.get(target_user_id, {}).get("last_ai_target", "unknown")
                links = analyzer.last_result.get("links", [])
                description = user_data.get(target_user_id, {}).get("last_ai_description", "Violation detected")
                text = await generate_complaint_text(target, violation, description, links)
                await upd("⏳ Отправка микс-жалобы...")
                result = await send_mix_report(target_user_id, target, text, edit_callback=None)
                data = load_data()
                data.setdefault('reports', []).append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'target': target,
                    'type': 'Микс-жалоба (AI)',
                    'destination': 'AU + TIDA',
                    'user': target_user_id,
                    'links': links
                })
                save_data(data)
                await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
        @bot.on(events.NewMessage)
        async def handle_messages(event):
            if event.message.text and event.message.text.startswith('/'):
                return
            user_id = event.sender_id
            text = event.message.text.strip()
            state = user_states.get(user_id)
            await event.delete()
            async def upd(msg_text, buttons=None):
                await update_message(event, msg_text, buttons)
            if state == 'waiting_mix_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    if user_id not in user_data:
                        user_data[user_id] = {}
                    user_data[user_id]['target'] = target
                    user_states[user_id] = 'waiting_mix_drugs'
                    buttons = [
                        [KeyboardButtonCallback("✅ Да", b"mix_drugs_yes")],
                        [KeyboardButtonCallback("❌ Нет", b"mix_drugs_no")],
                        [KeyboardButtonCallback("🔙 Назад", b"main_menu")]
                    ]
                    await upd("Наркотики?", buttons)
                else:
                    await upd("❌ Неверная ссылка.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if state == 'waiting_telethon_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_states.pop(user_id, None)
                    await upd("⏳ Отправка Telethon...")
                    result = await send_telethon_report(user_id, target, edit_callback=None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': target,
                        'type': 'Telethon-отчёт',
                        'destination': 'Все сессии',
                        'user': user_id
                    })
                    save_data(data)
                    await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                else:
                    await upd("❌ Неверная ссылка.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if state == 'waiting_operator_target':
                if 't.me/' in text or text.startswith('@'):
                    username = text
                    user_states.pop(user_id, None)
                    await upd("⏳ Отправка оператору...")
                    result = await send_operator_report(user_id, username, edit_callback=None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': username,
                        'type': 'Оператор',
                        'destination': 'Telegram API',
                        'user': user_id
                    })
                    save_data(data)
                    await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                else:
                    await upd("❌ Неверный юзернейм.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if state == 'waiting_ai_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_states.pop(user_id, None)
                    if user_id not in user_data:
                        user_data[user_id] = {}
                    user_data[user_id]['last_ai_target'] = target
                    await upd("⏳ Сканирование...")
                    result, error = await analyzer.analyze_target(target, user_id, bot)
                    if error:
                        await upd(f"{error}", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                        return
                    if not result or not result.get("violation"):
                        await upd(
                            "🔍 AI-АНАЛИЗ\n\n✅ Нарушений не найдено.\n\nЕсли вы считаете, что конкретное сообщение нарушает правила, отправьте его ссылку для анализа.",
                            [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]]
                        )
                        return
                    violation = result.get("violation")
                    severity = result.get("severity", "medium")
                    explanation = result.get("explanation", "")
                    links = result.get("links", [])
                    report = f"🔍 AI-АНАЛИЗ\n\nЦель: {target}\nТип: КАНАЛ\nНарушение: {violation.upper()} ({severity.upper()})\nОбъяснение: {explanation}\n"
                    if links:
                        report += "\n🔗 Ссылки на нарушения:\n" + "\n".join(links)
                    buttons = [
                        [KeyboardButtonCallback("🚀 Отправить жалобу", f"send_ai_report_{user_id}")],
                        [KeyboardButtonCallback("🔙 Назад", b"main_menu")]
                    ]
                    user_data[user_id]['last_ai_description'] = f"Violation type: {violation}. Found in {len(result.get('messages', []))} messages."
                    await upd(report, buttons)
                else:
                    await upd("❌ Неверная ссылка.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            if state == 'waiting_mix_description':
                description = text
                target = user_data.get(user_id, {}).get('target')
                drugs = user_data.get(user_id, {}).get('drugs', 'no')
                if not target:
                    await upd("❌ Ошибка: цель не найдена", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    return
                parts = description.split(';')
                target_type = parts[0].strip() if len(parts) > 0 else "unknown"
                evidence_links = parts[2].strip() if len(parts) > 2 else ""
                violation = "drugs" if drugs == 'yes' else "violation"
                links = [link.strip() for link in evidence_links.split(',')] if evidence_links else []
                text = await generate_complaint_text(target, violation, description, links)
                user_states.pop(user_id, None)
                await upd("⏳ Отправка микс-жалобы...")
                result = await send_mix_report(user_id, target, text, edit_callback=None)
                data = load_data()
                data.setdefault('reports', []).append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'target': target,
                    'type': 'Микс-жалоба',
                    'destination': 'AU + TIDA',
                    'user': user_id,
                    'links': links
                })
                save_data(data)
                await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
        @bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel(event):
            user_id = event.sender_id
            await event.delete()
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            if user_id in pending_requests:
                pending_requests.pop(user_id, None)
            if has_subscription(user_id):
                buttons = [
                    [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                    [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")],
                    [KeyboardButtonCallback("📜 Моя история", b"history")]
                ]
                text = f"📌 {BOT_NAME}\n\n❌ Отменено"
            else:
                text = f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}"
                buttons = None
            await update_message(event, text, buttons)
        print("Bot ready")
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"Error: {e}")

# ===== ЗАПУСК =====
async def main():
    http_task = asyncio.create_task(start_http_server())
    main_task = asyncio.create_task(main_bot())
    sub_task = asyncio.create_task(run_subscription_bot())
    await asyncio.gather(main_task, sub_task, http_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
    except Exception as e:
        print(f"Fatal error: {e}")
