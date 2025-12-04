# tests/test_daily_sync.py
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from daily_sync import DailySync


def test_daily_sync_extracts_meeting_series():
    sync = DailySync(transcripts_dir="/tmp/transcripts", db_path="/tmp/test.db")

    filepath = "/tmp/transcripts/Ambient_ Project/meeting.txt"
    series = sync.extract_meeting_series(filepath)

    assert series == "Ambient_ Project"
    sync.close()


def test_daily_sync_extracts_date_from_filename():
    sync = DailySync(transcripts_dir="/tmp/transcripts", db_path="/tmp/test.db")

    filename = "Asurion x Section 2025-09-22 12_31 transcript.txt"
    date = sync.extract_date_from_filename(filename)

    assert date == "2025-09-22"
    sync.close()
