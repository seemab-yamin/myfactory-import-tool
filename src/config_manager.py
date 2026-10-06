"""Configuration manager with interactive setup, validation, and secure storage."""

import getpass
import json
import os
from dataclasses import MISSING, dataclass, fields
from typing import Any, Dict, Optional, Tuple

import keyring
from dotenv import load_dotenv

from src.logger import setup_logger
from src.paths import BASE_DIR

logger = setup_logger(__name__)

# Constants
KEYRING_SERVICE = "myfactory_import"
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"
ENV_PATH = CONFIG_DIR / ".env"


@dataclass
class AppSettings:
    """Validated application settings."""

    # Database Connection
    db_server: str
    db_database: str
    db_driver: str
    db_username: str
    db_password: str
    db_port: int
    db_connection_timeout: int

    # Import Settings
    default_products_table: str

    # Logging
    log_level: str = "INFO"
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    log_backup_count: int = 5

    # App Metadata
    app_name: str = "MyFactory Import Tool"
    app_version: str = "1.0.0"

    def _to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for JSON serialization."""
        return {
            "db_server": self.db_server,
            "db_database": self.db_database,
            "db_driver": self.db_driver,
            "db_username": self.db_username,
            "db_password": self.db_password,
            "db_port": self.db_port,
            "db_connection_timeout": self.db_connection_timeout,
            "default_products_table": self.default_products_table,
            "log_level": self.log_level,
            "log_max_bytes": self.log_max_bytes,
            "log_backup_count": self.log_backup_count,
            "app_name": self.app_name,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        """Create settings from configuration dictionary."""

        valid_fields = fields(cls)

        filtered_data = {
            field.name: data[field.name] for field in valid_fields if field.name in data
        }

        missing = [
            field.name
            for field in valid_fields
            if field.default is MISSING
            and field.default_factory is MISSING
            and field.name not in filtered_data
        ]

        if missing:
            raise ValueError(
                "Missing required configuration values: " + ", ".join(missing)
            )

        return cls(**filtered_data)

    def get_connection_string(self) -> str:
        """Get ODBC connection string."""

        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_server};"
            f"DATABASE={self.db_database};"
            f"UID={self.db_username};"
            f"PWD={self.db_password};"
            f"Connection Timeout={self.db_connection_timeout};"
        )

    def get_sqlalchemy_url(self) -> str:
        """Get SQLAlchemy connection URL."""
        return (
            f"mssql+pyodbc://{self.db_username}:{self.db_password}"
            f"@{self.db_server}/{self.db_database}?"
            f"driver={self.db_driver}"
        )

    def validate(self) -> Tuple[bool, str]:
        """Validate settings."""
        if not self.db_server:
            return False, "Database server is required"

        if not self.db_database:
            return False, "Database name is required"

        if not self.db_driver:
            return False, "Database driver is required"

        if not self.db_username:
            return False, "Username is required for SQL authentication"

        if not self.db_password:
            return False, "Password is required for SQL authentication"

        return True, "Valid"


class ConfigManager:
    """Configuration manager with interactive setup and secure storage."""

    def __init__(self):
        self.config_path = CONFIG_PATH
        self.env_path = ENV_PATH
        self._settings: Optional[AppSettings] = None

        self._load()

    def _load(self):
        """Load and validate configuration."""

        config_data: Dict[str, Any] = {}

        cdata = self._load_config_file()

        # 2. Load Windows Keyring
        if not self._load_keyring(config_data):
            # only call if keyring method fails
            is_credential_loaded = self._load_env(config_data)
        else:
            is_credential_loaded = True

        if is_credential_loaded and cdata:
            config_data.update(cdata)
            logger.info("Configuration and Credential loaded successfully")
        else:
            # if values missing call interactive_setup
            self.interactive_setup(config_data)
            return

        self._settings = AppSettings.from_dict(config_data)
        # 3. Validate and construct AppSettings
        valid, message = self._settings.validate()

        if not valid:
            raise ValueError(f"Invalid configuration: {message}")

    def _load_config_file(self) -> Dict[str, Any]:
        """Load settings from config.json."""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("config.json must contain a JSON object")

            logger.info(f"Loaded config from {self.config_path}")
            return data

        except Exception as e:
            raise RuntimeError(
                f"Could not load config file {self.config_path}: {e}"
            ) from e

    def _load_env(self, config_data: Dict[str, Any]):
        """Load credentials from .env file."""

        if not self.env_path.exists():
            return

        try:
            load_dotenv(self.env_path)

            username = os.getenv("DB_USERNAME")
            password = os.getenv("DB_PASSWORD")

            if username is not None:
                config_data["db_username"] = username

            if password is not None:
                config_data["db_password"] = password

            if username and password:
                logger.info(f"Loaded settings from {self.env_path}")
                return True

        except Exception as e:
            raise RuntimeError(f"Could not load .env file {self.env_path}: {e}") from e

    def _load_keyring(self, config_data: Dict[str, Any]):
        """Load credentials from Windows Keyring."""

        if os.name != "nt":
            return

        try:
            username = keyring.get_password(
                KEYRING_SERVICE,
                "db_username",
            )
            password = keyring.get_password(
                KEYRING_SERVICE,
                "db_password",
            )

            if username is not None:
                config_data["db_username"] = username

            if password is not None:
                config_data["db_password"] = password

            if username and password:
                logger.info("Loaded credentials from Windows Keyring")
                return True
        except Exception as e:
            logger.warning(f"Keyring not available: {e}")

    def _require_settings(self) -> AppSettings:
        """Return loaded settings or raise if unavailable."""
        if self._settings is None:
            raise RuntimeError("Application configuration has not been loaded")

        return self._settings

    def interactive_setup(
        self, config_data: Dict[str, Any], force: bool = False
    ) -> bool:
        """Run interactive setup to configure credentials."""

        if not force and self._settings is not None and self.is_configured():
            print("\n✅ Configuration already exists.")
            choice = input("Do you want to reconfigure? (y/n): ").strip().lower()

            if choice != "y":
                return True

        print("\n" + "=" * 70)
        print("🔐 MyFactory Import Tool - Interactive Setup")
        print("=" * 70)

        print("\nThis will configure your database connection settings.")

        if os.name == "nt":
            print(
                "Credentials will be stored securely in "
                "Windows Credential Manager.\n"
            )

        try:
            # Use existing values only when available.
            current = self._settings

            # Step 1: Database Server
            print("--- Database Connection ---")

            default_server = (
                current.db_server
                if current and current.db_server
                else "TCS135\\SQLEXPRESS"
            )

            server = input(f"SQL Server instance [{default_server}]: ").strip()

            config_data["db_server"] = server or default_server

            default_db = (
                current.db_database if current and current.db_database else "master"
            )

            database = input(f"Database name [{default_db}]: ").strip()

            config_data["db_database"] = database or default_db

            default_driver = (
                current.db_driver
                if current and current.db_driver
                else "ODBC Driver 17 for SQL Server"
            )

            default_port = current.db_port if current and current.db_port else 1433
            db_port = input(f"Database port [{default_port}]: ").strip()
            config_data["db_port"] = int(db_port) if db_port else default_port

            default_db_connection_timeout = (
                current.db_connection_timeout
                if current and current.db_connection_timeout
                else 30
            )
            db_connection_timeout = input(
                f"Database connection timeout (seconds) [{default_db_connection_timeout}]: "
            ).strip()
            config_data["db_connection_timeout"] = (
                int(db_connection_timeout)
                if db_connection_timeout
                else default_db_connection_timeout
            )

            driver = input(f"ODBC Driver [{default_driver}]: ").strip()

            config_data["db_driver"] = driver or default_driver

            username = input("Username: ").strip()

            while not username:
                print("❌ Username is required.")
                username = input("Username: ").strip()

            config_data["db_username"] = username

            password = getpass.getpass("Password: ")

            while not password:
                print("❌ Password is required.")
                password = getpass.getpass("Password: ")

            config_data["db_password"] = password

            # Step 3: Import Settings
            print("\n--- Import Settings ---")

            default_products_table = (
                current.default_products_table
                if current and current.default_products_table
                else "tdProducts"
            )

            table = input(f"Default product table [{default_products_table}]: ").strip()
            config_data["default_products_table"] = table or default_products_table

            self._settings = AppSettings.from_dict(config_data)
            # 3. Validate and construct AppSettings
            valid, message = self._settings.validate()

            if not valid:
                raise ValueError(f"Invalid configuration: {message}")

            # Step 4: Test Connection
            print("\n--- Testing Connection ---")
            if self._test_connection():
                print("✅ Connection successful!")

                # Save configuration
                self._save_all()
                self._is_configured = True

                print("\n✅ Setup complete! Configuration saved.")
                print(f"📁 Config file: {self.config_path}")
                if os.name == "nt":
                    print("🔐 Credentials stored in: Windows Credential Manager")
                else:
                    print(f"🔐 Credentials stored in: {self.env_path}")
                return True
            else:
                print(
                    "\n❌ Connection failed. Please check your credentials and try again."
                )
                retry = input("Retry setup? (y/n): ").strip().lower()
                if retry == "y":
                    return self.interactive_setup(force=True)
                else:
                    return False
        except KeyboardInterrupt:
            print("\n\n❌ Setup cancelled by user.")
            return False

        except Exception as e:
            print(f"\n❌ Setup error: {e}")
            logger.error("Setup error", exc_info=True)
            return False

    def _test_connection(self) -> bool:
        """Test database connection."""
        try:
            import pyodbc

            settings = self._require_settings()

            conn_str = settings.get_connection_string()

            conn = pyodbc.connect(
                conn_str,
                timeout=settings.db_connection_timeout,
            )

            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()

            cursor.close()
            conn.close()

            return True

        except Exception as e:
            print(f"❌ Connection error: {e}")
            logger.error(f"Connection test failed: {e}")
            return False

    def _save_all(self):
        """Save all configuration."""

        settings = self._require_settings()

        self.config_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        config_data = settings._to_dict()

        # Never store sensitive credentials in config.json.
        config_data.pop("db_password", None)
        config_data.pop("db_username", None)

        with open(
            self.config_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Config saved to {self.config_path}")

        # Store credentials in Windows Keyring.
        if os.name == "nt":
            try:
                keyring.set_password(
                    KEYRING_SERVICE,
                    "db_username",
                    settings.db_username,
                )

                keyring.set_password(
                    KEYRING_SERVICE,
                    "db_password",
                    settings.db_password,
                )

                logger.info("Credentials saved to Windows Keyring")

            except Exception as e:
                logger.warning(f"Could not save to Keyring: {e}")

        # Keep .env as fallback.
        self._save_env_credentials()

    def _save_env_credentials(self):
        """Save credentials to .env file."""

        settings = self._require_settings()

        try:
            self.env_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                self.env_path,
                "w",
                encoding="utf-8",
            ) as f:
                f.write(f"DB_USERNAME={settings.db_username}\n")
                f.write(f"DB_PASSWORD={settings.db_password}\n")

            logger.info(f"Credentials saved to {self.env_path}")

        except Exception as e:
            logger.warning(f"Could not save .env: {e}")

    def get_credentials(
        self,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get credentials."""
        settings = self._require_settings()

        return (
            settings.db_username,
            settings.db_password,
        )

    def clear_credentials(self):
        """Clear stored credentials."""

        try:
            if os.name == "nt":
                for credential in ("db_username", "db_password"):
                    try:
                        keyring.delete_password(
                            KEYRING_SERVICE,
                            credential,
                        )
                    except keyring.errors.PasswordDeleteError:
                        pass

                logger.info("Credentials cleared from Keyring")

        except Exception as e:
            logger.debug(f"Keyring clear failed: {e}")

        if self.env_path.exists():
            try:
                self.env_path.unlink()
                logger.info("Credentials cleared from .env")
            except Exception as e:
                logger.warning(f"Could not delete .env: {e}")

        settings = self._require_settings()

        settings.db_username = ""
        settings.db_password = ""

        self._save_all()

    def set_setting(
        self,
        key: str,
        value: Any,
    ):
        """Update a setting and save."""

        settings = self._require_settings()

        if not hasattr(settings, key):
            raise ValueError(f"Unknown setting: {key}")

        setattr(settings, key, value)

        valid, message = settings.validate()

        if not valid:
            raise ValueError(f"Invalid setting: {message}")

        self._save_all()

        logger.info(f"Updated setting: {key}")

    def get_config_summary(self) -> str:
        """Get a summary of the configuration."""

        s = self._require_settings()

        lines = [
            "=" * 50,
            "📋 Configuration Summary",
            "=" * 50,
            f"Server:        {s.db_server}",
            f"Database:      {s.db_database}",
            f"Driver:        {s.db_driver}",
            f"Table:         {s.default_products_table}",
            f"Log Level:     {s.log_level}",
            "=" * 50,
        ]

        return "\n".join(lines)

    def is_configured(self) -> bool:
        """Return True when a valid configuration is available."""

        if self._settings is None:
            return False

        valid, _ = self._settings.validate()
        return valid

    def get(self) -> AppSettings:
        """Return the validated application settings."""
        if self.is_configured():
            return self._require_settings()
        else:
            raise RuntimeError("Configuration is not available or invalid")


# Global instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance."""
    global _config_manager

    if _config_manager is None:
        _config_manager = ConfigManager()

    return _config_manager
