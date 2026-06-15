"""
ingest_core.py — ядро нормализации. Без зависимостей от CLI.
Импортируется бэкендом.
"""
import re
import subprocess
import warnings
from pathlib import Path

import pandas as pd
import sqlite3

warnings.filterwarnings('ignore')

# ─── Маппинг колонок ────────────────────────────────────────────────────────
COL_IDX = {
    0: 'azs_raw', 1: 'date', 2: 'time',
    3: 'loyalty_card_id', 4: 'loyalty_status',
    5: 'payment_type', 6: 'payment_card_num',
    7: 'item_type', 8: 'direction', 9: 'product_name',
    10: 'barcode', 11: 'qty', 12: 'price', 13: 'gross_amount',
    14: 'bonus_spent_base', 15: 'bonus_spent_promo',
    17: 'bonus_earned_base', 18: 'bonus_earned_promo',
    19: 'discount', 20: 'promo', 21: 'net_amount', 22: 'receipt_id',
}

SKIP_PATTERN = re.compile(r'ИТОГО|АЗС №|Итого|Дата|Карта', re.IGNORECASE)

def categorize(item_type: str, direction: str) -> str:
    it = str(item_type).strip()
    dr = str(direction).strip()
    if it == 'Топливо': return 'fuel'
    if it == 'Товары' and dr == 'ФФ': return 'ff'
    if it == 'Товары' and dr == 'ММ': return 'mm'
    if it in ('Сервис', 'Услуги'): return 'service'
    if it == 'Сертификаты': return 'cert'
    return 'other'

def convert_to_xlsx(xls_path: Path, tmpdir: Path) -> Path:
    out = tmpdir / (xls_path.stem + '.xlsx')
    if out.exists():
        return out
    subprocess.run(
        ['libreoffice', '--headless', '--convert-to', 'xlsx',
         '--outdir', str(tmpdir), str(xls_path)],
        check=True, capture_output=True
    )
    return out

def read_xlsx(filepath: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(str(filepath), engine='openpyxl')
    sheets = [s for s in xl.sheet_names if s.startswith('Page')]
    if not sheets:
        sheets = xl.sheet_names

    all_dfs = []
    for sname in sheets:
        df = pd.read_excel(
            filepath, sheet_name=sname, header=None,
            engine='openpyxl', skiprows=4,
            usecols=list(COL_IDX.keys()), dtype=str
        )
        df.columns = [COL_IDX[c] for c in sorted(COL_IDX.keys())]
        mask = ~df['azs_raw'].str.contains(SKIP_PATTERN, na=True)
        all_dfs.append(df[mask])

    return pd.concat(all_dfs, ignore_index=True)

def normalize(df: pd.DataFrame, source_file: str) -> tuple[pd.DataFrame, list[str]]:
    anomalies = []

    df['azs_num'] = df['azs_raw'].where(df['azs_raw'].str.match(r'^\d+$', na=False))
    df['azs_num'] = df['azs_num'].ffill().fillna('0')

    df = df[df['product_name'].notna() & (df['product_name'].str.strip() != '')].copy()

    for col in ['qty', 'price', 'gross_amount', 'discount', 'net_amount',
                'bonus_spent_base', 'bonus_spent_promo', 'bonus_earned_base', 'bonus_earned_promo']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    df['date_parsed'] = pd.to_datetime(df['date'].str.strip(), dayfirst=True, errors='coerce')
    df['datetime'] = pd.to_datetime(
        df['date_parsed'].dt.strftime('%Y-%m-%d') + ' ' + df['time'].str.strip(),
        errors='coerce'
    )
    df['year']    = df['date_parsed'].dt.year.fillna(0).astype(int)
    df['month']   = df['date_parsed'].dt.month.fillna(0).astype(int)
    df['day']     = df['date_parsed'].dt.day.fillna(0).astype(int)
    df['hour']    = df['datetime'].dt.hour.fillna(0).astype(int)
    df['weekday'] = df['date_parsed'].dt.dayofweek.fillna(0).astype(int)
    df['dt_str']  = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    df['category'] = df.apply(
        lambda r: categorize(r['item_type'], r['direction']), axis=1
    )
    other = (df['category'] == 'other').sum()
    if other:
        anomalies.append(f"Не категоризировано: {other} строк")

    df['has_loyalty'] = df['loyalty_card_id'].notna() & (df['loyalty_card_id'].str.strip() != '')
    df['loyalty_card_id'] = df['loyalty_card_id'].where(df['has_loyalty'], '')
    df['bonus_spent']  = df['bonus_spent_base']  + df['bonus_spent_promo']
    df['bonus_earned'] = df['bonus_earned_base'] + df['bonus_earned_promo']
    df['source_file']  = source_file

    return df, anomalies

def ingest_to_db(xlsx_path: Path, source_file: str, db_path: Path,
                 progress_cb=None) -> dict:
    """
    Нормализует файл и записывает в SQLite.
    progress_cb(pct, msg) — опциональный колбэк для SSE.
    Returns: dict со статистикой.
    """
    def cb(p, m):
        if progress_cb: progress_cb(p, m)

    cb(5, 'Читаю листы...')
    df_raw = read_xlsx(xlsx_path)
    cb(40, f'Прочитано {len(df_raw):,} строк, нормализую...')

    df, anomalies = normalize(df_raw, source_file)
    cb(70, f'Нормализовано {len(df):,} строк, записываю в БД...')

    con = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(con)
        # Удаляем старые данные из того же файла (перезапись)
        con.execute("DELETE FROM lines WHERE source_file = ?", (source_file,))
        con.commit()

        # Пишем построчно батчами
        cols = [
            'dt_str', 'year', 'month', 'day', 'hour', 'weekday',
            'azs_num', 'category', 'product_name', 'barcode',
            'qty', 'price', 'gross_amount', 'discount', 'net_amount',
            'bonus_spent', 'bonus_earned', 'promo',
            'payment_type', 'payment_card_num',
            'loyalty_card_id', 'loyalty_status', 'has_loyalty',
            'receipt_id', 'source_file'
        ]
        rows = df[cols].values.tolist()
        con.executemany(
            f"INSERT INTO lines ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
            rows
        )
        con.commit()

        # Обновляем manifest
        total_net = float(df['net_amount'].sum())
        total_discount = float(df['discount'].sum())
        n_receipts = int(df['receipt_id'].nunique())
        n_lines = len(df)

        # Период из данных
        min_date = df['dt_str'].min()[:10] if len(df) else ''
        max_date = df['dt_str'].max()[:10] if len(df) else ''

        con.execute("""
            INSERT OR REPLACE INTO manifest
              (source_file, min_date, max_date, n_lines, n_receipts,
               total_net, total_discount, loaded_at, anomalies)
            VALUES (?,?,?,?,?,?,?,datetime('now'),?)
        """, (source_file, min_date, max_date, n_lines, n_receipts,
              total_net, total_discount, '; '.join(anomalies)))
        con.commit()
    finally:
        con.close()

    cb(100, 'Готово!')
    return {
        'n_lines': n_lines, 'n_receipts': n_receipts,
        'total_net': total_net, 'total_discount': total_discount,
        'min_date': min_date, 'max_date': max_date,
        'anomalies': anomalies,
    }

def _ensure_schema(con: sqlite3.Connection):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS lines (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        dt_str        TEXT,
        year          INTEGER,
        month         INTEGER,
        day           INTEGER,
        hour          INTEGER,
        weekday       INTEGER,
        azs_num       TEXT,
        category      TEXT,
        product_name  TEXT,
        barcode       TEXT,
        qty           REAL,
        price         REAL,
        gross_amount  REAL,
        discount      REAL,
        net_amount    REAL,
        bonus_spent   REAL,
        bonus_earned  REAL,
        promo         TEXT,
        payment_type  TEXT,
        payment_card_num TEXT,
        loyalty_card_id  TEXT,
        loyalty_status   TEXT,
        has_loyalty   INTEGER,
        receipt_id    TEXT,
        source_file   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_dt      ON lines(dt_str);
    CREATE INDEX IF NOT EXISTS idx_cat     ON lines(category);
    CREATE INDEX IF NOT EXISTS idx_azs     ON lines(azs_num);
    CREATE INDEX IF NOT EXISTS idx_pay     ON lines(payment_type);
    CREATE INDEX IF NOT EXISTS idx_receipt ON lines(receipt_id);
    CREATE INDEX IF NOT EXISTS idx_loyalty ON lines(has_loyalty);

    CREATE TABLE IF NOT EXISTS manifest (
        source_file   TEXT PRIMARY KEY,
        min_date      TEXT,
        max_date      TEXT,
        n_lines       INTEGER,
        n_receipts    INTEGER,
        total_net     REAL,
        total_discount REAL,
        loaded_at     TEXT,
        anomalies     TEXT
    );
    """)
