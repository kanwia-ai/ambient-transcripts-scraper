# Transcript Synthesis Pipeline - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated daily pipeline that scrapes Ambient transcripts, summarizes them via Claude API, and stores structured context in Memory MCP's `work-planning` context.

**Architecture:** Enhanced Playwright scraper iterates all Meeting Series and My Meetings, SQLite tracks processed files, Claude Haiku summarizes transcripts, Memory MCP updater creates/updates client entities with meeting observations.

**Tech Stack:** Python 3.11, Playwright, Anthropic SDK, SQLite3, Memory MCP, launchd

---

## Task 1: Create Tracking Database Module

**Files:**
- Create: `src/database.py`
- Create: `tests/test_database.py`

**Step 1: Write the failing test**

```python
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
    db_path.unlink()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_tracker_initialization_creates_tables -v`
Expected: FAIL with "No module named 'src.database'"

**Step 3: Create src directory and write minimal implementation**

```bash
mkdir -p src
touch src/__init__.py
```

```python
# src/database.py
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py::test_tracker_initialization_creates_tables -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/__init__.py src/database.py tests/test_database.py
git commit -m "feat: add TranscriptTracker with table initialization"
```

---

## Task 2: Add Transcript Tracking Methods

**Files:**
- Modify: `src/database.py`
- Modify: `tests/test_database.py`

**Step 1: Write the failing test**

```python
# tests/test_database.py (append)

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py::test_tracker_mark_processed_and_check -v`
Expected: FAIL with "AttributeError: 'TranscriptTracker' object has no attribute 'is_processed'"

**Step 3: Add methods to implementation**

```python
# src/database.py (add these methods to TranscriptTracker class)

    def is_processed(self, filepath: str) -> bool:
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
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_transcripts
            (filepath, filename, meeting_date, client_entity, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (filepath, filename, meeting_date, client_entity, status))
        self.conn.commit()

    def get_unprocessed(self, all_files: List[str]) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT filepath FROM processed_transcripts")
        processed = {row[0] for row in cursor.fetchall()}
        return [f for f in all_files if f not in processed]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/database.py tests/test_database.py
git commit -m "feat: add transcript tracking methods to TranscriptTracker"
```

---

## Task 3: Create Client Mapping Configuration

**Files:**
- Create: `config/client_mapping.json`
- Create: `src/client_mapper.py`
- Create: `tests/test_client_mapper.py`

**Step 1: Write the failing test**

```python
# tests/test_client_mapper.py
import pytest
from pathlib import Path
from src.client_mapper import ClientMapper

def test_client_mapper_from_meeting_series():
    mapper = ClientMapper()

    assert mapper.get_client("Ambient_ Project") == "Asurion"
    assert mapper.get_client("AIT Consulting Weekly") == "AIT_Internal"
    assert mapper.get_client("All Hands") == "Section_Internal"
    assert mapper.get_client("Weekly Proposal Review") == "Section_Internal"


def test_client_mapper_from_filename():
    mapper = ClientMapper()

    # Extract from filename pattern
    client = mapper.get_client_from_filename(
        "Asurion x Section 2025-09-22 12_31 transcript.txt"
    )
    assert client == "Asurion"


def test_client_mapper_unknown_defaults():
    mapper = ClientMapper()

    assert mapper.get_client("Unknown Meeting Series") == "Other"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_client_mapper.py -v`
Expected: FAIL with "No module named 'src.client_mapper'"

**Step 3: Create config and implementation**

```bash
mkdir -p config
```

```json
// config/client_mapping.json
{
  "meeting_series_to_client": {
    "Ambient_ Project": "Asurion",
    "AIT Consulting Weekly": "AIT_Internal",
    "All Hands": "Section_Internal",
    "Weekly Proposal Review": "Section_Internal",
    "Kyra & Alli 1x1": "Section_Internal",
    "Team Meetings": "Section_Internal",
    "External": "External_Meetings"
  },
  "filename_patterns": {
    "Asurion": "Asurion",
    "Section": "Section_Internal",
    "AIT": "AIT_Internal",
    "Havas": "Havas"
  },
  "default_client": "Other"
}
```

```python
# src/client_mapper.py
import json
import re
from pathlib import Path
from typing import Optional

class ClientMapper:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "client_mapping.json"

        with open(config_path) as f:
            self.config = json.load(f)

        self.series_map = self.config.get("meeting_series_to_client", {})
        self.filename_patterns = self.config.get("filename_patterns", {})
        self.default = self.config.get("default_client", "Other")

    def get_client(self, meeting_series: str) -> str:
        return self.series_map.get(meeting_series, self.default)

    def get_client_from_filename(self, filename: str) -> str:
        for pattern, client in self.filename_patterns.items():
            if pattern.lower() in filename.lower():
                return client
        return self.default
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client_mapper.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add config/client_mapping.json src/client_mapper.py tests/test_client_mapper.py
git commit -m "feat: add ClientMapper for meeting series to client mapping"
```

---

## Task 4: Create Transcript Processor (Claude API)

**Files:**
- Create: `src/processor.py`
- Create: `tests/test_processor.py`
- Modify: `requirements.txt`

**Step 1: Update requirements**

```txt
# requirements.txt
playwright==1.41.0
anthropic>=0.18.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

Run: `pip install -r requirements.txt`

**Step 2: Write the failing test**

```python
# tests/test_processor.py
import pytest
from unittest.mock import Mock, patch
from src.processor import TranscriptProcessor

def test_processor_extracts_structured_data():
    # Mock the Anthropic client
    mock_response = Mock()
    mock_response.content = [Mock(text='''{
        "meeting_title": "Asurion Weekly Sync",
        "date": "2025-09-22",
        "project_client": "Asurion",
        "attendees": ["Scott", "Kyra"],
        "main_topics": ["PRD automation status"],
        "key_context": ["PRD moving to pilot phase"],
        "implied_work": ["Prep pilot documentation"]
    }''')]

    with patch('src.processor.Anthropic') as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        processor = TranscriptProcessor()
        result = processor.process_transcript("Sample transcript text here...")

        assert result["meeting_title"] == "Asurion Weekly Sync"
        assert result["project_client"] == "Asurion"
        assert "Scott" in result["attendees"]
        assert len(result["main_topics"]) > 0


def test_processor_handles_empty_transcript():
    with patch('src.processor.Anthropic') as mock_anthropic:
        mock_response = Mock()
        mock_response.content = [Mock(text='{}')]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        processor = TranscriptProcessor()
        result = processor.process_transcript("")

        assert result == {}
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_processor.py::test_processor_extracts_structured_data -v`
Expected: FAIL with "No module named 'src.processor'"

**Step 4: Write implementation**

```python
# src/processor.py
import json
import os
from typing import Dict, Any, Optional
from anthropic import Anthropic

EXTRACTION_PROMPT = """Summarize this meeting transcript for work planning context.

Extract and return as JSON:
{
  "meeting_title": "Meeting name",
  "date": "YYYY-MM-DD",
  "project_client": "Client or project name",
  "attendees": ["Person1", "Person2"],
  "main_topics": ["Topic discussed"],
  "key_context": ["Important background info mentioned"],
  "implied_work": ["Things that might need follow-up even if not explicit action items"]
}

Keep it concise - this is for background context, not detailed notes.
Only include fields where you have clear information.

Transcript:
"""

class TranscriptProcessor:
    def __init__(self, api_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-3-haiku-20240307"

    def process_transcript(self, transcript_text: str) -> Dict[str, Any]:
        if not transcript_text.strip():
            return {}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + transcript_text[:50000]  # Limit to ~50k chars
            }]
        )

        try:
            result_text = response.content[0].text
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            return json.loads(result_text.strip())
        except (json.JSONDecodeError, IndexError):
            return {}

    def process_file(self, filepath: str) -> Dict[str, Any]:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.process_transcript(content)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_processor.py -v`
Expected: All 2 tests PASS

**Step 6: Commit**

```bash
git add requirements.txt src/processor.py tests/test_processor.py
git commit -m "feat: add TranscriptProcessor with Claude API summarization"
```

---

## Task 5: Create Memory MCP Updater

**Files:**
- Create: `src/memory_updater.py`
- Create: `tests/test_memory_updater.py`

**Step 1: Write the failing test**

```python
# tests/test_memory_updater.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.memory_updater import MemoryUpdater

def test_memory_updater_builds_observation():
    updater = MemoryUpdater()

    processed_data = {
        "meeting_title": "Asurion Weekly",
        "date": "2025-09-22",
        "main_topics": ["PRD automation", "HR pilot"],
        "key_context": ["Moving to pilot phase"],
        "implied_work": ["Prep documentation"]
    }

    observation = updater.build_observation(processed_data)

    assert "2025-09-22" in observation
    assert "PRD automation" in observation
    assert "pilot phase" in observation


def test_memory_updater_formats_entity_name():
    updater = MemoryUpdater()

    assert updater.format_entity_name("Asurion") == "Asurion"
    assert updater.format_entity_name("AIT_Internal") == "AIT_Internal"
    assert updater.format_entity_name("Some Client Name") == "Some_Client_Name"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_updater.py -v`
Expected: FAIL with "No module named 'src.memory_updater'"

**Step 3: Write implementation**

```python
# src/memory_updater.py
import subprocess
import json
from typing import Dict, Any, List, Optional

class MemoryUpdater:
    def __init__(self, context: str = "work-planning"):
        self.context = context

    def format_entity_name(self, name: str) -> str:
        """Format name for entity (replace spaces with underscores)."""
        return name.replace(" ", "_")

    def build_observation(self, processed_data: Dict[str, Any]) -> str:
        """Build a concise observation string from processed transcript data."""
        parts = []

        date = processed_data.get("date", "Unknown date")
        parts.append(f"{date}:")

        if processed_data.get("main_topics"):
            topics = ", ".join(processed_data["main_topics"][:3])
            parts.append(f"Discussed {topics}.")

        if processed_data.get("key_context"):
            context = processed_data["key_context"][0]
            parts.append(context)

        if processed_data.get("implied_work"):
            work = processed_data["implied_work"][0]
            parts.append(f"Potential follow-up: {work}")

        return " ".join(parts)

    def entity_exists(self, entity_name: str) -> bool:
        """Check if entity exists in memory (searches for it)."""
        # This will be implemented to call Memory MCP
        # For now, return False to always create
        return False

    def create_entity(
        self,
        name: str,
        entity_type: str,
        observations: List[str]
    ) -> bool:
        """Create a new entity in Memory MCP."""
        # Will call mcp__memory__aim_create_entities
        print(f"Would create entity: {name} ({entity_type})")
        print(f"  Observations: {observations}")
        return True

    def add_observation(self, entity_name: str, observation: str) -> bool:
        """Add observation to existing entity."""
        # Will call mcp__memory__aim_add_observations
        print(f"Would add to {entity_name}: {observation}")
        return True

    def update_from_transcript(
        self,
        client: str,
        processed_data: Dict[str, Any]
    ) -> bool:
        """Update memory with processed transcript data."""
        entity_name = self.format_entity_name(client)
        observation = self.build_observation(processed_data)

        if self.entity_exists(entity_name):
            return self.add_observation(entity_name, observation)
        else:
            # Create with initial observation
            return self.create_entity(
                name=entity_name,
                entity_type="client",
                observations=[observation]
            )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_updater.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/memory_updater.py tests/test_memory_updater.py
git commit -m "feat: add MemoryUpdater for Memory MCP integration"
```

---

## Task 6: Create Daily Sync Orchestrator

**Files:**
- Create: `daily_sync.py`
- Create: `tests/test_daily_sync.py`

**Step 1: Write the failing test**

```python
# tests/test_daily_sync.py
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from daily_sync import DailySync

def test_daily_sync_finds_transcript_files():
    with patch('daily_sync.Path') as mock_path:
        # Mock the glob to return test files
        mock_path.return_value.glob.return_value = [
            Path("/transcripts/Asurion/meeting1.txt"),
            Path("/transcripts/Asurion/meeting2.txt"),
        ]

        sync = DailySync(
            transcripts_dir="/transcripts",
            db_path="/tmp/test.db"
        )

        # Mock the tracker
        sync.tracker = Mock()
        sync.tracker.get_unprocessed.return_value = [
            "/transcripts/Asurion/meeting1.txt"
        ]

        unprocessed = sync.get_unprocessed_transcripts()
        assert len(unprocessed) == 1


def test_daily_sync_extracts_meeting_series():
    sync = DailySync(transcripts_dir="/transcripts", db_path="/tmp/test.db")

    filepath = "/transcripts/Ambient_ Project/meeting.txt"
    series = sync.extract_meeting_series(filepath)

    assert series == "Ambient_ Project"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_daily_sync.py -v`
Expected: FAIL with "No module named 'daily_sync'"

**Step 3: Write implementation**

```python
# daily_sync.py
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
        import re
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_daily_sync.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add daily_sync.py tests/test_daily_sync.py
git commit -m "feat: add DailySync orchestrator for full pipeline"
```

---

## Task 7: Enhance Scraper with Auto Mode

**Files:**
- Modify: `scraper.py`
- Create: `tests/test_scraper_auto.py`

**Step 1: Write the failing test**

```python
# tests/test_scraper_auto.py
import pytest
from scraper import AmbientScraper

def test_scraper_has_auto_mode_flag():
    scraper = AmbientScraper(auto_mode=True)
    assert scraper.auto_mode == True


def test_scraper_has_all_series_flag():
    scraper = AmbientScraper(all_series=True)
    assert scraper.all_series == True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper_auto.py -v`
Expected: FAIL with "TypeError: AmbientScraper.__init__() got an unexpected keyword argument 'auto_mode'"

**Step 3: Modify scraper.py**

Add to `AmbientScraper.__init__`:

```python
# In scraper.py, modify __init__ method (around line 36)
def __init__(
    self,
    download_dir: str = "./transcripts",
    browser_path: Optional[str] = None,
    auto_mode: bool = False,
    all_series: bool = False
):
    self.download_dir = Path(download_dir)
    self.download_dir.mkdir(exist_ok=True)
    self.browser_path = browser_path
    self.auto_mode = auto_mode
    self.all_series = all_series
    # ... rest of init
```

Modify `wait_for_navigation` to skip input in auto_mode:

```python
# In wait_for_navigation method, replace the input() call:
if not self.auto_mode:
    await asyncio.to_thread(input, "Press ENTER when you're ready to start scraping...")
```

Add argument parsing:

```python
# In main(), add arguments:
parser.add_argument(
    '--auto',
    action='store_true',
    help='Run in automated mode (no manual input required)'
)
parser.add_argument(
    '--all-series',
    action='store_true',
    help='Scrape all meeting series automatically'
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scraper_auto.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add scraper.py tests/test_scraper_auto.py
git commit -m "feat: add auto_mode and all_series flags to scraper"
```

---

## Task 8: Add Meeting Series Iterator to Scraper

**Files:**
- Modify: `scraper.py`

**Step 1: Add method to get all meeting series URLs**

```python
# In scraper.py, add new method to AmbientScraper class:

async def get_all_meeting_series(self) -> List[Dict[str, str]]:
    """Navigate to View All and get list of all meeting series."""
    print("\n📋 Getting all meeting series...")

    # Navigate to meeting series view
    await self.page.goto('https://app.ambient.us/dashboard')
    await asyncio.sleep(2)

    # Click "View All" under Meeting Series
    view_all = await self.page.query_selector('text=View All')
    if view_all:
        await view_all.click()
        await asyncio.sleep(2)

    # Get all meeting series links
    series_links = await self.page.evaluate('''() => {
        const links = [];
        const anchors = document.querySelectorAll('a[href*="/meetingseries/"]');
        anchors.forEach(a => {
            links.push({
                name: a.textContent.trim(),
                url: a.href
            });
        });
        return links;
    }''')

    print(f"  Found {len(series_links)} meeting series")
    return series_links


async def scrape_all_series(self):
    """Scrape all meeting series automatically."""
    series_list = await self.get_all_meeting_series()

    for i, series in enumerate(series_list):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(series_list)}] Scraping: {series['name']}")
        print(f"{'='*60}")

        await self.page.goto(series['url'])
        await asyncio.sleep(2)

        await self.scrape_meeting_series()

    print("\n✅ All meeting series scraped!")
```

**Step 2: Modify run() method**

```python
# In scraper.py, modify run() method:

async def run(self):
    """Main execution flow."""
    try:
        await self.setup()

        if self.all_series:
            # Auto mode: scrape all series
            await self.scrape_all_series()
        else:
            # Interactive mode
            page_type = await self.wait_for_navigation()

            if page_type == 'meetingseries':
                await self.scrape_meeting_series()
            elif page_type == 'project':
                await self.scrape_project()

        if not self.auto_mode:
            print("\nPress ENTER to close the browser...")
            await asyncio.to_thread(input)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
```

**Step 3: Test manually**

Run: `python scraper.py --auto --all-series --download-dir ./transcripts`
Expected: Scraper navigates through all meeting series automatically

**Step 4: Commit**

```bash
git add scraper.py
git commit -m "feat: add all_series mode to iterate through all meeting series"
```

---

## Task 9: Create Launchd Plist

**Files:**
- Create: `launchd/com.kyra.ambient-sync.plist`
- Create: `install.sh`

**Step 1: Create launchd directory and plist**

```bash
mkdir -p launchd
```

```xml
<!-- launchd/com.kyra.ambient-sync.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kyra.ambient-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/kyraatekwana/Documents/ambient-transcripts-scraper/daily_sync.py</string>
        <string>--transcripts-dir</string>
        <string>/Users/kyraatekwana/Documents/ambient-transcripts-scraper/transcripts</string>
        <string>--db-path</string>
        <string>/Users/kyraatekwana/Documents/ambient-transcripts-scraper/processing.db</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/ambient-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ambient-sync.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>YOUR_API_KEY_HERE</string>
    </dict>
</dict>
</plist>
```

**Step 2: Create install script**

```bash
#!/bin/bash
# install.sh - Install the ambient-sync launchd job

PLIST_SRC="launchd/com.kyra.ambient-sync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.kyra.ambient-sync.plist"

echo "Installing ambient-sync launchd job..."

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Warning: ANTHROPIC_API_KEY not set"
    echo "You'll need to edit the plist to add your API key"
fi

# Copy plist
cp "$PLIST_SRC" "$PLIST_DEST"

# Replace API key placeholder if set
if [ -n "$ANTHROPIC_API_KEY" ]; then
    sed -i '' "s/YOUR_API_KEY_HERE/$ANTHROPIC_API_KEY/" "$PLIST_DEST"
fi

# Load the job
launchctl load "$PLIST_DEST"

echo "✅ Installed! Job will run daily at 8 AM"
echo ""
echo "Commands:"
echo "  View logs:    tail -f /tmp/ambient-sync.log"
echo "  Run now:      launchctl start com.kyra.ambient-sync"
echo "  Uninstall:    launchctl unload $PLIST_DEST && rm $PLIST_DEST"
```

**Step 3: Make install script executable**

```bash
chmod +x install.sh
```

**Step 4: Commit**

```bash
git add launchd/com.kyra.ambient-sync.plist install.sh
git commit -m "feat: add launchd plist and install script for daily automation"
```

---

## Task 10: Integration Test - Full Pipeline

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
# tests/test_integration.py
"""
Integration test for the full pipeline.
Uses mock data instead of real API calls.
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from daily_sync import DailySync
from src.database import TranscriptTracker
from src.client_mapper import ClientMapper


@pytest.fixture
def temp_transcripts():
    """Create temporary transcript files."""
    temp_dir = Path(tempfile.mkdtemp())

    # Create Asurion folder with transcripts
    asurion_dir = temp_dir / "Ambient_ Project"
    asurion_dir.mkdir()

    (asurion_dir / "Meeting 2025-09-22 12_31 transcript.txt").write_text(
        "Speaker 1: Let's discuss the PRD automation.\n"
        "Speaker 2: Yes, we need to move to pilot phase.\n"
    )

    (asurion_dir / "Meeting 2025-09-15 12_31 transcript.txt").write_text(
        "Speaker 1: Kickoff for workflow redesign.\n"
        "Speaker 2: Scott will lead this effort.\n"
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_db():
    """Create temporary database."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    yield db_path
    if db_path.exists():
        db_path.unlink()


def test_full_pipeline_processes_transcripts(temp_transcripts, temp_db):
    """Test the full pipeline with mock Claude API."""

    mock_processed = {
        "meeting_title": "Asurion Weekly",
        "date": "2025-09-22",
        "project_client": "Asurion",
        "attendees": ["Speaker 1", "Speaker 2"],
        "main_topics": ["PRD automation"],
        "key_context": ["Moving to pilot phase"],
        "implied_work": ["Prep pilot documentation"]
    }

    with patch('daily_sync.TranscriptProcessor') as mock_processor_class:
        mock_processor = Mock()
        mock_processor.process_file.return_value = mock_processed
        mock_processor_class.return_value = mock_processor

        with patch('daily_sync.MemoryUpdater') as mock_memory_class:
            mock_memory = Mock()
            mock_memory.update_from_transcript.return_value = True
            mock_memory_class.return_value = mock_memory

            sync = DailySync(
                transcripts_dir=str(temp_transcripts),
                db_path=str(temp_db)
            )

            result = sync.run()

            assert result["total"] == 2
            assert result["success"] == 2
            assert result["failed"] == 0

            # Verify processor was called for each file
            assert mock_processor.process_file.call_count == 2

            # Verify memory was updated for each
            assert mock_memory.update_from_transcript.call_count == 2

            sync.close()


def test_pipeline_skips_already_processed(temp_transcripts, temp_db):
    """Test that already processed files are skipped."""

    # Pre-mark one file as processed
    tracker = TranscriptTracker(temp_db)
    transcript_path = str(temp_transcripts / "Ambient_ Project" / "Meeting 2025-09-22 12_31 transcript.txt")
    tracker.mark_processed(
        filepath=transcript_path,
        filename="Meeting 2025-09-22 12_31 transcript.txt",
        meeting_date="2025-09-22",
        client_entity="Asurion",
        status="success"
    )
    tracker.close()

    mock_processed = {
        "meeting_title": "Test",
        "date": "2025-09-15",
        "project_client": "Asurion",
        "attendees": [],
        "main_topics": [],
        "key_context": [],
        "implied_work": []
    }

    with patch('daily_sync.TranscriptProcessor') as mock_processor_class:
        mock_processor = Mock()
        mock_processor.process_file.return_value = mock_processed
        mock_processor_class.return_value = mock_processor

        with patch('daily_sync.MemoryUpdater') as mock_memory_class:
            mock_memory = Mock()
            mock_memory_class.return_value = mock_memory

            sync = DailySync(
                transcripts_dir=str(temp_transcripts),
                db_path=str(temp_db)
            )

            result = sync.run()

            # Only 1 should be processed (the other was pre-marked)
            assert result["total"] == 1
            assert mock_processor.process_file.call_count == 1

            sync.close()
```

**Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: All 2 tests PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for full pipeline"
```

---

## Task 11: Initial Sync - Process Existing Transcripts

**This is a manual step after all code is committed.**

**Step 1: Verify all tests pass**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Run dry-run to see what would be processed**

Run: `python daily_sync.py --dry-run --transcripts-dir ../transcripts`
Expected: Lists 75+ transcripts to process

**Step 3: Process in batches (to manage API costs)**

Run: `python daily_sync.py --limit 10 --transcripts-dir ../transcripts`
Expected: Processes 10 transcripts, ~$0.10-0.20 API cost

**Step 4: Continue until all processed**

Repeat with `--limit 20` until all transcripts are processed.

**Step 5: Verify memory was populated**

In Claude Code, run:
```
Search the work-planning memory context for "Asurion"
```
Expected: Returns Asurion entity with meeting observations

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | TranscriptTracker (init) | 1 test |
| 2 | TranscriptTracker (methods) | 2 tests |
| 3 | ClientMapper | 3 tests |
| 4 | TranscriptProcessor | 2 tests |
| 5 | MemoryUpdater | 2 tests |
| 6 | DailySync orchestrator | 2 tests |
| 7 | Scraper auto mode | 2 tests |
| 8 | Scraper all_series mode | manual |
| 9 | Launchd automation | manual |
| 10 | Integration tests | 2 tests |
| 11 | Initial sync | manual |

**Total: 16 automated tests + 3 manual verification steps**
