# Transcript Synthesis Pipeline - Design Document

**Goal:** Automatically scrape all Ambient transcripts, summarize them, and store structured context in Memory MCP's `work-planning` context to inform Claude during work planning sessions.

**Trigger:** Daily at 8 AM via launchd (runs when Mac wakes if asleep)

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Ambient        │     │  Transcript      │     │  Memory MCP     │
│  Scraper        │────▶│  Processor       │────▶│  Updater        │
│  (Playwright)   │     │  (Claude API)    │     │  (work-planning)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                        │
         └───────────┬───────────┴────────────────────────┘
                     ▼
              ┌─────────────┐
              │  SQLite DB  │
              │  (tracking) │
              └─────────────┘
```

---

## Component 1: Enhanced Scraper

**Changes to existing `scraper.py`:**

1. **Auto-navigate all Meeting Series**
   - Go to "View All" under Meeting Series
   - Get list of all series (1:1s, Team Meetings, External, etc.)
   - Scrape each one sequentially

2. **Then hit My Meetings for stragglers**
   - Navigate to Feed → My Meetings
   - Scrape any meetings not already captured

3. **Fully automated mode**
   - Use saved auth state (already working)
   - `--auto` flag skips "press ENTER" prompts
   - `--all-series` flag iterates through everything

**Command:**
```bash
python scraper.py --auto --all-series --download-dir ./transcripts
```

**Flow:**
1. Load saved auth state
2. Navigate to Meeting Series → View All
3. Get list of all series URLs
4. For each series: scrape (skips existing), return to list
5. Navigate to Feed → My Meetings
6. Scrape any remaining meetings
7. Exit

---

## Component 2: Transcript Processor

**Purpose:** Extract structured context from raw transcripts.

**Input:** Raw `.txt` transcript file

**Output:** Structured JSON:
```json
{
  "meeting_title": "Asurion x Section Weekly Sync",
  "date": "2025-09-22",
  "project_client": "Asurion",
  "attendees": ["Scott", "Kyra", "Frank"],
  "main_topics": [
    "PRD automation workflow status",
    "HR virtual agent timeline discussion"
  ],
  "key_context": [
    "PRD workflow moving to pilot phase next month",
    "HR team wants to revisit job description generator",
    "Scott mentioned budget review coming in Q4"
  ],
  "implied_work": [
    "May need to prep pilot documentation",
    "Follow up with HR on generator requirements"
  ]
}
```

**Claude API Prompt:**
```
Summarize this meeting transcript for work planning context.
Extract: project/client name, attendees, main topics discussed,
key context (things mentioned that provide background), and
implied work (things that might need follow-up even if not
explicitly assigned as action items).
Keep it concise - this is for background context, not detailed notes.
```

**Model:** Claude Haiku (cost-effective, ~$0.01-0.02 per transcript)

---

## Component 3: Memory MCP Updater

**Entity Structure:**

```
Entity: "Asurion" (type: client)
Observations:
- "Consulting engagement with Section, started June 2025"
- "Key contacts: Scott, Frank, Claudia"
- "Workstream: PRD automation and workflow redesign"
- "Workstream: HR Virtual Agent exploration"
- "2025-09-22: Discussed PRD pilot timeline, HR wants to revisit job description generator"
- "2025-09-15: Workflow redesign kickoff, Scott mentioned Q4 budget review"
```

**Logic:**

1. **Client/project detection** - Match transcript to existing entity or create new
   - Fuzzy matching on project name ("Asurion x Section" → "Asurion")
   - Use mapping file for meeting series → client

2. **Observation deduplication** - Don't add redundant observations
   - Date-prefix meeting-specific observations

3. **Relationships** - Create where useful
   ```
   Relation: "Kyra" → works_with → "Scott"
   Relation: "Asurion" → has_workstream → "PRD_Automation"
   ```

**Mapping Configuration (`client_mapping.json`):**
```json
{
  "meeting_series_to_client": {
    "Asurion": "Asurion",
    "Ambient_ Project": "Asurion",
    "AIT Consulting Weekly": "AIT_Internal",
    "All Hands": "Section_Internal",
    "Weekly Proposal Review": "Section_Internal",
    "Kyra & Alli 1x1": "Section_Internal"
  }
}
```

---

## Component 4: Tracking Database

**Location:** `~/Documents/ambient-transcripts-scraper/processing.db`

**Schema:**
```sql
CREATE TABLE processed_transcripts (
    id INTEGER PRIMARY KEY,
    filepath TEXT UNIQUE,
    filename TEXT,
    meeting_date TEXT,
    client_entity TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT  -- 'success', 'failed', 'skipped'
);

CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    transcripts_scraped INTEGER,
    transcripts_processed INTEGER,
    status TEXT
);
```

**Daily check:** Processor scans `transcripts/` folder, compares against `processed_transcripts`, only processes new files.

---

## Component 5: Launchd Automation

**File:** `~/Library/LaunchAgents/com.kyra.ambient-sync.plist`

```xml
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
</dict>
</plist>
```

**Enable:**
```bash
launchctl load ~/Library/LaunchAgents/com.kyra.ambient-sync.plist
```

**Disable:**
```bash
launchctl unload ~/Library/LaunchAgents/com.kyra.ambient-sync.plist
```

---

## File Structure

```
ambient-transcripts-scraper/
├── scraper.py              # Enhanced with --auto --all-series
├── processor.py            # NEW: Claude API summarization
├── memory_updater.py       # NEW: Memory MCP integration
├── daily_sync.py           # NEW: Orchestrator script
├── client_mapping.json     # NEW: Meeting series → client mapping
├── processing.db           # NEW: SQLite tracking
├── transcripts/            # Downloaded transcripts
│   ├── Asurion/
│   ├── AIT Consulting Weekly/
│   ├── All Hands/
│   └── ...
└── docs/plans/
    └── 2025-12-04-transcript-synthesis-pipeline.md
```

---

## Initial Sync (One-Time)

Before daily automation:

1. **Scrape all transcripts** - Run enhanced scraper to get everything from Ambient
2. **Process existing 75+ transcripts** - Batch process into memory
3. **Verify memory state** - Check entities were created correctly

This seeds Claude with full meeting history.

---

## Daily Operation

1. **8 AM:** launchd triggers `daily_sync.py`
2. **Scrape:** Check for new transcripts (skips existing files)
3. **Process:** Summarize only new transcripts via Claude API
4. **Update:** Add observations to Memory MCP entities
5. **Log:** Record sync run in SQLite

Typical daily run: 5-10 minutes for ~5 new transcripts.

---

## Integration with Work Planning

The `work-planning` memory context now contains:

- **Client entities** with rich historical context
- **Meeting observations** with dates and key points
- **Implied work** that might need follow-up
- **Relationships** between people and projects

During `/weekly-planning`:
- Claude reads from `work-planning` context
- Has background on all clients and recent discussions
- Can proactively suggest follow-ups
- Understands context when you mention projects

---

## Dependencies

- `playwright` - Browser automation for scraping
- `anthropic` - Claude API for summarization
- `sqlite3` - Tracking database (built-in)
- Memory MCP server - Already configured

**Environment Variables:**
- `ANTHROPIC_API_KEY` - For transcript summarization
