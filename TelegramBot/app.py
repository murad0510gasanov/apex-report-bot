# app.py — APEX REPORT (ФИНАЛЬНЫЙ КОД)
import os
import sys
import json
import asyncio
import re
import random
import time
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from io import BytesIO

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
            print(f"[{session_name}] ✅ Подключена (попытка {attempt+1})")
            return client
        except asyncio.TimeoutError:
            if client:
                await client.disconnect()
            print(f"[{session_name}] ⏰ Таймаут (попытка {attempt+1})")
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

# ===== ГЕНЕРАЦИЯ PDF =====
def generate_pdf(user_id, reports):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "APEX REPORT - USER HISTORY")
    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"User ID: {user_id}")
    y -= 20
    c.drawString(50, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 30
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total reports: {len(reports)}")
    y -= 20
    
    for i, report in enumerate(reports, 1):
        if y < 100:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 12)
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"Report {i}")
        y -= 15
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Target: {report.get('target', 'Unknown')}")
        y -= 12
        c.drawString(50, y, f"Type: {report.get('type', 'Unknown')}")
        y -= 12
        c.drawString(50, y, f"Time: {report.get('time', 'Unknown')}")
        y -= 12
        c.drawString(50, y, f"Status: {report.get('destination', 'Unknown')}")
        
        if 'links' in report and report['links']:
            y -= 12
            c.drawString(50, y, "Links:")
            for link in report['links'][:3]:
                y -= 10
                c.drawString(60, y, link[:60])
        y -= 20
    
    c.save()
    buffer.seek(0)
    return buffer

# ===== ОТПРАВКА ЛОГОВ В КАНАЛ =====
async def send_log_to_channel(text):
    try:
        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
            channel = await temp_client.get_entity(CHANNEL_ID)
            await temp_client.send_message(channel, text)
            print(f"[LOG] Отправлено в канал: {text[:50]}...")
    except Exception as e:
        print(f"[LOG] Ошибка отправки в канал: {e}")

# ===== ОПЕРАТОР =====
async def send_operator_report(user_id, username, edit_callback=None):
    try:
        client = await get_live_session()
        if not client:
            result = "ERROR: No live sessions"
            if edit_callback:
                await edit_callback(result)
            return result

        username = username.replace('https://t.me/', '').replace('@', '')
        
        try:
            entity = await client.get_entity(f"@{username}")
        except UsernameNotOccupiedError:
            await client.disconnect()
            result = f"ERROR: Operator @{username} not found"
            if edit_callback:
                await edit_callback(result)
            return result
        except Exception as e:
            await client.disconnect()
            result = f"ERROR: {str(e)[:50]}"
            if edit_callback:
                await edit_callback(result)
            return result

        try:
            await client(ReportPeerRequest(
                peer=entity,
                reason=InputReportReasonSpam(),
                message="Spam and violation of Telegram Terms of Service"
            ))
            result = f"SUCCESS: Complaint sent to @{username}"
            
            await send_log_to_channel(f"Operator report sent to @{username}")
                
        except FloodWaitError as e:
            result = f"FLOODWAIT: {e.seconds} seconds"
        except Exception as e:
            result = f"ERROR: {str(e)[:50]}"
        finally:
            await client.disconnect()

    except Exception as e:
        result = f"ERROR: {str(e)[:50]}"

    if edit_callback:
        await edit_callback(result)
    return result

# ===== ТЕЛЕТОН =====
async def send_telethon_report(user_id, target, edit_callback=None):
    all_sessions = get_all_sessions()
    if not all_sessions:
        if edit_callback:
            await edit_callback("ERROR: No sessions")
        return "ERROR: No sessions"
    if not target:
        if edit_callback:
            await edit_callback("ERROR: Invalid link")
        return "ERROR: Invalid link"

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

    print(f"\nTelethon - sending to {target}")
    print(f"Total sessions: {total}")

    async def send_one(session_path, index):
        nonlocal errors, success_count
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=20, retries=3)
        if not client:
            errors += 1
            print(f"[{session_name}] ERROR: Failed to connect")
            return

        try:
            if is_message:
                try:
                    chat = await client.get_entity(chat_username)
                    await client(ReportPeerRequest(peer=chat, reason=InputReportReasonSpam(), message=""))
                    success_count += 1
                    print(f"[{session_name}] SUCCESS")
                except UsernameNotOccupiedError:
                    errors += 1
                    print(f"[{session_name}] ERROR: Channel not found")
                except FloodWaitError as e:
                    errors += 1
                    print(f"[{session_name}] FLOODWAIT: {e.seconds}s")
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception as e:
                    errors += 1
                    print(f"[{session_name}] ERROR: {str(e)[:50]}")
            else:
                try:
                    entity = await client.get_entity(target)
                    await client(ReportPeerRequest(peer=entity, reason=InputReportReasonSpam(), message=""))
                    success_count += 1
                    print(f"[{session_name}] SUCCESS")
                except UsernameNotOccupiedError:
                    errors += 1
                    print(f"[{session_name}] ERROR: Target not found")
                except FloodWaitError as e:
                    errors += 1
                    print(f"[{session_name}] FLOODWAIT: {e.seconds}s")
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception as e:
                    errors += 1
                    print(f"[{session_name}] ERROR: {str(e)[:50]}")
        finally:
            await client.disconnect()

    tasks = [send_one(session_path, i+1) for i, session_path in enumerate(all_sessions)]
    await asyncio.gather(*tasks)

    print(f"\nResult: {success_count}/{total} successful, {errors} errors")

    result = f"SUCCESS: {success_count}/{total} sent"
    if errors > 0:
        result += f", Errors: {errors}"

    await send_log_to_channel(f"Telethon report on {target}: {success_count}/{total} successful")

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
            await edit_callback("ERROR: No sessions for mix (AU + US)")
        return "ERROR: No sessions for mix"

    total = len(all_sessions)
    au_sessions = [s for s in all_sessions if 'au' in s]
    us_sessions = [s for s in all_sessions if 'us' in s]
    current = 0

    print(f"\nMix - sending to {target}")
    print(f"AU sessions: {len(au_sessions)}, US sessions: {len(us_sessions)}")

    for session_path in au_sessions:
        current += 1
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=15, retries=2)
        if not client:
            print(f"[AU] {session_name} ERROR: Failed to connect")
            continue
        try:
            print(f"[AU] {session_name} Sending... ({current}/{total})")
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
            print(f"[AU] {session_name} SUCCESS")
        except Exception as e:
            print(f"[AU] {session_name} ERROR: {str(e)[:50]}")
        finally:
            await client.disconnect()

    for session_path in us_sessions:
        current += 1
        session_name = os.path.basename(session_path)
        client = await try_connect(session_path, timeout=15, retries=2)
        if not client:
            print(f"[US] {session_name} ERROR: Failed to connect")
            continue
        try:
            print(f"[US] {session_name} Sending... ({current}/{total})")
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
            print(f"[US] {session_name} SUCCESS")
        except Exception as e:
            print(f"[US] {session_name} ERROR: {str(e)[:50]}")
        finally:
            await client.disconnect()

    print(f"\nMix - sent {current}/{total} sessions")

    await send_log_to_channel(f"Mix complaint sent to {target}")

    if edit_callback:
        await edit_callback("SUCCESS: Mix complaint sent")
    return "SUCCESS: Mix complaint sent"

# ===== ГЕНЕРАЦИЯ ТЕКСТА ДЛЯ МИКСА =====
def generate_mix_text(target, violation, links):
    if not links:
        links = ["No links provided"]
    
    text = f"""hello
I would like to report a Telegram channel that appears to contain content related to {violation}.
Channel:
{target}
Reported messages:
{chr(10).join(links)}
These posts appear to contain content that violates Telegram's policies.
Please review the reported content and take appropriate action if it violates Telegram's policies.
Thank you for your attention."""
    return text

# ===== AI-АНАЛИЗ (ТОЛЬКО ФОЛБЭК) =====
class ContentAnalyzer:
    def __init__(self):
        self.last_result = None
        self.keywords = {
            "drugs": [
                "наркотик", "наркота", "наркотики", "кокаин", "кока", "кокс",
                "героин", "метамфетамин", "экстази", "марихуана", "анаша", "план",
                "шишки", "бошки", "гашиш", "спайс", "соль", "скорость", "кристалл",
                "закладка", "закладки", "продажа", "продам", "куплю", "синтетика",
                "drugs", "cocaine", "heroin", "meth", "mdma", "weed", "cannabis"
            ],
            "personal": [
                "паспорт", "фио", "ф.и.о", "адрес", "прописка", "регистрация",
                "дом", "квартира", "подъезд", "этаж", "улица", "телефон",
                "снилс", "инн", "личные данные", "passport", "address", "phone"
            ],
            "porn": [
                "порно", "порнография", "секс", "эротика", "голый", "голая",
                "интим", "18+", "porn", "sex", "nude", "adult"
            ],
            "violence": [
                "насилие", "убить", "убийство", "смерть", "оружие", "пистолет",
                "нож", "угроза", "избить", "кровь", "взорвать", "бомба",
                "violence", "kill", "death", "weapon", "gun", "threat"
            ],
            "spam": [
                "спам", "реклама", "пиар", "подпишись", "подписка", "рассылка",
                "spam", "ad", "promo", "subscribe"
            ],
            "scam": [
                "лохотрон", "развод", "обман", "мошенник", "пирамида",
                "инвестиции", "фишинг", "scam", "fraud", "phishing"
            ],
            "bullying": [
                "буллинг", "травля", "оскорбление", "унижение", "bullying",
                "harassment", "insult"
            ]
        }

        self.patterns = {
            "phone": r'(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "passport": r'[0-9]{4}\s?[0-9]{6}',
            "address": r'(г|гор|город|ул|улица|пр|проспект|пер|переулок|бул|бульвар|д|дом|кв|квартира)[\.\s]',
            "fio": r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
        }

    def analyze_text(self, text):
        text_lower = text.lower()
        results = {}
        for category, words in self.keywords.items():
            count = 0
            for word in words:
                if word in text_lower:
                    count += 1
            results[category] = min(count * 25, 100)

        for pattern_name, pattern in self.patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                cat_map = {"phone": "personal", "email": "personal", "passport": "personal", "address": "personal", "fio": "personal"}
                if pattern_name in cat_map:
                    cat = cat_map[pattern_name]
                    results[cat] = min(results.get(cat, 0) + 30, 100)
        return results

    def analyze_messages(self, messages):
        combined = " ".join(messages)
        return self.analyze_text(combined)

    def get_violation(self, results):
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        for cat, percent in sorted_results:
            if percent >= 30:
                return cat, percent
        return None, 0

    async def analyze_target(self, target, bot_instance):
        client = await get_live_session()
        if not client:
            return None, "ERROR: No live sessions"

        messages = []
        target_type = "unknown"
        chat_username = ""
        message_ids = []

        try:
            if 't.me/' in target:
                clean_target = target.replace('https://t.me/', '').replace('t.me/', '')
                if '/' in clean_target and not clean_target.startswith('joinchat') and not clean_target.startswith('+'):
                    chat_username = clean_target.split('/')[0]
                    entity = await client.get_entity(f"@{chat_username}")
                    target_type = "channel"
                else:
                    try:
                        entity = await client.get_entity(target)
                        chat_username = getattr(entity, 'username', 'unknown')
                        target_type = "channel"
                    except Exception:
                        if '/' in clean_target:
                            chat_username = clean_target.split('/')[0]
                        else:
                            chat_username = clean_target
                        entity = await client.get_entity(f"@{chat_username}")
                        target_type = "channel"
            elif target.startswith('@'):
                chat_username = target.replace('@', '')
                entity = await client.get_entity(target)
                target_type = "user"
            else:
                await client.disconnect()
                return None, "ERROR: Invalid link"

            try:
                await client(JoinChannelRequest(entity))
                print(f"[JOIN] Subscribed to {chat_username}")
                await asyncio.sleep(3)
            except ChannelPrivateError:
                try:
                    await client.send_message(entity, "Request to join")
                    print(f"[JOIN] Join request sent to {chat_username}")
                    await client.disconnect()
                    return None, f"PRIVATE: Channel {chat_username} is private. Join request sent."
                except Exception as e:
                    print(f"[JOIN] Error: {e}")
            except Exception as e:
                print(f"[JOIN] Error: {e}")

            msgs = await client.get_messages(entity, limit=50)
            for m in msgs:
                if m and m.text:
                    messages.append(m.text)
                    message_ids.append(m.id)

        except Exception as e:
            await client.disconnect()
            return None, f"ERROR: {str(e)[:50]}"

        await client.disconnect()

        if not messages:
            return None, "ERROR: No messages in channel"

        results = self.analyze_messages(messages)
        violation, percent = self.get_violation(results)

        links = []
        if violation and chat_username:
            for idx, msg_id in enumerate(message_ids[:5]):
                links.append(f"https://t.me/{chat_username}/{msg_id}")

        result = {
            "results": results,
            "violation": violation,
            "percent": percent,
            "messages": messages,
            "target_type": target_type,
            "count": len(messages),
            "links": links,
            "chat_username": chat_username
        }

        self.last_result = result

        if violation:
            await send_log_to_channel(f"AI Analysis: {target} - {violation} ({percent}%)")

        return result, None

# ===== БОТ ДЛЯ ПОДПИСОК =====
async def run_subscription_bot():
    try:
        print("[SUB-BOT] Starting...")
        bot = TelegramClient('subscription_bot', API_ID, API_HASH)
        await bot.start(bot_token=SUBSCRIPTION_BOT_TOKEN)
        print("[SUB-BOT] Subscription bot started")

        user_states = {}

        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            if event.sender_id not in ADMIN_IDS:
                await event.reply("ACCESS DENIED")
                return
            await event.delete()
            buttons = [
                [KeyboardButtonCallback("LIST", b"sub_list")],
                [KeyboardButtonCallback("REQUESTS", b"sub_requests")],
                [KeyboardButtonCallback("GIVE", b"sub_give")],
                [KeyboardButtonCallback("REMOVE", b"sub_remove")]
            ]
            await event.reply("SUBSCRIPTION BOT", buttons=buttons)

        @bot.on(events.CallbackQuery)
        async def handle_sub_callbacks(event):
            if event.sender_id not in ADMIN_IDS:
                await event.answer("ACCESS DENIED")
                return
            await event.answer()
            user_id = event.sender_id
            data = event.data.decode('utf-8')

            if data == "sub_list":
                subs = load_subs()
                if not subs:
                    await event.edit("No subscribers.")
                    return
                text = "SUBSCRIBERS:\n\n"
                for uid, data in subs.items():
                    status = "ACTIVE" if has_subscription(int(uid)) else "EXPIRED"
                    text += f"{uid} - {status} until {data.get('expiry', 'N/A')[:10]}\n"
                await event.edit(text, buttons=[[KeyboardButtonCallback("BACK", b"sub_back")]])
                return

            if data == "sub_requests":
                reqs = load_requests()
                if not reqs:
                    await event.edit("No requests.")
                    return
                text = "REQUESTS:\n\n"
                for r in reqs:
                    text += f"ID: {r.get('user_id')} - {r.get('time')}\n"
                await event.edit(text, buttons=[[KeyboardButtonCallback("BACK", b"sub_back")]])
                return

            if data == "sub_give":
                user_states[user_id] = 'waiting_give'
                await event.edit("GIVE SUBSCRIPTION\n\nSend: ID days\nExample: 123456789 7",
                    buttons=[[KeyboardButtonCallback("CANCEL", b"sub_back")]])
                return

            if data == "sub_remove":
                user_states[user_id] = 'waiting_remove'
                await event.edit("REMOVE SUBSCRIPTION\n\nSend ID\nExample: 123456789",
                    buttons=[[KeyboardButtonCallback("CANCEL", b"sub_back")]])
                return

            if data == "sub_back":
                user_states.pop(user_id, None)
                buttons = [
                    [KeyboardButtonCallback("LIST", b"sub_list")],
                    [KeyboardButtonCallback("REQUESTS", b"sub_requests")],
                    [KeyboardButtonCallback("GIVE", b"sub_give")],
                    [KeyboardButtonCallback("REMOVE", b"sub_remove")]
                ]
                await event.edit("SUBSCRIPTION BOT", buttons=buttons)
                return

        @bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel_sub(event):
            if event.sender_id not in ADMIN_IDS:
                return
            user_states.pop(event.sender_id, None)
            await event.reply("CANCELLED")

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
                    await event.reply("ERROR: Format: ID days")
                    return
                uid, days = parts[0], int(parts[1])
                subs = load_subs()
                expiry = datetime.now() + timedelta(days=days)
                subs[uid] = {'expiry': expiry.isoformat()}
                save_subs(subs)
                requests = load_requests()
                requests = [r for r in requests if r.get('user_id') != int(uid)]
                save_requests(requests)
                await event.reply(f"SUCCESS: {uid} given {days} days")
                user_states.pop(user_id, None)

            elif state == 'waiting_remove':
                if not text.isdigit():
                    await event.reply("ERROR: Send ID")
                    return
                uid = text
                subs = load_subs()
                if uid in subs:
                    del subs[uid]
                    save_subs(subs)
                    await event.reply(f"SUCCESS: {uid} removed")
                else:
                    await event.reply(f"ERROR: {uid} not found")
                user_states.pop(user_id, None)

        print("[SUB-BOT] Ready")
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"[SUB-BOT] Error: {e}")

# ===== ГЛАВНЫЙ БОТ =====
async def main_bot():
    try:
        bot = TelegramClient('bot_session', API_ID, API_HASH)
        await bot.start(bot_token=BOT_TOKEN)
        print("Bot connected")

        user_states = {}
        user_data = {}
        active_messages = {}
        analyzer = ContentAnalyzer()

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
                    [KeyboardButtonCallback("MENU", b"main_menu")],
                    [KeyboardButtonCallback("PROFILE", b"profile"), KeyboardButtonCallback("DEVELOPER", b"developer")],
                    [KeyboardButtonCallback("HISTORY", b"history")]
                ]
                await update_message(event, f"{BOT_NAME}", buttons)
            else:
                await update_message(event, f"ACCESS DENIED\n\nPurchase: {DEVELOPER_LINK}")

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
                    await upd(f"ACCESS DENIED\n\nPurchase: {DEVELOPER_LINK}", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                buttons = [
                    [KeyboardButtonCallback("MIX", b"mix_menu")],
                    [KeyboardButtonCallback("TELETHON", b"telethon_report")],
                    [KeyboardButtonCallback("AI ANALYSIS", b"ai_analyze")],
                    [KeyboardButtonCallback("OPERATOR", b"operator")],
                    [KeyboardButtonCallback("BACK", b"back_to_start")]
                ]
                await upd("MAIN MENU", buttons)
                return

            if data == "profile":
                user_entity = await event.client.get_entity(user_id)
                username = f"@{user_entity.username}" if user_entity.username else "-"
                user_reports = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                status = "ACTIVE" if has_subscription(user_id) else "INACTIVE"
                await upd(f"PROFILE\n\nID: {user_id}\nUsername: {username}\nStatus: {status}\nReports: {len(user_reports)}", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                return

            if data == "developer":
                await upd(f"DEVELOPER\n\n{DEVELOPER_LINK}", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                return

            if data == "history":
                history = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                if not history:
                    await upd("HISTORY\n\nNo records.", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                text = "HISTORY\n\n"
                for i, r in enumerate(history[-10:], 1):
                    status = "SUCCESS" if "success" in r.get('destination', '').lower() else "PENDING"
                    text += f"{i}. {r.get('target', '')} - {status} - {r.get('type', '')}\n"
                buttons = [
                    [KeyboardButtonCallback("DOWNLOAD PDF", b"download_pdf")],
                    [KeyboardButtonCallback("BACK", b"back_to_start")]
                ]
                await upd(text, buttons)
                return

            if data == "download_pdf":
                history = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                if not history:
                    await upd("No reports to export.", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                pdf_buffer = generate_pdf(user_id, history)
                await event.reply(file=pdf_buffer, file_name=f"history_{user_id}.pdf")
                return

            if data == "back_to_start":
                if has_subscription(user_id):
                    buttons = [
                        [KeyboardButtonCallback("MENU", b"main_menu")],
                        [KeyboardButtonCallback("PROFILE", b"profile"), KeyboardButtonCallback("DEVELOPER", b"developer")],
                        [KeyboardButtonCallback("HISTORY", b"history")]
                    ]
                    await upd(f"{BOT_NAME}", buttons)
                else:
                    await upd(f"ACCESS DENIED\n\nPurchase: {DEVELOPER_LINK}")
                return

            if data == "mix_menu":
                if not has_subscription(user_id):
                    await upd("ACCESS DENIED", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_mix_target'
                await upd("MIX\n\nSend link\n@username or https://t.me/...", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "telethon_report":
                if not has_subscription(user_id):
                    await upd("ACCESS DENIED", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_telethon_target'
                await upd("TELETHON\n\nSend link", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "operator":
                if not has_subscription(user_id):
                    await upd("ACCESS DENIED", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_operator_target'
                await upd("OPERATOR\n\nSend username\n@username or https://t.me/...", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "ai_analyze":
                if not has_subscription(user_id):
                    await upd("ACCESS DENIED", [[KeyboardButtonCallback("BACK", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_ai_target'
                await upd("AI ANALYSIS\n\nSend link\n@channel or https://t.me/...", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "mix_drugs_yes":
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['drugs'] = 'yes'
                user_states[user_id] = 'waiting_mix_description'
                await upd("DESCRIPTION\n\nType; Reason; Links\nExample: Channel; drugs; https://t.me/x/12", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "mix_drugs_no":
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['drugs'] = 'no'
                user_states[user_id] = 'waiting_mix_description'
                await upd("DESCRIPTION\n\nType; Reason; Links\nExample: Channel; drugs; https://t.me/x/12", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if data == "send_report_from_ai":
                if not analyzer.last_result or not analyzer.last_result.get("violation"):
                    await upd("No violations to send.", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                    return
                
                violation = analyzer.last_result.get("violation")
                target = user_data.get(user_id, {}).get("last_ai_target", "unknown")
                links = analyzer.last_result.get("links", [])
                
                text = generate_mix_text(target, violation, links)
                
                await upd("Sending mix complaint...")
                result = await send_mix_report(user_id, target, text, edit_callback=None)
                
                data = load_data()
                data.setdefault('reports', []).append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'target': target,
                    'type': 'Mix complaint (AI)',
                    'destination': 'AU + TIDA',
                    'user': user_id,
                    'links': links
                })
                save_data(data)
                
                await upd(result, [[KeyboardButtonCallback("BACK", b"main_menu")]])
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
                        [KeyboardButtonCallback("YES", b"mix_drugs_yes")],
                        [KeyboardButtonCallback("NO", b"mix_drugs_no")],
                        [KeyboardButtonCallback("BACK", b"main_menu")]
                    ]
                    await upd("Drugs?", buttons)
                else:
                    await upd("ERROR: Invalid link.", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if state == 'waiting_telethon_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_states.pop(user_id, None)
                    await upd("Sending Telethon...")
                    result = await send_telethon_report(user_id, target, edit_callback=None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': target,
                        'type': 'Telethon report',
                        'destination': 'All sessions',
                        'user': user_id
                    })
                    save_data(data)
                    await upd(result, [[KeyboardButtonCallback("BACK", b"main_menu")]])
                else:
                    await upd("ERROR: Invalid link.", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if state == 'waiting_operator_target':
                if 't.me/' in text or text.startswith('@'):
                    username = text
                    user_states.pop(user_id, None)
                    await upd("Sending operator...")
                    result = await send_operator_report(user_id, username, edit_callback=None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': username,
                        'type': 'Operator report',
                        'destination': 'API',
                        'user': user_id
                    })
                    save_data(data)
                    await upd(result, [[KeyboardButtonCallback("BACK", b"main_menu")]])
                else:
                    await upd("ERROR: Invalid username.", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if state == 'waiting_ai_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_states.pop(user_id, None)
                    if user_id not in user_data:
                        user_data[user_id] = {}
                    user_data[user_id]['last_ai_target'] = target
                    await upd("Scanning...")
                    
                    result, error = await analyzer.analyze_target(target, None)
                    
                    if error:
                        await upd(f"{error}", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                        return
                    
                    if not result or not result.get("violation"):
                        await upd(
                            "AI ANALYSIS\n\nNo violations found.\n\nIf you think a specific message violates rules, send its link for analysis.",
                            [[KeyboardButtonCallback("BACK", b"main_menu")]]
                        )
                        return
                    
                    violation = result.get("violation")
                    percent = result.get("percent", 70)
                    messages = result.get("messages", [])
                    target_type = result.get("target_type", "unknown")
                    links = result.get("links", [])
                    
                    report = f"AI ANALYSIS\n\nTarget: {target}\nType: {target_type.upper()}\nViolation: {violation.upper()} ({percent}%)\nMessages: {len(messages)}\n"
                    if links:
                        report += "\nLinks to violations:\n" + "\n".join(links)
                    
                    buttons = [
                        [KeyboardButtonCallback("SEND COMPLAINT", b"send_report_from_ai")],
                        [KeyboardButtonCallback("BACK", b"main_menu")]
                    ]
                    await upd(report, buttons)
                else:
                    await upd("ERROR: Invalid link.", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

            if state == 'waiting_mix_description':
                description = text
                target = user_data.get(user_id, {}).get('target')
                drugs = user_data.get(user_id, {}).get('drugs', 'no')
                
                if not target:
                    await upd("ERROR: Target not found", [[KeyboardButtonCallback("BACK", b"main_menu")]])
                    return
                
                parts = description.split(';')
                target_type = parts[0].strip() if len(parts) > 0 else "unknown"
                evidence_links = parts[2].strip() if len(parts) > 2 else ""
                
                violation = "drugs" if drugs == 'yes' else "violation"
                links = evidence_links.split(',') if evidence_links else []
                
                text = generate_mix_text(target, violation, links)
                
                user_states.pop(user_id, None)
                await upd("Sending mix complaint...")
                result = await send_mix_report(user_id, target, text, edit_callback=None)
                
                data = load_data()
                data.setdefault('reports', []).append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'target': target,
                    'type': 'Mix complaint',
                    'destination': 'AU + TIDA',
                    'user': user_id,
                    'links': links
                })
                save_data(data)
                
                await upd(result, [[KeyboardButtonCallback("BACK", b"main_menu")]])
                return

        @bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel(event):
            user_id = event.sender_id
            await event.delete()
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            if has_subscription(user_id):
                buttons = [
                    [KeyboardButtonCallback("MENU", b"main_menu")],
                    [KeyboardButtonCallback("PROFILE", b"profile"), KeyboardButtonCallback("DEVELOPER", b"developer")],
                    [KeyboardButtonCallback("HISTORY", b"history")]
                ]
                text = f"{BOT_NAME}\n\nCANCELLED"
            else:
                text = f"ACCESS DENIED\n\nPurchase: {DEVELOPER_LINK}"
                buttons = None
            await update_message(event, text, buttons)

        print("Bot ready")
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"Error: {e}")

# ===== ЗАПУСК =====
async def main():
    main_task = asyncio.create_task(main_bot())
    sub_task = asyncio.create_task(run_subscription_bot())
    await asyncio.gather(main_task, sub_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
    except Exception as e:
        print(f"Fatal error: {e}")
