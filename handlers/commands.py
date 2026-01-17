from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from datetime import datetime, timedelta
import asyncio
from db_functions.db import get_messages_since, get_last_messages


router = Router()

def summarize_messages(messages):
    """
    Placeholder
    
    :param messages: Description
    """
    return " ".join(messages)



@router.message(Command("summarize"))
async def summarize(message: Message):
    args = message.text.split()  
    
    limit = None
    since_time = None

    
    if len(args) == 1:
        since_time = datetime.utcnow() - timedelta(hours=24)

    else:
        arg = args[1].lower()

        if arg.endswith("h"):
            try:
                hours = int(arg[:-1])
                since_time = datetime.utcnow() - timedelta(hours=hours)
            except ValueError:
                await message.answer("Неверный формат времени. Используй /summarize 10h или /summarize 1000")
                return
        else:
            try:
                limit = int(arg)
            except ValueError:
                await message.answer("Неверный аргумент. Используй /summarize 10h или /summarize 1000")
                return

    
    if since_time:
        messages = get_messages_since(chat_id=message.chat.id, since=since_time)
    elif limit:
        messages = get_last_messages(chat_id=message.chat.id, limit=limit)
    else:
        messages = []

    if not messages:
        await message.answer("Сообщений для суммаризации не найдено.")
        return

    summary_text = await asyncio.to_thread(summarize_messages, messages)

    await message.answer(f"📄 Суммаризация:\n\n{summary_text}")
