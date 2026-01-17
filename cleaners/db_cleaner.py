import asyncio
from db_functions.db import cleanup_old_messages
from pathlib import Path
from typing import List


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
            print("Cleaning started")
            media_to_delete = await asyncio.to_thread(cleanup_old_messages)
            res = await delete_media_files(media_to_delete)
            print("Cleanup success")
        except Exception as e:
            print(e)

        await asyncio.sleep(interval_seconds)
            