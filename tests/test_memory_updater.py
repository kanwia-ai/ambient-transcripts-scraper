# tests/test_memory_updater.py
import pytest
from src.memory_updater import MemoryUpdater


def test_memory_updater_builds_observation():
    updater = MemoryUpdater()

    processed_data = {
        "meeting_title": "Asurion Weekly",
        "date": "2025-09-22",
        "main_topics": ["PRD automation", "HR pilot"],
        "key_context": ["Moving to pilot phase"],
        "implied_work": ["Prep documentation"]
    }

    observation = updater.build_observation(processed_data)

    assert "2025-09-22" in observation
    assert "PRD automation" in observation
    assert "pilot phase" in observation


def test_memory_updater_formats_entity_name():
    updater = MemoryUpdater()

    assert updater.format_entity_name("Asurion") == "Asurion"
    assert updater.format_entity_name("AIT_Internal") == "AIT_Internal"
    assert updater.format_entity_name("Some Client Name") == "Some_Client_Name"
