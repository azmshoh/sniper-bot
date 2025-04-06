# migration.py
import sqlite3
import logging
from datetime import datetime
from config.settings import DB_NAME

def run_migrations():
    """Database jadvallarini yaratish va yangilash"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        
        # RPC endpoints jadvali
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rpc_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network TEXT NOT NULL,
            rpc_url TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            last_success TIMESTAMP,
            last_check TIMESTAMP,
            last_error TEXT,
            success_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(network, rpc_url)
        );
        """)

        # Ustunlarni dinamik qo'shish
        columns_to_add = [
            ("is_active", "INTEGER DEFAULT 1"),
            ("last_success", "TIMESTAMP"),
            ("last_check", "TIMESTAMP"),
            ("last_error", "TEXT"),
            ("success_count", "INTEGER DEFAULT 0"),
            ("error_count", "INTEGER DEFAULT 0")
        ]

        for column_name, column_type in columns_to_add:
            try:
                cur.execute(f"ALTER TABLE rpc_endpoints ADD COLUMN {column_name} {column_type}")
            except sqlite3.OperationalError:
                # Ustun allaqachon mavjud bo'lsa
                pass

        conn.commit()
        logging.info("✅ Database migrations completed successfully")
        conn.close()
        
    except Exception as e:
        logging.error(f"❌ Migration error: {e}")
        raise