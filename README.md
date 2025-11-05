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

### Basic Usage

```bash
python scraper.py
```

### Step-by-Step Process

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

## Example Workflow

```bash
# First time: Download all transcripts from a meeting series
python scraper.py
# -> Log in, navigate to meeting series, press ENTER
# -> Downloads all 25 transcripts

# Two weeks later: Get new transcripts
python scraper.py
# -> Log in, navigate to same meeting series, press ENTER
# -> Skips existing 25, downloads only the 3 new ones
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