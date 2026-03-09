#!/usr/bin/env python3
"""
Ambient Transcripts Scraper

This script automates downloading transcripts from app.ambient.us.
It supports both Meeting Series and Project pages.

Usage:
    python scraper.py [--browser-path /path/to/chromium]

Environment Variables:
    CHROMIUM_PATH - Path to Chromium executable (DEPRECATED: use --browser-path)

The script will:
1. Launch a Chromium browser
2. Wait for you to log in and navigate to a meeting series or project page
3. Automatically detect the page type
4. Download all transcripts (skipping existing ones)
"""

import argparse
import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright, Page, Browser, BrowserContext, Error
)


class AmbientScraper:
    def __init__(self, download_dir: str = "./transcripts", browser_path: Optional[str] = None):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        # Use explicit argument for browser path, ignore environment variables
        self.browser_path = browser_path
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # Auth state file to persist login session
        self.auth_state_file = self.download_dir / "auth_state.json"
        # Cache of meetings known to have no transcript content
        self.no_transcript_cache_file = self.download_dir / ".no_transcript_cache.json"
        self.no_transcript_cache: Set[str] = self._load_no_transcript_cache()

    def _load_no_transcript_cache(self) -> Set[str]:
        """Load the set of meeting keys known to have no transcript."""
        if self.no_transcript_cache_file.exists():
            try:
                data = json.loads(self.no_transcript_cache_file.read_text())
                return set(data)
            except (json.JSONDecodeError, TypeError):
                return set()
        return set()

    def _save_no_transcript_cache(self):
        """Persist the no-transcript cache to disk."""
        self.no_transcript_cache_file.write_text(
            json.dumps(sorted(self.no_transcript_cache), indent=2)
        )

    def _make_cache_key(self, title: str, date: str) -> str:
        """Create a stable cache key from meeting title and date."""
        return f"{title.strip()}|{date.strip()}"

    def _is_transcript_empty(self, filepath: Path) -> bool:
        """Check if a downloaded transcript file has no real content."""
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore').strip()
            # Empty, or just whitespace/newlines, or under 20 chars (e.g. just a header)
            return len(content) < 20
        except Exception:
            return True

    async def setup(self):
        """Initialize Playwright and launch browser."""
        self.playwright = await async_playwright().start()

        # Base launch args
        base_args = ['--disable-blink-features=AutomationControlled']

        # Strategy:
        # 1) If browser_path is provided, use it.
        # 2) Else try bundled Chromium.
        # 3) If that fails (e.g., macOS Sequoia incompatibility), fall back to Chrome channel.
        async def _try_launch_variant(variant: str):
            if variant == "custom_path" and self.browser_path:
                print(f"Using custom Chromium at: {self.browser_path}")
                return await self.playwright.chromium.launch(
                    headless=False,
                    executable_path=self.browser_path,
                    args=base_args,
                )
            if variant == "bundled":
                print("Trying Playwright's bundled Chromium...")
                return await self.playwright.chromium.launch(
                    headless=False,
                    args=base_args,
                )
            if variant == "chrome_channel":
                print("Falling back to Chrome channel...")
                # Requires: python3 -m playwright install chrome
                return await self.playwright.chromium.launch(
                    headless=False,
                    channel="chrome",
                    args=base_args,
                )
            raise RuntimeError("Unknown launch variant")

        launch_order = (["custom_path"] if self.browser_path else []) + ["bundled", "chrome_channel"]
        last_err = None
        for v in launch_order:
            try:
                self.browser = await _try_launch_variant(v)
                print(f"✓ Successfully launched browser using '{v}'")
                break
            except Exception as e:
                last_err = e
                print(f"✗ Launch attempt '{v}' failed: {e.__class__.__name__}: {e}")
                continue

        if not self.browser:
            raise RuntimeError(f"Could not launch any browser variant. Last error: {last_err}")

        # Check if we have saved authentication state
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'accept_downloads': True
        }

        if self.auth_state_file.exists():
            print(f"✓ Found saved login session, loading...")
            context_options['storage_state'] = str(self.auth_state_file)
        else:
            print("ℹ️  No saved login session found, you'll need to log in")

        self.context = await self.browser.new_context(**context_options)

        self.page = await self.context.new_page()

    async def wait_for_navigation(self):
        """Wait for user to log in and navigate to target page."""
        # Only show instructions if we don't have saved auth
        if not self.auth_state_file.exists():
            print("\n" + "="*60)
            print("INSTRUCTIONS:")
            print("="*60)
            print("1. Log in to your Ambient account")
            print("2. You can either:")
            print("   a) Stay on the dashboard to scrape ALL your meetings")
            print("   b) Navigate to a Meeting Series page to scrape just that series")
            print("   c) Navigate to a Project page to scrape just that project")
            print("3. Press ENTER here to continue")
            print("="*60 + "\n")
        else:
            print("\n" + "="*60)
            print("INSTRUCTIONS:")
            print("="*60)
            print("You can either:")
            print("   a) Press ENTER now to scrape ALL your meetings from the dashboard")
            print("   b) Navigate to a specific Meeting Series or Project, then press ENTER")
            print("="*60 + "\n")

        await self.page.goto('https://app.ambient.us/')

        # Non-blocking input inside async function
        await asyncio.to_thread(input, "Press ENTER when you're ready to start scraping...")

        # Save authentication state for future runs
        if not self.auth_state_file.exists():
            await self.context.storage_state(path=str(self.auth_state_file))
            print(f"✓ Saved login session to {self.auth_state_file.name}")
            print("  (You won't need to log in next time!)")

        # Give the page a moment in case ENTER was pressed immediately after navigation
        try:
            await self.page.wait_for_function(
                """() => location.href.includes('/meetingseries/') || location.href.includes('/projects/')""",
                timeout=2000
            )
        except Exception:
            pass

        # Get current URL to determine page type
        current_url = self.page.url
        return self.detect_page_type(current_url)

    def detect_page_type(self, url: str) -> str:
        """Detect whether we're on a meeting series, project, or dashboard/feed page."""
        if '/meetingseries/' in url:
            return 'meetingseries'
        elif '/projects/' in url:
            return 'project'
        elif '/dashboard' in url:
            # Dashboard home, feed, or My Meetings page — scrape all meetings
            return 'my_meetings'
        else:
            raise ValueError(f"Unknown page type. URL must be an Ambient dashboard page.\nCurrent URL: {url}")

    def sanitize_filename(self, name: str) -> str:
        """Remove invalid characters from filename."""
        # Replace invalid characters with underscore
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing spaces and dots
        name = name.strip('. ')
        # Collapse multiple spaces
        name = re.sub(r'\s+', ' ', name)
        return name

    async def scroll_until_stable(self, max_scrolls: int = 20, wait_seconds: float = 1.0):
        """Scroll to bottom repeatedly until no new content loads.

        Useful for pages with infinite scroll / lazy-loaded content.
        """
        previous_height = 0
        for i in range(max_scrolls):
            current_height = await self.page.evaluate('document.body.scrollHeight')
            if current_height == previous_height and i > 0:
                # No new content appeared after last scroll
                break
            previous_height = current_height
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(wait_seconds)
        return previous_height

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

        print(f"Saving to: {series_folder}")

        # Scroll to load all meetings (handles infinite scroll / lazy loading)
        await self.scroll_until_stable(max_scrolls=20)

        # Wait for the meetings table to load
        print("\n🔍 Looking for Meetings table...")
        try:
            await self.page.wait_for_selector('table', timeout=10000)
            print("  ✓ Table found")
        except Exception as e:
            print(f"  ✗ No table found: {e}")
            return

        # Try multiple selectors for the View Summary buttons
        view_buttons = []
        button_selectors = [
            'button:has-text("View Summary")',
            'button:text("View Summary")',
            'button:text-is("View Summary")',
            'button[aria-label*="View"]',
            'a:has-text("View Summary")',
        ]

        for selector in button_selectors:
            try:
                buttons = await self.page.query_selector_all(selector)
                if len(buttons) > 0:
                    print(f"  ✓ Found {len(buttons)} buttons with selector: {selector}")
                    view_buttons = buttons
                    break
            except:
                continue

        if not view_buttons:
            print("❌ No meetings found on this page")
            print("💡 Tip: Make sure you're on a meeting series page with meetings listed")
            return

        print(f"\n✅ Found {len(view_buttons)} meetings")
        total_meetings = len(view_buttons)

        # Process each meeting *by index* to avoid stale elements
        for idx in range(total_meetings):
            try:
                # Scroll back to meetings section
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.5)

                # Re-query the buttons *inside* the loop to get a fresh list
                view_buttons_fresh = []
                for selector in button_selectors:
                    try:
                        buttons = await self.page.query_selector_all(selector)
                        if len(buttons) > 0:
                            view_buttons_fresh = buttons
                            break
                    except:
                        continue

                if idx >= len(view_buttons_fresh):
                    print(f"❌ Error: Button list changed, could not find meeting at index {idx+1}")
                    break

                button = view_buttons_fresh[idx]

                # Get the meeting row to extract date and title
                row = await button.evaluate_handle('btn => btn.closest("tr")')
                cells = await row.query_selector_all('td')

                # Extract meeting info from table cells
                # Based on the screenshot: cells[0] = Date, cells[1] = Summary Title
                meeting_date = "unknown_date"
                meeting_title = f"meeting_{idx+1}"

                if len(cells) > 0:
                    date_text = await cells[0].text_content()
                    meeting_date = self.sanitize_filename(date_text.strip()) if date_text else "unknown_date"

                if len(cells) > 1:
                    title_text = await cells[1].text_content()
                    meeting_title = self.sanitize_filename(title_text.strip()) if title_text else f"meeting_{idx+1}"

                print(f"\n📥 [{idx+1}/{total_meetings}] Processing: {meeting_date} - {meeting_title}")

                # Click to open meeting page
                await button.click()
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(1)

                # Download the transcript
                downloaded_filepath = await self.download_transcript(series_folder)

                if not downloaded_filepath:
                    print(f"  ⚠️  Failed to download transcript")
                elif downloaded_filepath == "skipped":
                    print(f"  ⏭️  Skipping (already exists)")
                else:
                    print(f"  ✓ Downloaded successfully")

                # Go back to meetings list
                print(f"  ← Going back to meeting series page...")
                await self.page.go_back()
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"❌ Error processing meeting {idx+1}: {e}")
                import traceback
                traceback.print_exc()
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
        await asyncio.sleep(2)

        # Wait for Summaries section to load
        print("\n🔍 Looking for Summaries section...")

        # Take a debug screenshot to see what we're working with
        debug_initial = self.download_dir / "debug_project_before_click.png"
        await self.page.screenshot(path=str(debug_initial))
        print(f"  📸 Initial screenshot saved: {debug_initial.name}")

        # Strategy: Use JavaScript to find meeting cards in the Summaries section
        # Each card has a calendar icon (SVG) and should link to a meeting page

        summary_items = await self.page.evaluate('''() => {
            // Find the Summaries heading
            const headings = [...document.querySelectorAll('h2, h3')];
            const summariesHeading = headings.find(h => h.textContent.includes('Summaries'));

            let container;

            if (summariesHeading) {
                // Get the container that holds the summary cards
                // Usually it's a sibling or parent element
                container = summariesHeading.nextElementSibling;

                // If that doesn't work, try going up and finding a container
                if (!container || !container.querySelectorAll) {
                    container = summariesHeading.parentElement;
                }
            } else {
                // No Summaries heading - might be a feed-style page
                // Look for the main content area
                container = document.querySelector('main') || document.body;
            }

            // Find all clickable elements with calendar icons within this container
            const cards = [];

            // Strategy 1: Look for meeting cards with SVG + date pattern
            const clickableElements = container.querySelectorAll('[role="button"], div[class*="cursor"], a');

            clickableElements.forEach((el, idx) => {
                const text = el.textContent || '';
                const hasSVG = el.querySelector('svg') !== null;
                const hasDate = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(text) ||
                               /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d+,?\\s+\\d{4}/i.test(text);

                // Filter out navigation items
                const navTerms = ['my meetings', 'my emails', 'shared with', 'view all', 'latest', 'drafts', 'meeting series'];
                const isNav = navTerms.some(term => text.toLowerCase().includes(term));

                if (hasSVG && hasDate && !isNav && text.length > 10 && text.length < 300) {
                    el.setAttribute('data-summary-idx', idx);
                    cards.push({
                        index: idx,
                        text: text.substring(0, 100).replace(/\\n/g, ' ').trim()
                    });
                }
            });

            // Strategy 2: If no cards found, try looking for divs that contain meeting titles
            // These appear in feed-style pages as horizontal cards
            if (cards.length === 0) {
                const seenCards = new Set();
                const allDivs = container.querySelectorAll('div');

                allDivs.forEach((el, idx) => {
                    const text = el.textContent || '';
                    const hasSVG = el.querySelector('svg') !== null;

                    // Look for pattern: has calendar SVG and contains a date
                    const hasDate = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(text) ||
                                   /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d+,?\\s+\\d{4}/i.test(text);

                    // Check if it's clickable (might not have role="button")
                    const isClickable = el.onclick ||
                                       el.getAttribute('role') === 'button' ||
                                       window.getComputedStyle(el).cursor === 'pointer' ||
                                       el.tagName === 'A';

                    const navTerms = ['my meetings', 'my emails', 'shared with', 'view all', 'latest', 'drafts', 'meeting series', 'dashboard'];
                    const isNav = navTerms.some(term => text.toLowerCase().includes(term));

                    // Look for meeting-like content
                    if (hasSVG && hasDate && !isNav && text.length > 15 && text.length < 400 && isClickable) {
                        // IMPORTANT: Check if this element is a child of an already-found card
                        // This prevents counting title and date as separate meetings
                        let isChild = false;
                        for (const parentEl of seenCards) {
                            if (parentEl.contains(el)) {
                                isChild = true;
                                break;
                            }
                        }

                        // Also check if el contains any already-found cards (prefer parent)
                        let shouldReplace = false;
                        for (const childEl of seenCards) {
                            if (el.contains(childEl)) {
                                seenCards.delete(childEl);
                                shouldReplace = true;
                            }
                        }

                        if (!isChild || shouldReplace) {
                            seenCards.add(el);
                            el.setAttribute('data-summary-idx', 1000 + idx);
                            cards.push({
                                index: 1000 + idx,
                                text: text.substring(0, 100).replace(/\\n/g, ' ').trim()
                            });
                        }
                    }
                });
            }

            return { cards };
        }''')

        cards_info = summary_items.get('cards', [])

        if not cards_info:
            print("  ✗ No summary cards found with expected pattern (SVG icon + date)")
            print("\n❌ No meetings found in Summaries section")
            print("💡 Make sure you're on a project page with meetings listed")
            return

        print(f"\n✅ Found {len(cards_info)} summary cards:")
        for card in cards_info:
            print(f"  {card['index']}. {card['text'][:60]}...")

        # Now get the actual elements by their data attribute
        summary_items = []
        for card in cards_info:
            elem = await self.page.query_selector(f'[data-summary-idx="{card["index"]}"]')
            if elem:
                summary_items.append({'element': elem, 'text': card['text'], 'index': card['index']})

        if not summary_items:
            print("\n❌ Could not retrieve summary elements")
            return

        print(f"\n✅ Ready to process {len(summary_items)} meetings")

        # summary_items already contains {'element', 'text', 'index'} dictionaries
        # No need to extract again

        # Process each summary by clicking on it
        total_summaries = len(summary_items)
        for idx in range(total_summaries):
            try:
                # Scroll back to page bottom where summaries are
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(1)

                # Re-run the search JavaScript to get fresh elements
                fresh_items = await self.page.evaluate('''() => {
                    const headings = [...document.querySelectorAll('h2, h3')];
                    const summariesHeading = headings.find(h => h.textContent.includes('Summaries'));

                    let container;
                    if (summariesHeading) {
                        container = summariesHeading.nextElementSibling;
                        if (!container || !container.querySelectorAll) {
                            container = summariesHeading.parentElement;
                        }
                    } else {
                        container = document.querySelector('main') || document.body;
                    }

                    const cards = [];
                    const clickableElements = container.querySelectorAll('[role="button"], div[class*="cursor"], a');

                    clickableElements.forEach((el, idx) => {
                        const text = el.textContent || '';
                        const hasSVG = el.querySelector('svg') !== null;
                        const hasDate = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(text) ||
                                       /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d+,?\\s+\\d{4}/i.test(text);

                        const navTerms = ['my meetings', 'my emails', 'shared with', 'view all', 'latest', 'drafts', 'meeting series'];
                        const isNav = navTerms.some(term => text.toLowerCase().includes(term));

                        if (hasSVG && hasDate && !isNav && text.length > 10 && text.length < 300) {
                            el.setAttribute('data-summary-fresh-idx', idx);
                            cards.push({ index: idx, text: text.substring(0, 100).replace(/\\n/g, ' ').trim() });
                        }
                    });

                    if (cards.length === 0) {
                        const seenCards = new Set();
                        const allDivs = container.querySelectorAll('div');

                        allDivs.forEach((el, idx) => {
                            const text = el.textContent || '';
                            const hasSVG = el.querySelector('svg') !== null;
                            const hasDate = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(text) ||
                                           /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d+,?\\s+\\d{4}/i.test(text);
                            const isClickable = el.onclick || el.getAttribute('role') === 'button' ||
                                               window.getComputedStyle(el).cursor === 'pointer' || el.tagName === 'A';
                            const navTerms = ['my meetings', 'my emails', 'shared with', 'view all', 'latest', 'drafts', 'meeting series', 'dashboard'];
                            const isNav = navTerms.some(term => text.toLowerCase().includes(term));

                            if (hasSVG && hasDate && !isNav && text.length > 15 && text.length < 400 && isClickable) {
                                // Prevent counting title and date as separate meetings
                                let isChild = false;
                                for (const parentEl of seenCards) {
                                    if (parentEl.contains(el)) {
                                        isChild = true;
                                        break;
                                    }
                                }

                                let shouldReplace = false;
                                for (const childEl of seenCards) {
                                    if (el.contains(childEl)) {
                                        seenCards.delete(childEl);
                                        shouldReplace = true;
                                    }
                                }

                                if (!isChild || shouldReplace) {
                                    seenCards.add(el);
                                    el.setAttribute('data-summary-fresh-idx', 1000 + idx);
                                    cards.push({ index: 1000 + idx, text: text.substring(0, 100).replace(/\\n/g, ' ').trim() });
                                }
                            }
                        });
                    }

                    return { cards };
                }''')

                fresh_cards = fresh_items.get('cards', [])

                if idx >= len(fresh_cards):
                    print(f"❌ Could not find summary at index {idx+1}")
                    continue

                # Get the fresh card info
                card_info = fresh_cards[idx]
                summary_item = await self.page.query_selector(f'[data-summary-fresh-idx="{card_info["index"]}"]')

                if not summary_item:
                    print(f"❌ Could not find summary element at index {idx+1}")
                    continue

                summary_text = card_info['text'][:60].replace('\n', ' ')

                print(f"\n📥 [{idx+1}/{total_summaries}] Clicking on: {summary_text}...")

                # Click the summary item - this opens a modal/popup
                await summary_item.click()
                await asyncio.sleep(2)  # Wait for modal to open

                # Extract meeting title and date
                meeting_title = await self.get_page_title()

                print(f"📥 Downloading transcript...")

                # Download the transcript and get the actual filename
                downloaded_filepath = await self.download_transcript(project_folder)

                if not downloaded_filepath:
                    print(f"⚠️  Failed to download transcript")
                    await self.close_modal()
                    continue

                # Check if we already have this file
                if downloaded_filepath == "skipped":
                    print(f"⏭️  Skipping (already exists)")
                    await self.close_modal()
                    continue

                # Close the modal to return to project page
                print(f"  ← Closing modal...")
                await self.close_modal()

            except Exception as e:
                print(f"❌ Error processing summary {idx+1}: {e}")
                import traceback
                traceback.print_exc()
                # Try to close modal if it's open
                try:
                    await self.close_modal()
                except:
                    pass
                continue

        print(f"\n✅ Completed! Transcripts saved to: {project_folder}")

    async def close_modal(self):
        """Close a modal/popup by clicking the close button."""
        # Try multiple selectors for close buttons
        close_selectors = [
            'button:has-text("Close")',
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
            '[aria-label*="close" i]',
            'button.close',
            'button:has(svg):near(:text("Close"))',
            # Look for X button
            'button:has-text("×")',
            'button:has-text("✕")',
            # Generic close icon
            'button[class*="close" i]',
        ]

        for selector in close_selectors:
            try:
                close_button = await self.page.query_selector(selector)
                if close_button:
                    print(f"  ✓ Found close button with selector: {selector}")
                    await close_button.click()
                    await asyncio.sleep(1)
                    return
            except:
                continue

        # If no close button found, try pressing Escape key
        print("  ℹ️  No close button found, trying Escape key...")
        await self.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    def _get_all_existing_filenames(self) -> set:
        """Return a set of all transcript filenames across every subfolder.

        This lets us detect duplicates even if the same transcript was
        previously saved into a different series/project folder.
        """
        names = set()
        for path in self.download_dir.rglob('*.txt'):
            names.add(path.name)
        return names

    async def download_transcript(self, folder: Path):
        """Download transcript from an individual meeting page.

        Args:
            folder: The folder to save the transcript in

        Returns:
            Path to the downloaded file, None if failed, or "skipped" if already exists
        """
        try:
            # Wait for page to fully load
            await asyncio.sleep(2)

            # First, try to click on Transcript tab if it exists.
            # IMPORTANT: use exact text match — has-text("Transcript") also matches
            # "Download Transcript" and "Copy Transcript".
            print("  Looking for Transcript tab...")
            transcript_tab = None
            for selector in [
                'button:has-text("Transcript")',
                'a:has-text("Transcript")',
                '[role="tab"]:has-text("Transcript")',
            ]:
                try:
                    candidates = await self.page.query_selector_all(selector)
                    for cand in candidates:
                        text = (await cand.text_content() or '').strip()
                        if text == 'Transcript':
                            transcript_tab = cand
                            break
                    if transcript_tab:
                        break
                except:
                    continue

            if transcript_tab:
                await transcript_tab.click()
                await asyncio.sleep(1.5)
                print("  ✓ Clicked Transcript tab")
            else:
                print("  ℹ️  No Transcript tab found (might already be on transcript view)")

            # Look for the Download Transcript button - try multiple selectors
            print("  Looking for Download Transcript button...")
            download_button_selectors = [
                'button:has-text("Download Transcript")',
                'a:has-text("Download Transcript")',
                '[aria-label*="Download Transcript"]',
                'button:text("Download Transcript")',
            ]

            download_button = None
            for selector in download_button_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        download_button = button
                        print(f"  ✓ Found Download Transcript button with selector: {selector}")
                        break
                except:
                    continue

            if not download_button:
                print("⚠️  Download Transcript button not found")
                # Take a debug screenshot
                debug_path = folder / f"debug_no_button_{int(asyncio.get_event_loop().time())}.png"
                await self.page.screenshot(path=str(debug_path))
                print(f"  📸 Debug screenshot saved: {debug_path.name}")
                return None

            # Set up download handler (10s timeout — downloads are data: URLs, instant)
            async with self.page.expect_download(timeout=10000) as download_info:
                await download_button.click()

            download = await download_info.value

            # Get the suggested filename from the download
            suggested_filename = download.suggested_filename
            filepath = folder / suggested_filename

            # Check if file already exists in target folder
            if filepath.exists():
                print(f"  ⏭️  File already exists: {suggested_filename}")
                return "skipped"

            # Also check all other folders (same transcript may have been
            # saved under a different series previously)
            all_existing = self._get_all_existing_filenames()
            if suggested_filename in all_existing:
                print(f"  ⏭️  Already downloaded elsewhere: {suggested_filename}")
                return "skipped"

            # Save the file with original filename
            await download.save_as(filepath)

            # Check if the downloaded file is empty
            if self._is_transcript_empty(filepath):
                filepath.unlink()
                print(f"⏭️  Empty transcript — deleted: {suggested_filename}")
                return "skipped"

            print(f"✅ Saved: {suggested_filename}")

            return filepath

        except Exception as e:
            print(f"❌ Error downloading transcript: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def ensure_authenticated(self):
        """Check if we're logged in, and prompt for login if not.

        Detects login page redirects (expired auth) and handles re-authentication.
        """
        current_url = self.page.url
        page_text = await self.page.text_content('body') or ''

        # Detect login/signup page
        is_login_page = (
            'sign in' in page_text.lower()[:500]
            or 'sign up' in page_text.lower()[:500]
            or 'log in' in page_text.lower()[:500]
            or '/login' in current_url
            or '/signin' in current_url
            or '/signup' in current_url
            or ('continue with google' in page_text.lower()[:1000]
                and '/dashboard' not in current_url)
        )

        if is_login_page:
            print("\n⚠️  Auth session has expired — you need to log in again.")
            print("   Log in to Ambient in the browser window that just opened.")
            await asyncio.to_thread(
                input, "Press ENTER here after you've logged in and see the dashboard..."
            )

            # Save fresh auth state
            await self.context.storage_state(path=str(self.auth_state_file))
            print(f"✓ Saved new login session to {self.auth_state_file.name}")

            # After login, navigate to dashboard if we're not already there
            current_url = self.page.url
            if '/dashboard' not in current_url:
                await self.page.goto(
                    'https://app.ambient.us/dashboard', wait_until='networkidle'
                )
                await asyncio.sleep(2)

    async def discover_series(self) -> List[Dict[str, str]]:
        """Find all meeting series from the sidebar/navigation.

        Returns list of {"name": ..., "url": ...} dicts.
        """
        print("\nDiscovering meeting series from sidebar...")

        # Navigate to dashboard
        await self.page.goto('https://app.ambient.us/dashboard', wait_until='networkidle')
        await asyncio.sleep(3)

        # Verify we're logged in
        await self.ensure_authenticated()

        # Save auth state
        await self.context.storage_state(path=str(self.auth_state_file))

        # Find series links in sidebar
        series_links = await self.page.evaluate('''() => {
            const series = [];
            const seen = new Set();

            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                if (href.includes('/meetingseries/')) {
                    const normalized = href.split('?')[0].replace(/\\/$/, '');
                    if (!seen.has(normalized)) {
                        seen.add(normalized);
                        const name = (a.textContent || '').trim().replace(/\\s+/g, ' ').substring(0, 200);
                        series.push({name, url: normalized});
                    }
                }
            });

            return series;
        }''')

        # If no series found, try clicking "View All" in Meeting Series section
        if not series_links:
            for sel in ['a:has-text("View All")', 'a:has-text("View all")']:
                try:
                    view_all = await self.page.query_selector(sel)
                    if view_all:
                        await view_all.click()
                        await self.page.wait_for_load_state('networkidle')
                        await asyncio.sleep(2)

                        series_links = await self.page.evaluate('''() => {
                            const series = [];
                            const seen = new Set();
                            document.querySelectorAll('a[href*="/meetingseries/"]').forEach(a => {
                                const n = a.href.split('?')[0].replace(/\\/$/, '');
                                if (!seen.has(n)) {
                                    seen.add(n);
                                    series.push({
                                        name: (a.textContent||'').trim().substring(0,200),
                                        url: n
                                    });
                                }
                            });
                            return series;
                        }''')
                        break
                except Exception:
                    continue

        # Deduplicate
        unique = []
        seen = set()
        for s in series_links:
            if s['url'] not in seen:
                seen.add(s['url'])
                name = s['name'].strip() or s['url'].rstrip('/').split('/')[-1]
                unique.append({'name': name, 'url': s['url']})

        print(f"  Found {len(unique)} meeting series")
        for i, s in enumerate(unique, 1):
            print(f"    {i}. {s['name']}")

        return unique

    async def scrape_my_meetings(self, cutoff_days: Optional[int] = None):
        """Navigate to My Meetings page and scrape meetings with pagination.

        Extracts post IDs from the table via React fiber internals, then
        navigates directly to each /dashboard/post/{id} page to download
        the transcript.

        Args:
            cutoff_days: Only check meetings from the last N days. None = check all.
        """
        print("\n" + "=" * 60)
        if cutoff_days:
            cutoff_date = (datetime.now() - timedelta(days=cutoff_days)).strftime('%Y-%m-%d')
            print(f"SCRAPING MEETINGS FROM LAST {cutoff_days} DAYS (since {cutoff_date})")
        else:
            cutoff_date = None
            print("SCRAPING ALL MEETINGS FROM MY MEETINGS")
        print("=" * 60)

        # Navigate to My Meetings feed page
        try:
            await self.page.goto(
                'https://app.ambient.us/dashboard/post?a=myMeetings',
                wait_until='domcontentloaded', timeout=60000
            )
        except Exception:
            pass  # Page may not fully settle — that's ok
        await asyncio.sleep(5)
        await self.ensure_authenticated()
        await self.context.storage_state(path=str(self.auth_state_file))

        # Click "My Meetings" tab if it exists (shows count like "My Meetings 924")
        for sel in ['button:has-text("My Meetings")', '[role="tab"]:has-text("My Meetings")']:
            try:
                tabs = await self.page.query_selector_all(sel)
                for tab in tabs:
                    text = (await tab.text_content() or '').strip()
                    if 'my meetings' in text.lower() and len(text) < 40:
                        await tab.click()
                        await asyncio.sleep(2)
                        break
            except Exception:
                continue

        # Debug screenshot
        debug_path = self.download_dir / "debug_my_meetings.png"
        await self.page.screenshot(path=str(debug_path), full_page=True)
        print(f"  Screenshot: {debug_path}")

        existing = self._get_all_existing_filenames()
        print(f"Already have {len(existing)} transcript files on disk")

        downloaded = 0
        skipped = 0
        failed = 0
        total_found = 0
        page_num = 0
        reached_cutoff = False
        my_meetings_url = 'https://app.ambient.us/dashboard/post?a=myMeetings'

        while True:
            page_num += 1

            # Refresh existing files set each page (picks up newly downloaded ones)
            existing = self._get_all_existing_filenames()

            # Get pagination info for display
            pag_info = await self.page.evaluate(r'''() => {
                const text = document.body.innerText;
                const m = text.match(/(\d+)[-\u2013](\d+)\s+of\s+(\d+)/);
                return m ? { start: parseInt(m[1]), end: parseInt(m[2]), total: parseInt(m[3]) } : null;
            }''')
            if pag_info:
                print(f"\n--- Page {page_num} (items {pag_info['start']}-{pag_info['end']} of {pag_info['total']}) ---")
            else:
                print(f"\n--- Page {page_num} ---")

            # Extract post IDs and metadata from table rows via React fiber.
            meetings_on_page = await self.page.evaluate(r'''() => {
                const rows = document.querySelectorAll('tr');
                const meetings = [];

                for (const row of rows) {
                    const text = (row.textContent || '').trim();
                    if (text.length < 20) continue;

                    // Extract post ID from React fiber tree
                    const keys = Object.keys(row);
                    const fiberKey = keys.find(k => k.startsWith('__reactFiber'));
                    if (!fiberKey) continue;

                    let fiber = row[fiberKey];
                    let postId = null;

                    let current = fiber;
                    let depth = 0;
                    while (current && depth < 25) {
                        const props = current.memoizedProps || current.pendingProps || {};
                        for (const key of ['id', 'postId', 'meetingId']) {
                            if (props[key] && typeof props[key] === 'string' && props[key].includes('-')) {
                                postId = props[key];
                                break;
                            }
                        }
                        if (!postId && props.post && props.post.id) postId = props.post.id;
                        if (!postId && props.row && props.row.id) postId = props.row.id;
                        if (!postId && props.item && props.item.id) postId = props.item.id;
                        if (postId) break;
                        current = current.return;
                        depth++;
                    }

                    if (!postId) continue;

                    // Extract title and date from the row cells
                    const tds = row.querySelectorAll('td');
                    let title = '';
                    let dateStr = '';

                    // td[1] = title cell (td[0] is checkbox)
                    if (tds.length > 1) {
                        const titleP = tds[1].querySelector('.post-table-title-link, p');
                        if (titleP) title = (titleP.textContent || '').trim();
                    }

                    // td[2] = date cell — format "3/9/2026, 3:47PM"
                    if (tds.length > 2) {
                        const dateText = (tds[2].textContent || '').trim().replace(/\s+/g, ' ');
                        const m = dateText.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
                        if (m) {
                            dateStr = m[3] + '-' + m[1].padStart(2, '0') + '-' + m[2].padStart(2, '0');
                        }
                    }

                    meetings.push({ postId, title, date: dateStr });
                }

                return meetings;
            }''')

            print(f"  Found {len(meetings_on_page)} meeting items on this page")

            if not meetings_on_page:
                print("  No meetings found — stopping")
                await self.page.screenshot(path=str(self.download_dir / f"debug_no_meetings_page{page_num}.png"), full_page=True)
                break

            total_found += len(meetings_on_page)

            # Visit each meeting's post page to download transcript
            for card_idx, meeting in enumerate(meetings_on_page):
                post_id = meeting['postId']
                card_title = meeting.get('title', '')
                card_date = meeting.get('date', '')
                label = f"{card_title[:50]} ({card_date})" if card_title else post_id
                print(f"  [{card_idx + 1}/{len(meetings_on_page)}] {label}")

                # Stop early if this meeting is older than the cutoff
                if cutoff_date and card_date and card_date < cutoff_date:
                    print(f"  \u23f9\ufe0f  Reached cutoff date ({cutoff_date}) — stopping")
                    reached_cutoff = True
                    break

                if card_title and card_date:
                    # Check no-transcript cache first
                    cache_key = self._make_cache_key(card_title, card_date)
                    if cache_key in self.no_transcript_cache:
                        print(f"    \u23ed\ufe0f  No transcript (cached): {card_title} ({card_date})")
                        skipped += 1
                        continue

                    # Check if we already have this transcript on disk
                    safe_title = re.sub(r'[<>:"/\\|?*]', '_', card_title).strip()
                    prefix = f"{safe_title} {card_date}"
                    match_found = any(f.startswith(prefix) for f in existing)
                    if match_found:
                        print(f"    \u23ed\ufe0f  Already have transcript for: {safe_title} ({card_date})")
                        skipped += 1
                        continue

                try:
                    # Navigate to the individual post page
                    post_url = f'https://app.ambient.us/dashboard/post/{post_id}'
                    await self.page.goto(post_url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)

                    # Use the existing download_transcript method which handles
                    # clicking the Transcript tab and Download Transcript button
                    # Determine folder for saving
                    card_folder = self.download_dir / "Individual Meetings"
                    if card_title:
                        # Check if title matches an existing subfolder name
                        matched = None
                        for d in self.download_dir.iterdir():
                            if not d.is_dir():
                                continue
                            dn = d.name.lower().replace('_', ' ').replace('  ', ' ')
                            ct = card_title.lower().replace('_', ' ').replace('  ', ' ')
                            if ct == dn or ct.startswith(dn) or dn.startswith(ct):
                                matched = d.name
                                break
                        if matched:
                            card_folder = self.download_dir / matched
                    card_folder.mkdir(exist_ok=True)

                    result = await self.download_transcript(card_folder)

                    if result is None:
                        print(f"    \u26a0\ufe0f  No transcript available")
                        if card_title and card_date:
                            self.no_transcript_cache.add(self._make_cache_key(card_title, card_date))
                            self._save_no_transcript_cache()
                        failed += 1
                    elif result == "skipped":
                        skipped += 1
                    else:
                        existing.add(result.name if hasattr(result, 'name') else str(result))
                        downloaded += 1

                except Exception as e:
                    print(f"    \u274c Error: {e}")
                    failed += 1

                finally:
                    # Navigate back to My Meetings list
                    try:
                        await self.page.goto(my_meetings_url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)
                        # Re-click My Meetings tab if needed
                        for sel in ['button:has-text("My Meetings")', '[role="tab"]:has-text("My Meetings")']:
                            try:
                                tabs = await self.page.query_selector_all(sel)
                                for tab in tabs:
                                    text = (await tab.text_content() or '').strip()
                                    if 'my meetings' in text.lower() and len(text) < 40:
                                        await tab.click()
                                        await asyncio.sleep(1)
                                        break
                            except Exception:
                                continue
                    except Exception:
                        pass

            # Stop if we hit the date cutoff
            if reached_cutoff:
                break

            # Try next page
            has_next = await self._go_to_next_page()
            if not has_next:
                print(f"\n  No more pages after page {page_num}")
                break

        print(f"\nMy Meetings complete:")
        print(f"  Total found: {total_found}")
        print(f"  Downloaded:  {downloaded}")
        print(f"  Skipped:     {skipped}")
        print(f"  Failed:      {failed}")

        return {
            'total_found': total_found,
            'downloaded': downloaded,
            'skipped': skipped,
            'failed': failed,
        }

    async def _mark_meeting_cards(self) -> int:
        """Mark meeting items with data-scraper-index attributes. Returns count."""
        return await self.page.evaluate(r'''() => {
            const datePattern = /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}/;
            let cards = [];

            // Try MUI Cards first
            let muiCards = Array.from(document.querySelectorAll('.MuiCard-root, [class*="MuiCard"]'));
            muiCards = muiCards.filter(el => datePattern.test(el.textContent || '') && (el.textContent || '').length < 500);
            muiCards = muiCards.filter(el => {
                const nested = el.querySelectorAll('.MuiCard-root, [class*="MuiCard"]');
                return !Array.from(nested).some(n => n !== el && datePattern.test(n.textContent || ''));
            });

            if (muiCards.length > 0) {
                cards = muiCards;
            } else {
                // Try table rows
                const rows = Array.from(document.querySelectorAll('tr, [role="row"]'));
                cards = rows.filter(el => datePattern.test(el.textContent || '') && (el.textContent || '').length < 800);
            }

            cards.forEach((card, i) => card.setAttribute('data-scraper-index', String(i)));
            return cards.length;
        }''')

    async def _go_to_next_page(self) -> bool:
        """Try to navigate to the next page of results. Returns True if successful."""

        # First try: find the ">" forward arrow button near pagination text like "1-25 of 850"
        # This is what Ambient uses (MUI TablePagination)
        next_btn = await self.page.evaluate('''() => {
            // Look for pagination container — text like "X-Y of Z" or "X of Y"
            const allText = document.body.innerText;
            const paginationMatch = allText.match(/(\\d+)[-–](\\d+)\\s+of\\s+(\\d+)/);

            if (paginationMatch) {
                const current = parseInt(paginationMatch[2]);
                const total = parseInt(paginationMatch[3]);
                if (current >= total) return { found: false, reason: 'last_page', debug: `${current}/${total}` };
            }

            // Priority 1: MUI pagination — look for aria-label "Go to next page"
            const muiNext = document.querySelector('button[aria-label="Go to next page"]');
            if (muiNext) {
                if (muiNext.disabled || muiNext.getAttribute('aria-disabled') === 'true') {
                    return { found: false, reason: 'disabled', debug: 'mui_next_disabled' };
                }
                muiNext.click();
                return { found: true, reason: 'mui_next' };
            }

            // Priority 2: Find buttons/links with ">" or "›" or "next" labels
            const candidates = document.querySelectorAll('button, a, [role="button"]');
            for (const el of candidates) {
                const text = (el.textContent || '').trim();
                const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                const title = (el.getAttribute('title') || '').toLowerCase();

                // Match ">" arrow, "›" arrow, or "next" labels
                const isNext = (
                    text === '>' || text === '›' || text === '→' || text === '»' ||
                    text.toLowerCase() === 'next' ||
                    ariaLabel.includes('next') || ariaLabel.includes('forward') ||
                    title.includes('next') || title.includes('forward')
                );

                if (!isNext) continue;

                // Check not disabled
                if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
                    return { found: false, reason: 'disabled', debug: ariaLabel || text };
                }
                if ((el.className || '').includes('disabled')) {
                    return { found: false, reason: 'disabled_class', debug: ariaLabel || text };
                }

                // Found it — click it
                el.click();
                return { found: true, reason: 'clicked' };
            }

            // Priority 3: find an SVG chevron-right inside a button (no position restriction)
            const svgButtons = document.querySelectorAll('button:not([disabled]), [role="button"]:not([aria-disabled="true"])');
            for (const btn of svgButtons) {
                const svg = btn.querySelector('svg');
                if (!svg) continue;
                const path = svg.querySelector('path');
                if (!path) continue;
                // Check if this button has a sibling that looks like "<" (prev button)
                const sibling = btn.previousElementSibling;
                if (sibling && (sibling.tagName === 'BUTTON' || sibling.getAttribute('role') === 'button')) {
                    btn.click();
                    return { found: true, reason: 'svg_chevron' };
                }
            }

            return { found: false, reason: 'not_found', debug: 'no_matching_button' };
        }''')

        if next_btn and next_btn.get('found'):
            # Don't use networkidle — SPA may keep connections open. Just wait for content.
            await asyncio.sleep(3)
            print(f"    (pagination: {next_btn.get('reason')})")
            return True

        if next_btn:
            reason = next_btn.get('reason', 'unknown')
            debug = next_btn.get('debug', '')
            if reason in ('last_page', 'disabled', 'disabled_class'):
                print(f"    (pagination: reached end — {reason} {debug})")
                return False
            print(f"    (pagination: JS search failed — {reason} {debug})")

        # Fallback: try standard selectors
        for sel in [
            'button[aria-label*="next" i]',
            'a[aria-label*="next" i]',
            '[class*="pagination"] button:last-of-type',
        ]:
            try:
                btn = await self.page.query_selector(sel)
                if btn:
                    is_disabled = await btn.get_attribute('disabled')
                    if is_disabled is not None:
                        continue
                    await btn.click()
                    await asyncio.sleep(3)
                    return True
            except Exception:
                continue

        # Last resort: try scrolling (infinite scroll)
        before_height = await self.page.evaluate('document.body.scrollHeight')
        await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)
        after_height = await self.page.evaluate('document.body.scrollHeight')

        return after_height > before_height

    async def scrape_all(self, cutoff_days: Optional[int] = None):
        """Scrape meetings from the My Meetings page."""

        results = await self.scrape_my_meetings(cutoff_days=cutoff_days)

        # ---- Summary ----
        print("\n" + "=" * 60)
        print("SCRAPE ALL COMPLETE")
        print("=" * 60)

        total = results.get('total_found', 0)
        print(f"\n  My Meetings:")
        print(f"    Total found:     {total}")
        print(f"    Downloaded:      {results.get('downloaded', 0)}")
        print(f"    Skipped:         {results.get('skipped', 0)}")
        print(f"    No transcript:   {results.get('failed', 0)}")

        print(f"\n  Transcripts saved to: {self.download_dir}")

    async def run(self, mode: str = 'interactive', url: Optional[str] = None, cutoff_days: Optional[int] = None):
        """Main execution flow.

        Args:
            mode: 'interactive' (default), 'auto' (scrape url without prompts),
                  or 'auto_all' (discover and scrape everything)
            url: URL to scrape (required for 'auto' mode)
            cutoff_days: Only check meetings from the last N days. None = all.
        """
        try:
            await self.setup()

            if mode == 'auto_all':
                # discover_all_series handles auth check internally
                await self.scrape_all(cutoff_days=cutoff_days)

            elif mode == 'auto':
                if not url:
                    raise ValueError("--auto requires --url to be specified")

                # Navigate to target URL; check auth
                page_type = self.detect_page_type(url)
                await self.page.goto(url, wait_until='networkidle')
                await asyncio.sleep(2)
                await self.ensure_authenticated()

                # Re-navigate in case ensure_authenticated redirected us
                if '/meetingseries/' not in self.page.url and '/projects/' not in self.page.url:
                    await self.page.goto(url, wait_until='networkidle')
                    await asyncio.sleep(2)

                await self.scroll_until_stable(max_scrolls=20)

                if page_type == 'meetingseries':
                    await self.scrape_meeting_series()
                elif page_type == 'project':
                    await self.scrape_project()
                elif page_type == 'my_meetings':
                    await self.scrape_my_meetings(cutoff_days=cutoff_days)

            else:
                # Existing interactive flow
                page_type = await self.wait_for_navigation()

                if page_type == 'meetingseries':
                    await self.scrape_meeting_series()
                elif page_type == 'project':
                    await self.scrape_project()
                elif page_type == 'my_meetings':
                    await self.scrape_my_meetings(cutoff_days=cutoff_days)

            print("\nAll done!")
            if mode == 'interactive':
                print("\nPress ENTER to close the browser...")
                await asyncio.to_thread(input)

        except Exception as e:
            print(f"\nError: {e}")
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
        help='Path to Chromium executable (e.g., /usr/bin/chromium)'
    )
    parser.add_argument(
        '--download-dir',
        type=str,
        default='./transcripts',
        help='Directory to save transcripts (default: ./transcripts)'
    )
    parser.add_argument(
        '--auto-all',
        action='store_true',
        help='Discover all meeting series and scrape everything automatically'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Skip interactive prompts (use saved auth). Requires a URL with --url.'
    )
    parser.add_argument(
        '--url',
        type=str,
        help='URL of a specific meeting series or project to scrape (used with --auto)'
    )
    parser.add_argument(
        '--clear-session',
        action='store_true',
        help='Clear saved login session and log in again'
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear the no-transcript cache (re-check meetings previously marked as having no transcript)'
    )
    parser.add_argument(
        '--cutoff-days',
        type=int,
        default=None,
        help='Only scrape meetings from the last N days (default: all)'
    )

    args = parser.parse_args()

    scraper = AmbientScraper(
        download_dir=args.download_dir,
        browser_path=args.browser_path
    )

    # Clear session if requested
    if args.clear_session and scraper.auth_state_file.exists():
        scraper.auth_state_file.unlink()
        print("Cleared saved login session")

    # Clear no-transcript cache if requested
    if args.clear_cache and scraper.no_transcript_cache_file.exists():
        scraper.no_transcript_cache_file.unlink()
        scraper.no_transcript_cache = set()
        print("Cleared no-transcript cache")

    # Determine run mode
    if args.auto_all:
        mode = 'auto_all'
    elif args.auto:
        mode = 'auto'
    else:
        mode = 'interactive'

    await scraper.run(mode=mode, url=args.url, cutoff_days=args.cutoff_days)


if __name__ == "__main__":
    asyncio.run(main())
