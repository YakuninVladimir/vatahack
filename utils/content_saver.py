from pathlib import Path
from aiogram.types import Message

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

    tg_file = await message.bot.get_file(file_id)
    filename = Path(tg_file.file_path).name if tg_file.file_path else file_id
    target_path = target_dir / filename

    await message.bot.download(file_id, destination=target_path)

    return str(target_path)
