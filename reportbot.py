import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton
from aiogram.filters import Command
from aiogram import F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

API_TOKEN = "8165729586:AAGpJ1rtPNUhJvgxQZLt8J9lHSu-JDYu168"
DEVELOPER_ID = 5675745209
CHANNEL_ID = -1003048269697

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- DB Setup ---
conn = sqlite3.connect("reportbot.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE,
    username TEXT,
    name TEXT,
    unique_number INTEGER UNIQUE,
    last_report_time TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS moderators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE,
    name TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_unique_number INTEGER,
    text TEXT,
    media TEXT,
    timestamp TEXT
)
""")
conn.commit()

# --- Utils ---
def get_next_unique_number():
    cursor.execute("SELECT MAX(unique_number) FROM users")
    res = cursor.fetchone()
    return (res[0] or 0) + 1

def get_user_by_tg_id(tg_id):
    cursor.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
    return cursor.fetchone()

def add_user(tg_id, username, name):
    unique_number = get_next_unique_number()
    cursor.execute(
        "INSERT OR IGNORE INTO users (tg_id, username, name, unique_number) VALUES (?, ?, ?, ?)",
        (tg_id, username, name, unique_number)
    )
    conn.commit()
    return unique_number

def update_last_report_time(tg_id):
    now = datetime.now().isoformat()
    cursor.execute("UPDATE users SET last_report_time=? WHERE tg_id=?", (now, tg_id))
    conn.commit()

def can_send_report(user):
    last_time = user[5]
    if not last_time:
        return True
    last_dt = datetime.fromisoformat(last_time)
    return datetime.now() - last_dt > timedelta(minutes=30)

def get_wait_minutes(user):
    last_time = user[5]
    if not last_time:
        return 0
    last_dt = datetime.fromisoformat(last_time)
    delta = datetime.now() - last_dt
    wait = timedelta(minutes=30) - delta
    return max(int(wait.total_seconds() // 60) + 1, 0)

def get_moderators():
    cursor.execute("SELECT tg_id, name FROM moderators")
    return cursor.fetchall()

def add_moderator(tg_id, name):
    cursor.execute(
        "INSERT OR IGNORE INTO moderators (tg_id, name) VALUES (?, ?)",
        (tg_id, name)
    )
    conn.commit()

def remove_moderator(tg_id):
    cursor.execute("DELETE FROM moderators WHERE tg_id=?", (tg_id,))
    conn.commit()

def get_all_users():
    cursor.execute("SELECT tg_id, username, name, unique_number FROM users")
    return cursor.fetchall()

def get_moderator_by_tg_id(tg_id):
    cursor.execute("SELECT name FROM moderators WHERE tg_id=?", (tg_id,))
    res = cursor.fetchone()
    return res[0] if res else None

def get_user_by_unique_number(unique_number):
    cursor.execute("SELECT tg_id FROM users WHERE unique_number=?", (unique_number,))
    res = cursor.fetchone()
    return res[0] if res else None

# --- Handlers ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = get_user_by_tg_id(message.from_user.id)
    if not user:
        unique_number = add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name
        )
        await message.answer(
            f"Добро пожаловать!\nТут вы сможете оставить вашу жалобу анонимно.\nПожалуйста, напишите подробно и чётко вашу жалобу.\nВаш уникальный номер: {unique_number}"
        )
    else:
        await message.answer(
            f"Вы уже зарегистрированы!\nВаш уникальный номер: {user[4]}\n\n"
            "Чтобы отправить жалобу, просто напишите сообщение (минимум 25 символов или прикрепите фото/видео).\n"
            "Жалобы можно отправлять раз в 30 минут."
        )

@dp.message(Command("add"))
async def cmd_add_moderator(message: types.Message):
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("Только разработчик может добавлять модераторов.")
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Используйте: /add <айди_модератора> <имя>")
        return
    tg_id, name = args[1], args[2]
    try:
        tg_id = int(tg_id)
    except ValueError:
        await message.answer("Айди должен быть числом.")
        return
    add_moderator(tg_id, name)
    await message.answer(f"Модератор {name} добавлен.")

@dp.message(Command("admins"))
async def cmd_admins(message: types.Message):
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("Только разработчик может просматривать список модераторов.")
        return
    moderators = get_moderators()
    if not moderators:
        await message.answer("Модераторов нет.")
        return
    kb = InlineKeyboardBuilder()
    text = "Список модераторов:\n"
    for tg_id, name in moderators:
        text += f"{name} — {tg_id}\n"
        kb.add(
            InlineKeyboardButton(
                text=f"Удалить {name}",
                callback_data=f"remove_mod_{tg_id}"
            )
        )
    await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("remove_mod_"))
async def remove_mod_callback(callback: types.CallbackQuery):
    if callback.from_user.id != DEVELOPER_ID:
        await callback.answer("Нет доступа.")
        return
    tg_id = int(callback.data.split("_")[-1])
    remove_moderator(tg_id)
    await callback.answer("Модератор удалён.")
    await callback.message.delete()

@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != DEVELOPER_ID:
        await message.answer("Нет доступа.")
        return
    users = get_all_users()
    text = f"Всего пользователей: {len(users)}\n\n"
    for tg_id, username, name, unique_number in users:
        # Ссылка через айди: tg://user?id=<tg_id>
        link = f"[{username if username else 'Профиль'}](tg://user?id={tg_id})"
        username_display = f"@{username}" if username else "нет"
        text += (
            f"Имя: {name}\n"
            f"ID: {tg_id}\n"
            f"Юзернейм: {username_display}\n"
            f"Ссылка: {link}\n"
            f"Уникальный номер: {unique_number}\n\n"
        )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("rep"))
async def cmd_rep(message: types.Message):
    moderator_name = get_moderator_by_tg_id(message.from_user.id)
    if not moderator_name:
        await message.answer("Только модератор может отправлять обратную связь.")
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Используйте: /rep <уникальный_номер> <текст>")
        return
    unique_number, reply_text = args[1], args[2]
    try:
        unique_number = int(unique_number)
    except ValueError:
        await message.answer("Уникальный номер должен быть числом.")
        return
    user_tg_id = get_user_by_unique_number(unique_number)
    if not user_tg_id:
        await message.answer("Пользователь с таким уникальным номером не найден.")
        return
    await bot.send_message(
        user_tg_id,
        f"Вам ответил модератор {moderator_name}:\n{reply_text}"
    )
    await message.answer("Ответ отправлен.")

def is_not_command(message: types.Message) -> bool:
    # Если это команда, не обрабатывать
    if message.text and message.text.startswith("/"):
        return False
    return True

@dp.message(is_not_command)
async def handle_report(message: types.Message):
    user = get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer("Сначала используйте /start для регистрации.")
        return

    if not can_send_report(user):
        minutes = get_wait_minutes(user)
        await message.answer(f"Вы сможете отправить новую жалобу через {minutes} мин.")
        return

    media_file_id = None
    text = message.text or ""
    if message.photo:
        media_file_id = message.photo[-1].file_id
        text = message.caption or ""
    elif message.video:
        media_file_id = message.video.file_id
        text = message.caption or ""

    if len(text) < 25 and not media_file_id:
        await message.answer("Жалоба должна содержать минимум 25 символов текста или медиафайл.")
        return

    # Сохраняем жалобу
    cursor.execute(
        "INSERT INTO reports (user_unique_number, text, media, timestamp) VALUES (?, ?, ?, ?)",
        (user[4], text, media_file_id, datetime.now().isoformat())
    )
    conn.commit()
    update_last_report_time(message.from_user.id)

    # Формируем сообщение для канала
    report_msg = f"Уникальный номер: {user[4]}\n"
    if text:
        report_msg += f"Жалоба: {text}"

    if media_file_id:
        if message.photo:
            await bot.send_photo(CHANNEL_ID, media_file_id, caption=report_msg)
        elif message.video:
            await bot.send_video(CHANNEL_ID, media_file_id, caption=report_msg)
    else:
        await bot.send_message(CHANNEL_ID, report_msg)

    await message.answer("Ваша жалоба отправлена анонимно. Спасибо!")

if __name__ == "__main__":
    try:
        asyncio.run(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")