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
        target_url: Optional[str] = None
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.browser_path = browser_path or os.environ.get('CHROMIUM_PATH')
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.auto_mode = auto_mode
        self.all_series = all_series
        self.target_url = target_url

    async def setup(self):
        """Initialize Playwright and launch browser."""
        self.playwright = await async_playwright().start()

        # Prepare launch options
        launch_options = {
            'headless': False,
            'args': ['--start-maximized']
        }

        # Use custom browser path if provided
        if self.browser_path:
            launch_options['executable_path'] = self.browser_path
            print(f"Using Chromium at: {self.browser_path}")

        # Launch browser with visible UI so user can log in
        self.browser = await self.playwright.chromium.launch(**launch_options)

        self.context = await self.browser.new_context(
            viewport=None,
            accept_downloads=True
        )

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
        await self.page.wait_for_selector('table', timeout=10000)

        # Find all "View Summary" buttons
        view_buttons = await self.page.query_selector_all('button:has-text("View Summary")')

        if not view_buttons:
            print("❌ No meetings found on this page")
            return

        print(f"\n✅ Found {len(view_buttons)} meetings")

        # Process each meeting
        for idx, button in enumerate(view_buttons, 1):
            try:
                # Get the meeting row to extract date and title
                row = await button.evaluate_handle('btn => btn.closest("tr")')
                cells = await row.query_selector_all('td')

                # Extract meeting info from table cells
                meeting_date = await cells[0].text_content() if len(cells) > 0 else "unknown_date"
                meeting_title = await cells[1].text_content() if len(cells) > 1 else f"meeting_{idx}"

                meeting_date = self.sanitize_filename(meeting_date.strip())
                meeting_title = self.sanitize_filename(meeting_title.strip())

                filename = f"{meeting_date}_{meeting_title}.txt"
                filepath = series_folder / filename

                # Skip if already exists
                if filepath.exists():
                    print(f"⏭️  [{idx}/{len(view_buttons)}] Skipping (already exists): {filename}")
                    continue

                print(f"\n📥 [{idx}/{len(view_buttons)}] Downloading: {filename}")

                # Click to open meeting page
                await button.click()
                await self.page.wait_for_load_state('networkidle')

                # Download the transcript
                await self.download_transcript(filepath)

                # Go back to meetings list
                await self.page.go_back()
                await self.page.wait_for_load_state('networkidle')

                # Re-query buttons as DOM may have changed
                view_buttons = await self.page.query_selector_all('button:has-text("View Summary")')

            except Exception as e:
                print(f"❌ Error processing meeting {idx}: {e}")
                # Try to go back to the list
                try:
                    await self.page.go_back()
                    await self.page.wait_for_load_state('networkidle')
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
            # First, try to click on Transcript tab if it exists
            transcript_tab = await self.page.query_selector('button:has-text("Transcript"), a:has-text("Transcript")')
            if transcript_tab:
                await transcript_tab.click()
                await asyncio.sleep(1)

            # Look for the Download Transcript button
            download_button = await self.page.query_selector('button:has-text("Download Transcript")')

            if not download_button:
                print("⚠️  Download Transcript button not found")
                return

            # Set up download handler
            async with self.page.expect_download() as download_info:
                await download_button.click()

            download = await download_info.value

            # Save the file
            await download.save_as(filepath)
            print(f"✅ Saved: {filepath.name}")

        except Exception as e:
            print(f"❌ Error downloading transcript: {e}")

    async def get_all_meeting_series_urls(self) -> List[str]:
        """Get URLs for all meeting series from the Meeting Series page.

        Returns:
            List of meeting series URLs
        """
        print("\n📋 Fetching all meeting series...")

        # Navigate to Meeting Series page
        await self.page.goto('https://app.ambient.us/dashboard/meetingseries')
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        # Find all meeting series links
        series_urls = await self.page.evaluate('''() => {
            const links = document.querySelectorAll('a[href*="/meetingseries/"]');
            const urls = [];
            const seen = new Set();

            links.forEach(link => {
                const href = link.href;
                // Skip the main meetingseries page itself
                if (href.match(/\\/meetingseries\\/[^/]+$/)) {
                    if (!seen.has(href)) {
                        seen.add(href);
                        urls.push(href);
                    }
                }
            });

            return urls;
        }''')

        print(f"  Found {len(series_urls)} meeting series")
        return series_urls

    async def run_all_series(self):
        """Process all meeting series automatically.

        Iterates through all meeting series and scrapes transcripts from each.
        """
        try:
            await self.setup()

            # Get all meeting series URLs
            series_urls = await self.get_all_meeting_series_urls()

            if not series_urls:
                print("❌ No meeting series found")
                return

            print(f"\n📊 Will process {len(series_urls)} meeting series\n")

            for idx, url in enumerate(series_urls):
                print(f"\n{'='*60}")
                print(f"[{idx+1}/{len(series_urls)}] Processing: {url}")
                print('='*60)

                try:
                    await self.page.goto(url)
                    await self.page.wait_for_load_state('networkidle')
                    await asyncio.sleep(1)

                    await self.scrape_meeting_series()
                except Exception as e:
                    print(f"❌ Error processing series: {e}")
                    continue

            print("\n🎉 Finished processing all meeting series!")

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
        '--target-url',
        type=str,
        help='Navigate directly to this URL (requires --auto)'
    )

    args = parser.parse_args()

    scraper = AmbientScraper(
        download_dir=args.download_dir,
        browser_path=args.browser_path,
        auto_mode=args.auto,
        all_series=args.all_series,
        target_url=args.target_url
    )
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
