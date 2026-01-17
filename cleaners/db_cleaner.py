import asyncio
import logging
from db_functions.db import cleanup_old_messages
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

async def delete_media_files(media_to_delete: List[dict]) -> List[dict]:
    """
    Удаляет медиаконтент с диска по списку media_to_delete.
    media_to_delete: список словарей
        {
            "id": ...,
            "chat_id": ...,
            "message_id": ...,
            "thread_id": ...,
            "type": ...,
            "file_path": ...
        }
    Возвращает список результатов:
        {
            "file_path": ...,
            "deleted": True/False
        }
    """
    results = []

    for media in media_to_delete:
        file_path = media.get("file_path")
        if not file_path:
            results.append({"file_path": None, "deleted": False})
            continue

        path = Path(file_path)
        try:
            if path.exists():
                path.unlink()
                results.append({"file_path": file_path, "deleted": True})
            else:
                results.append({"file_path": file_path, "deleted": False})
        except Exception as e:
            # можно логировать ошибку e
            results.append({"file_path": file_path, "deleted": False})

    return results




async def db_periodic_cleaner(interval_seconds: int = 1 * 3600):
    while True:
        try:
            logger.info("Cleaning started")
            media_to_delete = await cleanup_old_messages()
            res = await delete_media_files(media_to_delete)
            deleted = sum(1 for item in res if item.get("deleted"))
            logger.info("Cleanup success deleted=%s", deleted)
        except Exception as e:
            logger.exception("Cleanup failed: %s", e)

        await asyncio.sleep(interval_seconds)
            
