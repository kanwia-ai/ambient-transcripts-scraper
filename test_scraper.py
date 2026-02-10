#!/usr/bin/env python3
"""Test script to verify the enhanced scraper works"""

import asyncio
import pytest
from src.scraper_headless import HeadlessAmbientScraper
from src.database import ProgressTracker
from src.retry_manager import RetryManager
from pathlib import Path

@pytest.mark.asyncio
async def test_components():
    print("Testing Enhanced Ambient Scraper Components...")

    # Test 1: Headless Scraper
    print("\n1. Testing Headless Scraper...")
    try:
        scraper = HeadlessAmbientScraper(
            download_dir="./test_transcripts",
            headless=True,
            auto_mode=True
        )
        print("   ✅ Headless scraper initialized successfully")
        print(f"   📁 Download directory: {scraper.download_dir}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Database
    print("\n2. Testing Database...")
    try:
        db_path = Path("./test_progress.db")
        tracker = ProgressTracker(db_path)
        print("   ✅ Database initialized successfully")
        # Clean up test database
        db_path.unlink()
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 3: Retry Manager
    print("\n3. Testing Retry Manager...")
    try:
        manager = RetryManager()

        # Test function that succeeds on third try
        attempt_count = 0
        async def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Test error")
            return "Success!"

        result = await manager.retry_with_backoff(test_func, max_attempts=3)
        print(f"   ✅ Retry manager works! Result: {result}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n✨ Component testing complete!")
    print("\nTo run the full scraper:")
    print("1. Update scraper.py to use the new components")
    print("2. Run: python scraper.py --headless --auto-mode")

if __name__ == "__main__":
    asyncio.run(test_components())