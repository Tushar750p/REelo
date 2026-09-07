"""Persistent user/content reports for REelo."""
from __future__ import annotations
from uuid import uuid4


def ensure_reports_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL,target_type TEXT NOT NULL,target_id TEXT NOT NULL,reason TEXT NOT NULL,details TEXT DEFAULT '',status TEXT DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def create_report(c, reporter_id: str, target_type: str, target_id: str, reason: str, details: str = ""):
    ensure_reports_table(c)
    report_id = uuid4().hex
    c.execute("INSERT INTO reports(id,reporter_id,target_type,target_id,reason,details) VALUES(?,?,?,?,?,?)", (report_id, reporter_id, target_type, target_id, reason, details[:1000]))
    return report_id
