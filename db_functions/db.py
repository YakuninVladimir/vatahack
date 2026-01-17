import asyncpg
import asyncio
from datetime import datetime, timedelta
from config import DB_DSN


db_pool: asyncpg.Pool | None = None  # глобальный пул


async def db_init(dsn: str = DB_DSN):
    """
    Инициализация БД:
    - создаём пул
    - создаём таблицу messages, если не существует
    - создаём индексы для быстрого поиска
    """
    global db_pool
    db_pool = await asyncpg.create_pool(dsn=dsn)

    async with db_pool.acquire() as conn:
        # создаём таблицу
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            thread_id BIGINT,
            user_id BIGINT,
            username TEXT,
            type TEXT,
            text TEXT,
            file_id TEXT,
            file_path TEXT,
            created_at TIMESTAMPTZ NOT NULL
        );
        """)

        # индекс для поиска по чату и времени
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_time ON messages(chat_id, created_at);
        """)

        # индекс для поиска по чату и топику (ветке)
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_thread ON messages(chat_id, thread_id);
        """)

    print("✅ DB initialized and ready")



async def get_messages_since(chat_id: int, since, thread_id: int | None = None):
    """
    Получить сообщения с указанного времени.
    Если thread_id указан, фильтруем по конкретной ветке форума.
    Если thread_id=None, берём все сообщения чата.
    """
    async with db_pool.acquire() as conn:
        if thread_id is not None:
            query = """
                SELECT * FROM messages
                WHERE chat_id=$1 AND created_at > $2 AND thread_id=$3
                ORDER BY created_at ASC
            """
            rows = await conn.fetch(query, chat_id, since, thread_id)
        else:
            query = """
                SELECT * FROM messages
                WHERE chat_id=$1 AND created_at > $2
                ORDER BY created_at ASC
            """
            rows = await conn.fetch(query, chat_id, since)

        return [dict(row) for row in rows]

    

async def cleanup_old_messages(hours: int = 24) -> list[dict]:
    """
    Получает все старые сообщения с медиа (voice, photo, video, video_note),
    возвращает список словарей {file_path, type, message_id, chat_id, thread_id}, 
    затем удаляет их из таблицы.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    old_media = []

    async with db_pool.acquire() as conn:
        # 1️⃣ Получаем все сообщения старше cutoff с медиаконтентом
        rows = await conn.fetch(
            """
            SELECT id, chat_id, message_id, thread_id, type, file_path
            FROM messages
            WHERE created_at < $1
            AND type IN ('voice', 'photo', 'video', 'video_note')
            """,
            cutoff
        )

        for row in rows:
            if row["file_path"]:  # если есть локальный файл
                old_media.append({
                    "id": row["id"],
                    "chat_id": row["chat_id"],
                    "message_id": row["message_id"],
                    "thread_id": row["thread_id"],
                    "type": row["type"],
                    "file_path": row["file_path"]
                })

        # 2️⃣ Удаляем все сообщения старше cutoff
        await conn.execute(
            "DELETE FROM messages WHERE created_at < $1",
            cutoff
        )

    return old_media


async def get_last_messages(chat_id: int, limit: int, thread_id: int | None = None):
    """
    Получить последние сообщения чата с лимитом.
    Если thread_id указан, фильтруем по конкретной ветке форума.
    Если thread_id=None, берём все сообщения чата.
    """
    async with db_pool.acquire() as conn:
        if thread_id is not None:
            query = """
                SELECT * FROM messages
                WHERE chat_id=$1 AND thread_id=$2
                ORDER BY created_at DESC
                LIMIT $3
            """
            rows = await conn.fetch(query, chat_id, thread_id, limit)
        else:
            query = """
                SELECT * FROM messages
                WHERE chat_id=$1
                ORDER BY created_at DESC
                LIMIT $2
            """
            rows = await conn.fetch(query, chat_id, limit)

        return [dict(row) for row in reversed(rows)]


async def save_message(
    chat_id: int,
    message_id: int,
    thread_id: int | None,
    user_id: int | None,
    username: str | None,
    msg_type: str,
    text: str | None,
    file_id: str | None,
    file_path: str | None,
    created_at: datetime
):
    """
    Сохраняет одно сообщение в таблицу messages.
    thread_id: привязка к ветке форума (None = General)
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (
                chat_id,
                message_id,
                thread_id,
                user_id,
                username,
                type,
                text,
                file_id,
                file_path,
                created_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (chat_id, message_id) DO NOTHING
            """,
            chat_id,
            message_id,
            thread_id,
            user_id,
            username,
            msg_type,
            text,
            file_id,
            file_path,
            created_at
        )



if __name__ == "__main__":
    asyncio.run(db_init())
