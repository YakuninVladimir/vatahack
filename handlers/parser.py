import logging
import mimetypes

from aiogram import Router
from aiogram.types import Message
from utils.content_saver import download_file
from db_functions.db import save_message
import asyncio
import os
import httpx

from config import PHOTO_SERVICE_URL, SPEECH_SERVICE_URL, MEDIA_TIMEOUT_SECONDS, TESS_LANG
from db_functions.db import save_message, update_message_text

router = Router()
logger = logging.getLogger(__name__)

async def _post_file(url: str, field: str, file_path: str, timeout_sec: int, params=None) -> dict:
    timeout = httpx.Timeout(timeout_sec)
    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or "application/octet-stream"

    async with httpx.AsyncClient(timeout=timeout) as client:
        with open(file_path, "rb") as f:
            files = {field: (os.path.basename(file_path), f, mime)}
            r = await client.post(url, files=files, params=params)
            r.raise_for_status()
            return r.json()


async def _process_media(chat_id: int, message_id: int, msg_type: str, file_path: str):
    try:
        if not file_path or not os.path.exists(file_path):
            return

        if msg_type == "photo" and PHOTO_SERVICE_URL:
            url = PHOTO_SERVICE_URL.rstrip("/") + "/v1/ocr"
            data = await _post_file(url, "image", file_path, MEDIA_TIMEOUT_SECONDS)
            text = (data.get("text") or "").strip()
            if text:
                await update_message_text(chat_id, message_id, f"[OCR {data.get('lang','')}]\n{text}")

        elif msg_type in ("voice", "video_note", "video") and SPEECH_SERVICE_URL:
            url = SPEECH_SERVICE_URL.rstrip("/") + "/v1/transcribe"
            data = await _post_file(url, "audio", file_path, MEDIA_TIMEOUT_SECONDS)
            text = (data.get("text") or "").strip()
            if text:
                await update_message_text(chat_id, message_id, f"[ASR]\n{text}")

    except Exception:
        logger.exception("Media processing failed chat_id=%s message_id=%s type=%s", chat_id, message_id, msg_type)

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
            # После сохранения — распознаём медиа в фоне и дописываем text в БД
        if file_path and msg_type in ("photo", "voice", "video_note", "video"):
            asyncio.create_task(_process_media(message.chat.id, message.message_id, msg_type, file_path))

    except Exception as exc:
        logger.exception("Failed to save message chat_id=%s message_id=%s: %s", message.chat.id, message.message_id, exc)
