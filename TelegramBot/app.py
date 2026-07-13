if is_bot:
    bot_username = f"@{username}"
    print(f"[{session_name}] ⏳ Отправка боту {bot_username}")
    
    # 1. Нажимаем /start
    await client.send_message(bot_username, '/start')
    await asyncio.sleep(2)
    
    # 2. Отправляем ссылку
    link = f"https://t.me/{username}"
    await client.send_message(bot_username, link)
    await asyncio.sleep(2)
    
    # 3. Ищем кнопку "Жалоба"
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
