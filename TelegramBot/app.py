# app.py — APEX REPORT С GEMINI (ФИНАЛ)
import os
import sys
import json
import asyncio
import re
import random
import time
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web

try:
    from telethon import TelegramClient, events, errors
    from telethon.tl.types import KeyboardButtonCallback
    from telethon.tl.functions.account import ReportPeerRequest
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.types import InputReportReasonSpam
    from telethon.errors import FloodWaitError, UsernameNotOccupiedError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# ===== GEMINI =====
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    GEMINI_MODEL = genai.GenerativeModel('gemini-2.0-flash-exp')
    print("[GEMINI] Подключен успешно!")
else:
    GEMINI_MODEL = None
    print("[WARN] Нет API-ключа Gemini")

# ===== ТВОИ ДАННЫЕ =====
API_ID = 21826549
API_HASH = 'c1a19f792cfd9e397200d16c7e448160'
BOT_TOKEN = '8870668741:AAHL2cO1BWoHau-bVmBLziMadDj94SnU7IA'
CHANNEL_ID = -1004489395750
RUCAPTCHA_API_KEY = 'a2e1b40a756ccc16c11ede55eb2c6567'
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

# ===== КЕШ ПОДПИСОК =====
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

async def solve_captcha(api_key):
    try:
        async with aiohttp.ClientSession() as session:
            session.headers.update({'User-Agent': 'Mozilla/5.0'})
            async with session.get("https://telegram.org/support", timeout=15) as resp:
                html = await resp.text()
                match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
                if not match:
                    return None, None
                sitekey = match.group(1)
            
            data = {
                "key": api_key,
                "method": "turnstile",
                "sitekey": sitekey,
                "pageurl": "https://telegram.org/support",
                "json": 1
            }
            async with session.post("http://rucaptcha.com/in.php", data=data, timeout=30) as resp:
                res = await resp.json()
                if res.get("status") != 1:
                    return None, None
                captcha_id = res.get("request")
            
            for _ in range(60):
                await asyncio.sleep(2)
                async with session.get(f"http://rucaptcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1") as resp:
                    data = await resp.json()
                    if data.get("status") == 1:
                        return data.get("request"), session
                    elif "CAPCHA_NOT_READY" in str(data):
                        continue
                    else:
                        return None, None
            return None, None
    except:
        return None, None

async def send_web_report(api_key, name, phone, text):
    token, session = await solve_captcha(api_key)
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
        async with session.post("https://telegram.org/support", headers=headers, data=data, timeout=15) as r:
            if r.status == 200:
                return True, f"код: {r.status}"
            else:
                return False, f"код: {r.status}"
    except:
        return False, "ошибка"

async def try_connect(session_path, timeout=15):
    client = None
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await asyncio.wait_for(client.start(), timeout=timeout)
        await asyncio.wait_for(client.get_me(), timeout=timeout)
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

def get_all_sessions():
    sessions = []
    if os.path.exists(SESSIONS_DIR):
        for root, dirs, files in os.walk(SESSIONS_DIR):
            for f in files:
                if f.endswith('.session'):
                    sessions.append(os.path.join(root, f))
    return sessions

async def get_live_session():
    """Находит первую живую сессию и возвращает клиент"""
    all_sessions = get_all_sessions()
    if not all_sessions:
        return None
    
    for session_path in all_sessions:
        client = await try_connect(session_path, timeout=10)
        if client:
            return client
    return None

async def analyze_with_gemini(texts, target):
    """Анализирует текст через Gemini"""
    if not GEMINI_API_KEY or not GEMINI_MODEL:
        return None, "Нет API-ключа Gemini"
    
    messages_text = "\n".join(texts[:100])
    
    if len(messages_text) < 10:
        return None, "Слишком мало текста для анализа"
    
    prompt = f"""
Ты — AI-аналитик Telegram. Проанализируй сообщения из канала и определи, есть ли нарушения правил Telegram.

**Канал:** {target}

**Сообщения:**
{messages_text}

**Ответь строго в формате JSON (без лишнего текста):**
{{
    "violation": "название_нарушения" или null,
    "confidence": 0-100,
    "explanation": "почему ты так считаешь (на русском)",
    "severity": "high" / "medium" / "low" или null
}}

**Типы нарушений:**
- "drugs" — наркотики
- "spam" — спам
- "porn" — порнография
- "violence" — насилие
- "scam" — мошенничество
- "personal" — личные данные
- "bullying" — травля

Не выдумывай. Если нарушений нет — укажи "violation": null.
Ответь ТОЛЬКО JSON.
"""
    
    try:
        response = await asyncio.to_thread(
            GEMINI_MODEL.generate_content,
            prompt
        )
        
        result_text = response.text.strip()
        
        if result_text.startswith('```json'):
            result_text = result_text.replace('```json', '').replace('```', '').strip()
        elif result_text.startswith('```'):
            result_text = result_text.replace('```', '').strip()
        
        try:
            result = json.loads(result_text)
            return result, None
        except json.JSONDecodeError:
            return None, "Ошибка парсинга JSON от Gemini"
            
    except Exception as e:
        return None, f"Ошибка Gemini: {str(e)[:100]}"

# ===== ОТПРАВКА TELEHON (ВСЕ СЕССИИ) =====
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
    error_details = []

    async def send_one(session_path, index):
        nonlocal errors, error_details
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=15)
            if not client:
                errors += 1
                error_details.append(f"{session_name}: не удалось подключиться")
                return
            
            if is_message:
                try:
                    chat = await client.get_entity(chat_username)
                    await client(ReportPeerRequest(peer=chat, reason=InputReportReasonSpam(), message=""))
                    print(f"[{session_name}] ✅ Успешно")
                except UsernameNotOccupiedError:
                    errors += 1
                    error_details.append(f"{session_name}: канал не найден")
                except Exception as e:
                    errors += 1
                    error_details.append(f"{session_name}: {str(e)[:50]}")
            else:
                try:
                    entity = await client.get_entity(target)
                    await client(ReportPeerRequest(peer=entity, reason=InputReportReasonSpam(), message=""))
                    print(f"[{session_name}] ✅ Успешно")
                except UsernameNotOccupiedError:
                    errors += 1
                    error_details.append(f"{session_name}: цель не найдена")
                except Exception as e:
                    errors += 1
                    error_details.append(f"{session_name}: {str(e)[:50]}")
        except FloodWaitError as e:
            errors += 1
            error_details.append(f"{session_name}: FloodWait {e.seconds}s")
            if edit_callback:
                await edit_callback(f"⏳ Отправка Telethon... ({index}/{total}) FloodWait {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 30))
        except Exception as e:
            errors += 1
            error_details.append(f"{session_name}: {str(e)[:50]}")
        finally:
            if client:
                await client.disconnect()

    tasks = [send_one(session_path, i+1) for i, session_path in enumerate(all_sessions)]
    await asyncio.gather(*tasks)

    for detail in error_details:
        print(f"[ERROR] {detail}")

    result = "✅ Telethon — ОТПРАВЛЕНО"
    if errors > 0:
        result += f"\n⚠️ Ошибок: {errors}"

    try:
        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
            channel = await temp_client.get_entity(CHANNEL_ID)
            await temp_client.send_message(channel, f"✅ Telethon репорт на {target}\nОшибок: {errors}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить в канал: {e}")

    if edit_callback:
        await edit_callback(result)
    return result

# ===== ОТПРАВКА МИКС (ТОЛЬКО AU + US) =====
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

    for session_path in au_sessions:
        current += 1
        if edit_callback:
            await edit_callback(f"⏳ Отправка микс-жалобы... ({current}/{total})")
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
        except Exception as e:
            print(f"[AU] {session_name} ошибка: {e}")
        finally:
            if client:
                await client.disconnect()

    for session_path in us_sessions:
        current += 1
        if edit_callback:
            await edit_callback(f"⏳ Отправка микс-жалобы... ({current}/{total})")
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
        except Exception as e:
            print(f"[US] {session_name} ошибка: {e}")
        finally:
            if client:
                await client.disconnect()

    try:
        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
            channel = await temp_client.get_entity(CHANNEL_ID)
            await temp_client.send_message(channel, f"✅ Микс-жалоба отправлена на {target}")
    except Exception as e:
        print(f"[ERROR] Не удалось отправить в канал: {e}")

    if edit_callback:
        await edit_callback("✅ Микс-жалоба отправлена!")
    return "✅ Микс-жалоба отправлена!"

# ===== ОПЕРАТОР =====
async def send_operator_report(user_id, username, edit_callback=None):
    phone = generate_phone()
    name = "Operator Report"
    text = f"Complaint against drug shop operator: {username}"
    success, msg = await send_web_report(RUCAPTCHA_API_KEY, name, phone, text)
    if success:
        result = f"✅ Оператор {username}"
        try:
            async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
                channel = await temp_client.get_entity(CHANNEL_ID)
                await temp_client.send_message(channel, f"✅ Оператор {username} — жалоба отправлена")
        except:
            pass
    else:
        result = f"❌ Оператор {username}: {msg}"
    if edit_callback:
        await edit_callback(result)
    return result

# ===== AI =====
class PowerAI:
    def generate_mix_text(self, target, target_type, violation_desc, evidence_links=""):
        variants = [
            f"URGENT REPORT — TELEGRAM TERMS OF SERVICE VIOLATION. Target: {target} ({target_type}). Violation: {violation_desc}. This entity systematically violates Telegram rules by engaging in {violation_desc}, which directly contravenes Telegram ToS (Community Guidelines). Evidence has been documented and includes public accessibility of violating content, active user engagement with prohibited material, and clear intent to bypass Telegram's moderation systems.",
            f"EMERGENCY COMPLAINT — {target} ({target_type}) is actively violating Telegram's Community Guidelines through {violation_desc}. This account/channel is involved in illegal activities that are clearly prohibited by Telegram ToS. Multiple instances of violations have been observed and documented. Requesting immediate investigation and account suspension.",
            f"OFFICIAL REPORT — Telegram rule violation detected on {target} ({target_type}). The entity is engaged in {violation_desc}, which falls under prohibited content according to Telegram's Terms of Service. Evidence includes public posts, user interactions, and clear violation patterns. Requesting immediate action against this account."
        ]
        report = random.choice(variants)
        if evidence_links:
            report += f" DIRECT EVIDENCE: {evidence_links}."
        report += " Signed, Telegram Compliance Reporting System."
        return report

class ContentAnalyzer:
    def __init__(self):
        self.keywords = {
            "drugs": [
                "buy", "cocaine", "heroin", "meth", "drugs", "shop", "dealer",
                "наркотик", "кокаин", "героин", "метамфетамин", "экстази", "марихуана",
                "продажа", "продам", "куплю", "закладка", "шишки", "бошки", "соль",
                "трава", "план", "вещество", "синтетика", "аптечка"
            ],
            "spam": ["spam", "ad", "promo", "subscribe", "referral", "реклама", "подпишись", "пиар"],
            "porn": ["porn", "sex", "nude", "18+", "порно", "секс", "голый", "эротика"],
            "violence": ["violence", "kill", "death", "blood", "weapon", "насилие", "убить", "смерть", "оружие"],
            "scam": ["scam", "pyramid", "invest", "phishing", "лохотрон", "пирамида", "инвестиции", "развод"],
            "personal": ["passport", "address", "phone", "personal", "data", "паспорт", "адрес", "телефон", "личные"],
            "bullying": ["bullying", "harass", "threat", "insult", "травля", "угроза", "оскорбление", "буллинг"]
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
        # Используем ОДНУ живую сессию
        client = await get_live_session()
        if not client:
            return None, "Нет живых сессий для анализа"

        messages = []
        target_type = "unknown"
        entity = None

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
                await client.disconnect()
                return None, "Неверная ссылка"

            try:
                await client(JoinChannelRequest(entity))
                await asyncio.sleep(5)
            except:
                pass

            all_messages = []
            offset_id = 0
            limit = 100
            MAX_MESSAGES = 200
            total_loaded = 0

            while total_loaded < MAX_MESSAGES:
                try:
                    msgs = await client.get_messages(entity, limit=min(limit, MAX_MESSAGES - total_loaded), offset_id=offset_id)
                    if not msgs:
                        break
                    for m in msgs:
                        if m and m.text:
                            all_messages.append(m.text)
                    offset_id = msgs[-1].id
                    total_loaded += len(msgs)
                    if len(msgs) < limit:
                        break
                except:
                    break

            messages = all_messages

        except Exception as e:
            await client.disconnect()
            return None, f"Ошибка: {e}"

        await client.disconnect()

        if not messages:
            return None, "Нет сообщений"

        # === АНАЛИЗ ЧЕРЕЗ GEMINI ===
        if GEMINI_API_KEY and GEMINI_MODEL:
            try:
                ai_result, error = await analyze_with_gemini(messages, target)
                
                if ai_result and ai_result.get('violation'):
                    violation = ai_result['violation']
                    percent = ai_result.get('confidence', 70)
                    explanation = ai_result.get('explanation', '')
                    severity = ai_result.get('severity', 'medium')
                    
                    print(f"[GEMINI] Найдено нарушение: {violation} ({percent}%)")
                    print(f"[GEMINI] Объяснение: {explanation}")
                    
                    # Отправляем отчёт в канал
                    try:
                        async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
                            channel = await temp_client.get_entity(CHANNEL_ID)
                            report_text = (
                                f"🔍 AI Анализ (Gemini): {target}\n"
                                f"⚠️ Нарушение: {violation.upper()} ({percent}%)\n"
                                f"📝 Объяснение: {explanation}\n"
                                f"📊 Сообщений: {len(messages)}\n"
                                f"🚨 Серьёзность: {severity.upper()}"
                            )
                            await temp_client.send_message(channel, report_text)
                    except Exception as e:
                        print(f"[GEMINI] Не удалось отправить в канал: {e}")
                    
                    return {
                        "results": {},
                        "violation": violation,
                        "percent": percent,
                        "messages": messages,
                        "target_type": target_type,
                        "count": len(messages)
                    }, None
                    
                elif ai_result:
                    print(f"[GEMINI] Нарушений не найдено")
            except Exception as e:
                print(f"[GEMINI] Ошибка: {e}")

        # === ФОЛБЭК: Старый анализ по ключевым словам ===
        results = self.analyze_messages(messages)
        violation, percent = self.get_violation(results)

        result = {
            "results": results,
            "violation": violation,
            "percent": percent,
            "messages": messages,
            "target_type": target_type,
            "count": len(messages)
        }

        if violation:
            try:
                async with TelegramClient('temp', API_ID, API_HASH) as temp_client:
                    channel = await temp_client.get_entity(CHANNEL_ID)
                    report_text = (
                        f"🔍 AI Анализ: {target}\n"
                        f"Тип: {target_type.upper()}\n"
                        f"Нарушение: {violation.upper()} ({percent}%)\n"
                        f"Сообщений: {len(messages)}\n"
                        f"⚠️ Найдено нарушение!"
                    )
                    await temp_client.send_message(channel, report_text)
            except Exception as e:
                print(f"[AI] Не удалось отправить в канал: {e}")

        return result, None

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
        bot = await TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        print("Bot connected")

        user_states = {}
        user_data = {}
        active_messages = {}

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
                    status = "✅" if "успешно" in r.get('type', '').lower() else "⏳"
                    text += f"{i}. {r.get('target', '')} {status} {r.get('time', '')}\n"
                await upd(text, [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                return
            
            if data == "back_to_start":
                if has_subscription(user_id):
                    buttons = [
                        [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                        [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")],
                        [KeyboardButtonCallback("📜 История", b"history")]
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
                    user_data[user_id] = {'target': target}
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
                    
                    async def edit_callback(new_text):
                        await upd(new_text)
                    
                    result = await send_telethon_report(user_id, target, edit_callback)
                    
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
                    
                    async def edit_callback(new_text):
                        await upd(new_text)
                    
                    result = await send_operator_report(user_id, username, edit_callback)
                    
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
                    await upd("⏳ Сканирование через Gemini...")
                    
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
                    
                    report = f"🔍 AI-АНАЛИЗ (Gemini)\n\nЦель: {target}\nТип: {target_type.upper()}\nСообщений: {len(messages)}\n"
                    if violation:
                        report += f"⚠️ Нарушение: {violation.upper()} ({percent}%)\n❌ Найдено!"
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
                report_text = ai.generate_mix_text(target, target_type, violation_desc, evidence_links)
                user_states.pop(user_id, None)
                
                await upd("⏳ Отправка микс-жалобы...")
                
                async def edit_callback(new_text):
                    await upd(new_text)
                
                result = await send_mix_report(user_id, target, report_text, edit_callback)
                
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
            user_id = event.sender_id
            await event.delete()
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            if has_subscription(user_id):
                buttons = [
                    [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                    [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("👨‍💻 Разработчик", b"developer")],
                    [KeyboardButtonCallback("📜 История", b"history")]
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
