# app.py — APEX REPORT (ПОЛНАЯ ВЕРСИЯ, ПАРАЛЛЕЛЬНАЯ ОТПРАВКА TELEHON)
import os
import sys
import json
import asyncio
import threading
import re
import random
import time
from datetime import datetime, timedelta
import requests

try:
    from telethon import TelegramClient, events
    from telethon.tl.types import KeyboardButtonCallback
    from telethon.tl.functions.account import ReportPeerRequest
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.types import InputReportReasonOther, InputReportReasonSpam, InputReportReasonIllegalDrugs, InputReportReasonPornography, InputReportReasonViolence
    from telethon.errors import FloodWaitError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# ===== ТВОИ ДАННЫЕ =====
API_ID = 21826549
API_HASH = 'c1a19f792cfd9e397200d16c7e448160'
BOT_TOKEN = '8870668741:AAHL2cO1BWoHau-bVmBLziMadDj94SnU7IA'
CHANNEL_ID = -1004489395750
RUCAPTCHA_API_KEY = 'a2e1b40a756ccc16c11ede55eb2c6567'
SUBSCRIPTION_BOT_TOKEN = '8238807176:AAFBRezNnlRiJ3oE-D81aOQGJ8NvJzBGBiU'
DEVELOPER_LINK = 'https://t.me/cazlen'
BOT_NAME = 'APEX REPORT'

# ===== ПУТИ =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

possible_sessions_dirs = [
    os.path.join(BASE_DIR, 'sessions'),
    os.path.join(BASE_DIR, 'сессии'),
    os.path.join(BASE_DIR, '..', 'sessions'),
]

SESSIONS_DIR = None
for d in possible_sessions_dirs:
    if os.path.exists(d):
        SESSIONS_DIR = d
        print(f"[INFO] Найдена папка с сессиями: {SESSIONS_DIR}")
        break

if not SESSIONS_DIR:
    SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    print(f"[INFO] Создана папка с сессиями: {SESSIONS_DIR}")

AU_DIR = os.path.join(SESSIONS_DIR, 'au')
US_DIR = os.path.join(SESSIONS_DIR, 'us')
INTERNAL_DIR = os.path.join(SESSIONS_DIR, 'internal')

for d in [AU_DIR, US_DIR, INTERNAL_DIR]:
    os.makedirs(d, exist_ok=True)

LOG_FILE = os.path.join(BASE_DIR, 'bot_analytics.json')
SUBS_FILE = os.path.join(BASE_DIR, 'subscriptions.json')
REQUESTS_FILE = os.path.join(BASE_DIR, 'requests.json')

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
    subs = load_subs()
    user_id_str = str(user_id)
    if user_id_str not in subs:
        return False
    expiry = subs[user_id_str].get('expiry')
    if not expiry:
        return False
    try:
        expiry_dt = datetime.fromisoformat(expiry)
        return expiry_dt > datetime.now()
    except:
        return False

def generate_phone():
    return f"+7{random.randint(1000000000, 9999999999)}"

def solve_captcha(api_key):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        resp = session.get("https://telegram.org/support", timeout=15)
        match = re.search(r'data-sitekey=["\']([^"\']+)["\']', resp.text)
        if not match:
            return None, None
        sitekey = match.group(1)
        r = requests.post("http://rucaptcha.com/in.php", data={
            "key": api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": "https://telegram.org/support",
            "json": 1
        }, timeout=30)
        res = r.json()
        if res.get("status") != 1:
            return None, None
        captcha_id = res.get("request")
        for _ in range(60):
            time.sleep(2)
            r2 = requests.get(f"http://rucaptcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1")
            data = r2.json()
            if data.get("status") == 1:
                return data.get("request"), session
            elif "CAPCHA_NOT_READY" in str(data):
                continue
            else:
                return None, None
        return None, None
    except:
        return None, None

def send_web_report(api_key, name, phone, text):
    token, session = solve_captcha(api_key)
    if not token or not session:
        return False, "Капча не решена"
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'name': name,
        'email': "sms@telegram.org",
        'phone': phone,
        'msg': text,
        'cf-turnstile-response': token
    }
    try:
        r = session.post("https://telegram.org/support", headers=headers, data=data, timeout=15)
        session.close()
        if r.status_code == 200:
            return True, f"код: {r.status_code}"
        else:
            return False, f"код: {r.status_code}"
    except:
        session.close()
        return False, "ошибка"

async def try_connect(session_path, timeout=10):
    client = None
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await asyncio.wait_for(client.start(), timeout=timeout)
        try:
            await asyncio.wait_for(client.get_me(), timeout=timeout)
        except:
            if client:
                await client.disconnect()
            return None
        return client
    except:
        if client:
            await client.disconnect()
        return None

async def join_chat_if_needed(client, target):
    try:
        if 't.me/joinchat' in target or 't.me/+' in target:
            await client.join_channel(target)
            return True
        entity = await client.get_entity(target)
        if hasattr(entity, 'username') and entity.username:
            try:
                await client(JoinChannelRequest(entity))
                return True
            except:
                pass
        return True
    except:
        return False

async def send_mix_report(user_id, target, text, bot_instance):
    all_sessions = []
    for dir_path in [AU_DIR, US_DIR]:
        if os.path.exists(dir_path):
            for f in os.listdir(dir_path):
                if f.endswith('.session'):
                    all_sessions.append(os.path.join(dir_path, f))

    if not all_sessions:
        return "❌ Нет сессий"

    au_success = 0
    au_total = 0
    tida_success = 0
    tida_total = 0

    au_sessions = [s for s in all_sessions if 'au' in s]
    au_total = len(au_sessions)
    for session_path in au_sessions:
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=10)
            if not client:
                continue
            await join_chat_if_needed(client, target)
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
            await client.disconnect()
            au_success += 1
        except:
            if client:
                await client.disconnect()
            continue

    us_sessions = [s for s in all_sessions if 'us' in s]
    tida_total = len(us_sessions)
    for session_path in us_sessions:
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=10)
            if not client:
                continue
            await join_chat_if_needed(client, target)
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
            await client.disconnect()
            tida_success += 1
        except:
            if client:
                await client.disconnect()
            continue

    return f"✅ Жалоба отправлена\n🎯 {target}"

# ===== ПАРАЛЛЕЛЬНАЯ ОТПРАВКА TELEHON =====
async def send_telethon_report(user_id, target, bot_instance):
    all_sessions = []
    for dir_path in [AU_DIR, US_DIR, INTERNAL_DIR]:
        if os.path.exists(dir_path):
            for f in os.listdir(dir_path):
                if f.endswith('.session'):
                    all_sessions.append(os.path.join(dir_path, f))

    if not all_sessions:
        return "❌ Нет сессий"

    message_link_pattern = r'https://t\.me/([^/]+)/(\d+)'
    match = re.search(message_link_pattern, target)
    if match:
        chat_username = match.group(1)
        message_id = int(match.group(2))
        is_message = True
    else:
        is_message = False

    async def send_one(session_path):
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=10)
            if not client:
                return (session_name, False, "не авторизована")
            
            if is_message:
                parts = target.split('/')
                chat_username = parts[-2]
                chat = await client.get_entity(chat_username)
                await client(ReportPeerRequest(
                    peer=chat,
                    reason=InputReportReasonSpam(),
                    message=""
                ))
            else:
                entity = await client.get_entity(target)
                await client(ReportPeerRequest(
                    peer=entity,
                    reason=InputReportReasonSpam(),
                    message=""
                ))
            await client.disconnect()
            return (session_name, True, "успешно")
        except FloodWaitError as e:
            if client:
                await client.disconnect()
            await asyncio.sleep(min(e.seconds, 30))
            return (session_name, False, f"FloodWait {e.seconds}s")
        except Exception as e:
            if client:
                await client.disconnect()
            return (session_name, False, str(e)[:30])

    # ПАРАЛЛЕЛЬНАЯ ОТПРАВКА
    tasks = [send_one(session_path) for session_path in all_sessions]
    results = await asyncio.gather(*tasks)

    success = sum(1 for _, status, _ in results if status)
    total = len(results)

    return f"✅ Telethon — {success}/{total}"

async def send_operator_report(user_id, username, bot_instance):
    phone = generate_phone()
    name = "Operator Report"
    text = f"Complaint against drug shop operator: {username}"
    success, msg = send_web_report(RUCAPTCHA_API_KEY, name, phone, text)
    if success:
        return f"✅ Оператор {username}"
    else:
        return f"❌ Оператор {username}: {msg}"

class PowerAI:
    def generate_mix_text(self, target, target_type, violation_desc, evidence_links=""):
        report = f"URGENT REPORT — TELEGRAM TERMS OF SERVICE VIOLATION. Target: {target} ({target_type}). Violation: {violation_desc}. This entity systematically violates Telegram rules by engaging in {violation_desc}, which directly contravenes Telegram ToS (Community Guidelines). Evidence has been documented and includes public accessibility of violating content, active user engagement with prohibited material, and clear intent to bypass Telegram's moderation systems."
        if evidence_links:
            report += f" DIRECT EVIDENCE: {evidence_links}."
        report += " Request: immediate account/channel suspension and full investigation into reported activities. Signed, Telegram Compliance Reporting System."
        return report

class ContentAnalyzer:
    def __init__(self):
        self.keywords = {
            "drugs": ["buy", "cocaine", "heroin", "meth", "drugs", "shop", "dealer"],
            "spam": ["spam", "ad", "promo", "subscribe", "referral"],
            "porn": ["porn", "sex", "nude", "18+"],
            "violence": ["violence", "kill", "death", "blood", "weapon"],
            "scam": ["scam", "pyramid", "invest", "phishing"],
            "personal": ["passport", "address", "phone", "personal", "data"],
            "bullying": ["bullying", "harass", "threat", "insult"]
        }

    def analyze_text(self, text):
        text_lower = text.lower()
        results = {}
        for category, words in self.keywords.items():
            count = sum(1 for word in words if word in text_lower)
            results[category] = min(int((count / len(words)) * 100), 100)
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
        all_sessions = []
        for dir_path in [AU_DIR, US_DIR, INTERNAL_DIR]:
            if os.path.exists(dir_path):
                for f in os.listdir(dir_path):
                    if f.endswith('.session'):
                        all_sessions.append(os.path.join(dir_path, f))

        if not all_sessions:
            return None, "Нет сессий"

        messages = []
        target_type = "unknown"
        client = None

        for session_path in all_sessions:
            try:
                client = await try_connect(session_path, timeout=10)
                if client:
                    break
            except:
                continue

        if not client:
            return None, "Не удалось подключиться"

        try:
            if 't.me/' in target:
                username = target.replace('https://t.me/', '')
                if '/' in username:
                    username = username.split('/')[0]
                entity = await client.get_entity(f"@{username}")
                target_type = "канал"
            elif target.startswith('@'):
                entity = await client.get_entity(target)
                if entity.bot:
                    target_type = "бот"
                    await client.send_message(entity, '/start')
                    await asyncio.sleep(2)
                else:
                    target_type = "пользователь"
            else:
                return None, "Неверная ссылка"

            try:
                await client(JoinChannelRequest(entity))
                await asyncio.sleep(10)
            except:
                pass

            all_messages = []
            offset_id = 0
            limit = 100

            while True:
                try:
                    msgs = await client.get_messages(entity, limit=limit, offset_id=offset_id)
                    if not msgs:
                        break
                    for m in msgs:
                        if m and m.text:
                            all_messages.append(m.text)
                    offset_id = msgs[-1].id
                    if len(msgs) < limit:
                        break
                except:
                    break

            await client.disconnect()
            messages = all_messages

        except Exception as e:
            if client:
                await client.disconnect()
            return None, f"Ошибка: {e}"

        if not messages:
            return None, "Нет сообщений"

        results = self.analyze_messages(messages)
        violation, percent = self.get_violation(results)

        return {
            "results": results,
            "violation": violation,
            "percent": percent,
            "messages": messages,
            "target_type": target_type,
            "count": len(messages)
        }, None

# ===== ВТОРОЙ БОТ (ДЛЯ ПОДПИСОК) =====
async def run_subscription_bot():
    try:
        print("[SUB-BOT] Запуск...")
        bot = TelegramClient('subscription_bot', API_ID, API_HASH)
        await bot.start(bot_token=SUBSCRIPTION_BOT_TOKEN)
        print("[SUB-BOT] Бот для подписок запущен")

        user_states = {}

        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
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

        @bot.on(events.NewMessage)
        async def handle_sub_messages(event):
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
        bot = await TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        print("Bot connected")

        user_states = {}
        user_data = {}
        active_message = None

        async def update_message(event, text, buttons):
            nonlocal active_message
            try:
                if active_message:
                    await active_message.edit(text, buttons=buttons)
                else:
                    active_message = await event.reply(text, buttons=buttons)
            except:
                active_message = await event.reply(text, buttons=buttons)

        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            nonlocal active_message
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
                active_message = await event.reply(f"📌 {BOT_NAME}", buttons=buttons)
            else:
                active_message = await event.reply(f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}")

        @bot.on(events.CallbackQuery)
        async def handle_callbacks(event):
            nonlocal active_message
            await event.answer()
            user_id = event.sender_id
            data = event.data.decode('utf-8')
            
            try:
                await event.message.delete()
            except:
                pass
            
            async def upd(text, buttons):
                nonlocal active_message
                try:
                    if active_message:
                        await active_message.edit(text, buttons=buttons)
                    else:
                        active_message = await event.reply(text, buttons=buttons)
                except:
                    active_message = await event.reply(text, buttons=buttons)

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
                await upd("📋 МЕНЮ", buttons=buttons)
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
                    status = "✅" if "успешно" in r.get('type', '').lower() else "⏳"
                    text += f"{i}. {r.get('target', '')} {status} {r.get('time', '')}\n"
                buttons = [[KeyboardButtonCallback("📥 PDF", b"download_pdf")], [KeyboardButtonCallback("🔙 Назад", b"back_to_start")]]
                await upd(text, buttons)
                return
            
            if data == "download_pdf":
                await upd("📥 PDF отправлен в личные сообщения.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                return
            
            if data == "back_to_start":
                if has_subscription(user_id):
                    buttons = [[KeyboardButtonCallback("📋 Меню", b"main_menu")], [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")], [KeyboardButtonCallback("📜 История", b"history")]]
                    await upd(f"📌 {BOT_NAME}", buttons)
                else:
                    await upd(f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}", None)
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
                user_data[user_id]['drugs'] = 'yes'
                user_states[user_id] = 'waiting_mix_description'
                await upd("📝 ОПИСАНИЕ\n\nТип; Причина; Ссылки\nПример: Канал; продажа; https://t.me/x/12", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return
            
            if data == "mix_drugs_no":
                user_data[user_id]['drugs'] = 'no'
                user_states[user_id] = 'waiting_mix_description'
                await upd("📝 ОПИСАНИЕ\n\nТип; Причина; Ссылки\nПример: Канал; продажа; https://t.me/x/12", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

        @bot.on(events.NewMessage)
        async def handle_messages(event):
            nonlocal active_message
            if event.message.text and event.message.text.startswith('/'):
                return
            user_id = event.sender_id
            text = event.message.text.strip()
            state = user_states.get(user_id)
            await event.delete()

            async def upd(msg_text, buttons):
                nonlocal active_message
                try:
                    if active_message:
                        await active_message.edit(msg_text, buttons=buttons)
                    else:
                        active_message = await event.reply(msg_text, buttons=buttons)
                except:
                    active_message = await event.reply(msg_text, buttons=buttons)

            if state == 'waiting_mix_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_data[user_id] = {'target': target}
                    user_states[user_id] = 'waiting_mix_drugs'
                    buttons = [[KeyboardButtonCallback("✅ Да", b"mix_drugs_yes")], [KeyboardButtonCallback("❌ Нет", b"mix_drugs_no")], [KeyboardButtonCallback("🔙 Назад", b"main_menu")]]
                    await upd("Наркотики?", buttons)
                else:
                    await upd("❌ Неверная ссылка.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_telethon_target':
                if 't.me/' in text or text.startswith('@'):
                    target = text
                    user_states.pop(user_id, None)
                    await event.reply("⏳ Отправка...")
                    result = await send_telethon_report(user_id, target, None)
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
                    await event.reply("⏳ Отправка...")
                    result = await send_operator_report(user_id, username, None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': username,
                        'type': 'Оператор',
                        'destination': 'Веб-метод',
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
                    await upd("⏳ Сканирование...", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    analyzer = ContentAnalyzer()
                    result, error = await analyzer.analyze_target(target, None)
                    if error:
                        await upd(f"❌ {error}", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                        return
                    if not result:
                        await upd("❌ Нет сообщений", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                        return
                    results = result["results"]
                    violation = result["violation"]
                    percent = result["percent"]
                    messages = result["messages"]
                    target_type = result["target_type"]
                    report = f"🔍 AI-АНАЛИЗ\n\nЦель: {target}\nТип: {target_type.upper()}\nСообщений: {len(messages)}\n"
                    if violation:
                        report += f"Нарушение: {violation.upper()} ({percent}%)\n❌ Найдено!"
                    else:
                        report += f"Нарушений: 0\n✅ Чисто"
                    await upd(report, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                else:
                    await upd("❌ Неверная ссылка.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_mix_description':
                description = text
                target = user_data.get(user_id, {}).get('target')
                drugs = user_data.get(user_id, {}).get('drugs', 'no')
                if not target:
                    await upd("❌ Ошибка", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    return
                violation_desc = "distribution of illegal narcotics" if drugs == 'yes' else "violation of Telegram rules"
                parts = description.split(';')
                target_type = parts[0].strip() if len(parts) > 0 else "unknown"
                evidence_links = parts[2].strip() if len(parts) > 2 else ""
                ai = PowerAI()
                text = ai.generate_mix_text(target, target_type, violation_desc, evidence_links)
                user_states.pop(user_id, None)
                await event.reply("⏳ Отправка...")
                result = await send_mix_report(user_id, target, text, None)
                data = load_data()
                data.setdefault('reports', []).append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'target': target,
                    'type': 'Микс-жалоба',
                    'destination': 'AU + TIDA',
                    'user': user_id
                })
                save_data(data)
                await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

        @bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel(event):
            nonlocal active_message
            await event.delete()
            user_states.pop(event.sender_id, None)
            user_data.pop(event.sender_id, None)
            if has_subscription(event.sender_id):
                buttons = [[KeyboardButtonCallback("📋 Меню", b"main_menu")], [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")], [KeyboardButtonCallback("📜 История", b"history")]]
                text = f"📌 {BOT_NAME}\n\n❌ Отменено"
            else:
                text = f"🚫 ДОСТУП ЗАПРЕЩЁН\n\nДля покупки напишите:\n{DEVELOPER_LINK}"
                buttons = None
            if active_message:
                await active_message.edit(text, buttons=buttons)
            else:
                active_message = await event.reply(text, buttons=buttons)

        print("Bot ready")
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"Error: {e}")

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
