import os
import sqlite3
from contextlib import closing
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
    CallbackQuery,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ContentType
from aiogram.client.default import DefaultBotProperties
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DB_PATH = "bot.db"
def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                text TEXT,
                content_type TEXT,
                telegram_file_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'new'
            )
            """
        )
        conn.commit()
init_db()
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()
app = FastAPI()
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Прислать историю",
                    callback_data="send_story"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Как это работает",
                    callback_data="how_it_works"
                )
            ],
        ]
    )
def moderation_keyboard(submission_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать",
                    callback_data=f"approve:{submission_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Доработать",
                    callback_data=f"edit:{submission_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject:{submission_id}"
                )
            ],
        ]
    )
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 <b>Произошло | Бот</b>\n\n"
        "Есть история, которую должны увидеть другие?\n\n"
        "Присылай её сюда — текстом, фото, видео или ссылкой. "
        "Мы проверим историю, оформим её и, если она подходит, "
        "опубликуем в «Произошло».",
        reply_markup=main_menu()
    )
@dp.message(Command("myid"))
async def myid(message: Message):
    await message.answer(
        f"Твой Telegram ID: <code>{message.from_user.id}</code>"
    )
@dp.callback_query(F.data == "how_it_works")
async def how_it_works(callback: CallbackQuery):
    await callback.message.answer(
        "📝 <b>Как это работает</b>\n\n"
        "1. Ты присылаешь историю.\n"
        "2. Можно добавить фото, видео или ссылку.\n"
        "3. Мы проверяем материал.\n"
        "4. Если история подходит — оформляем её для канала.\n"
        "5. После публикации сообщаем тебе."
    )
    await callback.answer()
@dp.callback_query(F.data == "send_story")
async def send_story(callback: CallbackQuery):
    await callback.message.answer(
        "Рассказывай, что произошло.\n\n"
        "Можно своими словами — за оформление переживать не нужно. "
        "Также можешь сразу приложить фото, видео или ссылку."
    )
    await callback.answer()
async def save_submission(
    message: Message,
    text: str,
    content_type: str,
    file_id=None
):
    username = message.from_user.username or ""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            """
            INSERT INTO submissions
            (user_id, username, text, content_type, telegram_file_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message.from_user.id,
                username,
                text,
                content_type,
                file_id
            )
        )
        conn.commit()
        return cur.lastrowid
async def notify_admin(
    message: Message,
    submission_id: int,
    text: str,
    content_type: str,
    file_id=None
):
    username = message.from_user.username
    author = (
        f"@{username}"
        if username
        else f"ID {message.from_user.id}"
    )
    admin_text = (
        f"🆕 <b>Новая история #{submission_id}</b>\n\n"
        f"👤 Автор: {author}\n"
        f"📝 Тип: {content_type}\n\n"
        f"{(text or 'Без текста')[:3500]}"
    )
    await bot.send_message(
        ADMIN_ID,
        admin_text,
        reply_markup=moderation_keyboard(submission_id)
    )
    if file_id:
        if content_type == "photo":
            await bot.send_photo(ADMIN_ID, file_id)
        elif content_type == "video":
            await bot.send_video(ADMIN_ID, file_id)
        elif content_type == "document":
            await bot.send_document(ADMIN_ID, file_id)
def update_status(submission_id: int, status: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "UPDATE submissions SET status = ? WHERE id = ?",
            (status, submission_id)
        )
        conn.commit()
def get_submission(submission_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, username, text, content_type,
                   telegram_file_id, status
            FROM submissions
            WHERE id = ?
            """,
            (submission_id,)
        ).fetchone()
        return row
@dp.callback_query(F.data.startswith("approve:"))
async def approve_submission(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    submission_id = int(callback.data.split(":")[1])
    submission = get_submission(submission_id)

    if not submission:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    _, user_id, username, text, content_type, file_id, status = submission

    try:
        post_text = text or "Без текста"

        if content_type == "photo" and file_id:
            await bot.send_photo(
                "@proizoshlo_news",
                file_id,
                caption=post_text
            )
        elif content_type == "video" and file_id:
            await bot.send_video(
                "@proizoshlo_news",
                file_id,
                caption=post_text
            )
        elif content_type == "document" and file_id:
            await bot.send_document(
                "@proizoshlo_news",
                file_id,
                caption=post_text
            )
        else:
            await bot.send_message(
                "@proizoshlo_news",
                post_text
            )

        update_status(submission_id, "published")

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Опубликовано! 🔥")

        await bot.send_message(
            ADMIN_ID,
            f"🔥 История #{submission_id} опубликована в @proizoshlo_news"
        )

    except Exception as e:
        await callback.answer(
            "Не удалось опубликовать.",
            show_alert=True
        )

        await bot.send_message(
            ADMIN_ID,
            f"⚠️ Ошибка публикации истории #{submission_id}:\n{e}"
        )
@dp.callback_query(F.data.startswith("edit:"))
async def edit_submission(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    submission_id = int(callback.data.split(":")[1])
    submission = get_submission(submission_id)
    if not submission:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    update_status(submission_id, "edit")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отправлено на доработку ✏️")
    await bot.send_message(
        ADMIN_ID,
        f"✏️ История #{submission_id} отправлена на доработку.\n"
        f"Статус: edit"
    )
@dp.callback_query(F.data.startswith("reject:"))
async def reject_submission(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    submission_id = int(callback.data.split(":")[1])
    submission = get_submission(submission_id)
    if not submission:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    update_status(submission_id, "rejected")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("История отклонена ❌")
    await bot.send_message(
        ADMIN_ID,
        f"❌ История #{submission_id} отклонена.\n"
        f"Статус: rejected"
    )
@dp.message(F.content_type == ContentType.TEXT)
async def receive_text(message: Message):
    if message.text.startswith("/"):
        return
    sid = await save_submission(
        message,
        message.text,
        "text"
    )
    await notify_admin(
        message,
        sid,
        message.text,
        "text"
    )
    await message.answer(
        "Принял 👌\n\n"
        "История отправлена на модерацию. "
        "Если она подойдёт для канала — мы её опубликуем."
    )
@dp.message(F.photo)
async def receive_photo(message: Message):
    caption = message.caption or ""
    file_id = message.photo[-1].file_id
    sid = await save_submission(
        message,
        caption,
        "photo",
        file_id
    )
    await notify_admin(
        message,
        sid,
        caption,
        "photo",
        file_id
    )
    await message.answer(
        "Фото получил 👌\n\n"
        "История отправлена на модерацию."
    )
@dp.message(F.video)
async def receive_video(message: Message):
    caption = message.caption or ""
    file_id = message.video.file_id
    sid = await save_submission(
        message,
        caption,
        "video",
        file_id
    )
    await notify_admin(
        message,
        sid,
        caption,
        "video",
        file_id
    )
    await message.answer(
        "Видео получил 👌\n\n"
        "История отправлена на модерацию."
    )
@dp.message(F.document)
async def receive_document(message: Message):
    caption = message.caption or ""
    file_id = message.document.file_id
    sid = await save_submission(
        message,
        caption,
        "document",
        file_id
    )
    await notify_admin(
        message,
        sid,
        caption,
        "document",
        file_id
    )
    await message.answer(
        "Файл получил 👌\n\n"
        "История отправлена на модерацию."
    )
@app.get("/")
async def health():
    return {
        "status": "ok",
        "bot": "proizoshlo"
    }
@app.post("/telegram")
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}
@app.on_event("startup")
async def startup():
    await bot.set_webhook(
        f"{os.environ['RENDER_EXTERNAL_URL'].rstrip('/')}/telegram"
    )
@app.on_event("shutdown")
async def shutdown():
    await bot.delete_webhook()
    await bot.session.close()