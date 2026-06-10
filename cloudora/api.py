import os
import re
import secrets
import shutil
import datetime
import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, Header, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import settings
from .database import (
    add_file, get_file_by_id, delete_file_db,
    get_file_by_share_token, increment_view_count,
    list_files, get_stats, verify_key_db, init_db,
)
from .bot import cluster

logger = logging.getLogger(__name__)

api = FastAPI(title="Cloudora API")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)


async def verify_api_key(
    x_api_key: Optional[str] = Header(None),
    key: Optional[str] = Query(None),
):
    provided = (x_api_key or key or "").strip()
    if not provided:
        raise HTTPException(403, "API key required")
    if provided == settings.ADMIN_API_KEY.strip():
        return provided
    if await verify_key_db(provided):
        return provided
    raise HTTPException(403, "Invalid API key")


@api.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(cluster.start_all())
    asyncio.create_task(cleanup_loop())


import asyncio


async def cleanup_loop():
    while True:
        try:
            from .database import get_expired_files
            expired = await get_expired_files()
            for f in expired:
                try:
                    await cluster.delete_messages(
                        settings.CHANNEL_ID, f["message_id"]
                    )
                except Exception:
                    pass
                await delete_file_db(f["file_id"])
        except Exception:
            pass
        await asyncio.sleep(3600)


@api.get("/", response_class=HTMLResponse)
async def dashboard():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>Cloudora</h1><p>Dashboard not found</p>"


@api.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    expiration_days: int = Form(None),
    password: str = Form(None),
    auth: str = Depends(verify_api_key),
):
    bot = await cluster.get_healthy_bot()
    if not bot:
        raise HTTPException(503, "No healthy bots available")

    temp = f"temp_{secrets.token_hex(4)}_{file.filename}"
    try:
        with open(temp, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        size = os.path.getsize(temp)

        is_video = file.content_type and "video" in file.content_type.lower()
        with open(temp, "rb") as f:
            if is_video:
                msg = await asyncio.wait_for(
                    bot.send_video(
                        chat_id=settings.CHANNEL_ID, video=f,
                        filename=file.filename, supports_streaming=True,
                    ),
                    timeout=600,
                )
            else:
                msg = await asyncio.wait_for(
                    bot.send_document(
                        chat_id=settings.CHANNEL_ID, document=f,
                        filename=file.filename,
                    ),
                    timeout=300,
                )

        media = msg.video or msg.document
        fid = media.file_id
        token = secrets.token_urlsafe(16)
        exp = None
        if expiration_days:
            exp = (
                datetime.datetime.now() + datetime.timedelta(days=expiration_days)
            ).isoformat()

        await add_file(
            fid, msg.message_id, file.filename, size,
            file.content_type or "application/octet-stream",
            exp, token, password,
        )

        return {
            "status": "ok",
            "file_id": fid,
            "filename": file.filename,
            "size": size,
            "direct_url": f"{settings.BASE_URL}/dl/{fid}/{file.filename}",
            "share_url": f"{settings.BASE_URL}/share/{token}",
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, str(e))
    finally:
        if os.path.exists(temp):
            os.remove(temp)


@api.get("/dl/{file_id}/{filename:path}")
async def download(file_id: str, filename: str, request: Request):
    data = await get_file_by_id(file_id)
    if not data:
        raise HTTPException(404, "File not found")

    await increment_view_count(file_id)
    bot = await cluster.get_healthy_bot()
    if not bot:
        raise HTTPException(503, "No bots available")

    try:
        tg_file = await bot.get_file(file_id)
        url = tg_file.file_path
    except Exception as e:
        raise HTTPException(502, f"Telegram error: {e}")

    size = data["file_size"]
    mime = data["mime_type"]
    range_h = request.headers.get("range")
    start, end = 0, size - 1
    status = 200

    if range_h:
        m = re.match(r"bytes=(\d+)-(\d+)?", range_h)
        if m:
            start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            status = 206

    headers = {
        "Content-Type": mime,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{data["file_name"]}"',
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "public, max-age=3600",
    }

    async def stream():
        proxy = None
        if settings.PROXY_HOST and settings.PROXY_PORT:
            auth = ""
            if settings.PROXY_USER and settings.PROXY_PASS:
                auth = f"{settings.PROXY_USER}:{settings.PROXY_PASS}@"
            proxy = f"http://{auth}{settings.PROXY_HOST}:{settings.PROXY_PORT}"

        req_headers = {"Range": f"bytes={start}-{end}"}
        async with httpx.AsyncClient(proxy=proxy) as client:
            async with client.stream("GET", url, headers=req_headers) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), status_code=status, headers=headers)


@api.get("/share/{token}")
async def share_page(token: str, request: Request):
    data = await get_file_by_share_token(token)
    if not data:
        raise HTTPException(404, "File not found")
    return f"""<!DOCTYPE html><html><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Cloudora - {data['file_name']}</title>
    <script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-900 text-white min-h-screen flex items-center justify-center">
    <div class="text-center p-8"><h1 class="text-2xl font-bold mb-4">{data['file_name']}</h1>
    <p class="text-gray-400 mb-6">{(data['file_size'] / 1024 / 1024):.1f} MB</p>
    <a href="/dl/{data['file_id']}/{data['file_name']}"
       class="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg inline-block">Download</a></div></body></html>"""


@api.get("/api/files")
async def api_list_files(
    limit: int = 50, offset: int = 0, search: str = None,
    auth: str = Depends(verify_api_key),
):
    files = await list_files(limit, offset, search)
    return [
        {
            "id": f["id"],
            "file_id": f["file_id"],
            "file_name": f["file_name"],
            "file_size": f["file_size"],
            "mime_type": f["mime_type"],
            "upload_date": f["upload_date"],
            "view_count": f["view_count"],
            "share_url": f"{settings.BASE_URL}/share/{f['share_token']}" if f["share_token"] else None,
        }
        for f in files
    ]


@api.get("/api/stats")
async def api_stats(auth: str = Depends(verify_api_key)):
    return await get_stats()


@api.delete("/api/files/{file_id}")
async def api_delete_file(
    file_id: str, auth: str = Depends(verify_api_key)
):
    data = await get_file_by_id(file_id)
    if not data:
        raise HTTPException(404, "File not found")
    try:
        await cluster.delete_messages(settings.CHANNEL_ID, data["message_id"])
    except Exception:
        pass
    await delete_file_db(file_id)
    return {"status": "deleted"}
