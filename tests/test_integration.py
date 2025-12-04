# tests/test_integration.py
"""Integration tests for the transcript synthesis pipeline."""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from src.database import TranscriptTracker
from src.client_mapper import ClientMapper
from src.processor import TranscriptProcessor
from src.memory_updater import MemoryUpdater
from daily_sync import DailySync


class TestDailySyncIntegration:
    """Integration tests for DailySync orchestrator."""

    def test_daily_sync_finds_transcripts(self):
        """DailySync should find transcript files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test transcript files
            transcripts_dir = Path(tmpdir) / "transcripts"
            transcripts_dir.mkdir()

            series_dir = transcripts_dir / "Test Series"
            series_dir.mkdir()

            (series_dir / "meeting1.txt").write_text("Test content 1")
            (series_dir / "meeting2.txt").write_text("Test content 2")

            sync = DailySync(
                transcripts_dir=str(transcripts_dir),
                db_path=str(Path(tmpdir) / "test.db")
            )

            files = sync.get_all_transcripts()
            assert len(files) == 2
            sync.close()

    def test_daily_sync_tracks_processed_files(self):
        """DailySync should track processed files in database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcripts_dir = Path(tmpdir) / "transcripts"
            transcripts_dir.mkdir()

            series_dir = transcripts_dir / "Test Series"
            series_dir.mkdir()

            (series_dir / "meeting.txt").write_text("Test content")

            db_path = Path(tmpdir) / "test.db"

            sync = DailySync(
                transcripts_dir=str(transcripts_dir),
                db_path=str(db_path)
            )

            files = sync.get_all_transcripts()
            assert len(files) == 1

            # Mark as processed
            sync.tracker.mark_processed(
                filepath=files[0],
                filename="meeting.txt",
                meeting_date="2025-01-01",
                client_entity="Test",
                status="success"
            )

            # Check it's now filtered
            unprocessed = sync.get_unprocessed_transcripts()
            assert len(unprocessed) == 0

            sync.close()


class TestClientMapperIntegration:
    """Integration tests for ClientMapper."""

    def test_mapper_uses_config_file(self):
        """ClientMapper should load and use config file."""
        mapper = ClientMapper()

        # Test known mappings from config
        assert mapper.get_client("Ambient_ Project") == "Asurion"
        assert mapper.get_client("AIT Consulting Weekly") == "AIT_Internal"
        assert mapper.get_client("Unknown Series") == "Other"


class TestMemoryUpdaterIntegration:
    """Integration tests for MemoryUpdater."""

    def test_updater_builds_complete_observation(self):
        """MemoryUpdater should build observation from full processed data."""
        updater = MemoryUpdater()

        processed = {
            "meeting_title": "Weekly Sync",
            "date": "2025-01-15",
            "project_client": "Acme Corp",
            "attendees": ["Alice", "Bob"],
            "main_topics": ["Project roadmap", "Budget review", "Team updates"],
            "key_context": ["Q1 planning deadline approaching", "New hire starting"],
            "implied_work": ["Prepare roadmap document", "Schedule onboarding"]
        }

        observation = updater.build_observation(processed)

        # Should contain key elements
        assert "2025-01-15" in observation
        assert "Project roadmap" in observation
        assert "Q1 planning deadline" in observation
        assert "Prepare roadmap document" in observation


class TestPipelineIntegration:
    """End-to-end pipeline integration tests."""

    @patch.object(TranscriptProcessor, 'process_transcript')
    def test_full_pipeline_with_mock_processor(self, mock_process):
        """Full pipeline should process transcript and update memory."""
        # Mock the Claude API response
        mock_process.return_value = {
            "meeting_title": "Test Meeting",
            "date": "2025-01-20",
            "main_topics": ["Topic A"],
            "key_context": ["Context info"],
            "implied_work": ["Follow up task"]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            transcripts_dir = Path(tmpdir) / "transcripts"
            transcripts_dir.mkdir()

            series_dir = transcripts_dir / "Test_Series"
            series_dir.mkdir()

            transcript_file = series_dir / "Test Meeting 2025-01-20 transcript.txt"
            transcript_file.write_text("Speaker 1: Hello\nSpeaker 2: Hi there")

            sync = DailySync(
                transcripts_dir=str(transcripts_dir),
                db_path=str(Path(tmpdir) / "test.db")
            )

            # Process single file
            result = sync.process_single(str(transcript_file))

            assert result is True
            assert sync.tracker.is_processed(str(transcript_file))

            sync.close()

    def test_pipeline_handles_empty_transcript(self):
        """Pipeline should handle empty transcripts gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcripts_dir = Path(tmpdir) / "transcripts"
            transcripts_dir.mkdir()

            series_dir = transcripts_dir / "Test_Series"
            series_dir.mkdir()

            transcript_file = series_dir / "empty.txt"
            transcript_file.write_text("")

            sync = DailySync(
                transcripts_dir=str(transcripts_dir),
                db_path=str(Path(tmpdir) / "test.db")
            )

            # Process should return False for empty
            with patch.object(sync.processor, 'process_file', return_value={}):
                result = sync.process_single(str(transcript_file))
                assert result is False

            sync.close()

    def test_pipeline_run_with_limit(self):
        """Pipeline run should respect limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            transcripts_dir = Path(tmpdir) / "transcripts"
            transcripts_dir.mkdir()

            series_dir = transcripts_dir / "Test_Series"
            series_dir.mkdir()

            # Create 5 transcripts
            for i in range(5):
                (series_dir / f"meeting{i}.txt").write_text(f"Content {i}")

            sync = DailySync(
                transcripts_dir=str(transcripts_dir),
                db_path=str(Path(tmpdir) / "test.db")
            )

            # Mock the processor to avoid API calls
            with patch.object(sync.processor, 'process_file', return_value={
                "meeting_title": "Test",
                "date": "2025-01-01"
            }):
                result = sync.run(limit=2)

            assert result["total"] == 2
            assert result["success"] + result["failed"] == 2

            sync.close()
