#!/bin/bash
# Weekly Ambient Transcript Sync
# Runs: scrape new meetings → process with Claude → update memory

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/weekly_sync_$(date +%Y%m%d_%H%M%S).log"
OBSIDIAN_DIR="/Users/kyraatekwana/Documents/Obsidian Vault/Section Transcripts"

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "Weekly Ambient Sync - $(date)"
echo "=========================================="

cd "$SCRIPT_DIR"

# Step 1: Scrape new meetings from Ambient
echo ""
echo "[1/4] Scraping new meetings from Ambient..."
python3 scraper.py --my-meetings --headless 2>&1 || {
    echo "Warning: Scraper encountered issues (may need manual auth)"
}

# Step 2: Copy any new transcripts to Obsidian
echo ""
echo "[2/4] Syncing to Obsidian vault..."
python3 << 'EOF'
import os
import shutil
from pathlib import Path

src_dir = Path("transcripts")
dest_dir = Path("/Users/kyraatekwana/Documents/Obsidian Vault/Section Transcripts")
dest_dir.mkdir(parents=True, exist_ok=True)

new_count = 0
for txt_file in src_dir.glob("**/*.txt"):
    series = txt_file.parent.name
    name = txt_file.stem
    new_name = f"{series} - {name}.md"
    dest_path = dest_dir / new_name

    # Only copy if doesn't exist or source is newer
    if not dest_path.exists() or txt_file.stat().st_mtime > dest_path.stat().st_mtime:
        shutil.copy2(txt_file, dest_path)
        new_count += 1

print(f"Copied {new_count} new/updated transcripts to Obsidian")
EOF

# Step 3: Process new transcripts with Claude
echo ""
echo "[3/4] Processing transcripts with Claude API..."
if [ -n "$ANTHROPIC_API_KEY" ]; then
    python3 daily_sync.py 2>&1
else
    echo "Warning: ANTHROPIC_API_KEY not set - skipping Claude processing"
fi

# Step 4: Summary
echo ""
echo "[4/4] Sync complete!"
echo "Log saved to: $LOG_FILE"

# Show stats
echo ""
echo "Current stats:"
sqlite3 processing.db "SELECT status, COUNT(*) FROM processed_transcripts GROUP BY status" 2>/dev/null || echo "No database yet"
