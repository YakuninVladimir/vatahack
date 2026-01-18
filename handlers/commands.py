import logging

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

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
from db_functions.db import get_messages_after_id, get_summary_state_db, set_summary_state_db

router = Router()
logger = logging.getLogger(__name__)

TG_MESSAGE_LIMIT = 3900


def split_tg_message(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    """
    Splits text into chunks safe for Telegram message limit.

    Strategy:
    1. Try to split by double newline (paragraphs)
    2. If paragraph too big — split by single newline
    3. If still too big — hard split by characters
    """

    if not text:
        return []

    parts: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            parts.append(buf)
            buf = ""

    for paragraph in text.split("\n\n"):
        if len(paragraph) > limit:
            # split by lines
            for line in paragraph.split("\n"):
                if len(line) > limit:
                    # hard split
                    for i in range(0, len(line), limit):
                        flush()
                        parts.append(line[i: i + limit])
                else:
                    if len(buf) + len(line) + 1 > limit:
                        flush()
                    buf = f"{buf}\n{line}" if buf else line
            flush()
        else:
            if len(buf) + len(paragraph) + 2 > limit:
                flush()
            buf = f"{buf}\n\n{paragraph}" if buf else paragraph

    flush()
    return parts


def _messages_for_agent(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        msg_type = msg.get("type") or "text"
        text = (msg.get("text") or "").strip()
        if not text:
            continue
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


def _summary_state_from_result(result: dict) -> dict[str, str]:
    state: dict[str, str] = {}
    for theme_key, item in result.items():
        if not isinstance(item, dict):
            continue
        theme = (item.get("theme") or theme_key or "").strip()
        summary = (item.get("summary") or "").strip()
        if not theme or not summary:
            continue
        state[theme] = summary
    return state


@router.message(Command("summarize"))
async def summarize(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    current_message_id = message.message_id

    await message.answer("⏳ Собираю и анализирую сообщения, подожди…")
    await message.chat.do("typing")

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
        await message.answer("Новых сообщений для суммаризации не найдено.")
        return

    logger.info("Messages collected for summary: %s", len(messages))
    last_message_id = messages[-1]["message_id"]

    agent_messages = _messages_for_agent(messages)

    if not agent_messages:
        await set_last_checkpoint(chat_id=chat_id, thread_id=thread_id, message_id=last_message_id)
        logger.info("Checkpoint updated chat_id=%s thread_id=%s message_id=%s", chat_id, thread_id, last_message_id)
        await message.answer("Новых текстовых сообщений для суммаризации не найдено.")
        return

    previous_summary = await get_summary_state_db(chat_id=chat_id, thread_id=thread_id)

    payload = {
        "messages": agent_messages,
        "min_topic_size": SUMMARY_MIN_TOPIC_SIZE,
        "include_noise": SUMMARY_INCLUDE_NOISE,
        "ollama_model": SUMMARY_OLLAMA_MODEL,
        "context_window_tokens": SUMMARY_CONTEXT_WINDOW_TOKENS,
    }
    if previous_summary:
        payload["previous_summary"] = previous_summary

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
    summary_state = _summary_state_from_result(result)
    if not summary_state and previous_summary:
        summary_state = previous_summary
    await set_summary_state_db(chat_id=chat_id, thread_id=thread_id, summary=summary_state)

    await set_last_checkpoint(chat_id=chat_id, thread_id=thread_id, message_id=last_message_id)

    logger.info("Checkpoint updated chat_id=%s thread_id=%s message_id=%s", chat_id, thread_id, last_message_id)

    full_text = f"📄 Суммаризация:\n\n{summary_text}"

    for chunk in split_tg_message(full_text):
        try:
            await message.answer(chunk)
        except TelegramBadRequest:
            # fallback на всякий случай
            await message.answer(chunk[:TG_MESSAGE_LIMIT])
