from telethon import events, functions, types
import requests
import re
import asyncio
from datetime import datetime

info = {
    "name": "Gender Empire System",
    "description": "Полный контроль: Админка, Списки, Кэш и Авто-ответ",
}

commands = [
    {"cmd": ".admin <user>", "desc": "Добавить админа (только хозяин)"},
    {"cmd": ".testall",       "desc": "Сканировать всех участников группы"},
    {"cmd": ".test <user>",   "desc": "Проверить одного пользователя"},
    {"cmd": ".w <user>",      "desc": "Добавить в women.txt"},
    {"cmd": ".m <user>",      "desc": "Добавить в men.txt"},
]

MESSAGE_TO_SEND = "⚠ Ваше сообщение не было доставлено получателю. Подробнее: @IHatWomen"
LUMEN_TOKEN = (client.config.get("lumen") or {}).get("api_key")
LUMEN_URL = "https://lumen.unionium.org/api/v1/chat/completions"
CACHE_FILE = "gender_cache.txt"
ADMINS_FILE = "admins.txt"

def get_admins():
    try:
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def add_admin(username):
    with open(ADMINS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{username}\n")

def get_cached_gender(username):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(username):
                    return line.split('|')[1].strip()
    except FileNotFoundError:
        pass
    return None

def save_to_cache(username, code):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{username}|{code}\n")

def save_to_list(filename, user_data):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | {user_data}\n")

async def analyze_gender_nocache(client, user):
    username = f"@{user.username}" if getattr(user, 'username', None) else f"ID:{user.id}"
    try:
        full_user_res = await client(functions.users.GetFullUserRequest(id=user.id))
        bio = getattr(full_user_res.full_user, 'about', 'Пусто')
    except Exception:
        bio = "Неизвестно"

    first_name = getattr(user, 'first_name', 'Не указано')
    last_name = getattr(user, 'last_name', '')
    profile_data = f"Имя: {first_name} {last_name}\nЮзернейм: {username}\nО себе: {bio}"

    loop = asyncio.get_event_loop()
    def make_request():
        headers = {"Authorization": f"Bearer {LUMEN_TOKEN}"}
        system_prompt = "Ты — высокоточный анализатор. Ответ в тегах <answer>X</answer>: 1=женщина, 2=скорее женщина, 3=без понятия, 4=скорее не женщина, 5=не женщина."
        data = {"model": "auto", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Данные профиля:\n{profile_data}"}]}
        try:
            response = requests.post(LUMEN_URL, headers=headers, json=data, timeout=10).json()
            text = response['choices'][0]['message']['content']
            match = re.search(r'<answer>(\d+)</answer>', text)
            return match.group(1) if match else "3"
        except Exception:
            return "3"
    return await loop.run_in_executor(None, make_request)

async def analyze_gender(client, user):
    username = f"@{user.username}" if getattr(user, 'username', None) else f"ID:{user.id}"
    cached = get_cached_gender(username)
    if cached: return cached
    res = await analyze_gender_nocache(client, user)
    save_to_cache(username, res)
    return res

async def smart_respond(client, event, text, **kwargs):
    topic_id = None
    if event.message.reply_to and getattr(event.message.reply_to, 'forum_topic', False):
        topic_id = event.message.reply_to.reply_to_top_id or event.message.reply_to.reply_to_msg_id
    if topic_id:
        return await client.send_message(event.chat_id, text, reply_to=topic_id, **kwargs)
    return await event.respond(text, **kwargs)

def make_bar(done, total, length=16):
    if total <= 0: return "░" * length
    filled = max(0, min(length, int(length * done / total)))
    return "█" * filled + "░" * (length - filled)

def format_progress(done, total, women, men, unknown):
    pct = int(100 * done / total) if total else 0
    return f"🔍 Скан чата: [{make_bar(done, total)}] {pct}% ({done}/{total})\n👩 {women}  |  👨 {men}  |  🤔 {unknown}"

def setup(client):
    client.registry["anal"] = {"info": info, "commands": commands}

    async def handler(event):
        raw = (event.raw_text or "").strip()
        if not raw: return

        me = await client.get_me()
        sender = await event.get_sender()
        if not sender: return

        sender_username = f"@{sender.username}" if getattr(sender, 'username', None) else None
        admins = get_admins()
        is_privileged = (sender.id == me.id) or (sender_username in admins)

        if raw.startswith(".admin") and sender.id == me.id:
            args = raw.split(maxsplit=1)
            if len(args) > 1:
                try:
                    target = await client.get_entity(args[1])
                    t_username = f"@{target.username}" if getattr(target, 'username', None) else f"ID:{target.id}"
                    if t_username not in admins:
                        add_admin(t_username)
                        await event.reply(f"✅ {t_username} теперь админ системы, хозяин!")
                    else:
                        await event.reply("Этот пользователь уже админ, ня!")
                except Exception as e:
                    await event.reply(f"❌ Ошибка: {e}")
            return

        if is_privileged:
            if raw == ".testall":
                if not event.is_group:
                    await event.reply("❌ Эта команда работает только в группах!")
                    return
                participants = []
                try:
                    async for user in client.iter_participants(event.chat_id):
                        if not user.bot and not getattr(user, 'deleted', False):
                            participants.append(user)
                except Exception as e:
                    await event.reply(f"❌ Ошибка получения участников: {e}")
                    return
                total = len(participants)
                if total == 0:
                    await event.reply("🤷 В группе нет участников для сканирования.")
                    return
                done, women, men, unknown, skipped = 0, 0, 0, 0, 0
                progress_msg = await smart_respond(client, event, format_progress(done, total, women, men, unknown))
                last_edit = 0.0
                for user in participants:
                    done += 1
                    try:
                        res = await analyze_gender(client, user)
                        if res in ["1", "2"]:
                            women += 1
                            un = f"@{user.username}" if getattr(user, 'username', None) else f"ID:{user.id}"
                            label = "👩 Женщина" if res == "1" else "👩‍🦰 Скорее женщина"
                            await smart_respond(client, event, f"{label}: {un} | {user.first_name or 'Без имени'} (Код: {res})")
                            await asyncio.sleep(0.3)
                        elif res in ["4", "5"]: men += 1
                        else: unknown += 1
                    except Exception:
                        skipped += 1; unknown += 1
                    now = asyncio.get_event_loop().time()
                    if now - last_edit >= 1.5 or done == total:
                        try: await progress_msg.edit(format_progress(done, total, women, men, unknown))
                        except: pass
                        last_edit = now
                await progress_msg.edit(f"✅ Скан завершён!\n📊 Проверено: {done}/{total}\n👩 Женщин: {women}\n👨 Мужчин: {men}\n🤔 Неясно: {unknown}" + (f"\n⚠ Пропущено: {skipped}" if skipped else ""))
                return

            if raw.startswith(".testnc"):
                args = raw.split(maxsplit=1)
                if len(args) > 1:
                    try:
                        target = await client.get_entity(args[1])
                        res = await analyze_gender_nocache(client, target)
                        mapping = {"1": "👩 Женщина", "2": "👩‍🦰 Скорее женщина", "3": "🤔 Без понятия", "4": "👨 Скорее не женщина", "5": "👨‍🦱 Точно не женщина"}
                        await event.reply(f"🧪 **Вердикт (без кеша):** {mapping.get(res, 'Ошибка')} (Код: {res})")
                    except Exception as e: await event.reply(f"❌ Ошибка: {e}")
                return

            if raw.startswith(".test"):
                args = raw.split(maxsplit=1)
                if len(args) > 1:
                    try:
                        target = await client.get_entity(args[1])
                        res = await analyze_gender(client, target)
                        mapping = {"1": "👩 Женщина", "2": "👩‍🦰 Скорее женщина", "3": "🤔 Без понятия", "4": "👨 Скорее не женщина", "5": "👨‍🦱 Точно не женщина"}
                        await event.reply(f"🧪 **Вердикт:** {mapping.get(res, 'Ошибка')} (Код: {res})")
                    except Exception as e: await event.reply(f"❌ Ошибка: {e}")
                return

            if raw.startswith(".w "):
                args = raw.split(maxsplit=1)
                if len(args) > 1:
                    try:
                        target = await client.get_entity(args[1])
                        un = f"@{target.username}" if getattr(target, 'username', None) else f"ID:{target.id}"
                        save_to_list("women.txt", f"ID:{target.id} | {target.first_name} | {un}")
                        await event.reply(f"🎀 Добавлена в список женщин: {un}")
                    except Exception as e: await event.reply(f"❌ Ошибка: {e}")
                return

            if raw.startswith(".m "):
                args = raw.split(maxsplit=1)
                if len(args) > 1:
                    try:
                        target = await client.get_entity(args[1])
                        un = f"@{target.username}" if getattr(target, 'username', None) else f"ID:{target.id}"
                        save_to_list("men.txt", f"ID:{target.id} | {target.first_name} | {un}")
                        await event.reply(f"👨 Добавлен в список мужчин: {un}")
                    except Exception as e: await event.reply(f"❌ Ошибка: {e}")
                return

        if sender.id != me.id and not getattr(sender, "bot", False) and isinstance(sender, types.User):
            is_pm = event.is_private
            is_reply_to_me = False
            if event.is_reply:
                reply = await event.get_reply_message()
                if reply and (await reply.get_sender()).id == me.id: is_reply_to_me = True
            is_mention = event.message.mentioned and (me.username and f"@{me.username.lower()}" in raw.lower() or str(me.id) in raw)
            if is_pm or is_reply_to_me or is_mention:
                result = await analyze_gender(client, sender)
                if result in ["1", "2"]:
                    await smart_respond(client, event, MESSAGE_TO_SEND)

    client.add_event_handler(handler, events.NewMessage(outgoing=True))
