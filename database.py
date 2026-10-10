import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "lostlink_ai.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL CHECK(status IN ('lost', 'found')),
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT NOT NULL,
                report_date TEXT NOT NULL,
                distinguishing_features TEXT,
                contact TEXT,
                reporter_name TEXT,
                share_contact_consent INTEGER NOT NULL DEFAULT 0,
                sms_consent INTEGER NOT NULL DEFAULT 0,
                image_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS match_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lost_id INTEGER NOT NULL,
                found_id INTEGER NOT NULL,
                match_score INTEGER NOT NULL,
                matching_features TEXT,
                conflicting_features TEXT,
                explanation TEXT,
                recommendation TEXT,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        report_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
        if "sms_consent" not in report_columns:
            conn.execute(
                "ALTER TABLE reports ADD COLUMN sms_consent INTEGER NOT NULL DEFAULT 0"
            )
        if "reporter_name" not in report_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN reporter_name TEXT")
        if "share_contact_consent" not in report_columns:
            conn.execute(
                "ALTER TABLE reports ADD COLUMN share_contact_consent INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sms_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lost_id INTEGER NOT NULL,
                found_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent', 'failed')),
                message_sid TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(lost_id, found_id)
            )
            """
        )


def add_report(report: Dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports (
                status, item_name, category, description, location, report_date,
                distinguishing_features, contact, reporter_name, share_contact_consent,
                sms_consent, image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["status"],
                report["item_name"],
                report["category"],
                report["description"],
                report["location"],
                report["report_date"],
                report.get("distinguishing_features") or "",
                report.get("contact") or "",
                report.get("reporter_name") or "",
                int(bool(report.get("share_contact_consent", False))),
                int(bool(report.get("sms_consent", False))),
                report.get("image_path") or "",
            ),
        )
        return int(cursor.lastrowid)


def update_report(report_id: int, report: Dict[str, Any]) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE reports
            SET item_name = ?,
                category = ?,
                description = ?,
                location = ?,
                report_date = ?,
                distinguishing_features = ?,
                contact = ?,
                reporter_name = ?,
                share_contact_consent = ?,
                sms_consent = ?,
                image_path = ?
            WHERE id = ?
            """,
            (
                report["item_name"],
                report["category"],
                report["description"],
                report["location"],
                report["report_date"],
                report.get("distinguishing_features") or "",
                report.get("contact") or "",
                report.get("reporter_name") or "",
                int(bool(report.get("share_contact_consent", False))),
                int(bool(report.get("sms_consent", False))),
                report.get("image_path") or "",
                report_id,
            ),
        )
        return cursor.rowcount > 0


def delete_report(report_id: int) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT image_path FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            "DELETE FROM match_assessments WHERE lost_id = ? OR found_id = ?",
            (report_id, report_id),
        )
        conn.execute(
            "DELETE FROM sms_notifications WHERE lost_id = ? OR found_id = ?",
            (report_id, report_id),
        )
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        return row["image_path"] or ""


def list_reports(
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM reports WHERE 1=1"
    params: List[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if category:
        query += " AND category = ?"
        params.append(category)
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    if keyword:
        query += " AND (item_name LIKE ? OR description LIKE ? OR distinguishing_features LIKE ? OR location LIKE ?)"
        token = f"%{keyword}%"
        params.extend([token, token, token, token])
    if date_from:
        query += " AND report_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND report_date <= ?"
        params.append(date_to)
    query += " ORDER BY report_date DESC, created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def get_recent_reports(limit: int = 6) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def get_stats() -> Dict[str, Any]:
    with get_connection() as conn:
        total_lost = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'lost'").fetchone()[0]
        total_found = conn.execute("SELECT COUNT(*) FROM reports WHERE status = 'found'").fetchone()[0]
        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM reports GROUP BY category ORDER BY count DESC"
        ).fetchall()
        recent = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 10").fetchall()
    return {
        "total_lost": total_lost,
        "total_found": total_found,
        "category_stats": [dict(row) for row in category_rows],
        "recent": [dict(row) for row in recent],
    }


def save_assessment(lost_id: int, found_id: int, result: Dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO match_assessments (
                lost_id, found_id, match_score, matching_features, conflicting_features,
                explanation, recommendation, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lost_id,
                found_id,
                result.get("match_score", 0),
                "; ".join(result.get("matching_features") or []),
                "; ".join(result.get("conflicting_features") or []),
                result.get("explanation") or "",
                result.get("recommendation") or "",
                result.get("source") or "basic",
            ),
        )


def has_sent_sms_notification(lost_id: int, found_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sms_notifications
            WHERE lost_id = ? AND found_id = ? AND status = 'sent'
            """,
            (lost_id, found_id),
        ).fetchone()
    return row is not None


def save_sms_notification(
    lost_id: int,
    found_id: int,
    status: str,
    message_sid: Optional[str] = None,
) -> None:
    if status not in {"sent", "failed"}:
        raise ValueError("SMS notification status must be 'sent' or 'failed'.")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sms_notifications (lost_id, found_id, status, message_sid)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(lost_id, found_id) DO UPDATE SET
                status = excluded.status,
                message_sid = excluded.message_sid,
                created_at = CURRENT_TIMESTAMP
            """,
            (lost_id, found_id, status, message_sid),
        )


init_db()
