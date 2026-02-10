"""Reorganize transcripts from My Meetings/ flat folder into client/project subfolders."""
import re
import shutil
from pathlib import Path

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
MY_MEETINGS = TRANSCRIPTS_DIR / "My Meetings"

# Client/project keyword mappings (checked in order, first match wins)
# Each entry: (folder_name, [keywords to match in filename, case-insensitive])
CLIENT_MAPPINGS = [
    ("Asurion", ["asurion", "section x asurion", "asurion x section"]),
    ("ABI", ["abi ", "abi_", " abi", "ab inbev"]),
    ("General Catalyst", [
        "general catalyst", " gc ", "gc x section", "gc prep", "gc event",
        "gc leaders", "gc functional", "gc ai for leaders", "gc internal",
        "zoom_ hatco x section ai", "zoom_ imco x section ai",
        "zoom_ ir x section ai", "zoom_ hr x section ai",
        "zoom_ gc capital x section ai", "zoom_ marketing x section ai",
        "zoom_ legal & compliance x section ai",
        "zoom_ operations x section ai",
        "zoom _ gcw ai champions x section",
        "hatco prompt file",
    ]),
    ("Havas", ["havas"]),
    ("HP", ["hp x section", "hp+section", "hp ai summit"]),
    ("L'Oreal", ["l'oreal", "loreal"]),
    ("Comcast", ["comcast"]),
    ("Autodesk", ["autodesk"]),
    ("Horizon", ["horizon", "martech 101"]),
    ("DeckSense", ["decksense", "deck sense", "wireframe review", "design sprint", "feature prioritization", "ui review"]),
    ("OpenAI", ["openai", "open ai", "oai partner"]),
    ("10x AI", ["10x ai"]),
    ("Builder", ["builder in a day", "building llm automations", "building agentic workflows"]),
    ("Unilever", ["unilever"]),
    ("BSWH", ["bswh"]),
]

# Recurring series: meetings that appear 3+ times get their own folder
RECURRING_SERIES = [
    "All Hands",
    "AIT Consulting Weekly",
    "Weekly Proposal Review",
    "Kyra & Alli 1x1",
    "Lauren _ Kyra 1_1",
    "Kyra _ Mary 1_1",
    "Kyra __ Tom Monday Check In",
    "Tom _ Kyra_ Working Session",
    "Education Team Weekly",
    "AI Transformation Lead Bootcamp Biweekly Sync",
    "Direct to Employee Experiences Weekly",
    "Enterprise Workshops Weekly",
    "Company Lunch & Learn",
]

# Personal/family meetings
PERSONAL_KEYWORDS = [
    "pa nkwate", "funeral", "ojukwu", "maryland wake", "maryland funeral",
    "fotemah", "celebration of life",
]

# Date pattern to split filename into title + date
DATE_RE = re.compile(r' (\d{4}-\d{2}-\d{2}) ')


def extract_title(filename: str) -> str:
    """Extract meeting title from filename (everything before the date)."""
    m = DATE_RE.search(filename)
    if m:
        return filename[:m.start()].strip()
    return filename.replace(" transcript.txt", "").strip()


def classify_file(filename: str) -> str:
    """Return the target folder name for a given transcript filename."""
    title = extract_title(filename)
    lower = filename.lower()

    # 1. Check client/project keywords
    for folder, keywords in CLIENT_MAPPINGS:
        for kw in keywords:
            if kw in lower:
                return folder

    # 2. Check personal/family
    for kw in PERSONAL_KEYWORDS:
        if kw in lower:
            return "Personal"

    # 3. Check recurring series (exact title match)
    for series in RECURRING_SERIES:
        if title == series or title.rstrip() == series:
            return series

    # 4. Fallback
    return "Individual Meetings"


def main():
    if not MY_MEETINGS.exists():
        print(f"No My Meetings folder found at {MY_MEETINGS}")
        return

    files = sorted(MY_MEETINGS.glob("*.txt"))
    print(f"Found {len(files)} transcript files in My Meetings/\n")

    moves = {}  # folder -> [filenames]
    for f in files:
        folder = classify_file(f.name)
        moves.setdefault(folder, []).append(f)

    # Preview
    print("=== REORGANIZATION PLAN ===\n")
    for folder in sorted(moves.keys()):
        file_list = moves[folder]
        print(f"  {folder}/ ({len(file_list)} files)")
        for f in file_list[:3]:
            print(f"    - {f.name}")
        if len(file_list) > 3:
            print(f"    ... and {len(file_list) - 3} more")
        print()

    total = sum(len(v) for v in moves.values())
    print(f"Total: {total} files -> {len(moves)} folders\n")

    confirm = input("Proceed with move? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # Execute moves
    moved = 0
    skipped = 0
    for folder, file_list in moves.items():
        target_dir = TRANSCRIPTS_DIR / folder
        target_dir.mkdir(exist_ok=True)
        for f in file_list:
            dest = target_dir / f.name
            if dest.exists():
                print(f"  SKIP (exists): {folder}/{f.name}")
                # Remove the duplicate from My Meetings
                f.unlink()
                skipped += 1
            else:
                shutil.move(str(f), str(dest))
                moved += 1

    print(f"\nDone! Moved {moved}, skipped {skipped} (duplicates removed)")

    # Clean up empty My Meetings folder
    remaining = list(MY_MEETINGS.glob("*"))
    if not remaining:
        MY_MEETINGS.rmdir()
        print("Removed empty My Meetings/ folder")
    else:
        print(f"Note: {len(remaining)} files remain in My Meetings/")


if __name__ == "__main__":
    main()
