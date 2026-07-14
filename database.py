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

    # ── create a migrations tracking table ────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # ── run any pending migrations ────────────────────────────────────────────
    run_migrations(conn)

    conn.close()
    print(f"[DB] Initialized: {DB_FILE}")

# ─────────────────────────────────────────────────────────────────────────────
# Migration system
#
# To add a new column or change the schema:
#   1. Add a new entry to MIGRATIONS with the next version number
#   2. Write the SQL in the "sql" field
#   3. Restart the app — it will auto-apply
#
# Migrations are applied in order and only once (tracked in schema_migrations)
# ─────────────────────────────────────────────────────────────────────────────

MIGRATIONS = [
    {
        "version": 1,
        "name":    "add_po_and_program_columns",
        "sql": [
            "ALTER TABLE machines ADD COLUMN po_sms TEXT",
            "ALTER TABLE machines ADD COLUMN program TEXT",
        ]
    },
    {
        "version": 2,
        "name":    "add_socket_make_model_columns",
        "sql": [
            "ALTER TABLE machines ADD COLUMN socket TEXT",
            "ALTER TABLE machines ADD COLUMN system_config TEXT",
            "ALTER TABLE machines ADD COLUMN make TEXT",
            "ALTER TABLE machines ADD COLUMN model TEXT",
        ]
    },
    {
        "version": 3,
        "name":    "add_category_asset_owner_serial_num_columns",
        "sql": [
            "ALTER TABLE machines ADD COLUMN category TEXT",
            "ALTER TABLE machines ADD COLUMN asset_owner TEXT",
            "ALTER TABLE machines ADD COLUMN serial TEXT",
        ]
    },
    {
        "version": 4,
        "name":    "add_pdu_switch_columns",
        "sql": [
            "ALTER TABLE machines ADD COLUMN maas_switch TEXT",
            "ALTER TABLE machines ADD COLUMN pdu_ip TEXT",
            "ALTER TABLE machines ADD COLUMN pdu_port TEXT",
        ]
    },
    {
        "version": 5,
        "name":    "add_location_columns",
        "sql": [
            "ALTER TABLE machines ADD COLUMN site TEXT",
            "ALTER TABLE machines ADD COLUMN lab TEXT",
            "ALTER TABLE machines ADD COLUMN row_location TEXT",
            "ALTER TABLE machines ADD COLUMN rack TEXT",
            "ALTER TABLE machines ADD COLUMN ru TEXT",
            "ALTER TABLE machines ADD COLUMN cpu TEXT",
            "ALTER TABLE machines ADD COLUMN backplane TEXT",
        ]
    },
    {
        "version": 6,
        "name":    "add_jira_column",
        "sql": [
            "ALTER TABLE machines ADD COLUMN jira TEXT",
        ]
    },
]

def get_applied_versions(conn):
    """Return a set of already-applied migration version numbers."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def run_migrations(conn):
    """Apply any migrations that haven't been applied yet."""
    applied = get_applied_versions(conn)

    for migration in sorted(MIGRATIONS, key=lambda m: m["version"]):
        ver  = migration["version"]
        name = migration["name"]

        if ver in applied:
            continue    # already applied

        print(f"[DB] Applying migration {ver}: {name}")

        try:
            for sql in migration["sql"]:
                conn.execute(sql)

            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (ver, name)
            )
            conn.commit()
            print(f"[DB] Migration {ver} applied successfully.")

        except Exception as e:
            conn.rollback()
            print(f"[DB] ERROR applying migration {ver}: {e}")
            raise

