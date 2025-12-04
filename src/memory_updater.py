# src/memory_updater.py
from typing import Dict, Any, List


class MemoryUpdater:
    def __init__(self, context: str = "work-planning"):
        self.context = context

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

    def entity_exists(self, entity_name: str) -> bool:
        """Check if entity exists in memory (placeholder - always returns False)."""
        # In real implementation, this would call Memory MCP to search
        return False

    def create_entity(
        self,
        name: str,
        entity_type: str,
        observations: List[str]
    ) -> bool:
        """Create a new entity in Memory MCP (placeholder)."""
        # In real implementation, this would call mcp__memory__aim_create_entities
        print(f"[Memory] Would create entity: {name} ({entity_type})")
        print(f"[Memory]   Observations: {observations}")
        return True

    def add_observation(self, entity_name: str, observation: str) -> bool:
        """Add observation to existing entity (placeholder)."""
        # In real implementation, this would call mcp__memory__aim_add_observations
        print(f"[Memory] Would add to {entity_name}: {observation}")
        return True

    def update_from_transcript(
        self,
        client: str,
        processed_data: Dict[str, Any]
    ) -> bool:
        """Update memory with processed transcript data."""
        entity_name = self.format_entity_name(client)
        observation = self.build_observation(processed_data)

        if self.entity_exists(entity_name):
            return self.add_observation(entity_name, observation)
        else:
            # Create with initial observation
            return self.create_entity(
                name=entity_name,
                entity_type="client",
                observations=[observation]
            )
