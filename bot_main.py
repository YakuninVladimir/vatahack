import asyncio
import logging
from aiogram import Bot, Dispatcher
from db_functions.db import db_init
from db_functions.checkpoints import checkpoints_init, checkpoints_close
from config import BOT_TOKEN, LOG_LEVEL
from handlers import commands, parser
from cleaners.db_cleaner import db_periodic_cleaner

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN is not set. Put it in .env or export it.")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    await db_init()
    await checkpoints_init()

    dp.include_router(commands.router)
    dp.include_router(parser.router)

    asyncio.create_task(db_periodic_cleaner())

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await checkpoints_close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
