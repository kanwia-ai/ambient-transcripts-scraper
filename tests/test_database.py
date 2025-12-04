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


def test_tracker_mark_processed_and_check():
    db_path = Path("/tmp/test_tracker2.db")
    if db_path.exists():
        db_path.unlink()

    tracker = TranscriptTracker(db_path)

    # Initially not processed
    assert not tracker.is_processed("/path/to/meeting.txt")

    # Mark as processed
    tracker.mark_processed(
        filepath="/path/to/meeting.txt",
        filename="meeting.txt",
        meeting_date="2025-09-22",
        client_entity="Asurion",
        status="success"
    )

    # Now it's processed
    assert tracker.is_processed("/path/to/meeting.txt")

    # Cleanup
    tracker.close()
    db_path.unlink()


def test_tracker_get_unprocessed():
    db_path = Path("/tmp/test_tracker3.db")
    if db_path.exists():
        db_path.unlink()

    tracker = TranscriptTracker(db_path)

    all_files = [
        "/transcripts/Asurion/meeting1.txt",
        "/transcripts/Asurion/meeting2.txt",
        "/transcripts/Asurion/meeting3.txt",
    ]

    # Mark first one as processed
    tracker.mark_processed(
        filepath="/transcripts/Asurion/meeting1.txt",
        filename="meeting1.txt",
        meeting_date="2025-09-22",
        client_entity="Asurion",
        status="success"
    )

    # Get unprocessed
    unprocessed = tracker.get_unprocessed(all_files)

    assert len(unprocessed) == 2
    assert "/transcripts/Asurion/meeting2.txt" in unprocessed
    assert "/transcripts/Asurion/meeting3.txt" in unprocessed

    # Cleanup
    tracker.close()
    db_path.unlink()
