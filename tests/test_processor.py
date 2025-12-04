# tests/test_processor.py
import pytest
from unittest.mock import Mock, patch
from src.processor import TranscriptProcessor


def test_processor_extracts_structured_data():
    # Mock the Anthropic client
    mock_response = Mock()
    mock_response.content = [Mock(text='''{
        "meeting_title": "Asurion Weekly Sync",
        "date": "2025-09-22",
        "project_client": "Asurion",
        "attendees": ["Scott", "Kyra"],
        "main_topics": ["PRD automation status"],
        "key_context": ["PRD moving to pilot phase"],
        "implied_work": ["Prep pilot documentation"]
    }''')]

    with patch('src.processor.Anthropic') as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        processor = TranscriptProcessor()
        result = processor.process_transcript("Sample transcript text here...")

        assert result["meeting_title"] == "Asurion Weekly Sync"
        assert result["project_client"] == "Asurion"
        assert "Scott" in result["attendees"]
        assert len(result["main_topics"]) > 0


def test_processor_handles_empty_transcript():
    with patch('src.processor.Anthropic') as mock_anthropic:
        mock_response = Mock()
        mock_response.content = [Mock(text='{}')]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        processor = TranscriptProcessor()
        result = processor.process_transcript("")

        assert result == {}
