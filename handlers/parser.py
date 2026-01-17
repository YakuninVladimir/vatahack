import logging

from aiogram import Router
from aiogram.types import Message
from utils.content_saver import download_file
from db_functions.db import save_message

router = Router()
logger = logging.getLogger(__name__)


@router.message()
async def save_to_db(message: Message):
    msg_type = None
    text = None
    file_id = None
    file_path = None

    thread_id = message.message_thread_id

    if message.text:
        msg_type = "text"
        text = message.text

    elif message.voice:
        msg_type = "voice"
        file_id = message.voice.file_id
        file_path = await download_file(message, file_id, "voice")

    elif message.photo:
        msg_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.caption
        file_path = await download_file(message, file_id, "photo")

    elif message.video:
        msg_type = "video"
        file_id = message.video.file_id
        text = message.caption
        file_path = await download_file(message, file_id, "video")

    elif message.video_note:
        msg_type = "video_note"
        file_id = message.video_note.file_id
        text = message.caption
        file_path = await download_file(message, file_id, "video_note")

    else:
        return

    try:
        await save_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            thread_id=thread_id,  # ветка форума или None
            user_id=message.from_user.id if message.from_user else None,
            username=message.from_user.username if message.from_user else None,
            msg_type=msg_type,
            text=text,
            file_id=file_id,
            file_path=file_path,
            created_at=message.date
        )
    except Exception as exc:
        logger.exception("Failed to save message chat_id=%s message_id=%s: %s", message.chat.id, message.message_id, exc)
