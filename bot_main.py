import asyncio
from aiogram import Bot, Dispatcher
from db_functions.db import db_init
from config import BOT_TOKEN
from handlers import commands, parser
from cleaners.db_cleaner import db_periodic_cleaner


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    db_init()

    dp.include_router(commands.router)
    dp.include_router(parser.router)

    asyncio.create_task(db_periodic_cleaner)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())