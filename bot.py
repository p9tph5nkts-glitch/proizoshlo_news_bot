import os
import sqlite3
from contextlib import closing
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, Update
from aiogram.filters import CommandStart, Command
from aiogram.enums import ContentType
from aiogram.client.default import DefaultBotProperties

TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])
DB_PATH = 'bot.db'

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, text TEXT, content_type TEXT, telegram_file_id TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'new')''')
        conn.commit()
init_db()

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
app = FastAPI()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Прислать историю', callback_data='send_story')],
        [InlineKeyboardButton(text='ℹ️ Как это работает', callback_data='how_it_works')],
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer('👋 <b>Произошло | Бот</b>\n\nЕсть история, которую должны увидеть другие?\n\nПрисылай её сюда — текстом, фото, видео или ссылкой. Мы проверим историю, оформим её и, если она подходит, опубликуем в «Произошло».', reply_markup=main_menu())

@dp.message(Command('myid'))
async def myid(message: Message):
    await message.answer(f'Твой Telegram ID: <code>{message.from_user.id}</code>')

@dp.callback_query(F.data == 'how_it_works')
async def how_it_works(callback):
    await callback.message.answer('📝 <b>Как это работает</b>\n\n1. Ты присылаешь историю.\n2. Можно добавить фото, видео или ссылку.\n3. Мы проверяем материал.\n4. Если история подходит — оформляем её для канала.\n5. После публикации сообщаем тебе.')
    await callback.answer()

@dp.callback_query(F.data == 'send_story')
async def send_story(callback):
    await callback.message.answer('Рассказывай, что произошло.\n\nМожно своими словами — за оформление переживать не нужно. Также можешь сразу приложить фото, видео или ссылку.')
    await callback.answer()

async def save_submission(message: Message, text: str, content_type: str, file_id=None):
    username = message.from_user.username or ''
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute('INSERT INTO submissions (user_id, username, text, content_type, telegram_file_id) VALUES (?, ?, ?, ?, ?)', (message.from_user.id, username, text, content_type, file_id))
        conn.commit()
        return cur.lastrowid

async def notify_admin(message: Message, submission_id: int, text: str, content_type: str, file_id=None):
    username = message.from_user.username
    author = f'@{username}' if username else f'ID {message.from_user.id}'
    admin_text = f'🆕 <b>Новая история #{submission_id}</b>\n\n👤 Автор: {author}\n📝 Тип: {content_type}\n\n{(text or "Без текста")[:3500]}'
    await bot.send_message(ADMIN_ID, admin_text)
    if file_id:
        if content_type == 'photo': await bot.send_photo(ADMIN_ID, file_id)
        elif content_type == 'video': await bot.send_video(ADMIN_ID, file_id)
        elif content_type == 'document': await bot.send_document(ADMIN_ID, file_id)

@dp.message(F.content_type == ContentType.TEXT)
async def receive_text(message: Message):
    if message.text.startswith('/'): return
    sid = await save_submission(message, message.text, 'text')
    await notify_admin(message, sid, message.text, 'text')
    await message.answer('Принял 👌\n\nИстория отправлена на модерацию. Если она подойдёт для канала — мы её опубликуем.')

@dp.message(F.photo)
async def receive_photo(message: Message):
    caption = message.caption or ''
    file_id = message.photo[-1].file_id
    sid = await save_submission(message, caption, 'photo', file_id)
    await notify_admin(message, sid, caption, 'photo', file_id)
    await message.answer('Фото получил 👌\n\nИстория отправлена на модерацию.')

@dp.message(F.video)
async def receive_video(message: Message):
    caption = message.caption or ''
    file_id = message.video.file_id
    sid = await save_submission(message, caption, 'video', file_id)
    await notify_admin(message, sid, caption, 'video', file_id)
    await message.answer('Видео получил 👌\n\nИстория отправлена на модерацию.')

@dp.message(F.document)
async def receive_document(message: Message):
    caption = message.caption or ''
    file_id = message.document.file_id
    sid = await save_submission(message, caption, 'document', file_id)
    await notify_admin(message, sid, caption, 'document', file_id)
    await message.answer('Файл получил 👌\n\nИстория отправлена на модерацию.')

@app.get('/')
async def health(): return {'status':'ok','bot':'proizoshlo'}

@app.post('/telegram')
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {'ok': True}

@app.on_event('startup')
async def startup():
    await bot.set_webhook(f"{os.environ['RENDER_EXTERNAL_URL'].rstrip('/')}/telegram")

@app.on_event('shutdown')
async def shutdown():
    await bot.delete_webhook()
    await bot.session.close()
