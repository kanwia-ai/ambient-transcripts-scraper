# tests/test_automation.py
import pytest
from pathlib import Path


def test_launchd_plist_exists():
    """Launchd plist template should exist."""
    plist_path = Path(__file__).parent.parent / "automation" / "com.user.transcript-sync.plist"
    assert plist_path.exists(), f"Plist not found at {plist_path}"


def test_launchd_plist_has_required_keys():
    """Plist should contain required keys."""
    plist_path = Path(__file__).parent.parent / "automation" / "com.user.transcript-sync.plist"
    content = plist_path.read_text()

    required_keys = [
        "<key>Label</key>",
        "<key>ProgramArguments</key>",
        "<key>StartCalendarInterval</key>",
        "<key>WorkingDirectory</key>",
    ]

    for key in required_keys:
        assert key in content, f"Missing key: {key}"


def test_launchd_plist_runs_at_8am():
    """Plist should be configured to run at 8 AM."""
    plist_path = Path(__file__).parent.parent / "automation" / "com.user.transcript-sync.plist"
    content = plist_path.read_text()

    assert "<key>Hour</key>" in content
    assert "<integer>8</integer>" in content


def test_install_script_exists():
    """Install script should exist and be executable."""
    install_path = Path(__file__).parent.parent / "automation" / "install.sh"
    assert install_path.exists(), f"Install script not found at {install_path}"


def test_install_script_is_executable():
    """Install script should be executable."""
    import os
    install_path = Path(__file__).parent.parent / "automation" / "install.sh"
    assert os.access(install_path, os.X_OK), "Install script is not executable"
