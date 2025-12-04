# tests/test_database.py
import pytest
import sqlite3
from pathlib import Path
from src.database import TranscriptTracker


def test_tracker_initialization_creates_tables():
    db_path = Path("/tmp/test_tracker.db")
    if db_path.exists():
        db_path.unlink()

    tracker = TranscriptTracker(db_path)

    # Verify tables exist
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "processed_transcripts" in tables
    assert "sync_runs" in tables

    # Cleanup
    tracker.close()
    db_path.unlink()
