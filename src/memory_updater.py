# src/memory_updater.py
import json
from pathlib import Path
from typing import Dict, Any, List


class MemoryUpdater:
    def __init__(self, context: str = "work-planning", output_file: str = None):
        self.context = context
        self.output_file = Path(output_file) if output_file else Path("memory_updates.json")
        self.pending_updates: Dict[str, List[str]] = {}  # entity -> list of observations

    def format_entity_name(self, name: str) -> str:
        """Format name for entity (replace spaces with underscores)."""
        return name.replace(" ", "_")

    def build_observation(self, processed_data: Dict[str, Any]) -> str:
        """Build a concise observation string from processed transcript data."""
        parts = []

        date = processed_data.get("date", "Unknown date")
        parts.append(f"{date}:")

        if processed_data.get("main_topics"):
            topics = ", ".join(processed_data["main_topics"][:3])
            parts.append(f"Discussed {topics}.")

        if processed_data.get("key_context"):
            context = processed_data["key_context"][0]
            parts.append(context)

        if processed_data.get("implied_work"):
            work = processed_data["implied_work"][0]
            parts.append(f"Potential follow-up: {work}")

        return " ".join(parts)

    def update_from_transcript(
        self,
        client: str,
        processed_data: Dict[str, Any]
    ) -> bool:
        """Queue an update for Memory MCP."""
        entity_name = self.format_entity_name(client)
        observation = self.build_observation(processed_data)

        if entity_name not in self.pending_updates:
            self.pending_updates[entity_name] = []

        self.pending_updates[entity_name].append(observation)

        print(f"[Memory] Queued for {entity_name}: {observation[:60]}...")
        self._save_pending()
        return True

    def _save_pending(self):
        """Save pending updates to JSON file."""
        output = {
            "context": self.context,
            "entities": [
                {
                    "name": name,
                    "entityType": "client",
                    "observations": obs_list
                }
                for name, obs_list in self.pending_updates.items()
            ]
        }
        self.output_file.write_text(json.dumps(output, indent=2))

    def get_summary(self) -> str:
        """Get summary of pending updates."""
        total_obs = sum(len(obs) for obs in self.pending_updates.values())
        return f"{len(self.pending_updates)} entities, {total_obs} observations"
