# tests/test_scraper_auto.py
import pytest
from scraper import AmbientScraper


def test_scraper_has_auto_mode_flag():
    """Scraper should accept auto_mode parameter."""
    scraper = AmbientScraper(
        download_dir="/tmp/test_transcripts",
        auto_mode=True
    )
    assert scraper.auto_mode is True


def test_scraper_auto_mode_defaults_to_false():
    """Scraper auto_mode should default to False."""
    scraper = AmbientScraper(download_dir="/tmp/test_transcripts")
    assert scraper.auto_mode is False


def test_scraper_has_all_series_flag():
    """Scraper should accept all_series parameter."""
    scraper = AmbientScraper(
        download_dir="/tmp/test_transcripts",
        all_series=True
    )
    assert scraper.all_series is True


def test_scraper_all_series_defaults_to_false():
    """Scraper all_series should default to False."""
    scraper = AmbientScraper(download_dir="/tmp/test_transcripts")
    assert scraper.all_series is False


def test_scraper_has_target_url_param():
    """Scraper should accept target_url parameter."""
    scraper = AmbientScraper(
        download_dir="/tmp/test_transcripts",
        target_url="https://app.ambient.us/dashboard/meetingseries/123"
    )
    assert scraper.target_url == "https://app.ambient.us/dashboard/meetingseries/123"


def test_scraper_target_url_defaults_to_none():
    """Scraper target_url should default to None."""
    scraper = AmbientScraper(download_dir="/tmp/test_transcripts")
    assert scraper.target_url is None


def test_scraper_has_get_all_meeting_series_method():
    """Scraper should have get_all_meeting_series_urls method."""
    scraper = AmbientScraper(download_dir="/tmp/test_transcripts")
    assert hasattr(scraper, 'get_all_meeting_series_urls')
    assert callable(scraper.get_all_meeting_series_urls)


def test_scraper_has_run_all_series_method():
    """Scraper should have run_all_series method."""
    scraper = AmbientScraper(download_dir="/tmp/test_transcripts")
    assert hasattr(scraper, 'run_all_series')
    assert callable(scraper.run_all_series)
