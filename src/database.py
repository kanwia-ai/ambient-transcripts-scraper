# src/database.py
import sqlite3
from pathlib import Path
from typing import Optional, List
from datetime import datetime


class TranscriptTracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_transcripts (
                id INTEGER PRIMARY KEY,
                filepath TEXT UNIQUE,
                filename TEXT,
                meeting_date TEXT,
                client_entity TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                transcripts_scraped INTEGER DEFAULT 0,
                transcripts_processed INTEGER DEFAULT 0,
                status TEXT
            )
        ''')
        self.conn.commit()

    def is_processed(self, filepath: str) -> bool:
        """Check if a transcript has already been processed."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM processed_transcripts WHERE filepath = ?",
            (filepath,)
        )
        return cursor.fetchone() is not None

    def mark_processed(
        self,
        filepath: str,
        filename: str,
        meeting_date: str,
        client_entity: str,
        status: str
    ):
        """Mark a transcript as processed."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_transcripts
            (filepath, filename, meeting_date, client_entity, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (filepath, filename, meeting_date, client_entity, status))
        self.conn.commit()

    def get_unprocessed(self, all_files: List[str]) -> List[str]:
        """Get list of files that haven't been processed yet."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT filepath FROM processed_transcripts")
        processed = {row[0] for row in cursor.fetchall()}
        return [f for f in all_files if f not in processed]

    def close(self):
        self.conn.close()
