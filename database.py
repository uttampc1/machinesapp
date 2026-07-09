import sqlite3

DB_FILE = "machines.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            id            INTEGER  PRIMARY KEY AUTOINCREMENT,
            machine_name  TEXT     NOT NULL UNIQUE,
            platform_name TEXT     NOT NULL,
            ip_address    TEXT,
            bmc_name      TEXT,
            os            TEXT,
            description   TEXT,
            status        TEXT     NOT NULL DEFAULT 'available'
                          CHECK(status IN ('available', 'reserved')),
            reserved_by   TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Initialized: {DB_FILE}")
