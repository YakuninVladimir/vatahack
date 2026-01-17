from pathlib import Path
from aiogram import Message

MEDIA_ROOT = Path("media")


async def download_file(message: Message, 
                        file_id: str, 
                        subdir: str) -> str:
    """
    Docstring for download_file
    
    :param message: Description
    :type message: Message
    :param file_id: Description
    :type file_id: str
    :param subdir: Description
    :type subdir: str
    :return: Description
    :rtype: str
    """

    MEDIA_ROOT.mkdir(exist_ok=True)
    target_dir = MEDIA_ROOT / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    await message.bot.download(file_id, destination=target_dir)

    return str(target_dir)
