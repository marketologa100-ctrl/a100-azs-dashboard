"""
FastAPI backend для дашборда АЗС.
Порт: 8000
"""
import asyncio
import json
import math
import os
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ingest_core import ingest_to_db, _ensure_schema
import queries as Q

# ─── Пути ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DB_PATH   = BASE_DIR / 'data.db'
UPLOAD_DIR = BASE_DIR / 'uploads'
FRONT_DIR  = BASE_DIR / 'frontend'
TMP_DIR    = BASE_DIR / 'uploads' / '_tmp'
UPLOAD_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# ─── Jobs store (in-memory) ──────────────────────────────────────────────────
_jobs: dict[str, dict] = {}

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title='AZS Dashboard API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'], allow_credentials=False,
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type', 'Accept'],
)

def get_con():
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    _ensure_schema(con)
    return con

def safe(v):
    if v is None: return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    return v

def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return safe(obj)

# ─── Эндпоинты ───────────────────────────────────────────────────────────────

@app.get('/api/health')
def health():
    return {'status': 'ok'}

@app.get('/api/manifest')
def manifest():
    con = get_con()
    try:
        rows = Q.q_manifest(con)
        dr = Q.q_date_range(con)
        return sanitize({'periods': rows, 'date_range': dr})
    finally:
        con.close()

@app.get('/api/azs_list')
def azs_list():
    """Список уникальных номеров АЗС."""
    con = get_con()
    try:
        return {'azs': Q.q_azs_list(con)}
    finally:
        con.close()

@app.get('/api/aggregates')
def aggregates(d1: str, d2: str, c1: Optional[str] = None, c2: Optional[str] = None,
               azs: Optional[str] = None):
    """
    d1, d2 — основной диапазон (YYYY-MM-DD).
    c1, c2 — диапазон сравнения (опционально).
    azs    — фильтр по АЗС: '1,5,12' (опционально, все АЗС если не задан).
    """
    if not d1 or not d2:
        raise HTTPException(400, 'Укажите d1 и d2')
    # Парсим список АЗС
    azs_filter = [a.strip() for a in azs.split(',') if a.strip()] if azs else None
    con = get_con()
    try:
        main_data = sanitize(Q.q_all(con, d1, d2, azs=azs_filter))
        result = {'main': main_data, 'range': {'d1': d1, 'd2': d2}}
        if c1 and c2:
            cmp_data = sanitize(Q.q_all(con, c1, c2, azs=azs_filter))
            result['compare'] = cmp_data
            result['compare_range'] = {'d1': c1, 'd2': c2}
        return result
    finally:
        con.close()

# ─── Загрузка файла ──────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
ALLOWED_EXTENSIONS = {'.xls', '.xlsx'}

@app.post('/api/upload')
async def upload_file(file: UploadFile = File(...)):
    """Принимает .xls/.xlsx, возвращает job_id для SSE-мониторинга."""
    # ── Валидация имени и расширения ──────────────────────────────────────
    orig_name = Path(file.filename or 'upload.xls').name  # strip any directory components
    suffix = Path(orig_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f'Недопустимый формат файла: {suffix}. Разрешены только .xls и .xlsx')

    # ── Читаем с ограничением размера ─────────────────────────────────────
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'Файл слишком большой. Максимальный размер: 200 МБ')

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {'status': 'queued', 'pct': 0, 'msg': 'В очереди...', 'result': None, 'error': None}

    # ── Сохраняем файл безопасно ──────────────────────────────────────────
    safe_name = f'{job_id}{suffix}'  # only job_id + validated extension
    save_path = UPLOAD_DIR / safe_name
    # Double-check no path traversal
    if not save_path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(400, 'Недопустимый путь файла')
    save_path.write_bytes(content)

    # Запускаем обработку в фоне
    asyncio.create_task(_process_file(job_id, save_path, orig_name))
    return {'job_id': job_id}

async def _process_file(job_id: str, save_path: Path, orig_name: str):
    """Асинхронная обёртка над синхронным ingest_to_db."""
    def progress(pct, msg):
        _jobs[job_id].update({'status': 'running', 'pct': pct, 'msg': msg})

    try:
        _jobs[job_id].update({'status': 'running', 'pct': 2, 'msg': 'Запуск...'})

        # .xls читается напрямую через xlrd, конвертация не нужна
        xlsx_path = save_path

        # Ingest
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: ingest_to_db(xlsx_path, orig_name, DB_PATH, progress)
        )
        _jobs[job_id].update({
            'status': 'done', 'pct': 100,
            'msg': f"Загружено: {result['n_receipts']:,} чеков, {result['n_lines']:,} позиций",
            'result': result
        })
    except Exception as e:
        _jobs[job_id].update({'status': 'error', 'pct': 0, 'msg': str(e), 'error': str(e)})

@app.get('/api/job/{job_id}')
def job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, 'Job not found')
    return _jobs[job_id]

@app.get('/api/job/{job_id}/stream')
def job_stream(job_id: str):
    """SSE-стрим прогресса."""
    if job_id not in _jobs:
        raise HTTPException(404, 'Job not found')

    def event_gen():
        last_ping = time.time()
        while True:
            job = _jobs.get(job_id, {})
            data = json.dumps(job)
            yield f'data: {data}\n\n'
            if job.get('status') in ('done', 'error'):
                break
            # Keepalive comment каждые 15 сек чтобы Render не закрыл соединение
            if time.time() - last_ping > 15:
                yield ': keepalive\n\n'
                last_ping = time.time()
            time.sleep(0.5)

    return StreamingResponse(event_gen(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

# ─── Статика (фронтенд) ──────────────────────────────────────────────────────
if FRONT_DIR.exists():
    app.mount('/', StaticFiles(directory=str(FRONT_DIR), html=True), name='frontend')

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000, log_level='info')
