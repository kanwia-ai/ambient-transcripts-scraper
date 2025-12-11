#!/usr/bin/env python3
"""
Ambient Transcripts Scraper

This script automates downloading transcripts from app.ambient.us.
It supports both Meeting Series and Project pages.

Usage:
    python scraper.py [--browser-path /path/to/chromium]

Environment Variables:
    CHROMIUM_PATH - Path to Chromium executable

The script will:
1. Launch a Chromium browser
2. Wait for you to log in and navigate to a meeting series or project page
3. Automatically detect the page type
4. Download all transcripts (skipping existing ones)
"""

import argparse
import asyncio
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Download


class AmbientScraper:
    def __init__(
        self,
        download_dir: str = "./transcripts",
        browser_path: Optional[str] = None,
        auto_mode: bool = False,
        all_series: bool = False,
        my_meetings: bool = False,
        target_url: Optional[str] = None,
        headless: bool = False
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.browser_path = browser_path or os.environ.get('CHROMIUM_PATH')
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.auto_mode = auto_mode
        self.all_series = all_series
        self.my_meetings = my_meetings
        self.target_url = target_url
        self.headless = headless

    async def setup(self):
        """Initialize Playwright and launch browser."""
        self.playwright = await async_playwright().start()

        # Prepare launch options
        launch_options = {
            'headless': self.headless,
            'args': ['--start-maximized'] if not self.headless else []
        }

        # Use custom browser path if provided
        if self.browser_path:
            launch_options['executable_path'] = self.browser_path
            print(f"Using Chromium at: {self.browser_path}")

        # Launch browser with visible UI so user can log in
        self.browser = await self.playwright.chromium.launch(**launch_options)

        # Check for saved auth state
        auth_state_file = self.download_dir / "auth_state.json"
        context_options = {
            'viewport': None,
            'accept_downloads': True
        }
        if auth_state_file.exists():
            context_options['storage_state'] = str(auth_state_file)
            print(f"✓ Loading saved session from {auth_state_file}")

        self.context = await self.browser.new_context(**context_options)

        self.page = await self.context.new_page()

    async def wait_for_navigation(self):
        """Wait for user to log in and navigate to target page.

        In auto_mode with target_url: navigates directly without user input.
        In auto_mode without target_url: skips instructions, waits briefly.
        In manual mode: shows instructions and waits for ENTER.
        """
        if self.auto_mode and self.target_url:
            # Auto mode with specific target - go directly there
            print(f"[Auto] Navigating to: {self.target_url}")
            await self.page.goto(self.target_url)
            await self.page.wait_for_load_state('networkidle')
            current_url = self.page.url
            return self.detect_page_type(current_url)

        if self.auto_mode:
            # Auto mode without target - wait for existing navigation
            print("[Auto] Waiting for page to be ready...")
            await self.page.goto('https://app.ambient.us/')
            await self.page.wait_for_load_state('networkidle')
            # Brief wait for any redirects
            await asyncio.sleep(2)
            current_url = self.page.url
            return self.detect_page_type(current_url)

        # Manual mode - show instructions and wait for user
        print("\n" + "="*60)
        print("INSTRUCTIONS:")
        print("="*60)
        print("1. Log in to your Ambient account")
        print("2. Navigate to either:")
        print("   - A Meeting Series page (app.ambient.us/dashboard/meetingseries/...)")
        print("   - A Project page (app.ambient.us/dashboard/projects/...)")
        print("3. Once on the correct page, press ENTER here to continue")
        print("="*60 + "\n")

        await self.page.goto('https://app.ambient.us/')

        # Wait for user input
        input("Press ENTER when you're ready to start scraping...")

        # Get current URL to determine page type
        current_url = self.page.url
        return self.detect_page_type(current_url)

    def detect_page_type(self, url: str) -> str:
        """Detect whether we're on a meeting series or project page."""
        if '/meetingseries/' in url:
            return 'meetingseries'
        elif '/projects/' in url:
            return 'project'
        else:
            raise ValueError(f"Unknown page type. URL must contain '/meetingseries/' or '/projects/'\nCurrent URL: {url}")

    def sanitize_filename(self, name: str) -> str:
        """Remove invalid characters from filename."""
        # Replace invalid characters with underscore
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing spaces and dots
        name = name.strip('. ')
        # Collapse multiple spaces
        name = re.sub(r'\s+', ' ', name)
        return name

    async def get_page_title(self) -> str:
        """Extract the meeting series or project name from the page."""
        try:
            # Try multiple selectors to get the title
            title = None

            # Try h1 first
            title_elem = await self.page.query_selector('h1')
            if title_elem:
                title = await title_elem.text_content()

            if not title:
                # Try getting from page title
                title = await self.page.title()

            return self.sanitize_filename(title.strip()) if title else "ambient_downloads"
        except Exception as e:
            print(f"Warning: Could not extract page title: {e}")
            return "ambient_downloads"

    async def scrape_meeting_series(self):
        """Scrape all meetings from a meeting series page."""
        print("\n📊 Detected: Meeting Series Page")

        # Get series name for folder
        series_name = await self.get_page_title()
        series_folder = self.download_dir / series_name
        series_folder.mkdir(exist_ok=True)

        print(f"📁 Saving to: {series_folder}")

        # Wait for the meetings table to load
        try:
            await self.page.wait_for_selector('table', timeout=10000)
        except Exception:
            print("❌ No meetings table found on this page")
            return

        # Find all "View Summary" buttons to get count
        view_buttons = await self.page.query_selector_all('button:has-text("View Summary")')

        if not view_buttons:
            print("❌ No meetings found on this page")
            return

        total_meetings = len(view_buttons)
        print(f"\n✅ Found {total_meetings} meetings")

        # Process each meeting using INDEX-BASED iteration
        for idx in range(total_meetings):
            try:
                # RE-QUERY buttons fresh at START of each iteration
                await asyncio.sleep(0.5)  # Brief pause for DOM stability
                view_buttons = await self.page.query_selector_all('button:has-text("View Summary")')

                if idx >= len(view_buttons):
                    print(f"⚠️  Button list changed, stopping at {idx}")
                    break

                button = view_buttons[idx]

                # Get the meeting row to extract date and title
                row = await button.evaluate_handle('btn => btn.closest("tr")')
                cells = await row.query_selector_all('td')

                # Extract meeting info from table cells
                meeting_date = await cells[0].text_content() if len(cells) > 0 else "unknown_date"
                meeting_title = await cells[1].text_content() if len(cells) > 1 else f"meeting_{idx+1}"

                meeting_date = self.sanitize_filename(meeting_date.strip())
                meeting_title = self.sanitize_filename(meeting_title.strip())

                filename = f"{meeting_date}_{meeting_title}.txt"
                filepath = series_folder / filename

                # Skip if already exists
                if filepath.exists():
                    print(f"⏭️  [{idx+1}/{total_meetings}] Skipping (already exists): {filename}")
                    continue

                print(f"\n📥 [{idx+1}/{total_meetings}] Downloading: {filename}")

                # Click to open meeting page
                await button.click()
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(1)  # Wait for page to fully render

                # Download the transcript
                await self.download_transcript(filepath)

                # Go back to meetings list
                await self.page.go_back()
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(1)  # Wait for list to reload

            except Exception as e:
                print(f"❌ Error processing meeting {idx+1}: {e}")
                # Try to go back to the list
                try:
                    await self.page.go_back()
                    await self.page.wait_for_load_state('networkidle')
                    await asyncio.sleep(1)
                except:
                    pass
                continue

        print(f"\n✅ Completed! Transcripts saved to: {series_folder}")

    async def scrape_project(self):
        """Scrape all meetings from a project page."""
        print("\n📊 Detected: Project Page")

        # Get project name for folder
        project_name = await self.get_page_title()
        project_folder = self.download_dir / project_name
        project_folder.mkdir(exist_ok=True)

        print(f"📁 Saving to: {project_folder}")

        # Scroll down to find the Summaries section
        await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)

        # Find all meeting links in the Summaries section
        # These are typically expandable items with meeting names
        meeting_links = await self.page.query_selector_all('[data-testid*="summary"], .summary-item, a[href*="/meeting/"]')

        if not meeting_links:
            print("❌ No meetings found in Summaries section")
            print("💡 Tip: Make sure you're on a project page with meetings listed")
            return

        print(f"\n✅ Found {len(meeting_links)} meetings")

        # Get all meeting URLs first (to avoid stale references)
        meeting_urls = []
        for link in meeting_links:
            try:
                href = await link.get_attribute('href')
                if href and '/meeting/' in href:
                    meeting_urls.append(href)
            except:
                continue

        if not meeting_urls:
            print("❌ Could not extract meeting URLs")
            return

        # Process each meeting
        for idx, meeting_url in enumerate(meeting_urls, 1):
            try:
                # Navigate directly to meeting page
                full_url = meeting_url if meeting_url.startswith('http') else f"https://app.ambient.us{meeting_url}"

                print(f"\n📥 [{idx}/{len(meeting_urls)}] Opening meeting...")
                await self.page.goto(full_url)
                await self.page.wait_for_load_state('networkidle')

                # Extract meeting title and date from the page
                meeting_title = await self.get_page_title()

                # Try to find date on the page
                meeting_date = "unknown_date"
                try:
                    date_elem = await self.page.query_selector('[data-testid*="date"], .date, time')
                    if date_elem:
                        meeting_date = await date_elem.text_content()
                        meeting_date = self.sanitize_filename(meeting_date.strip())
                except:
                    pass

                filename = f"{meeting_date}_{meeting_title}.txt"
                filepath = project_folder / filename

                # Skip if already exists
                if filepath.exists():
                    print(f"⏭️  Skipping (already exists): {filename}")
                    continue

                print(f"📥 Downloading: {filename}")

                # Download the transcript
                await self.download_transcript(filepath)

            except Exception as e:
                print(f"❌ Error processing meeting {idx}: {e}")
                continue

        print(f"\n✅ Completed! Transcripts saved to: {project_folder}")

    async def download_transcript(self, filepath: Path):
        """Download transcript from an individual meeting page."""
        try:
            # Wait for page to fully render
            await asyncio.sleep(2)

            # Wait for the Download Transcript button to appear (with timeout)
            try:
                download_button = await self.page.wait_for_selector(
                    'button:has-text("Download Transcript")',
                    timeout=15000
                )
            except Exception:
                # If Download Transcript not found, try clicking Transcript tab first
                try:
                    transcript_tab = await self.page.wait_for_selector(
                        'button:has-text("Transcript"):not(:has-text("Download"))',
                        timeout=5000
                    )
                    if transcript_tab:
                        await transcript_tab.click()
                        await asyncio.sleep(2)
                        download_button = await self.page.wait_for_selector(
                            'button:has-text("Download Transcript")',
                            timeout=10000
                        )
                except Exception:
                    download_button = None

            if not download_button:
                # Fallback: try to get the transcript text directly from the page
                print("⚠️  Download button not found, trying to extract text...")
                transcript_text = await self.extract_transcript_text()
                if transcript_text:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(transcript_text)
                    print(f"✅ Saved (text extraction): {filepath.name}")
                else:
                    print("⚠️  Could not extract transcript")
                return

            # Try to download - if it fails, fallback to text extraction
            try:
                async with self.page.expect_download(timeout=15000) as download_info:
                    await download_button.click()

                download = await download_info.value
                await download.save_as(filepath)
                print(f"✅ Saved: {filepath.name}")
            except Exception as download_err:
                # Download failed (possibly no file download triggered)
                print(f"⚠️  Download failed ({download_err.__class__.__name__}), extracting text...")
                transcript_text = await self.extract_transcript_text()
                if transcript_text:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(transcript_text)
                    print(f"✅ Saved (text extraction): {filepath.name}")
                else:
                    print("⚠️  Could not extract transcript")

        except Exception as e:
            print(f"❌ Error downloading transcript: {e}")

    async def extract_transcript_text(self) -> str:
        """Extract transcript text directly from the page as fallback."""
        try:
            # First, click on Transcript tab to show transcript content
            try:
                transcript_tab = await self.page.wait_for_selector(
                    'button:has-text("Transcript"):not(:has-text("Download"))',
                    timeout=5000
                )
                if transcript_tab:
                    await transcript_tab.click()
                    await asyncio.sleep(2)
            except Exception:
                pass

            # Extract the page content
            content = await self.page.evaluate('''() => {
                // Try to find transcript-specific content
                const transcriptContainer = document.querySelector('[class*="transcript"], [data-testid*="transcript"]');
                if (transcriptContainer) {
                    return transcriptContainer.innerText;
                }

                // Otherwise get main content area
                const main = document.querySelector('main');
                if (main) {
                    return main.innerText;
                }

                return document.body.innerText;
            }''')

            # Clean up the content (remove navigation, menus, etc)
            if content:
                lines = content.split('\n')
                # Skip header lines (navigation, menu items)
                start_idx = 0
                for i, line in enumerate(lines):
                    if 'Overview' in line or 'Key Topics' in line or 'Action Items' in line:
                        start_idx = i
                        break
                return '\n'.join(lines[start_idx:])

            return ""
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""

    async def scrape_my_meetings_feed(self):
        """Scrape all individual meetings from the My Meetings feed.

        This feed shows all meetings (700+) with infinite scroll pagination.
        Meetings are shown as cards/items that can be clicked to view details.
        """
        print("\n📋 Processing My Meetings feed...")

        # Create folder for individual meetings
        meetings_folder = self.download_dir / "My Meetings"
        meetings_folder.mkdir(exist_ok=True)

        # Go to My Meetings page
        await self.page.goto('https://app.ambient.us/dashboard/post?a=myMeetings')
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        # Get existing files to skip duplicates
        existing_files = {f.stem for f in meetings_folder.glob("*.txt")}
        print(f"📁 Saving to: {meetings_folder}")
        print(f"⏭️  {len(existing_files)} existing transcripts to skip")

        processed_count = 0
        skipped_count = 0
        error_count = 0
        page_num = 1
        consecutive_existing = 0

        while True:
            print(f"\n📄 Page {page_num}...")

            # Get meeting items on current view
            meeting_items = await self.get_meeting_items_from_feed()

            if not meeting_items:
                print("  No more meetings found")
                break

            print(f"  Found {len(meeting_items)} meetings on this page")

            for idx, meeting_info in enumerate(meeting_items):
                meeting_title = meeting_info.get('title', f'meeting_{page_num}_{idx}')
                meeting_date = meeting_info.get('date', '')

                # Create filename
                if meeting_date:
                    filename = f"{meeting_date}_{meeting_title}"
                else:
                    filename = meeting_title

                filename = self.sanitize_filename(filename)

                # Check if already exists
                if filename in existing_files:
                    skipped_count += 1
                    consecutive_existing += 1
                    if consecutive_existing >= 50:
                        # If we've seen 50 consecutive existing files, likely done
                        print(f"\n  ⏭️  Skipped {consecutive_existing} consecutive existing files, likely caught up")
                        break
                    continue

                consecutive_existing = 0  # Reset counter
                filepath = meetings_folder / f"{filename}.txt"

                print(f"\n📥 [{processed_count + skipped_count + 1}] {filename[:50]}...")

                # Click on the meeting to open detail view
                try:
                    # Click using the meeting's index to open it
                    success = await self.click_meeting_item(idx)
                    if not success:
                        print(f"  ⚠️ Could not open meeting")
                        error_count += 1
                        continue

                    await asyncio.sleep(2)

                    # Check if we navigated to a new page or opened in-place
                    current_url = self.page.url
                    navigated = '/posts/' in current_url or '/meeting/' in current_url

                    # Download transcript
                    await self.download_transcript(filepath)
                    processed_count += 1
                    existing_files.add(filename)

                    # If we navigated, go back. Otherwise close any drawer/panel
                    if navigated:
                        await self.page.go_back()
                        await self.page.wait_for_load_state('networkidle')
                        await asyncio.sleep(1)
                    else:
                        # Try to close any open drawer/panel by clicking outside or pressing Escape
                        await self.page.keyboard.press('Escape')
                        await asyncio.sleep(1)

                        # Also try clicking a "close" button if it exists
                        close_btn = await self.page.query_selector('button[aria-label*="close"], button[aria-label*="Close"], [class*="close"], [class*="Close"]')
                        if close_btn:
                            await close_btn.click()
                            await asyncio.sleep(1)

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    error_count += 1
                    try:
                        await self.page.goto('https://app.ambient.us/dashboard/post?a=myMeetings')
                        await self.page.wait_for_load_state('networkidle')
                        await asyncio.sleep(2)
                    except:
                        pass
                    continue

            # Check if we hit the consecutive existing limit
            if consecutive_existing >= 50:
                break

            # Try to load more meetings (scroll or click "next")
            has_more = await self.load_more_meetings()
            if not has_more:
                print("  No more meetings to load")
                break

            page_num += 1

        print(f"\n✅ My Meetings feed complete!")
        print(f"   Downloaded: {processed_count}")
        print(f"   Skipped (existing): {skipped_count}")
        print(f"   Errors: {error_count}")

    async def get_meeting_items_from_feed(self) -> List[Dict]:
        """Extract meeting items from the My Meetings feed.

        Returns list of dicts with 'title', 'date', and 'index' for each meeting.
        """
        return await self.page.evaluate('''() => {
            const items = [];

            // Meeting cards are MuiPaper elements with specific classes
            // Format: "Tom / Kyra: Working SessionKDec 4, 2025 3:00 PM"
            // The "K" is an avatar letter that appears inline

            const cards = document.querySelectorAll('.MuiPaper-root.MuiPaper-elevation.MuiPaper-rounded');

            cards.forEach((card, idx) => {
                const text = card.textContent?.trim() || '';

                // Filter to only meeting cards (have date pattern)
                const dateMatch = text.match(/([A-Z][a-z]{2}\\s+\\d{1,2},?\\s+\\d{4}\\s+\\d{1,2}:\\d{2}\\s+[AP]M)/);
                if (!dateMatch) return;

                // Extract title - text before the avatar letter (single capital letter before date)
                // Pattern: "Title Here" + avatar + "Date"
                const titleMatch = text.match(/^(.+?)(?:[A-Z](?=[A-Z][a-z]{2}\\s+\\d))/);
                const title = titleMatch ? titleMatch[1].trim() : text.split(/[A-Z][a-z]{2}\\s+\\d/)[0].trim();

                // Extract date
                const date = dateMatch[1];

                items.push({
                    title: title.substring(0, 100),
                    date: date,
                    index: idx,
                    fullText: text.substring(0, 150)
                });
            });

            return items;
        }''')

    async def click_meeting_item(self, index: int) -> bool:
        """Click on a meeting item by index to open its detail view.

        Clicking a meeting card in the feed opens it in-place (likely a drawer/panel).
        Returns True if successful, False otherwise.
        """
        try:
            # Get all meeting cards (MuiPaper elements with date patterns)
            cards = await self.page.query_selector_all('.MuiPaper-root.MuiPaper-elevation.MuiPaper-rounded')

            # Filter to only meeting cards (ones with date pattern)
            meeting_cards = []
            for card in cards:
                text = await card.text_content()
                if text and any(month in text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                    meeting_cards.append(card)

            if index >= len(meeting_cards):
                print(f"  ⚠️ Index {index} out of range (only {len(meeting_cards)} cards)")
                return False

            # Click the meeting card
            card = meeting_cards[index]
            await card.click()
            await asyncio.sleep(2)  # Wait for panel/content to load

            # Check if we navigated to a new URL or if content appeared
            current_url = self.page.url
            if '/posts/' in current_url or '/meeting/' in current_url:
                return True

            # Clicking might open a side panel instead of navigating
            # Look for panel content (Download Transcript button or transcript text)
            download_btn = await self.page.query_selector('button:has-text("Download Transcript")')
            if download_btn:
                return True

            # Also check for detail panel with Overview/Summary text
            detail_panel = await self.page.query_selector('[class*="drawer"], [class*="Drawer"], [class*="modal"], [class*="Modal"], [class*="panel"], [class*="Panel"]')
            if detail_panel:
                return True

            # Check if main content area changed (has meeting detail content)
            main_content = await self.page.evaluate('''() => {
                const main = document.querySelector('main');
                return main ? main.innerText.substring(0, 500) : '';
            }''')

            # Meeting detail typically has "Overview", "Key Topics", "Action Items" etc
            if 'Overview' in main_content or 'Key Topics' in main_content or 'Transcript' in main_content:
                return True

            return False

        except Exception as e:
            print(f"  Click error: {e}")
            return False

    async def load_more_meetings(self) -> bool:
        """Try to load more meetings by clicking the next page arrow.

        The My Meetings feed shows "1–25 of 700" with pagination arrows.
        Returns True if more meetings were loaded, False if no more.
        """
        try:
            # Look for the right/next arrow button (common in MUI pagination)
            # The button has aria-label "Go to next page" or similar
            next_btn = await self.page.query_selector('button[aria-label="Go to next page"]:not([disabled])')

            if not next_btn:
                # Try other common next button patterns
                next_btn = await self.page.query_selector('[data-testid*="next"]:not([disabled]), button:has(svg[data-testid="KeyboardArrowRightIcon"]):not([disabled])')

            if next_btn:
                await next_btn.click()
                await asyncio.sleep(2)

                # Wait for new content to load
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(1)
                return True

            # No pagination button found or disabled - we're at the end
            return False

        except Exception as e:
            print(f"  Load more error: {e}")
            return False

    async def run_my_meetings(self):
        """Process all meetings from the My Meetings feed."""
        try:
            await self.setup()

            # Check if we need to log in first
            auth_state_file = self.download_dir / "auth_state.json"
            if not auth_state_file.exists():
                print("\n" + "="*60)
                print("LOGIN REQUIRED")
                print("="*60)
                print("1. Log in to your Ambient account in the browser")
                print("2. Once logged in, press ENTER here to continue")
                print("="*60 + "\n")

                await self.page.goto('https://app.ambient.us/')
                input("Press ENTER after logging in...")

                # Save auth state
                await self.context.storage_state(path=str(auth_state_file))
                print("✓ Login session saved!")

            # Process My Meetings feed
            await self.scrape_my_meetings_feed()

            print(f"\n🎉 Finished processing My Meetings feed!")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()

    async def get_series_buttons_on_page(self) -> List[Dict]:
        """Get series name buttons from the current table page.

        Returns:
            List of dicts with 'name' and 'index' for each series button
        """
        return await self.page.evaluate('''() => {
            const rows = document.querySelectorAll('table tbody tr');
            const series = [];
            rows.forEach((row, rowIdx) => {
                const buttons = row.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent?.trim();
                    // Series name buttons have meaningful text, not just "Hide" etc
                    if (text && text.length > 2 && !['Hide', 'Show', ''].includes(text)) {
                        series.push({ name: text, rowIndex: rowIdx });
                        break;
                    }
                }
            });
            return series;
        }''')

    async def click_series_by_index(self, row_index: int) -> str:
        """Click on a series button by row index and wait for navigation.

        Returns:
            The URL navigated to, or empty string if navigation failed
        """
        rows = await self.page.query_selector_all('table tbody tr')
        if row_index >= len(rows):
            return ""

        row = rows[row_index]
        buttons = await row.query_selector_all('button')

        for btn in buttons:
            btn_text = await btn.text_content()
            if btn_text and btn_text.strip() not in ['', 'Hide', 'Show']:
                # Click and wait for URL to change
                await btn.click()

                # Wait for navigation (URL should change from list page)
                try:
                    await self.page.wait_for_url(
                        lambda url: 'meetingseries/' in url and 'list' not in url,
                        timeout=5000
                    )
                    return self.page.url
                except:
                    # Navigation might have failed
                    return ""

        return ""

    async def click_series_by_name(self, series_name: str) -> str:
        """Click on a series button by matching its name.

        Args:
            series_name: The exact name of the series to click

        Returns:
            The URL navigated to, or empty string if navigation failed
        """
        # Wait for table to be present
        try:
            await self.page.wait_for_selector('table tbody tr', timeout=10000)
        except:
            return ""

        rows = await self.page.query_selector_all('table tbody tr')

        for row in rows:
            buttons = await row.query_selector_all('button')
            for btn in buttons:
                btn_text = await btn.text_content()
                if btn_text and btn_text.strip() == series_name:
                    # Found the matching series button - click it
                    await btn.click()

                    # Wait for navigation
                    try:
                        await self.page.wait_for_url(
                            lambda url: 'meetingseries/' in url and 'list' not in url,
                            timeout=10000
                        )
                        await asyncio.sleep(1)  # Extra wait for content to load
                        return self.page.url
                    except:
                        return ""

        return ""

    async def navigate_to_list_page(self, page_num: int) -> None:
        """Navigate to a specific page of the meeting series list.

        Args:
            page_num: 1-based page number to navigate to
        """
        # Go to list first
        await self.page.goto('https://app.ambient.us/dashboard/meetingseries/list?all')
        try:
            await self.page.wait_for_load_state('networkidle', timeout=15000)
        except:
            await asyncio.sleep(3)
        await self.page.wait_for_selector('table tbody tr', timeout=10000)

        # Click "next page" (page_num - 1) times to get to the right page
        for _ in range(page_num - 1):
            next_button = await self.page.query_selector('button[aria-label="Go to next page"]:not([disabled])')
            if next_button:
                await next_button.click()
                try:
                    await self.page.wait_for_load_state('networkidle', timeout=15000)
                except:
                    await asyncio.sleep(3)
                await self.page.wait_for_selector('table tbody tr', timeout=10000)
                await asyncio.sleep(1)

    async def process_all_series_on_page(self, processed_names: set, total_processed: int, page_num: int) -> int:
        """Process all meeting series on the current table page.

        Args:
            processed_names: Set of series names already processed (to avoid duplicates)
            total_processed: Running count of processed series
            page_num: Current page number (1-based)

        Returns:
            Updated count of processed series
        """
        # Get series info from this page
        series_on_page = await self.get_series_buttons_on_page()
        series_names_on_page = [s['name'] for s in series_on_page]
        print(f"  Found {len(series_names_on_page)} series on this page")

        # Process each series by name (re-finding it each time after navigation)
        for series_name in series_names_on_page:
            if series_name in processed_names:
                print(f"  ⏭️ [{series_name[:40]}] Already processed")
                continue

            print(f"\n  → [{total_processed + 1}] {series_name[:50]}...")

            # Click to navigate to the series
            series_url = await self.click_series_by_name(series_name)

            if not series_url:
                print(f"    ⚠️ Could not navigate to series")
                continue

            processed_names.add(series_name)
            total_processed += 1

            # Scrape this series
            try:
                await self.scrape_meeting_series()
            except Exception as e:
                print(f"    ❌ Error scraping: {e}")

            # Go back to the correct page of the list
            await self.navigate_to_list_page(page_num)
            await asyncio.sleep(1)

        return total_processed

    async def get_all_meeting_series_urls(self) -> List[str]:
        """Process all meeting series by clicking through each one.

        This method navigates through all pages of meeting series,
        clicks each one to scrape it, then returns to the list.

        Returns:
            List of processed series names
        """
        print("\n📋 Processing all meeting series...")

        # Go to the All tab
        await self.page.goto('https://app.ambient.us/dashboard/meetingseries/list?all')
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        processed_names = set()
        total_processed = 0
        page_num = 0

        while True:
            page_num += 1
            print(f"\n📄 Page {page_num} of meeting series list...")

            # Process all series on current page
            total_processed = await self.process_all_series_on_page(processed_names, total_processed, page_num)

            # Check for next page button
            next_button = await self.page.query_selector('button[aria-label="Go to next page"]:not([disabled])')
            if next_button:
                print("  → Moving to next page...")
                await next_button.click()
                try:
                    await self.page.wait_for_load_state('networkidle', timeout=15000)
                except:
                    await asyncio.sleep(3)
                # Wait for table rows to appear on new page
                await self.page.wait_for_selector('table tbody tr', timeout=10000)
                await asyncio.sleep(2)  # Extra wait for content to stabilize
            else:
                print("  → No more pages")
                break

        print(f"\n✅ Total meeting series processed: {total_processed}")
        return list(processed_names)

    async def run_all_series(self):
        """Process all meeting series automatically.

        Iterates through all meeting series and scrapes transcripts from each.
        """
        try:
            await self.setup()

            # Check if we need to log in first
            auth_state_file = self.download_dir / "auth_state.json"
            if not auth_state_file.exists():
                print("\n" + "="*60)
                print("LOGIN REQUIRED")
                print("="*60)
                print("1. Log in to your Ambient account in the browser")
                print("2. Once logged in, press ENTER here to continue")
                print("="*60 + "\n")

                await self.page.goto('https://app.ambient.us/')
                input("Press ENTER after logging in...")

                # Save auth state
                await self.context.storage_state(path=str(auth_state_file))
                print("✓ Login session saved!")

            # Process all meeting series (now done directly in get_all_meeting_series_urls)
            processed_urls = await self.get_all_meeting_series_urls()

            print(f"\n🎉 Finished! Processed {len(processed_urls)} meeting series")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()

    async def run(self):
        """Main execution flow."""
        # If all_series mode, delegate to run_all_series
        if self.all_series:
            await self.run_all_series()
            return

        # If my_meetings mode, delegate to run_my_meetings
        if self.my_meetings:
            await self.run_my_meetings()
            return

        try:
            await self.setup()

            # Wait for user to navigate to the correct page
            page_type = await self.wait_for_navigation()

            # Scrape based on page type
            if page_type == 'meetingseries':
                await self.scrape_meeting_series()
            elif page_type == 'project':
                await self.scrape_project()

            print("\n🎉 All done!")
            if not self.auto_mode:
                print("\nPress ENTER to close the browser...")
                input()

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()


async def main():
    parser = argparse.ArgumentParser(
        description='Download transcripts from Ambient meeting series or projects'
    )
    parser.add_argument(
        '--browser-path',
        type=str,
        help='Path to Chromium executable (or set CHROMIUM_PATH env var)'
    )
    parser.add_argument(
        '--download-dir',
        type=str,
        default='./transcripts',
        help='Directory to save transcripts (default: ./transcripts)'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Run in auto mode (skip user input prompts)'
    )
    parser.add_argument(
        '--all-series',
        action='store_true',
        help='Process all meeting series automatically'
    )
    parser.add_argument(
        '--my-meetings',
        action='store_true',
        help='Process all individual meetings from My Meetings feed'
    )
    parser.add_argument(
        '--target-url',
        type=str,
        help='Navigate directly to this URL (requires --auto)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode (no visible window)'
    )

    args = parser.parse_args()

    scraper = AmbientScraper(
        download_dir=args.download_dir,
        browser_path=args.browser_path,
        auto_mode=args.auto,
        all_series=args.all_series,
        my_meetings=args.my_meetings,
        target_url=args.target_url,
        headless=args.headless
    )
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
