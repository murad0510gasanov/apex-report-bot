# app.py — APEX REPORT (FULL VERSION)
import os
import sys
import json
import asyncio
import threading
import re
import random
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
from datetime import datetime, timedelta
import requests

try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

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

# ===== YOUR DATA =====
API_ID = 21826549
API_HASH = 'c1a19f792cfd9e397200d16c7e448160'
BOT_TOKEN = '8870668741:AAHL2cO1BWoHau-bVmBLziMadDj94SnU7IA'
CHANNEL_ID = -1004489395750
RUCAPTCHA_API_KEY = 'a2e1b40a756ccc16c11ede55eb2c6567'
SUBSCRIPTION_BOT_TOKEN = '8238807176:AAFBRezNnlRiJ3oE-D81aOQGJ8NvJzBGBiU'
DEVELOPER_LINK = 'https://t.me/cazlen'
BOT_NAME = 'APEX REPORT'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
AU_DIR = os.path.join(SESSIONS_DIR, 'au')
US_DIR = os.path.join(SESSIONS_DIR, 'us')
INTERNAL_DIR = os.path.join(SESSIONS_DIR, 'internal')
for d in [AU_DIR, US_DIR, INTERNAL_DIR]:
    os.makedirs(d, exist_ok=True)

LOG_FILE = os.path.join(BASE_DIR, 'bot_analytics.json')
SUBS_FILE = os.path.join(BASE_DIR, 'subscriptions.json')
REQUESTS_FILE = os.path.join(BASE_DIR, 'requests.json')

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

async def try_connect(session_path, timeout=20):
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
        for f in os.listdir(dir_path):
            if f.endswith('.session'):
                all_sessions.append(os.path.join(dir_path, f))

    if not all_sessions:
        return "❌ No active sessions."

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
            client = await try_connect(session_path, timeout=20)
            if not client:
                bot_instance.log(f"⚠️ Session {session_name} not authorized")
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
            bot_instance.log(f"✅ Session {session_name} AU success")
        except Exception as e:
            if client:
                await client.disconnect()
            bot_instance.log(f"⚠️ Error on session {session_name}: {str(e)[:50]}")
            continue

    us_sessions = [s for s in all_sessions if 'us' in s]
    tida_total = len(us_sessions)
    for session_path in us_sessions:
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=20)
            if not client:
                bot_instance.log(f"⚠️ Session {session_name} not authorized")
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
            bot_instance.log(f"✅ Session {session_name} TIDA success")
        except Exception as e:
            if client:
                await client.disconnect()
            bot_instance.log(f"⚠️ Error on session {session_name}: {str(e)[:50]}")
            continue

    return f"✅ Mix report sent!\n🎯 Target: {target}"

async def send_telethon_report(user_id, target, bot_instance):
    all_sessions = []
    for dir_path in [AU_DIR, US_DIR, INTERNAL_DIR]:
        for f in os.listdir(dir_path):
            if f.endswith('.session'):
                all_sessions.append(os.path.join(dir_path, f))

    if not all_sessions:
        return "❌ No active sessions!"

    message_link_pattern = r'https://t\.me/([^/]+)/(\d+)'
    match = re.search(message_link_pattern, target)
    if match:
        chat_username = match.group(1)
        message_id = int(match.group(2))
        is_message = True
    else:
        is_message = False

    total = len(all_sessions)
    success = 0
    failed = 0

    for session_path in all_sessions:
        session_name = os.path.basename(session_path)
        client = None
        try:
            client = await try_connect(session_path, timeout=20)
            if not client:
                bot_instance.log(f"⚠️ Session {session_name} not authorized")
                failed += 1
                continue
            
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
            success += 1
            bot_instance.log(f"✅ Telethon {session_name} success")
        except FloodWaitError as e:
            if client:
                await client.disconnect()
            bot_instance.log(f"⏳ FloodWait on {session_name}: {e.seconds} sec")
            await asyncio.sleep(min(e.seconds, 30))
            failed += 1
            continue
        except Exception as e:
            if client:
                await client.disconnect()
            error_msg = str(e)
            if "username" in error_msg.lower():
                bot_instance.log(f"⚠️ {session_name}: username not found")
            else:
                bot_instance.log(f"⚠️ {session_name}: {error_msg[:50]}")
            failed += 1
            continue

    return f"✅ Telethon — done ({success}/{total})"

async def send_operator_report(user_id, username, bot_instance):
    phone = generate_phone()
    name = "Operator Report"
    text = f"Complaint against drug shop operator: {username}"
    success, msg = send_web_report(RUCAPTCHA_API_KEY, name, phone, text)
    if success:
        return f"✅ Operator {username} — report sent"
    else:
        return f"❌ Operator {username} — error: {msg}"

class PowerAI:
    def generate_mix_text(self, target, target_type, violation_desc, evidence_links=""):
        """Генерирует текст жалобы в одну строку на английском"""
        report = f"URGENT REPORT — TELEGRAM TERMS OF SERVICE VIOLATION. Target: {target} ({target_type}). Violation: {violation_desc}. This entity systematically violates Telegram rules by engaging in {violation_desc}, which directly contravenes Telegram ToS (Community Guidelines). Evidence has been documented and includes public accessibility of violating content, active user engagement with prohibited material, and clear intent to bypass Telegram's moderation systems."
        if evidence_links:
            report += f" DIRECT EVIDENCE: {evidence_links}."
        report += " Request: immediate account/channel suspension and full investigation into reported activities. Signed, Telegram Compliance Reporting System."
        return report

class ContentAnalyzer:
    def __init__(self):
        self.keywords = {
            "drugs": ["buy", "cocaine", "heroin", "meth", "drugs", "shop", "dealer", "cocaine", "heroin", "meth", "drugs", "дилер", "шоп", "магаз", "клад"],
            "spam": ["spam", "ad", "promo", "subscribe", "referral", "reklama", "рассылка", "подпишись"],
            "porn": ["porn", "sex", "nude", "18+", "эротика", "интим"],
            "violence": ["violence", "kill", "death", "blood", "weapon", "насилие", "убить", "смерть", "кровь", "оружие"],
            "scam": ["scam", "pyramid", "invest", "phishing", "скам", "лохотрон", "обман", "инвестиция", "пирамида"],
            "personal": ["passport", "address", "phone", "personal", "data", "паспорт", "адрес", "телефон", "данные"],
            "bullying": ["bullying", "harass", "threat", "insult", "буллинг", "травля", "угроза", "оскорбление"]
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
            for f in os.listdir(dir_path):
                if f.endswith('.session'):
                    all_sessions.append(os.path.join(dir_path, f))
        if not all_sessions:
            return None, "No active sessions"
        messages = []
        target_type = "unknown"
        client = None

        for session_path in all_sessions:
            try:
                client = await try_connect(session_path, timeout=20)
                if client:
                    break
            except:
                continue

        if not client:
            return None, "Failed to connect to any session"

        try:
            if 't.me/' in target:
                username = target.replace('https://t.me/', '')
                if '/' in username:
                    username = username.split('/')[0]
                entity = await client.get_entity(f"@{username}")
                target_type = "channel"
            elif target.startswith('@'):
                entity = await client.get_entity(target)
                if entity.bot:
                    target_type = "bot"
                    await client.send_message(entity, '/start')
                    await asyncio.sleep(2)
                else:
                    target_type = "user"
            else:
                return None, "Invalid link"

            try:
                await client(JoinChannelRequest(entity))
                bot_instance.log(f"✅ Join request sent to {target}")
                await asyncio.sleep(10)
            except:
                pass

            bot_instance.log(f"📥 Collecting all messages from {target}...")
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
                    bot_instance.log(f"📥 Collected {len(all_messages)} messages...")
                    if len(msgs) < limit:
                        break
                except Exception as e:
                    bot_instance.log(f"⚠️ Error collecting messages: {e}")
                    break

            await client.disconnect()
            messages = all_messages

        except Exception as e:
            if client:
                await client.disconnect()
            return None, f"Analysis error: {e}"

        if not messages:
            return None, "Failed to get messages"

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

async def run_subscription_bot():
    try:
        bot = TelegramClient('subscription_bot', API_ID, API_HASH)
        await bot.start(bot_token=SUBSCRIPTION_BOT_TOKEN)
        print("[SUB-BOT] Subscription bot started")

        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.delete()
            buttons = [
                [KeyboardButtonCallback("📋 Subscribers", b"sub_list")],
                [KeyboardButtonCallback("📥 Requests", b"sub_requests")],
                [KeyboardButtonCallback("➕ Give subscription", b"sub_give")],
                [KeyboardButtonCallback("🗑️ Remove", b"sub_remove")]
            ]
            await event.reply("🔑 SUBSCRIPTION BOT", buttons=buttons)

        @bot.on(events.CallbackQuery(data=b"sub_list"))
        async def sub_list(event):
            await event.answer()
            await event.message.delete()
            subs = load_subs()
            if not subs:
                await event.reply("No subscribers.")
                return
            text = "📋 LIST:\n\n"
            for uid, data in subs.items():
                status = "✅" if has_subscription(int(uid)) else "❌"
                text += f"{status} {uid} until {data.get('expiry', '—')[:10]}\n"
            await event.reply(text)

        @bot.on(events.CallbackQuery(data=b"sub_requests"))
        async def sub_requests(event):
            await event.answer()
            await event.message.delete()
            reqs = load_requests()
            if not reqs:
                await event.reply("No requests.")
                return
            text = "📥 REQUESTS:\n"
            for r in reqs:
                text += f"🆔 {r.get('user_id')} — {r.get('time')}\n"
            await event.reply(text)

        @bot.on(events.CallbackQuery(data=b"sub_give"))
        async def sub_give(event):
            await event.answer()
            await event.message.delete()
            await event.reply("Send: ID days\nExample: 123456789 7")

        @bot.on(events.CallbackQuery(data=b"sub_remove"))
        async def sub_remove(event):
            await event.answer()
            await event.message.delete()
            await event.reply("Send ID to remove")

        @bot.on(events.NewMessage)
        async def handle_sub(event):
            if event.message.text.startswith('/'):
                return
            text = event.message.text.strip()
            await event.delete()
            parts = text.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                uid, days = parts[0], int(parts[1])
                subs = load_subs()
                expiry = datetime.now() + timedelta(days=days)
                subs[uid] = {'expiry': expiry.isoformat()}
                save_subs(subs)
                await event.reply(f"✅ Subscription given to {uid} for {days} days")
            elif len(parts) == 1 and parts[0].isdigit():
                uid = parts[0]
                subs = load_subs()
                if uid in subs:
                    del subs[uid]
                    save_subs(subs)
                    await event.reply(f"✅ Subscription removed for {uid}")
                else:
                    await event.reply(f"❌ {uid} not found")

        await bot.run_until_disconnected()
    except Exception as e:
        print(f"[SUB-BOT] Error: {e}")

class BotPanel:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{BOT_NAME} — Control Panel")
        self.root.geometry("1200x800")
        self.root.configure(bg='#F8FAFC')
        self.is_running = False
        self.bot = None
        self.loop = None
        self.thread = None
        self.data = load_data()
        self.ai = PowerAI()
        self.analyzer = ContentAnalyzer()
        self.build_ui()
        self.update_stats()
        self.log("System initialized")
        self.update_ms()

    def build_ui(self):
        self.top_bar = tk.Frame(self.root, bg='#FFFFFF', height=60)
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)
        tk.Label(self.top_bar, text=f"{BOT_NAME}", font=("Segoe UI", 20, "bold"), fg="#1E293B", bg='#FFFFFF').pack(side=tk.LEFT, padx=20)
        self.status_label = tk.Label(self.top_bar, text="OFFLINE", font=("Segoe UI", 12, "bold"), fg="#EF4444", bg='#FFFFFF')
        self.status_label.pack(side=tk.RIGHT, padx=20)
        btn_frame = tk.Frame(self.top_bar, bg='#FFFFFF')
        btn_frame.pack(side=tk.RIGHT, padx=10)
        self.start_btn = tk.Button(btn_frame, text="START", command=self.start_bot, bg="#10B981", fg="white", font=("Segoe UI", 11, "bold"), width=10, relief=tk.FLAT)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk.Button(btn_frame, text="STOP", command=self.stop_bot, bg="#EF4444", fg="white", font=("Segoe UI", 11, "bold"), width=10, relief=tk.FLAT, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.ms_label = tk.Label(btn_frame, text="MS: 0", font=("Segoe UI", 10, "bold"), fg="#10B981", bg='#FFFFFF')
        self.ms_label.pack(side=tk.LEFT, padx=10)

        left_panel = tk.Frame(self.root, bg='#FFFFFF', width=180)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)
        btn_style = {"font": ("Segoe UI", 10), "width": 20, "height": 1, "relief": tk.FLAT, "anchor": "w", "padx": 10, "bg": '#FFFFFF', "fg": '#475569'}
        self.buttons = {}
        for text, key in [("Dashboard", "main"), ("Sessions", "sessions"), ("Reports", "reports"), ("Requests", "requests"), ("Subscriptions", "subscriptions"), ("Logs", "logs")]:
            btn = tk.Button(left_panel, text=text, command=lambda k=key: self.switch_tab(k), **btn_style)
            btn.pack(pady=2, padx=5, fill=tk.X)
            self.buttons[key] = btn

        self.tab_frame = tk.Frame(self.root, bg='#F8FAFC')
        self.tab_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.tabs = {}
        self.tabs["main"] = self.create_main_tab()
        self.tabs["sessions"] = self.create_sessions_tab()
        self.tabs["reports"] = self.create_reports_tab()
        self.tabs["requests"] = self.create_requests_tab()
        self.tabs["subscriptions"] = self.create_subscriptions_tab()
        self.tabs["logs"] = self.create_logs_tab()
        self.switch_tab("main")

    def switch_tab(self, key):
        for k, frame in self.tabs.items():
            frame.pack_forget()
        self.tabs[key].pack(fill=tk.BOTH, expand=True)

    def create_main_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="DASHBOARD", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        cards = tk.Frame(frame, bg='#F8FAFC')
        cards.pack(pady=10)
        for text, attr in [("Users", "main_users"), ("Reports", "main_reports"), ("Subscribers", "main_subs"), ("Sessions", "main_sessions")]:
            c = tk.Frame(cards, bg='white', relief=tk.RAISED, bd=1)
            c.pack(side=tk.LEFT, padx=10, ipadx=20, ipady=10)
            tk.Label(c, text=text, font=("Segoe UI", 10), fg="#64748B", bg='white').pack()
            val = tk.Label(c, text="0", font=("Segoe UI", 16, "bold"), fg="#2563EB", bg='white')
            val.pack()
            setattr(self, attr, val)
        return frame

    def create_sessions_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="SESSIONS", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        for label, dir_path in [("AU", AU_DIR), ("US", US_DIR), ("Internal", INTERNAL_DIR)]:
            f = tk.Frame(frame, bg='#F8FAFC')
            f.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
            tk.Label(f, text=label, font=("Segoe UI", 12, "bold"), bg='#F8FAFC').pack()
            lb = tk.Listbox(f, height=10)
            lb.pack(fill=tk.BOTH, expand=True)
            for file in os.listdir(dir_path):
                if file.endswith('.session'):
                    lb.insert(tk.END, file)
            setattr(self, f"{label.lower()}_list", lb)
        return frame

    def create_reports_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="REPORTS", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        self.reports_list = tk.Listbox(frame, height=15)
        self.reports_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        return frame

    def create_requests_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="REQUESTS", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        self.requests_tree = ttk.Treeview(frame, columns=("ID", "Time", "Status"), show="headings", height=10)
        self.requests_tree.heading("ID", text="ID")
        self.requests_tree.heading("Time", text="Time")
        self.requests_tree.heading("Status", text="Status")
        self.requests_tree.pack(fill=tk.BOTH, expand=True, padx=10)
        btn_frame = tk.Frame(frame, bg='#F8FAFC')
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Confirm", command=self.confirm_payment, bg="#10B981", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Reject", command=self.reject_request, bg="#EF4444", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Refresh", command=self.update_requests_list, bg="#2563EB", fg="white").pack(side=tk.LEFT, padx=5)
        return frame

    def create_subscriptions_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="SUBSCRIPTIONS", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        self.subs_tree = ttk.Treeview(frame, columns=("ID", "Until", "Status"), show="headings", height=10)
        self.subs_tree.heading("ID", text="ID")
        self.subs_tree.heading("Until", text="Until")
        self.subs_tree.heading("Status", text="Status")
        self.subs_tree.pack(fill=tk.BOTH, expand=True, padx=10)
        btn_frame = tk.Frame(frame, bg='#F8FAFC')
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Give", command=self.give_subscription, bg="#10B981", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Remove", command=self.remove_subscription, bg="#EF4444", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Refresh", command=self.update_subs_list, bg="#2563EB", fg="white").pack(side=tk.LEFT, padx=5)
        return frame

    def create_logs_tab(self):
        frame = tk.Frame(self.tab_frame, bg='#F8FAFC')
        tk.Label(frame, text="LOGS", font=("Segoe UI", 18, "bold"), fg="#1E293B", bg='#F8FAFC').pack(pady=10)
        self.log_text = scrolledtext.ScrolledText(frame, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10)
        return frame

    def update_stats(self):
        self.main_users.config(text=str(len(self.data.get('users', []))))
        self.main_reports.config(text=str(len(self.data.get('reports', []))))
        self.main_subs.config(text=str(len(load_subs())))
        sessions = 0
        for d in [AU_DIR, US_DIR, INTERNAL_DIR]:
            sessions += len([f for f in os.listdir(d) if f.endswith('.session')])
        self.main_sessions.config(text=str(sessions))
        self.root.after(5000, self.update_stats)

    def update_ms(self):
        self.ms_label.config(text=f"MS: {random.randint(20, 80)}")
        self.root.after(2000, self.update_ms)

    def log(self, text):
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
        self.log_text.see(tk.END)

    def update_requests_list(self):
        for item in self.requests_tree.get_children():
            self.requests_tree.delete(item)
        for r in load_requests():
            self.requests_tree.insert("", tk.END, values=(r.get('user_id'), r.get('time'), r.get('status', 'Pending')))

    def update_subs_list(self):
        for item in self.subs_tree.get_children():
            self.subs_tree.delete(item)
        for uid, data in load_subs().items():
            status = "Active" if has_subscription(int(uid)) else "Expired"
            self.subs_tree.insert("", tk.END, values=(uid, data.get('expiry', '—')[:10], status))

    def confirm_payment(self):
        sel = self.requests_tree.selection()
        if not sel:
            return
        uid = self.requests_tree.item(sel[0], 'values')[0]
        days = simpledialog.askstring("Duration", "Days:")
        if not days or not days.isdigit():
            return
        days = int(days)
        subs = load_subs()
        subs[uid] = {'expiry': (datetime.now() + timedelta(days=days)).isoformat()}
        save_subs(subs)
        reqs = [r for r in load_requests() if str(r.get('user_id')) != str(uid)]
        save_requests(reqs)
        self.update_requests_list()
        self.update_subs_list()
        self.log(f"Subscription {uid} for {days} days")

    def reject_request(self):
        sel = self.requests_tree.selection()
        if not sel:
            return
        uid = self.requests_tree.item(sel[0], 'values')[0]
        reqs = [r for r in load_requests() if str(r.get('user_id')) != str(uid)]
        save_requests(reqs)
        self.update_requests_list()

    def give_subscription(self):
        uid = simpledialog.askstring("ID", "Enter ID:")
        if not uid or not uid.isdigit():
            return
        days = simpledialog.askstring("Duration", "Days:")
        if not days or not days.isdigit():
            return
        subs = load_subs()
        subs[uid] = {'expiry': (datetime.now() + timedelta(days=int(days))).isoformat()}
        save_subs(subs)
        self.update_subs_list()
        self.log(f"Given {uid} for {days} days")

    def remove_subscription(self):
        uid = simpledialog.askstring("ID", "Enter ID to remove:")
        if not uid or not uid.isdigit():
            return
        subs = load_subs()
        if uid in subs:
            del subs[uid]
            save_subs(subs)
            self.update_subs_list()
            self.log(f"Removed {uid}")

    def start_bot(self):
        if not TELEGRAM_AVAILABLE:
            messagebox.showerror("Error", "Install telethon: pip install telethon")
            return
        if self.is_running:
            return
        self.log("Starting...")
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="ONLINE", fg="#10B981")
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.thread = threading.Thread(target=self.run_bots, daemon=True)
        self.thread.start()

    def run_bots(self):
        asyncio.run(self.bots_worker())

    async def bots_worker(self):
        main_task = asyncio.create_task(self.main_bot())
        sub_task = asyncio.create_task(run_subscription_bot())
        await asyncio.gather(main_task, sub_task)

    async def main_bot(self):
        try:
            self.bot = await TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
            self.log("Bot connected")
            user_states = {}
            user_data = {}
            active_message = None

            async def update_message(text, buttons):
                nonlocal active_message
                try:
                    if active_message:
                        await active_message.edit(text, buttons=buttons)
                    else:
                        active_message = await event.reply(text, buttons=buttons)
                except Exception as e:
                    print(f"Update error: {e}")
                    active_message = await event.reply(text, buttons=buttons)

            @self.bot.on(events.NewMessage(pattern='/start'))
            async def start_handler(event):
                nonlocal active_message
                await event.delete()
                user_id = event.sender_id
                if user_id not in self.data.get('users', []):
                    self.data.setdefault('users', []).append(user_id)
                    save_data(self.data)
                    self.update_stats()
                
                # Check subscription
                if has_subscription(user_id):
                    buttons = [
                        [KeyboardButtonCallback("📋 Menu", b"main_menu")],
                        [KeyboardButtonCallback("👤 Profile", b"profile"), KeyboardButtonCallback("👨‍💻 Developer", b"developer")],
                        [KeyboardButtonCallback("📜 My History", b"history")]
                    ]
                    text = f"📌 {BOT_NAME}\n\nSelect section:"
                    active_message = await event.reply(text, buttons=buttons)
                else:
                    # Access denied for non-subscribers
                    text = (
                        f"🚫 ACCESS DENIED\n\n"
                        f"To purchase a subscription, contact the developer:\n"
                        f"{DEVELOPER_LINK}"
                    )
                    active_message = await event.reply(text)

            @self.bot.on(events.CallbackQuery)
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
                        await upd(
                            f"🔒 ACCESS RESTRICTED\n\nTo purchase access contact developer:\n{DEVELOPER_LINK}",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    buttons = [
                        [KeyboardButtonCallback("📤 Send Mix", b"mix_menu")],
                        [KeyboardButtonCallback("⚡ Telethon", b"telethon_report")],
                        [KeyboardButtonCallback("🔍 AI Analysis", b"ai_analyze")],
                        [KeyboardButtonCallback("👤 Operator", b"operator")],
                        [KeyboardButtonCallback("🔙 Back", b"back_to_start")]
                    ]
                    await upd("📋 MAIN MENU\n\nSelect function:", buttons)
                    return
                
                if data == "profile":
                    user_entity = await event.client.get_entity(user_id)
                    username = f"@{user_entity.username}" if user_entity.username else "Not set"
                    user_reports = [r for r in self.data.get('reports', []) if r.get('user') == user_id]
                    status = "⭐ Premium" if has_subscription(user_id) else "🏠 User"
                    await upd(
                        f"👤 PROFILE\n\n🆔 ID: {user_id}\n👤 Username: {username}\n📊 Status: {status}\n📩 Requests: {len(user_reports)}",
                        [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                    )
                    return
                
                if data == "developer":
                    await upd(
                        f"👨‍💻 DEVELOPER\n\nFor all questions contact:\n{DEVELOPER_LINK}",
                        [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                    )
                    return
                
                if data == "history":
                    history = [r for r in self.data.get('reports', []) if r.get('user') == user_id]
                    if not history:
                        await upd(
                            "📜 MY HISTORY\n\nNo records.",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    text = "📜 MY HISTORY\n\n"
                    for i, r in enumerate(history[-10:], 1):
                        status = "✅ sent" if "успешно" in r.get('type', '').lower() else "⏳ pending"
                        text += f"{i}. {r.get('target', '')} - {status} · {r.get('time', '')}\n"
                    buttons = [
                        [KeyboardButtonCallback("📥 Download PDF", b"download_pdf")],
                        [KeyboardButtonCallback("🔙 Back", b"back_to_start")]
                    ]
                    await upd(text, buttons)
                    return
                
                if data == "download_pdf":
                    await upd(
                        "📥 PDF file with history generated and sent to personal messages.",
                        [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                    )
                    return
                
                if data == "back_to_start":
                    if has_subscription(user_id):
                        buttons = [
                            [KeyboardButtonCallback("📋 Menu", b"main_menu")],
                            [KeyboardButtonCallback("👤 Profile", b"profile"), KeyboardButtonCallback("👨‍💻 Developer", b"developer")],
                            [KeyboardButtonCallback("📜 My History", b"history")]
                        ]
                        await upd(f"📌 {BOT_NAME}\n\nSelect section:", buttons)
                    else:
                        text = f"🚫 ACCESS DENIED\n\nTo purchase a subscription, contact the developer:\n{DEVELOPER_LINK}"
                        await upd(text, None)
                    return
                
                if data == "mix_menu":
                    if not has_subscription(user_id):
                        await upd(
                            "🔒 No subscription.",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    user_states[user_id] = 'waiting_mix_target'
                    await upd(
                        "📤 SEND MIX\n\nSend target link\n@username or https://t.me/...",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return
                
                if data == "telethon_report":
                    if not has_subscription(user_id):
                        await upd(
                            "🔒 No subscription.",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    user_states[user_id] = 'waiting_telethon_target'
                    await upd(
                        "⚡ TELEHON\n\nSend target — bot or message link.",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return
                
                if data == "operator":
                    if not has_subscription(user_id):
                        await upd(
                            "🔒 No subscription.",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    user_states[user_id] = 'waiting_operator_target'
                    await upd(
                        "👤 OPERATOR\n\nSend operator username:\n@username or https://t.me/username",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return
                
                if data == "ai_analyze":
                    if not has_subscription(user_id):
                        await upd(
                            "🔒 No subscription.",
                            [[KeyboardButtonCallback("🔙 Back", b"back_to_start")]]
                        )
                        return
                    user_states[user_id] = 'waiting_ai_target'
                    await upd(
                        "🔍 AI ANALYSIS\n\nSend channel/group link:\n@channel or https://t.me/+invite_link",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return
                
                if data == "mix_drugs_yes":
                    user_data[user_id]['drugs'] = 'yes'
                    user_states[user_id] = 'waiting_mix_description'
                    await upd(
                        "Describe the violation\n\nSpecify:\n1. Target type — Channel / Bot / Account / Group\n2. Reason — what exactly violates\n3. Evidence links\n\nExample: Channel; selling prohibited goods;\nhttps://t.me/x/12",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return
                
                if data == "mix_drugs_no":
                    user_data[user_id]['drugs'] = 'no'
                    user_states[user_id] = 'waiting_mix_description'
                    await upd(
                        "Describe the violation\n\nSpecify:\n1. Target type — Channel / Bot / Account / Group\n2. Reason — what exactly violates\n3. Evidence links\n\nExample: Channel; selling prohibited goods;\nhttps://t.me/x/12",
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return

            @self.bot.on(events.NewMessage)
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
                        buttons = [
                            [KeyboardButtonCallback("✅ Yes", b"mix_drugs_yes")],
                            [KeyboardButtonCallback("❌ No", b"mix_drugs_no")],
                            [KeyboardButtonCallback("🔙 Back", b"main_menu")]
                        ]
                        await upd("Related to drugs?", buttons)
                    else:
                        await upd(
                            "❌ Invalid link.",
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    return

                if state == 'waiting_telethon_target':
                    if 't.me/' in text or text.startswith('@'):
                        target = text
                        user_states.pop(user_id, None)
                        await event.reply("⏳ Sending Telethon...")
                        result = await send_telethon_report(user_id, target, self)
                        self.data.setdefault('reports', []).append({
                            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'target': target,
                            'type': 'Telethon Report',
                            'destination': 'All sessions',
                            'user': user_id
                        })
                        save_data(self.data)
                        self.update_stats()
                        await upd(
                            result,
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    else:
                        await upd(
                            "❌ Invalid link.",
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    return

                if state == 'waiting_operator_target':
                    if 't.me/' in text or text.startswith('@'):
                        username = text
                        user_states.pop(user_id, None)
                        await event.reply("⏳ Sending operator complaint...")
                        result = await send_operator_report(user_id, username, self)
                        self.data.setdefault('reports', []).append({
                            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'target': username,
                            'type': 'Operator',
                            'destination': 'Web method',
                            'user': user_id
                        })
                        save_data(self.data)
                        self.update_stats()
                        await upd(
                            result,
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    else:
                        await upd(
                            "❌ Invalid username.",
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    return

                if state == 'waiting_ai_target':
                    if 't.me/' in text or text.startswith('@'):
                        target = text
                        user_states.pop(user_id, None)
                        await upd("⏳ Scanning...\nLoading all messages...", 
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]])
                        
                        result, error = await self.analyzer.analyze_target(target, self)
                        if error:
                            await upd(
                                f"❌ {error}",
                                [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                            )
                            return
                        if not result:
                            await upd(
                                "❌ Failed to get messages",
                                [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                            )
                            return
                        results = result["results"]
                        violation = result["violation"]
                        percent = result["percent"]
                        messages = result["messages"]
                        target_type = result["target_type"]
                        report = f"🔍 AI ANALYSIS: {target}\n"
                        report += f"📌 Type: {target_type.upper()}\n"
                        report += f"📝 Scanned: {len(messages)} messages\n"
                        if violation:
                            report += f"🔴 Violations: 1\n"
                            report += f"⚠️ Detected: {violation.upper()} ({percent}%)\n"
                            report += f"\n❌ Violation found!"
                        else:
                            report += f"🔴 Violations: 0\n"
                            report += f"\n✅ No serious violations found."
                        await upd(
                            report,
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    else:
                        await upd(
                            "❌ Invalid link.",
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                    return

                if state == 'waiting_mix_description':
                    description = text
                    target = user_data.get(user_id, {}).get('target')
                    drugs = user_data.get(user_id, {}).get('drugs', 'no')
                    if not target:
                        await upd(
                            "❌ Error, restart /start",
                            [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                        )
                        return
                    violation_desc = "distribution of illegal narcotics and prohibited substances" if drugs == 'yes' else "violation of Telegram Terms of Service and community guidelines"
                    parts = description.split(';')
                    target_type = parts[0].strip() if len(parts) > 0 else "unknown"
                    reason = parts[1].strip() if len(parts) > 1 else "rules violation"
                    evidence_links = parts[2].strip() if len(parts) > 2 else ""
                    text = self.ai.generate_mix_text(target, target_type, violation_desc, evidence_links)
                    user_states.pop(user_id, None)
                    await event.reply("⏳ Sending mix report...")
                    result = await send_mix_report(user_id, target, text, self)
                    self.data.setdefault('reports', []).append({
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'target': target,
                        'type': 'Mix Report',
                        'destination': 'AU + TIDA',
                        'user': user_id
                    })
                    save_data(self.data)
                    self.update_stats()
                    await upd(
                        result,
                        [[KeyboardButtonCallback("🔙 Back", b"main_menu")]]
                    )
                    return

            @self.bot.on(events.NewMessage(pattern='/cancel'))
            async def cancel(event):
                nonlocal active_message
                await event.delete()
                user_states.pop(event.sender_id, None)
                user_data.pop(event.sender_id, None)
                if has_subscription(event.sender_id):
                    buttons = [
                        [KeyboardButtonCallback("📋 Menu", b"main_menu")],
                        [KeyboardButtonCallback("👤 Profile", b"profile"), KeyboardButtonCallback("👨‍💻 Developer", b"developer")],
                        [KeyboardButtonCallback("📜 My History", b"history")]
                    ]
                    text = f"📌 {BOT_NAME}\n\n❌ Cancelled.\n\nSelect section:"
                else:
                    text = f"🚫 ACCESS DENIED\n\nTo purchase a subscription, contact the developer:\n{DEVELOPER_LINK}"
                    buttons = None
                if active_message:
                    await active_message.edit(text, buttons=buttons)
                else:
                    active_message = await event.reply(text, buttons=buttons)

            self.log("Bot ready")
            await self.bot.run_until_disconnected()
        except Exception as e:
            self.log(f"Error: {e}")

    def stop_bot(self):
        if not self.is_running:
            return
        self.log("Stopping...")
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="OFFLINE", fg="#EF4444")
        if self.bot:
            try:
                asyncio.run_coroutine_threadsafe(self.bot.disconnect(), self.loop)
            except:
                pass
        if self.thread:
            self.thread.join(timeout=2)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BotPanel(root)
        root.mainloop()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
