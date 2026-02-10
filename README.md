# Ambient Transcripts Scraper

Automatically download meeting transcripts from [Ambient](https://app.ambient.us/) meeting series and projects.

## Features

- 🤖 **Automated Downloads**: Scrapes all transcripts from meeting series or project pages
- 📁 **Smart Organization**: Saves transcripts organized by meeting series or project name
- ⚡ **Incremental Updates**: Skips already downloaded transcripts, only fetches new ones
- 🔍 **Auto-Detection**: Automatically detects whether you're on a meeting series or project page
- 📝 **Clean Filenames**: Names files as `{date}_{meeting_title}.txt`

## Supported Page Types

1. **Meeting Series**: `https://app.ambient.us/dashboard/meetingseries/{SERIES_ID}`
2. **Project Pages**: `https://app.ambient.us/dashboard/projects/{PROJECT_ID}`

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd ambient-transcripts-scraper
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

## Usage

### Download Everything (Recommended)

Scrape your entire Ambient dashboard — meeting series AND individual meetings:

```bash
python scraper.py --auto-all
```

On the first run, you'll need to log in manually in the browser window that opens. After that, your session is saved and future runs are fully automated.

### Scrape a Specific Series (Non-Interactive)

```bash
python scraper.py --auto --url "https://app.ambient.us/dashboard/meetingseries/YOUR_SERIES_ID"
```

### Interactive Mode (Original)

```bash
python scraper.py
```

### Using Your Own Chromium Installation

If you already have Chromium installed or can't install Playwright's browser:

```bash
python scraper.py --browser-path /path/to/chromium
```

### All Options

| Flag | Description |
|---|---|
| `--auto-all` | Discover all meeting series and scrape everything |
| `--auto` | Skip interactive prompts (requires `--url`) |
| `--url URL` | URL of a specific meeting series or project to scrape |
| `--browser-path PATH` | Path to Chromium executable |
| `--download-dir DIR` | Directory to save transcripts (default: `./transcripts`) |
| `--clear-session` | Clear saved login session and log in again |

### Step-by-Step Process (Interactive Mode)

1. **Run the script**:
   ```bash
   python scraper.py
   ```

2. **Log in**: A Chromium browser window will open
   - Navigate to `https://app.ambient.us/`
   - Log in with your credentials

3. **Navigate to target page**:
   - Go to either a Meeting Series page OR a Project page
   - Make sure you're on the correct page showing the list of meetings

4. **Start scraping**:
   - Return to the terminal
   - Press ENTER to start the automated download

5. **Wait for completion**:
   - The script will automatically:
     - Click through each meeting
     - Navigate to the Transcript tab
     - Download the transcript
     - Save it with a descriptive filename

6. **Find your transcripts**:
   - All transcripts are saved in the `./transcripts/` folder
   - Organized by meeting series or project name

## Output Structure

```
transcripts/
├── Meeting Series Name/
│   ├── 2024-01-15_Weekly Standup.txt
│   ├── 2024-01-22_Weekly Standup.txt
│   └── 2024-01-29_Weekly Standup.txt
└── Project Name/
    ├── 2024-02-01_Kickoff Meeting.txt
    └── 2024-02-15_Sprint Review.txt
```

## Incremental Downloads

The scraper is **additive** - if you've already downloaded transcripts from a meeting series or project:

1. Run the script again on the same page
2. It will check existing files
3. Only download NEW transcripts that don't exist yet
4. Skip all previously downloaded transcripts

Perfect for regular updates!

## Example Workflows

```bash
# Download EVERYTHING from your account
python scraper.py --auto-all
# -> First run: log in when prompted, then it auto-discovers all series
# -> Downloads all transcripts from every meeting series
# -> Prints summary: X series found, Y transcripts downloaded, Z skipped

# Run again later to get only new transcripts (incremental)
python scraper.py --auto-all
# -> Uses saved auth, discovers series, skips existing files
# -> Only downloads new transcripts since last run

# Scrape a specific series without interaction
python scraper.py --auto --url "https://app.ambient.us/dashboard/meetingseries/abc123"

# Interactive mode (original behavior)
python scraper.py
# -> Log in, navigate to meeting series, press ENTER
```

## Troubleshooting

### "No meetings found"
- Make sure you're on a meeting series or project page
- Check that meetings are visible on the page
- Try scrolling down to load the Summaries section (for projects)

### "Download Transcript button not found"
- Some meetings might not have transcripts available
- The script will skip these and continue to the next meeting

### Browser closes immediately
- Make sure you press ENTER in the terminal to start scraping
- The browser should stay open until scraping is complete

## Technical Details

- **Browser Automation**: Playwright (Chromium)
- **Language**: Python 3.7+
- **Downloads**: .txt files (native Ambient transcript format)

## Notes

- Ambient does not provide a public API, so this tool uses browser automation
- You must have valid Ambient account credentials
- Respects Ambient's download functionality (clicks the official "Download Transcript" button)

## License

MIT