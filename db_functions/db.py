import asyncpg
import asyncio
import json
import logging
from datetime import datetime, timedelta
from config import DB_DSN


logger = logging.getLogger(__name__)

db_pool: asyncpg.Pool | None = None  # глобальный пул


def _checkpoint_thread_id(thread_id: int | None) -> int:
    return int(thread_id or 0)


def _require_pool() -> asyncpg.Pool:
    if db_pool is None:
        raise RuntimeError("DB pool is not initialized. Call db_init() first.")
    return db_pool


async def db_init(dsn: str = DB_DSN):
    """
    Инициализация БД:
    - создаём пул
    - создаём таблицу messages, если не существует
    - создаём индексы для быстрого поиска
    """
    global db_pool
    if not dsn:
        raise RuntimeError("DB_DSN is not set. Put it in .env or export it.")
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

        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_thread_message ON messages(chat_id, thread_id, message_id);
        """)

        # уникальность сообщения в чате (для ON CONFLICT)
        await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_message ON messages(chat_id, message_id);
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS summary_checkpoints (
            chat_id BIGINT NOT NULL,
            thread_id BIGINT NOT NULL,
            last_message_id BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chat_id, thread_id)
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS summary_results (
            chat_id BIGINT NOT NULL,
            thread_id BIGINT NOT NULL,
            summary_json TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chat_id, thread_id)
        );
        """)

    logger.info("DB initialized and ready")



async def get_messages_since(chat_id: int, since, thread_id: int | None = None):
    """
    Получить сообщения с указанного времени.
    Если thread_id указан, фильтруем по конкретной ветке форума.
    Если thread_id=None, берём все сообщения чата.
    """
    pool = _require_pool()
    async with pool.acquire() as conn:
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


async def get_messages_after_id(
    chat_id: int,
    thread_id: int | None,
    after_message_id: int | None,
    before_message_id: int | None,
    limit: int | None = None,
):
    """
    Получить сообщения после указанного message_id (исключая его).
    Можно ограничить выборку верхней границей before_message_id (исключая её).
    Если limit задан, возвращает последние limit сообщений (в хронологическом порядке).
    """
    if limit is not None and limit <= 0:
        return []

    pool = _require_pool()
    async with pool.acquire() as conn:
        clauses = ["chat_id=$1"]
        params: list[object] = [chat_id]

        if thread_id is None:
            clauses.append("thread_id IS NULL")
        else:
            params.append(thread_id)
            clauses.append(f"thread_id=${len(params)}")

        if after_message_id is not None:
            params.append(after_message_id)
            clauses.append(f"message_id > ${len(params)}")

        if before_message_id is not None:
            params.append(before_message_id)
            clauses.append(f"message_id < ${len(params)}")

        order = "ORDER BY message_id ASC"
        limit_clause = ""

        if limit is not None:
            order = "ORDER BY message_id DESC"
            params.append(limit)
            limit_clause = f"LIMIT ${len(params)}"

        query = f"""
            SELECT * FROM messages
            WHERE {" AND ".join(clauses)}
            {order}
            {limit_clause}
        """
        rows = await conn.fetch(query, *params)
        if limit is not None:
            rows = list(reversed(rows))
        return [dict(row) for row in rows]

    

async def cleanup_old_messages(hours: int = 24) -> list[dict]:
    """
    Получает все старые сообщения с медиа (voice, photo, video, video_note),
    возвращает список словарей {file_path, type, message_id, chat_id, thread_id}, 
    затем удаляет их из таблицы.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    old_media = []

    pool = _require_pool()
    async with pool.acquire() as conn:
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


async def get_summary_checkpoint_db(chat_id: int, thread_id: int | None) -> int | None:
    """
    Возвращает последний message_id, который был отмечен как чекпоинт для суммаризации.
    """
    pool = _require_pool()
    tid = _checkpoint_thread_id(thread_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT last_message_id
            FROM summary_checkpoints
            WHERE chat_id=$1 AND thread_id=$2
            """,
            chat_id,
            tid,
        )
        return int(row["last_message_id"]) if row else None


async def set_summary_checkpoint_db(chat_id: int, thread_id: int | None, message_id: int):
    """
    Обновляет/создаёт чекпоинт для суммаризации.
    """
    pool = _require_pool()
    tid = _checkpoint_thread_id(thread_id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO summary_checkpoints (chat_id, thread_id, last_message_id, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (chat_id, thread_id)
            DO UPDATE SET last_message_id=EXCLUDED.last_message_id, updated_at=now()
            """,
            chat_id,
            tid,
            message_id,
        )


async def get_summary_state_db(chat_id: int, thread_id: int | None) -> dict[str, str] | None:
    """
    Возвращает сохраненное саммари в виде словаря {theme: summary}.
    """
    pool = _require_pool()
    tid = _checkpoint_thread_id(thread_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT summary_json
            FROM summary_results
            WHERE chat_id=$1 AND thread_id=$2
            """,
            chat_id,
            tid,
        )
        if not row:
            return None
        raw = row["summary_json"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid summary JSON chat_id=%s thread_id=%s", chat_id, tid)
        return None

    if not isinstance(data, dict):
        return None

    cleaned: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        cleaned[str(key)] = str(value)
    return cleaned


async def set_summary_state_db(chat_id: int, thread_id: int | None, summary: dict[str, str]):
    """
    Сохраняет саммари в виде словаря {theme: summary}.
    """
    pool = _require_pool()
    tid = _checkpoint_thread_id(thread_id)
    payload = json.dumps(summary or {})
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO summary_results (chat_id, thread_id, summary_json, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (chat_id, thread_id)
            DO UPDATE SET summary_json=EXCLUDED.summary_json, updated_at=now()
            """,
            chat_id,
            tid,
            payload,
        )


async def get_last_messages(chat_id: int, limit: int, thread_id: int | None = None):
    """
    Получить последние сообщения чата с лимитом.
    Если thread_id указан, фильтруем по конкретной ветке форума.
    Если thread_id=None, берём все сообщения чата.
    """
    pool = _require_pool()
    async with pool.acquire() as conn:
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
    pool = _require_pool()
    async with pool.acquire() as conn:
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
