# src/client_mapper.py
import json
from pathlib import Path
from typing import Optional


class ClientMapper:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "client_mapping.json"

        with open(config_path) as f:
            self.config = json.load(f)

        self.series_map = self.config.get("meeting_series_to_client", {})
        self.filename_patterns = self.config.get("filename_patterns", {})
        self.default = self.config.get("default_client", "Other")

    def get_client(self, meeting_series: str) -> str:
        """Get client name from meeting series name."""
        return self.series_map.get(meeting_series, self.default)

    def get_client_from_filename(self, filename: str) -> str:
        """Try to extract client from filename patterns."""
        for pattern, client in self.filename_patterns.items():
            if pattern.lower() in filename.lower():
                return client
        return self.default
