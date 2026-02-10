# tests/test_notification.py
import pytest
from unittest.mock import AsyncMock, patch
from src.notification import NotificationManager

@pytest.mark.asyncio
async def test_notification_manager_send():
    manager = NotificationManager()
    mock_send = AsyncMock()
    manager.channels['email'].send = mock_send

    await manager.notify_new_transcripts(
        new_files=["meeting1.txt", "meeting2.txt"],
        channel="email"
    )

    mock_send.assert_called_once()
