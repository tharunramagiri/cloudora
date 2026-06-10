import aiosqlite
import os
from . import settings


def get_db_path() -> str:
    path = settings.DATABASE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


async def init_db():
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                message_id INTEGER,
                file_name TEXT,
                file_size INTEGER,
                mime_type TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expiration_date TIMESTAMP,
                share_token TEXT UNIQUE,
                view_count INTEGER DEFAULT 0,
                password TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                owner TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO api_keys (key, owner) VALUES (?, ?)",
            (settings.ADMIN_API_KEY, "admin"),
        )
        await db.commit()


async def verify_key_db(key: str) -> bool:
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT 1 FROM api_keys WHERE key = ?", (key,)) as cur:
            return await cur.fetchone() is not None


async def add_file(file_id, message_id, file_name, file_size, mime_type,
                   expiration_date=None, share_token=None, password=None):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO files (file_id, message_id, file_name, file_size, "
            "mime_type, expiration_date, share_token, password) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, message_id, file_name, file_size, mime_type,
             expiration_date, share_token, password),
        )
        await db.commit()


async def get_file_by_id(file_id: str):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)) as cur:
            return await cur.fetchone()


async def get_file_by_share_token(token: str):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM files WHERE share_token = ?", (token,)
        ) as cur:
            return await cur.fetchone()


async def increment_view_count(file_id: str):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE files SET view_count = view_count + 1 WHERE file_id = ?",
            (file_id,),
        )
        await db.commit()


async def list_files(limit=50, offset=0, search=None):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM files"
        params = []
        if search:
            query += " WHERE file_name LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY upload_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        async with db.execute(query, params) as cur:
            return await cur.fetchall()


async def get_stats():
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT COUNT(*), COALESCE(SUM(file_size), 0), "
            "COALESCE(SUM(view_count), 0) FROM files"
        ) as cur:
            row = await cur.fetchone()
            return {
                "total_files": row[0] or 0,
                "total_size_bytes": row[1] or 0,
                "total_views": row[2] or 0,
            }


async def delete_file_db(file_id: str):
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
        await db.commit()


async def get_expired_files():
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM files WHERE expiration_date IS NOT NULL "
            "AND expiration_date <= datetime('now')"
        ) as cur:
            return await cur.fetchall()
