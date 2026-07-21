"""Создаёт пустую data.db если её нет (схема совпадает с ingest_core._ensure_schema)."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data.db')

def init_db():
    if os.path.exists(DB_PATH):
        return
    print("Создаю пустую базу данных...")
    con = sqlite3.connect(DB_PATH)
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
        n_rows        INTEGER,
        loaded_at     TEXT
    );
    """)
    con.commit()
    con.close()
    print("База данных создана.")

if __name__ == '__main__':
    init_db()
