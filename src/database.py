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

    def close(self):
        self.conn.close()
