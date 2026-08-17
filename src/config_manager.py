import json
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "config.json"
ENV_FILE = CONFIG_DIR / ".env"


class ConfigManager:
    """Manages configuration and secrets"""

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.secrets: Dict[str, str] = {}
        self._load_config()
        self._load_secrets()

    def _load_config(self) -> None:
        """Load config.json"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
        else:
            # raise FileNotFoundError(f"Config file {CONFIG_FILE} not found.")
            raise FileNotFoundError(
                f"Config file {CONFIG_FILE} not found. Please create a config.json file in the config directory with the necessary configuration settings."
            )

    def _load_secrets(self) -> None:
        """Load .env file"""
        if ENV_FILE.exists():
            load_dotenv(ENV_FILE)
            self.secrets = {
                "API_KEY": os.getenv("API_KEY", ""),
            }

    def _save_config(self) -> None:
        """Save config to file"""
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot notation key"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_mapping(self, mapping_name: str = "default") -> Dict[str, str]:
        """Get field mapping by name"""
        mappings = self.get("mappings", {})
        return mappings.get(mapping_name, {})
