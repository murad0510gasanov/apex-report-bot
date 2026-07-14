# app.py — APEX REPORT (ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)
import os
import sys
import json
import asyncio
import re
import random
import time
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from aiohttp import web
import aiohttp
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from telethon import TelegramClient, events, errors
    from telethon.tl.types import KeyboardButtonCallback
    from telethon.tl.functions.account import ReportPeerRequest
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.types import InputReportReasonSpam
    from telethon.errors import FloodWaitError, UsernameNotOccupiedError, ChannelPrivateError, AuthKeyError
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
ERROR_LOG = os.path.join(BASE_DIR, 'errors.log')
MAIL_FILE = os.path.join(BASE_DIR, 'mail.txt')

_subs_cache = {}
_subs_cache_time = 0
pending_requests = {}
bot_instance = None

# ===== MAILER ФУНКЦИИ =====
def load_mail_creds():
    if not os.path.exists(MAIL_FILE):
        return []
    creds = []
    with open(MAIL_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                creds.append((parts[0], parts[1]))
    return creds

def send_mail_sync(sender, passwd, target, subject, body, idx, total, results):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = target
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(sender, passwd)
            s.send_message(msg)
        results.append(f"[{idx+1}/{total}] {sender} -> {target} : УСПЕШНО ✅")
    except Exception as e:
        error_msg = str(e)
        if "Authentication failed" in error_msg:
            error_msg = "Неверный пароль или аккаунт заблокирован"
        elif "Daily limit" in error_msg:
            error_msg = "Дневной лимит отправки исчерпан"
        elif "Username and Password not accepted" in error_msg:
            error_msg = "Логин/пароль не приняты (включи доступ для ненадежных приложений)"
        results.append(f"[{idx+1}/{total}] {sender} -> {target} : ПРОВАЛ ❌ ({error_msg[:50]})")

def run_mailer(creds, targets, subject, body, max_per_account):
    results = []
    threads = []
    used = 0
    total_creds = len(creds)
    
    for target in targets:
        for i in range(max_per_account):
            if used >= total_creds:
                break
            sender, pwd = creds[used]
            th = threading.Thread(
                target=send_mail_sync,
                args=(sender, pwd, target, subject, body, used, total_creds, results)
            )
            threads.append(th)
            th.start()
            time.sleep(2)
            used += 1
        if used >= total_creds:
            break
    
    for th in threads:
        th.join()
    
    return results

def log_error(msg):
    try:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] {msg}\n")
        print(msg)
    except:
        pass

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

async def send_log_to_channel(
    user_id: int,
    username: str = None,
    method: str = "Микс",
    target: str = None,
    au_success: int = 0,
    au_total: int = 0,
    tida_success: int = 0,
    tida_total: int = 0,
    au_text: str = None,
    tida_text: str = None,
    status: str = "✅ Отправка завершена",
    error: str = None
):
    global bot_instance
    if not bot_instance:
        return
    if username:
        user_display = f"@{username} (ID: {user_id})"
    else:
        user_display = f"ID: {user_id}"
    log_text = f"{status}\n"
    log_text += f"👤 Пользователь: {user_display}\n"
    log_text += f"🚀 Метод: {method}\n"
    if target:
        log_text += f"🔗 Ссылка: {target}\n"
    if error:
        log_text += f"❌ Ошибка: {error}\n"
    else:
        if method in ["Микс", "Mix"]:
            au_total = au_total or 0
            tida_total = tida_total or 0
            total_success = au_success + tida_success
            total_total = au_total + tida_total
            log_text += f"📊 AU: {au_success}/{au_total} | TIDA: {tida_success}/{tida_total}\n"
            log_text += f"🔎 Итого: {total_success}/{total_total}\n"
            if au_text:
                log_text += f"\n📝 AU текст:\n{au_text}\n"
            if tida_text:
                log_text += f"\n📝 TIDA текст:\n{tida_text}\n"
        elif method in ["Telethon", "Оператор"]:
            log_text += f"📊 Результат: {au_success}/{au_total}\n"
        elif method == "Веб-жалоба":
            log_text += f"📊 Результат: {au_success}/{au_total}\n"
        elif method == "Рассылка":
            log_text += f"📊 Отправлено: {au_success}/{au_total}\n"
    try:
        await bot_instance.send_message(CHANNEL_ID, log_text)
    except Exception as e:
        log_error(f"Channel log error: {e}")

def generate_phone():
    return f"+7{random.randint(1000000000, 9999999999)}"

async def solve_captcha(api_key):
    try:
        async with aiohttp.ClientSession() as session:
            session.headers.update({'User-Agent': 'Mozilla/5.0'})
            async with session.get("https://telegram.org/support", timeout=10) as resp:
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
            async with session.post("http://rucaptcha.com/in.php", data=data, timeout=15) as resp:
                res = await resp.json()
                if res.get("status") != 1:
                    return None, None
                captcha_id = res.get("request")
            
            for _ in range(5):
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

# ===== НОВАЯ try_connect (с нормальными таймаутами и логами) =====
async def try_connect(session_path, timeout=15, retries=2):
    session_name = os.path.basename(session_path)
    for attempt in range(retries):
        client = None
        try:
            client = TelegramClient(session_path, API_ID, API_HASH)
            await asyncio.wait_for(client.start(), timeout=timeout)
            me = await asyncio.wait_for(client.get_me(), timeout=timeout)
            print(f"[{session_name}] ✅ Подключена (ID: {me.id})")
            return client
        except asyncio.TimeoutError:
            print(f"[{session_name}] ⏳ Таймаут подключения (попытка {attempt+1}/{retries})")
            if client:
                await client.disconnect()
        except AuthKeyError:
            print(f"[{session_name}] ❌ Невалидная сессия (AuthKeyError)")
            if client:
                await client.disconnect()
            return None
        except Exception as e:
            error_msg = str(e)
            if "Password" in error_msg:
                print(f"[{session_name}] 🔐 Требуется 2FA")
            elif "phone" in error_msg:
                print(f"[{session_name}] 📱 Требуется код подтверждения")
            else:
                print(f"[{session_name}] ❌ Ошибка: {error_msg[:50]}")
            if client:
                await client.disconnect()
        if attempt == retries - 1:
            return None
        await asyncio.sleep(1)
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

async def generate_complaint_text(target, violation, description, links):
    prompt = f"""Generate a formal complaint in English based on this description:
{description}

Channel: {target}
Violation type: {violation}
Links to violating messages: {', '.join(links) if links else 'No specific links'}

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
                    return f"I would like to report a Telegram channel involved in {violation}.\n\nChannel: {target}\n\n{description}\n\nReported messages:\n{chr(10).join(links) if links else 'No specific links'}\n\nPlease review this content and take appropriate action.\n\nThank you."
    except:
        return f"I would like to report a Telegram channel involved in {violation}.\n\nChannel: {target}\n\n{description}\n\nReported messages:\n{chr(10).join(links) if links else 'No specific links'}\n\nPlease review this content and take appropriate action.\n\nThank you."

def generate_pdf(user_id, reports):
    if not REPORTLAB_AVAILABLE:
        return None
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "APEX REPORT - HISTORY")
    y -= 30
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"User ID: {user_id}")
    y -= 20
    c.drawString(50, y, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total reports: {len(reports)}")
    y -= 20
    for i, report in enumerate(reports, 1):
        if y < 100:
            c.showPage()
            y = 800
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"{i}. {report.get('target', 'Unknown')} - {report.get('type', 'Unknown')} - {report.get('time', 'Unknown')}")
        if report.get('links'):
            y -= 12
            c.drawString(50, y, f"   Links: {', '.join(report['links'][:3])}")
        y -= 15
    c.save()
    buffer.seek(0)
    return buffer

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

    clean_target = target

    total = len(all_sessions)
    au_sessions = [s for s in all_sessions if 'au' in s]
    us_sessions = [s for s in all_sessions if 'us' in s]
    au_success = 0
    tida_success = 0
    current = 0
    au_texts = []
    tida_texts = []

    print(f"\n📤 Микс — отправка на {clean_target}")
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
            await client.send_message('@AUReportBot', clean_target)
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
            au_success += 1
            au_texts.append(text)
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
            await client.send_message('@TIDABot', clean_target)
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
            tida_success += 1
            tida_texts.append(text)
            print(f"[US] {session_name} ✅ Отправлено")
        except Exception as e:
            print(f"[US] {session_name} ❌ {str(e)[:50]}")
        finally:
            await client.disconnect()

    print(f"\n📊 Микс — отправлено {current}/{total} сессий")
    
    au_text_full = "\n".join(au_texts[:1]) if au_texts else None
    tida_text_full = "\n".join(tida_texts[:1]) if tida_texts else None
    await send_log_to_channel(
        user_id=user_id,
        username=None,
        method="Микс",
        target=clean_target,
        au_success=au_success,
        au_total=len(au_sessions),
        tida_success=tida_success,
        tida_total=len(us_sessions),
        au_text=au_text_full,
        tida_text=tida_text_full,
        status="✅ Отправка завершена"
    )
    return "✅ Микс-жалоба отправлена!"

# ===== ОПЕРАТОР =====
async def send_operator_report(user_id, target, edit_callback=None):
    try:
        clean_target = target
        text = f"This account {clean_target} is a known operator of a drug shop. It violates Telegram's Terms of Service by facilitating the sale of illegal substances."
        
        result = await send_mix_report(user_id, clean_target, text, edit_callback=None)
        if "✅" in result:
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="Оператор (микс)",
                target=clean_target,
                au_success=1,
                au_total=1,
                status="✅ Отправка завершена"
            )
            if edit_callback:
                await edit_callback(f"✅ Оператор {clean_target} — жалоба отправлена (микс)")
            return f"✅ Оператор {clean_target} — жалоба отправлена (микс)"
        else:
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="Оператор (микс)",
                target=clean_target,
                status="❌ Ошибка отправки",
                error="Не удалось отправить жалобу через микс"
            )
            if edit_callback:
                await edit_callback(f"❌ Оператор {clean_target} — не удалось отправить жалобу")
            return f"❌ Оператор {clean_target} — не удалось отправить жалобу"
    except Exception as e:
        result = f"❌ Ошибка: {str(e)[:50]}"
        if edit_callback:
            await edit_callback(result)
        return result

async def send_web_complaint(user_id, text, edit_callback=None):
    try:
        phone = generate_phone()
        name = "User Complaint"
        
        success, msg = await send_web_report(RUCAPTCHA_API_KEY, name, phone, text)
        if success:
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="Веб-жалоба",
                target="telegram.org/support",
                au_success=1,
                au_total=1,
                status="✅ Отправка завершена"
            )
            if edit_callback:
                await edit_callback("✅ Веб-жалоба отправлена")
            return "✅ Веб-жалоба отправлена"
        else:
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="Веб-жалоба",
                target="telegram.org/support",
                status="❌ Ошибка отправки",
                error=msg
            )
            if edit_callback:
                await edit_callback(f"❌ Ошибка: {msg}")
            return f"❌ Ошибка: {msg}"
    except Exception as e:
        result = f"❌ Ошибка: {str(e)[:50]}"
        if edit_callback:
            await edit_callback(result)
        return result

# ===== НОВАЯ send_telethon_report (с обработкой ошибок и таймаутами) =====
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

    clean_target = target

    is_bot = False
    if clean_target.startswith('@'):
        if '/' not in clean_target:
            is_bot = True
    elif 't.me/' in clean_target:
        if not re.search(r't\.me/[^/]+/\d+', clean_target):
            is_bot = True

    message_match = re.search(r't\.me/([^/]+)/(\d+)', clean_target)
    is_message = bool(message_match)
    chat_username = message_match.group(1) if is_message else None

    total = len(all_sessions)
    errors = 0
    success_count = 0

    print(f"\n📤 Telethon — отправка на {clean_target}")
    print(f"📁 Всего сессий: {total}")

    async def send_one(session_path, index):
        nonlocal errors, success_count
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=15, retries=2)
            if not client:
                errors += 1
                print(f"[{session_name}] ❌ Не удалось подключиться")
                return

            # ===== Если бот =====
            if is_bot:
                if 't.me/' in clean_target:
                    username = clean_target.split('t.me/')[-1].split('/')[0]
                else:
                    username = clean_target.replace('@', '')
                bot_username = f"@{username}"
                print(f"[{session_name}] ⏳ Отправка боту {bot_username}")
                
                await client.send_message(bot_username, '/start')
                await asyncio.sleep(2)
                
                await client.send_message(bot_username, clean_target)
                await asyncio.sleep(2)
                
                found_button = False
                async for msg in client.iter_messages(bot_username, limit=10):
                    if msg.buttons:
                        for row in msg.buttons:
                            for btn in row:
                                btn_text = btn.text.lower() if btn.text else ''
                                if any(keyword in btn_text for keyword in ['жалоб', 'report', 'пожаловаться', 'complaint']):
                                    await btn.click()
                                    await asyncio.sleep(1)
                                    found_button = True
                                    print(f"[{session_name}] Нажата кнопка: {btn.text}")
                                    break
                            if found_button:
                                break
                        if found_button:
                            break
                
                if not found_button:
                    print(f"[{session_name}] ⚠️ Кнопка жалобы не найдена")
                
                success_count += 1
                print(f"[{session_name}] ✅ Успешно (бот)")

            # ===== Если сообщение =====
            elif is_message and chat_username:
                try:
                    chat = await client.get_entity(f"@{chat_username}")
                    await client(ReportPeerRequest(peer=chat, reason=InputReportReasonSpam(), message=""))
                    success_count += 1
                    print(f"[{session_name}] ✅ Успешно (сообщение)")
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

            # ===== Если канал/пользователь =====
            else:
                try:
                    if 't.me/' in clean_target:
                        username = clean_target.split('t.me/')[-1].split('/')[0]
                    else:
                        username = clean_target.replace('@', '')
                    entity = await client.get_entity(f"@{username}")
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
        except Exception as e:
            errors += 1
            print(f"[{session_name}] ❌ Критическая ошибка: {str(e)[:50]}")
        finally:
            if client:
                await client.disconnect()

    # ===== Запускаем все сессии параллельно с таймаутом =====
    try:
        tasks = [send_one(session_path, i+1) for i, session_path in enumerate(all_sessions)]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
    except asyncio.TimeoutError:
        print("⏳ Общий таймаут выполнения (60 сек)")

    print(f"\n📊 Результат: {success_count}/{total} успешно, {errors} ошибок")

    await send_log_to_channel(
        user_id=user_id,
        username=None,
        method="Telethon",
        target=clean_target,
        au_success=success_count,
        au_total=total,
        status="✅ Отправка завершена"
    )

    result_text = f"✅ Telethon — отправлено: {success_count}\n❌ Ошибок: {errors}"

    if edit_callback:
        await edit_callback(result_text)
    return result_text

# ===== AI АНАЛИЗАТОР =====
class AIAnalyzer:
    def __init__(self):
        self.last_result = None
        self.keywords = {
            "drugs": ["наркотик", "кокаин", "героин", "спайс", "соль", "шишки", "закладка", "продажа", "продам", "drugs", "cocaine", "heroin", "метамфетамин", "экстази", "марихуана", "анаша", "план", "бошки", "гашиш", "скорость", "кристалл", "синтетика", "трава", "порошок", "белый", "кристаллы", "меф", "амф"],
            "personal": ["паспорт", "фио", "ф.и.о", "адрес", "прописка", "регистрация", "дом", "квартира", "подъезд", "этаж", "улица", "телефон", "снилс", "инн", "личные данные", "passport", "address", "phone"],
            "porn": ["порно", "порнография", "секс", "эротика", "голый", "голая", "интим", "18+", "porn", "sex", "nude", "adult"],
            "violence": ["насилие", "убить", "убийство", "смерть", "оружие", "пистолет", "нож", "угроза", "избить", "кровь", "взорвать", "бомба", "violence", "kill", "death", "weapon", "gun", "threat"],
            "spam": ["спам", "реклама", "пиар", "подпишись", "подписка", "рассылка", "spam", "ad", "promo", "subscribe"],
            "scam": ["лохотрон", "развод", "обман", "мошенник", "пирамида", "инвестиции", "фишинг", "scam", "fraud", "phishing"],
            "bullying": ["буллинг", "травля", "оскорбление", "унижение", "bullying", "harassment", "insult"]
        }

    def fallback_analyze(self, text):
        text_lower = text.lower()
        results = {}
        for category, words in self.keywords.items():
            count = 0
            for word in words:
                if word in text_lower:
                    count += 1
            if count > 0:
                results[category] = min(50 + (count * 10), 100)
            else:
                results[category] = 0
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
            entity = None
            if 't.me/' in target:
                clean_target = target.replace('https://t.me/', '').replace('t.me/', '')
                if '/' in clean_target and not clean_target.startswith('joinchat') and not clean_target.startswith('+'):
                    chat_username = clean_target.split('/')[0]
                    try:
                        entity = await client.get_entity(f"@{chat_username}")
                    except:
                        entity = await client.get_entity(target)
                else:
                    try:
                        entity = await client.get_entity(target)
                        chat_username = getattr(entity, 'username', 'unknown')
                    except:
                        chat_username = clean_target.split('/')[0] if '/' in clean_target else clean_target
                        entity = await client.get_entity(f"@{chat_username}")
                target_type = "канал"
            elif target.startswith('@'):
                chat_username = target.replace('@', '')
                entity = await client.get_entity(target)
                target_type = "бот" if entity.bot else "пользователь"
            else:
                await client.disconnect()
                return None, "❌ Неверная ссылка. Отправьте ссылку на канал (https://t.me/...)"

            if not entity:
                await client.disconnect()
                return None, "❌ Не удалось получить информацию о канале. Проверьте ссылку."

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

            try:
                msgs = await asyncio.wait_for(client.get_messages(entity, limit=50), timeout=15)
                if not msgs:
                    await client.disconnect()
                    return None, "❌ Нет сообщений в канале"
                for m in msgs:
                    if m and m.text:
                        messages.append(m.text)
                        message_ids.append(m.id)
            except asyncio.TimeoutError:
                await client.disconnect()
                return None, "❌ Таймаут при чтении сообщений"
            except Exception as e:
                await client.disconnect()
                return None, f"❌ Не удалось прочитать сообщения: {str(e)[:50]}"

        except UsernameNotOccupiedError:
            await client.disconnect()
            return None, f"❌ Канал {target} не найден. Проверьте ссылку."
        except Exception as e:
            await client.disconnect()
            return None, f"❌ Ошибка: {str(e)[:50]}"

        await client.disconnect()

        if not messages:
            return None, "❌ Нет сообщений"

        result = await analyze_with_ai(messages, target)
        
        if result.get("error") or not result.get("violation"):
            print(f"[AI] Ошибка или нарушение не найдено, используем фолбэк")
            results = self.fallback_analyze(" ".join(messages))
            violation, percent = self.get_violation(results)
            if violation:
                result = {
                    "violation": violation,
                    "severity": "high" if percent >= 70 else "medium",
                    "explanation": f"Найдено нарушение типа {violation} по ключевым словам (уверенность {percent}%)",
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
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="AI-анализ",
                target=target,
                au_success=1,
                au_total=1,
                status=f"🔍 Нарушение: {result['violation'].upper()} ({result.get('severity', 'medium').upper()})",
                error=result.get('explanation', '')
            )
        else:
            await send_log_to_channel(
                user_id=user_id,
                username=None,
                method="AI-анализ",
                target=target,
                au_success=0,
                au_total=1,
                status="✅ Нарушений не найдено"
            )

        return result, None

    async def check_pending_requests(self, bot_instance):
        while True:
            try:
                await asyncio.sleep(10)
                for user_id, req in list(pending_requests.items()):
                    if req.get("status") != "waiting":
                        continue
                    
                    client = await try_connect(req["client_filename"], timeout=10, retries=2)
                    if not client:
                        continue
                    
                    try:
                        msgs = await asyncio.wait_for(client.get_messages(req["entity"], limit=1), timeout=10)
                        if msgs:
                            req["status"] = "approved"
                            print(f"[JOIN] Заявка для {req['chat_username']} одобрена!")
                            
                            messages = []
                            message_ids = []
                            all_msgs = await asyncio.wait_for(client.get_messages(req["entity"], limit=50), timeout=15)
                            for m in all_msgs:
                                if m and m.text:
                                    messages.append(m.text)
                                    message_ids.append(m.id)
                            
                            if messages:
                                result = await analyze_with_ai(messages, req["target"])
                                if result.get("error") or not result.get("violation"):
                                    results = self.fallback_analyze(" ".join(messages))
                                    violation, percent = self.get_violation(results)
                                    if violation:
                                        result = {
                                            "violation": violation,
                                            "severity": "high" if percent >= 70 else "medium",
                                            "explanation": f"Найдено нарушение типа {violation} по ключевым словам (уверенность {percent}%)",
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
                                    except Exception as e:
                                        log_error(f"Ошибка отправки результата пользователю: {e}")
                                else:
                                    try:
                                        await bot_instance.send_message(user_id, f"🔍 AI-АНАЛИЗ\n\nЦель: {req['target']}\n✅ Нарушений не найдено.")
                                    except Exception as e:
                                        log_error(f"Ошибка отправки результата пользователю: {e}")
                            
                            await client.disconnect()
                            pending_requests.pop(user_id, None)
                        else:
                            await client.disconnect()
                    except asyncio.TimeoutError:
                        await client.disconnect()
                    except Exception as e:
                        await client.disconnect()
                        log_error(f"Ошибка в check_pending_requests: {e}")
            except Exception as e:
                log_error(f"Ошибка в check_pending_requests: {e}")

    async def analyze_single_message(self, message_text, link):
        result = await analyze_with_ai([message_text], link, single=True)
        if result.get("error") or not result.get("violation"):
            results = self.fallback_analyze(message_text)
            violation, percent = self.get_violation(results)
            if violation:
                result = {
                    "violation": violation,
                    "severity": "high" if percent >= 70 else "medium",
                    "explanation": f"Найдено нарушение типа {violation} по ключевым словам (уверенность {percent}%)",
                    "links": [link]
                }
            else:
                result = {"violation": None, "severity": None, "explanation": "Нарушений не найдено.", "links": []}
        if result.get("violation") and not result.get("links"):
            result["links"] = [link]
        self.last_result = result
        return result

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
        log_error(f"[SUB-BOT] Ошибка: {e}")

async def main_bot():
    global bot_instance
    try:
        bot = TelegramClient('bot_session', API_ID, API_HASH)
        await bot.start(bot_token=BOT_TOKEN)
        bot_instance = bot
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
                    [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("🛠 Поддержка", b"support")],
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
                    [KeyboardButtonCallback("📧 Рассылка", b"mailer_menu")],
                    [KeyboardButtonCallback("🛠 Поддержка", b"support")],
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

            if data == "support":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_support_message'
                await upd("📩 Напишите ваш вопрос или сообщение для поддержки.\n\nМы ответим вам в ближайшее время.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if data == "history":
                history = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                if not history:
                    await upd("📜 ИСТОРИЯ\n\nНет записей.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                page = user_data.get(user_id, {}).get('history_page', 0)
                items_per_page = 5
                total_pages = max(1, (len(history) + items_per_page - 1) // items_per_page)
                if page >= total_pages:
                    page = total_pages - 1
                start = page * items_per_page
                end = min(start + items_per_page, len(history))
                text = f"📜 ИСТОРИЯ (стр. {page+1}/{total_pages})\n\n"
                for i, r in enumerate(history[start:end], start+1):
                    status = "✅" if "успешно" in r.get('destination', '').lower() else "⏳"
                    text += f"{i}. {r.get('target', '')} - {status} - {r.get('type', '')}\n"
                buttons = []
                if page > 0:
                    buttons.append(KeyboardButtonCallback("⬅️ Назад", f"history_{page-1}"))
                if page < total_pages - 1:
                    buttons.append(KeyboardButtonCallback("➡️ Вперёд", f"history_{page+1}"))
                buttons.append(KeyboardButtonCallback("📥 Скачать PDF", b"download_pdf"))
                buttons.append(KeyboardButtonCallback("🔙 Назад", b"back_to_start"))
                await upd(text, [buttons] if buttons else None)
                return

            if data.startswith("history_"):
                page = int(data.split("_")[1])
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['history_page'] = page
                await handle_callbacks(event)
                return

            if data == "download_pdf":
                if not REPORTLAB_AVAILABLE:
                    await upd("❌ Ошибка: библиотека reportlab не установлена", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                history = [r for r in load_data().get('reports', []) if r.get('user') == user_id]
                if not history:
                    await upd("📜 Нет отчётов для экспорта.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                pdf_buffer = generate_pdf(user_id, history)
                if pdf_buffer is None:
                    await upd("❌ Ошибка генерации PDF", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                try:
                    await event.reply(file=pdf_buffer, force_document=True)
                except Exception as e:
                    await upd(f"❌ Ошибка отправки PDF: {str(e)[:50]}", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                return

            if data == "back_to_start":
                if has_subscription(user_id):
                    buttons = [
                        [KeyboardButtonCallback("📋 Меню", b"main_menu")],
                        [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("🛠 Поддержка", b"support")],
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
                await upd("📤 МИКС\n\nОтправь ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
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
                await upd("👤 ОПЕРАТОР\n\nОтправь ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if data == "ai_analyze":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                user_states[user_id] = 'waiting_ai_target'
                await upd("🔍 AI-АНАЛИЗ\n\nОтправь ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if data == "mailer_menu":
                if not has_subscription(user_id):
                    await upd("🔒 Нет подписки.", [[KeyboardButtonCallback("🔙 Назад", b"back_to_start")]])
                    return
                creds = load_mail_creds()
                if not creds:
                    await upd("❌ Нет аккаунтов для рассылки. Добавьте их в файл mail.txt", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    return
                user_states[user_id] = 'waiting_mailer_subject'
                await upd("📧 РАССЫЛКА\n\nВведите тему письма:", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
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
                await send_log_to_channel(
                    user_id=target_user_id,
                    username=None,
                    method="AI-жалоба",
                    target=target,
                    au_success=1,
                    au_total=1,
                    status="✅ Отправка завершена"
                )
                await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if data == "send_mail":
                if user_id not in user_data or 'mail_targets' not in user_data.get(user_id, {}):
                    await upd("❌ Ошибка: нет данных для рассылки.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    return
                
                targets = user_data[user_id].get('mail_targets', [])
                if not targets:
                    await upd("❌ Нет получателей.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    user_states.pop(user_id, None)
                    return
                
                subject = user_data[user_id].get('mail_subject', '')
                body = user_data[user_id].get('mail_body', '')
                creds = load_mail_creds()
                max_mails = len(creds)
                
                if max_mails == 0:
                    await upd("❌ Нет аккаунтов в mail.txt", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                    user_states.pop(user_id, None)
                    return
                
                await upd(f"⏳ Отправка писем...\n📊 Аккаунтов: {max_mails}\n📧 Получателей: {len(targets)}\n⏳ Подождите...")
                
                loop = asyncio.get_running_loop()
                results = await loop.run_in_executor(
                    None,
                    run_mailer,
                    creds,
                    targets,
                    subject,
                    body,
                    max_mails
                )
                
                success_count = sum(1 for r in results if "УСПЕШНО" in r)
                error_count = len(results) - success_count
                
                await send_log_to_channel(
                    user_id=user_id,
                    username=None,
                    method="Рассылка",
                    target="email",
                    au_success=success_count,
                    au_total=len(results),
                    status="✅ Рассылка завершена"
                )
                
                report_text = f"📧 РАССЫЛКА ЗАВЕРШЕНА\n\n✅ Успешно: {success_count}\n❌ Ошибок: {error_count}\n📊 Всего: {len(results)}"
                await upd(report_text, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                user_states.pop(user_id, None)
                user_data.pop(user_id, None)
                return

            if data == "add_more":
                user_states[user_id] = 'waiting_mailer_targets'
                await upd("📧 Введите email получателя:", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

        @bot.on(events.NewMessage)
        async def handle_messages(event):
            if event.message.text and event.message.text.startswith('/'):
                return
            user_id = event.sender_id
            text = event.message.text.strip()
            state = user_states.get(user_id)
            
            async def upd(msg_text, buttons=None):
                await update_message(event, msg_text, buttons)

            if state == 'waiting_mix_target':
                if text:
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
                    await upd("❌ Отправьте ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_telethon_target':
                if text:
                    target = text
                    user_states.pop(user_id, None)
                    await upd("⏳ Отправка Telethon...")
                    try:
                        result = await asyncio.wait_for(
                            send_telethon_report(user_id, target, edit_callback=None),
                            timeout=60
                        )
                    except asyncio.TimeoutError:
                        result = "❌ Telethon — таймаут (60 сек)"
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': target,
                        'type': 'Telethon-отчёт',
                        'destination': 'Все сессии',
                        'user': user_id
                    })
                    save_data(data)
                    await send_log_to_channel(
                        user_id=user_id,
                        username=None,
                        method="Telethon",
                        target=target,
                        au_success=1,
                        au_total=1,
                        status="✅ Отправка завершена"
                    )
                    await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                else:
                    await upd("❌ Отправьте ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_operator_target':
                if text:
                    target = text
                    user_states.pop(user_id, None)
                    await upd("⏳ Отправка оператору...")
                    result = await send_operator_report(user_id, target, edit_callback=None)
                    data = load_data()
                    data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': target,
                        'type': 'Оператор',
                        'destination': 'Микс',
                        'user': user_id
                    })
                    save_data(data)
                    await send_log_to_channel(
                        user_id=user_id,
                        username=None,
                        method="Оператор",
                        target=target,
                        au_success=1,
                        au_total=1,
                        status="✅ Отправка завершена"
                    )
                    await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                else:
                    await upd("❌ Отправьте ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_ai_target':
                if text:
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
                    await send_log_to_channel(
                        user_id=user_id,
                        username=None,
                        method="AI-анализ",
                        target=target,
                        au_success=1,
                        au_total=1,
                        status=f"🔍 Нарушение: {violation.upper()} ({severity.upper()})"
                    )
                    await upd(report, buttons)
                else:
                    await upd("❌ Отправьте ссылку", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
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
                await upd("⏳ Генерация текста жалобы через AI...")
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
                await send_log_to_channel(
                    user_id=user_id,
                    username=None,
                    method="Микс",
                    target=target,
                    au_success=1,
                    au_total=1,
                    status="✅ Отправка завершена"
                )
                await upd(result, [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            # ===== MAILER =====
            if state == 'waiting_mailer_subject':
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['mail_subject'] = text
                await event.delete()
                user_states[user_id] = 'waiting_mailer_body'
                await upd("📧 Введите текст письма:", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_mailer_body':
                if user_id not in user_data:
                    user_data[user_id] = {}
                user_data[user_id]['mail_body'] = text
                await event.delete()
                user_states[user_id] = 'waiting_mailer_targets'
                await upd("📧 Введите email получателя:", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_mailer_targets':
                if text:
                    if user_id not in user_data:
                        user_data[user_id] = {}
                    if 'mail_targets' not in user_data[user_id]:
                        user_data[user_id]['mail_targets'] = []
                    user_data[user_id]['mail_targets'].append(text)
                    await event.delete()
                    
                    targets_count = len(user_data[user_id]['mail_targets'])
                    buttons = [
                        [KeyboardButtonCallback("📧 Отправить", b"send_mail")],
                        [KeyboardButtonCallback("➕ Добавить ещё", b"add_more")],
                        [KeyboardButtonCallback("🔙 Назад", b"main_menu")]
                    ]
                    await upd(
                        f"📧 Добавлен: {text}\n\n📧 Всего получателей: {targets_count}\n\n"
                        f"📝 Тема: {user_data[user_id].get('mail_subject', '')}\n"
                        f"📝 Текст: {user_data[user_id].get('mail_body', '')[:50]}...\n\n"
                        f"Нажмите кнопку для отправки или добавьте ещё.",
                        buttons
                    )
                else:
                    await event.delete()
                    await upd("❌ Пустая строка. Введите email или нажмите кнопку.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                return

            if state == 'waiting_support_message':
                user_states.pop(user_id, None)
                user = await bot.get_entity(user_id)
                username = f"@{user.username}" if user.username else f"ID {user.id}"
                
                support_text = f"📩 НОВОЕ СООБЩЕНИЕ В ПОДДЕРЖКУ\n\n"
                support_text += f"👤 Пользователь: {username}\n"
                support_text += f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                support_text += f"📝 Текст:\n{text}"
                
                try:
                    await bot.send_message(ADMIN_IDS[0], support_text)
                    await upd("✅ Ваше сообщение отправлено в поддержку. Мы ответим вам в ближайшее время.", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
                except Exception as e:
                    log_error(f"Support error: {e}")
                    await upd(f"❌ Ошибка отправки: {str(e)[:50]}", [[KeyboardButtonCallback("🔙 Назад", b"main_menu")]])
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
                    [KeyboardButtonCallback("👤 Профиль", b"profile"), KeyboardButtonCallback("🛠 Поддержка", b"support")],
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
        log_error(f"Error in main_bot: {e}")

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
        log_error(f"Fatal error: {e}")
