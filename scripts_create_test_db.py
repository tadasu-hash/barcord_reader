from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DB_PATH = Path("asset_manager.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            barcode TEXT NOT NULL UNIQUE,
            asset_name TEXT NOT NULL,
            category TEXT,
            location TEXT,
            registered_at TEXT NOT NULL,
            last_confirmed_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            deleted_by TEXT,
            delete_comment TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scan_logs (
            scan_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_code TEXT NOT NULL,
            result TEXT NOT NULL,
            asset_id TEXT,
            message TEXT,
            scanned_at TEXT NOT NULL,
            scanned_by TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target_asset_id TEXT,
            before_json TEXT,
            after_json TEXT,
            acted_at TEXT NOT NULL,
            acted_by TEXT,
            comment TEXT
        );
        """
    )


def seed_assets(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if count > 0:
        return

    ts = now_iso()
    rows = [
        (str(uuid4()), "ABC-000123", "ノートPC", "PC", "3F-営業部", "2026-05-01", None, "active", 0, None, None, None, ts, ts),
        (str(uuid4()), "ABC-000124", "バーコードリーダー", "周辺機器", "1F-受付", "2026-05-02", None, "active", 0, None, None, None, ts, ts),
        (str(uuid4()), "ABC-000125", "プロジェクター", "AV機器", "2F-会議室A", "2026-04-25", None, "active", 0, None, None, None, ts, ts),
    ]
    conn.executemany(
        """
        INSERT INTO assets(
            asset_id, barcode, asset_name, category, location, registered_at,
            last_confirmed_at, status, is_deleted, deleted_at, deleted_by, delete_comment,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        seed_assets(conn)
        conn.commit()
    finally:
        conn.close()
    print(f"created: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()
