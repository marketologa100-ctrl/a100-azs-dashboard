"""Создаёт пустую data.db если её нет."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data.db')

def init_db():
    if os.path.exists(DB_PATH):
        return
    print("Создаю пустую базу данных...")
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt_str TEXT,
            receipt_id TEXT,
            azs_num TEXT,
            category TEXT,
            product TEXT,
            qty REAL,
            amount REAL,
            net_amount REAL,
            pay_type TEXT,
            loyalty TEXT,
            discount REAL,
            month_key TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_dt ON lines(dt_str)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_azs ON lines(azs_num)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_month ON lines(month_key)")
    con.commit()
    con.close()
    print("База данных создана.")

if __name__ == '__main__':
    init_db()
