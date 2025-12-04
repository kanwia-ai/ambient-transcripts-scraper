# tests/test_client_mapper.py
import pytest
from pathlib import Path
from src.client_mapper import ClientMapper


def test_client_mapper_from_meeting_series():
    mapper = ClientMapper()

    assert mapper.get_client("Ambient_ Project") == "Asurion"
    assert mapper.get_client("AIT Consulting Weekly") == "AIT_Internal"
    assert mapper.get_client("All Hands") == "Section_Internal"
    assert mapper.get_client("Weekly Proposal Review") == "Section_Internal"


def test_client_mapper_from_filename():
    mapper = ClientMapper()

    # Extract from filename pattern
    client = mapper.get_client_from_filename(
        "Asurion x Section 2025-09-22 12_31 transcript.txt"
    )
    assert client == "Asurion"


def test_client_mapper_unknown_defaults():
    mapper = ClientMapper()

    assert mapper.get_client("Unknown Meeting Series") == "Other"
