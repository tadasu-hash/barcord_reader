from __future__ import annotations

import csv
import io
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

DB_PATH = Path("asset_manager.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn:
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
        conn.commit()


class AssetCreate(BaseModel):
    barcode: str = Field(min_length=1)
    asset_name: str = Field(min_length=1)
    registered_at: str
    category: str | None = None
    location: str | None = None
    status: str = "active"
    acted_by: str | None = None


class AssetUpdate(BaseModel):
    asset_name: str | None = None
    category: str | None = None
    location: str | None = None
    status: str | None = None
    acted_by: str | None = None


class ScanRequest(BaseModel):
    barcode: str
    scanned_by: str | None = None


class DeleteRequest(BaseModel):
    deleted_by: str | None = None
    delete_comment: str = Field(min_length=1)


app = FastAPI(title="Barcode Asset Manager")
init_db()


def audit(action: str, target_asset_id: str | None, before_json: str | None, after_json: str | None, acted_by: str | None, comment: str | None = None) -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            """INSERT INTO audit_logs(action, target_asset_id, before_json, after_json, acted_at, acted_by, comment)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (action, target_asset_id, before_json, after_json, now_iso(), acted_by, comment),
        )
        conn.commit()


@app.post("/api/v1/scan")
def scan_asset(req: ScanRequest) -> dict[str, Any]:
    code = req.barcode.strip()
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE barcode = ? AND is_deleted = 0",
            (code,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO scan_logs(scanned_code, result, message, scanned_at, scanned_by) VALUES (?, 'not_found', ?, ?, ?)",
                (code, "asset not found for barcode", now_iso(), req.scanned_by),
            )
            conn.commit()
            raise HTTPException(status_code=404, detail={"result": "not_found", "message": "asset not found for barcode"})

        ts = now_iso()
        conn.execute("UPDATE assets SET last_confirmed_at = ?, updated_at = ? WHERE asset_id = ?", (ts, ts, row["asset_id"]))
        conn.execute(
            "INSERT INTO scan_logs(scanned_code, result, asset_id, message, scanned_at, scanned_by) VALUES (?, 'success', ?, ?, ?, ?)",
            (code, row["asset_id"], "matched", ts, req.scanned_by),
        )
        conn.commit()
    return {
        "result": "success",
        "asset": {
            "asset_id": row["asset_id"],
            "barcode": row["barcode"],
            "asset_name": row["asset_name"],
            "location": row["location"],
            "last_confirmed_at": ts,
        },
    }


@app.get("/api/v1/assets")
def list_assets(
    asset_name: str | None = None,
    barcode: str | None = None,
    registered_from: str | None = None,
    registered_to: str | None = None,
    confirmed_from: str | None = None,
    confirmed_to: str | None = None,
    location: str | None = None,
    category: str | None = None,
    unconfirmed_only: bool = False,
) -> dict[str, Any]:
    query = "SELECT * FROM assets WHERE is_deleted = 0"
    params: list[Any] = []

    if asset_name:
        query += " AND asset_name LIKE ?"
        params.append(f"%{asset_name}%")
    if barcode:
        query += " AND barcode = ?"
        params.append(barcode)
    if registered_from:
        query += " AND registered_at >= ?"
        params.append(registered_from)
    if registered_to:
        query += " AND registered_at <= ?"
        params.append(registered_to)
    if confirmed_from:
        query += " AND COALESCE(last_confirmed_at, '') >= ?"
        params.append(confirmed_from)
    if confirmed_to:
        query += " AND COALESCE(last_confirmed_at, '') <= ?"
        params.append(confirmed_to)
    if location:
        query += " AND location = ?"
        params.append(location)
    if category:
        query += " AND category = ?"
        params.append(category)
    if unconfirmed_only:
        query += " AND last_confirmed_at IS NULL"

    with closing(get_conn()) as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    return {"count": len(rows), "items": rows}


@app.post("/api/v1/assets")
def create_asset(req: AssetCreate) -> dict[str, Any]:
    asset_id = str(uuid4())
    ts = now_iso()
    with closing(get_conn()) as conn:
        try:
            conn.execute(
                """INSERT INTO assets(asset_id, barcode, asset_name, category, location, registered_at, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, req.barcode.strip(), req.asset_name.strip(), req.category, req.location, req.registered_at, req.status, ts, ts),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="barcode already exists")
    audit("create", asset_id, None, f"barcode={req.barcode}", req.acted_by)
    return {"asset_id": asset_id}


@app.put("/api/v1/assets/{asset_id}")
def update_asset(asset_id: str, req: AssetUpdate) -> dict[str, str]:
    with closing(get_conn()) as conn:
        before = conn.execute("SELECT * FROM assets WHERE asset_id = ? AND is_deleted = 0", (asset_id,)).fetchone()
        if before is None:
            raise HTTPException(status_code=404, detail="asset not found")

        updates = {k: v for k, v in req.model_dump().items() if v is not None and k != "acted_by"}
        if not updates:
            return {"result": "no_change"}
        updates["updated_at"] = now_iso()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [asset_id]
        conn.execute(f"UPDATE assets SET {set_clause} WHERE asset_id = ?", values)
        conn.commit()
    audit("update", asset_id, str(dict(before)), str(updates), req.acted_by)
    return {"result": "updated"}


@app.delete("/api/v1/assets/{asset_id}")
def delete_asset(asset_id: str, req: DeleteRequest) -> dict[str, str]:
    ts = now_iso()
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM assets WHERE asset_id = ? AND is_deleted = 0", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="asset not found")

        conn.execute(
            """UPDATE assets
               SET is_deleted = 1, deleted_at = ?, deleted_by = ?, delete_comment = ?, updated_at = ?
               WHERE asset_id = ?""",
            (ts, req.deleted_by, req.delete_comment, ts, asset_id),
        )
        conn.commit()
    audit("delete", asset_id, str(dict(row)), None, req.deleted_by, req.delete_comment)
    return {"result": "deleted"}


@app.post("/api/v1/assets/import")
def import_assets(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="only csv is supported in this initial implementation")

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    required = {"barcode", "asset_name", "registered_at"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise HTTPException(status_code=422, detail=f"required columns: {sorted(required)}")

    inserted = 0
    errors: list[dict[str, Any]] = []
    for idx, row in enumerate(reader, start=2):
        barcode = (row.get("barcode") or "").strip()
        asset_name = (row.get("asset_name") or "").strip()
        registered_at = (row.get("registered_at") or "").strip()

        if not barcode or not asset_name or not registered_at:
            errors.append({"row": idx, "error": "missing required values"})
            continue

        try:
            create_asset(AssetCreate(barcode=barcode, asset_name=asset_name, registered_at=registered_at, category=row.get("category"), location=row.get("location")))
            inserted += 1
        except HTTPException as exc:
            errors.append({"row": idx, "error": str(exc.detail)})

    return {"inserted": inserted, "errors": errors}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
