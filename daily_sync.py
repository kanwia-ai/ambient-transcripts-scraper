#!/usr/bin/env python3
"""
Daily Sync Orchestrator

Runs the full pipeline:
1. Find new transcript files
2. Process each through Claude API
3. Update Memory MCP
4. Track progress in SQLite
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from src.database import TranscriptTracker
from src.client_mapper import ClientMapper
from src.processor import TranscriptProcessor
from src.memory_updater import MemoryUpdater


class DailySync:
    def __init__(
        self,
        transcripts_dir: str = "./transcripts",
        db_path: str = "./processing.db"
    ):
        self.transcripts_dir = Path(transcripts_dir)
        self.db_path = Path(db_path)
        self.tracker = TranscriptTracker(self.db_path)
        self.mapper = ClientMapper()
        self.processor = TranscriptProcessor()
        self.memory = MemoryUpdater()

    def get_all_transcripts(self) -> List[str]:
        """Find all transcript files."""
        files = []
        if self.transcripts_dir.exists():
            for txt_file in self.transcripts_dir.glob("**/*.txt"):
                files.append(str(txt_file))
        return files

    def get_unprocessed_transcripts(self) -> List[str]:
        """Get transcripts that haven't been processed yet."""
        all_files = self.get_all_transcripts()
        return self.tracker.get_unprocessed(all_files)

    def extract_meeting_series(self, filepath: str) -> str:
        """Extract meeting series name from filepath."""
        path = Path(filepath)
        # Parent folder is the meeting series
        return path.parent.name

    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """Try to extract date from filename like 'Meeting 2025-09-22 12_31 transcript.txt'"""
        match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        if match:
            return match.group(1)
        return None

    def process_single(self, filepath: str) -> bool:
        """Process a single transcript file."""
        try:
            print(f"Processing: {filepath}")

            # Get meeting series and client
            series = self.extract_meeting_series(filepath)
            client = self.mapper.get_client(series)

            # If no series mapping, try filename patterns
            if client == "Other":
                filename = Path(filepath).name
                client = self.mapper.get_client_from_filename(filename)

            # Process transcript with Claude
            processed = self.processor.process_file(filepath)

            if not processed:
                print(f"  Warning: No data extracted from {filepath}")
                self.tracker.mark_processed(
                    filepath=filepath,
                    filename=Path(filepath).name,
                    meeting_date="unknown",
                    client_entity=client,
                    status="empty"
                )
                return False

            # Update memory
            self.memory.update_from_transcript(client, processed)

            # Mark as processed
            meeting_date = processed.get("date") or self.extract_date_from_filename(Path(filepath).name) or "unknown"
            self.tracker.mark_processed(
                filepath=filepath,
                filename=Path(filepath).name,
                meeting_date=meeting_date,
                client_entity=client,
                status="success"
            )

            print(f"  Done: {client} - {meeting_date}")
            return True

        except Exception as e:
            print(f"  Error processing {filepath}: {e}")
            self.tracker.mark_processed(
                filepath=filepath,
                filename=Path(filepath).name,
                meeting_date="unknown",
                client_entity="unknown",
                status=f"error: {str(e)[:100]}"
            )
            return False

    def run(self, limit: Optional[int] = None) -> dict:
        """Run the full sync pipeline."""
        started = datetime.now()

        unprocessed = self.get_unprocessed_transcripts()
        print(f"Found {len(unprocessed)} unprocessed transcripts")

        if limit:
            unprocessed = unprocessed[:limit]
            print(f"Processing {limit} (limited)")

        success = 0
        failed = 0

        for filepath in unprocessed:
            if self.process_single(filepath):
                success += 1
            else:
                failed += 1

        completed = datetime.now()
        duration = (completed - started).total_seconds()

        result = {
            "started": started.isoformat(),
            "completed": completed.isoformat(),
            "duration_seconds": duration,
            "total": len(unprocessed),
            "success": success,
            "failed": failed
        }

        print(f"\nSync complete: {success} processed, {failed} failed in {duration:.1f}s")
        return result

    def close(self):
        self.tracker.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync Ambient transcripts to Memory MCP")
    parser.add_argument("--transcripts-dir", default="./transcripts", help="Transcripts directory")
    parser.add_argument("--db-path", default="./processing.db", help="SQLite database path")
    parser.add_argument("--limit", type=int, help="Limit number of transcripts to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")

    args = parser.parse_args()

    sync = DailySync(
        transcripts_dir=args.transcripts_dir,
        db_path=args.db_path
    )

    if args.dry_run:
        unprocessed = sync.get_unprocessed_transcripts()
        print(f"Would process {len(unprocessed)} transcripts:")
        for f in unprocessed[:20]:
            print(f"  {f}")
        if len(unprocessed) > 20:
            print(f"  ... and {len(unprocessed) - 20} more")
    else:
        sync.run(limit=args.limit)

    sync.close()


if __name__ == "__main__":
    main()
