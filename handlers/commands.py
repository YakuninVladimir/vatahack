import logging

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import (
    AGENT_URL,
    SUMMARY_AGENT_TIMEOUT_SECONDS,
    SUMMARY_CONTEXT_WINDOW_TOKENS,
    SUMMARY_INCLUDE_NOISE,
    SUMMARY_MAX_MESSAGES,
    SUMMARY_MIN_TOPIC_SIZE,
    SUMMARY_OLLAMA_MODEL,
)
from db_functions.checkpoints import get_last_checkpoint, set_last_checkpoint
from db_functions.db import get_messages_after_id


router = Router()
logger = logging.getLogger(__name__)


def _messages_for_agent(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        msg_type = msg.get("type") or "text"
        text = (msg.get("text") or "").strip()
        if not text:
            text = f"[{msg_type}]"
        user = msg.get("username") or str(msg.get("user_id") or "user")
        out.append({"user": user, "type": msg_type, "text": text})
    return out


def _format_summary(result: dict) -> str:
    if not result:
        return "Нет данных для суммаризации."
    blocks: list[str] = []
    for theme_key, item in result.items():
        theme = theme_key
        summary = ""
        if isinstance(item, dict):
            theme = item.get("theme") or theme_key
            summary = (item.get("summary") or "").strip()
        if not summary:
            summary = "(нет данных)"
        blocks.append(f"Тема: {theme}\n{summary}")
    return "\n\n".join(blocks)



@router.message(Command("summarize"))
async def summarize(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    current_message_id = message.message_id

    checkpoint = await get_last_checkpoint(chat_id=chat_id, thread_id=thread_id)
    limit = SUMMARY_MAX_MESSAGES if SUMMARY_MAX_MESSAGES > 0 else None

    logger.info(
        "Summarize requested chat_id=%s thread_id=%s checkpoint=%s",
        chat_id,
        thread_id,
        checkpoint,
    )

    messages = await get_messages_after_id(
        chat_id=chat_id,
        thread_id=thread_id,
        after_message_id=checkpoint,
        before_message_id=current_message_id,
        limit=limit,
    )

    if not messages:
        await set_last_checkpoint(chat_id=chat_id, thread_id=thread_id, message_id=current_message_id)
        logger.info("Checkpoint updated chat_id=%s thread_id=%s message_id=%s", chat_id, thread_id, current_message_id)
        await message.answer("Новых сообщений для суммаризации не найдено.")
        return

    logger.info("Messages collected for summary: %s", len(messages))

    payload = {
        "messages": _messages_for_agent(messages),
        "min_topic_size": SUMMARY_MIN_TOPIC_SIZE,
        "include_noise": SUMMARY_INCLUDE_NOISE,
        "ollama_model": SUMMARY_OLLAMA_MODEL,
        "context_window_tokens": SUMMARY_CONTEXT_WINDOW_TOKENS,
    }

    base_url = AGENT_URL.rstrip("/")
    url = base_url if base_url.endswith("/analyze") else f"{base_url}/analyze"

    try:
        timeout = None
        if SUMMARY_AGENT_TIMEOUT_SECONDS > 0:
            timeout = httpx.Timeout(SUMMARY_AGENT_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
    except Exception as exc:
        logger.exception("Agent request failed: %s", exc)
        await message.answer("Ошибка при обращении к агенту. Попробуй позже.")
        return

    summary_text = _format_summary(result)

    await set_last_checkpoint(chat_id=chat_id, thread_id=thread_id, message_id=current_message_id)

    logger.info("Checkpoint updated chat_id=%s thread_id=%s message_id=%s", chat_id, thread_id, current_message_id)

    await message.answer(f"📄 Суммаризация:\n\n{summary_text}")
