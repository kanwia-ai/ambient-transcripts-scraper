# src/processor.py
import json
import os
from typing import Dict, Any, Optional
from anthropic import Anthropic

EXTRACTION_PROMPT = """Summarize this meeting transcript for work planning context.

Extract and return as JSON:
{
  "meeting_title": "Meeting name",
  "date": "YYYY-MM-DD",
  "project_client": "Client or project name",
  "attendees": ["Person1", "Person2"],
  "main_topics": ["Topic discussed"],
  "key_context": ["Important background info mentioned"],
  "implied_work": ["Things that might need follow-up even if not explicit action items"]
}

Keep it concise - this is for background context, not detailed notes.
Only include fields where you have clear information.

Transcript:
"""


class TranscriptProcessor:
    def __init__(self, api_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-3-haiku-20240307"

    def process_transcript(self, transcript_text: str) -> Dict[str, Any]:
        """Process a transcript and extract structured data."""
        if not transcript_text.strip():
            return {}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + transcript_text[:50000]  # Limit to ~50k chars
            }]
        )

        try:
            result_text = response.content[0].text
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            return json.loads(result_text.strip())
        except (json.JSONDecodeError, IndexError):
            return {}

    def process_file(self, filepath: str) -> Dict[str, Any]:
        """Process a transcript file and extract structured data."""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.process_transcript(content)
