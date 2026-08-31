"""Configuration manager with interactive setup, validation, and secure storage."""

import getpass
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import keyring
from dotenv import load_dotenv

from src.logger import setup_logger

logger = setup_logger(__name__)

# Constants
KEYRING_SERVICE = "myfactory_import"
CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "config.json"
ENV_FILE = CONFIG_DIR / ".env"


class AuthMethod(Enum):
    """Authentication method enum."""

    WINDOWS = "windows"
    SQL = "sql"


@dataclass
class AppSettings:
    """Application settings with validation."""

    # Database Connection
    db_server: str = "localhost"
    db_database: str = "master"
    db_driver: str = "ODBC Driver 17 for SQL Server"
    db_username: str = ""
    db_password: str = ""
    db_trusted_connection: bool = True
    db_port: int = 1433
    db_connection_timeout: int = 30

    # Authentication
    auth_method: str = "windows"  # "windows" or "sql"

    # Import Settings
    default_products_table: str = "tdProducts"
    default_supplier: str = "default"
    default_delimiter: str = ","
    default_batch_size: int = 1000
    skip_header: bool = True

    # Logging
    log_level: str = "INFO"
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 3

    # App Metadata
    app_name: str = "MyFactory Import Tool"
    app_version: str = "1.0.0"
    app_data_dir: str = ""

    def __post_init__(self):
        """Set default app data directory."""
        if not self.app_data_dir:
            self.app_data_dir = self._get_default_app_data_dir()

    def _get_default_app_data_dir(self) -> str:
        """Get default application data directory."""
        if os.name == "nt":  # Windows
            return os.path.join(os.environ.get("APPDATA", ""), "MyFactoryImport")
        else:  # Linux/macOS
            return os.path.join(os.path.expanduser("~"), ".config", "myfactory-import")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "db_server": self.db_server,
            "db_database": self.db_database,
            "db_driver": self.db_driver,
            "db_trusted_connection": self.db_trusted_connection,
            "db_port": self.db_port,
            "db_connection_timeout": self.db_connection_timeout,
            "auth_method": self.auth_method,
            "default_products_table": self.default_products_table,
            "default_supplier": self.default_supplier,
            "default_delimiter": self.default_delimiter,
            "default_batch_size": self.default_batch_size,
            "skip_header": self.skip_header,
            "log_level": self.log_level,
            "log_max_bytes": self.log_max_bytes,
            "log_backup_count": self.log_backup_count,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "app_data_dir": self.app_data_dir,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppSettings":
        """Create settings from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})

    def get_connection_string(self) -> str:
        """Get ODBC connection string."""
        if self.db_trusted_connection:
            return (
                f"DRIVER={{{self.db_driver}}};"
                f"SERVER={self.db_server};"
                f"DATABASE={self.db_database};"
                f"Trusted_Connection=yes;"
                f"Connection Timeout={self.db_connection_timeout};"
            )
        else:
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
        if self.db_trusted_connection:
            return f"mssql+pyodbc://@{self.db_server}/{self.db_database}?driver={self.db_driver}&Trusted_Connection=yes"
        else:
            return f"mssql+pyodbc://{self.db_username}:{self.db_password}@{self.db_server}/{self.db_database}?driver={self.db_driver}"

    def get_default_supplier(self) -> str:
        """Get default supplier from settings."""
        return self.get().default_supplier

    def validate(self) -> Tuple[bool, str]:
        """Validate settings."""
        if not self.db_server:
            return False, "Database server is required"

        if not self.db_database:
            return False, "Database name is required"

        if not self.db_trusted_connection:
            if not self.db_username:
                return False, "Username is required for SQL authentication"
            if not self.db_password:
                return False, "Password is required for SQL authentication"

        return True, "Valid"


class ConfigManager:
    """Configuration manager with interactive setup and secure storage."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.env_path = ENV_FILE
        self._settings: Optional[AppSettings] = None
        self._is_configured = False
        self._load()

    def _load(self):
        """Load configuration from multiple sources."""
        # Start with defaults
        self._settings = AppSettings()

        # 1. Load from config.json
        self._load_config_file()

        # 2. Load from .env
        self._load_env()

        # 3. Load from Windows Keyring
        self._load_keyring()

        # 4. Check if configured
        self._is_configured = self._settings.validate()[0]

        logger.info(f"Configuration loaded (configured: {self._is_configured})")

    def _load_config_file(self):
        """Load settings from config.json."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self._settings, key):
                            setattr(self._settings, key, value)
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Could not load config.json: {e}")

    def _load_env(self):
        """Load credentials from .env file."""
        if self.env_path.exists():
            try:
                load_dotenv(self.env_path)
                self._settings.db_server = os.getenv(
                    "DB_SERVER", self._settings.db_server
                )
                self._settings.db_database = os.getenv(
                    "DB_DATABASE", self._settings.db_database
                )
                self._settings.db_username = os.getenv(
                    "DB_USERNAME", self._settings.db_username
                )
                self._settings.db_password = os.getenv(
                    "DB_PASSWORD", self._settings.db_password
                )
                self._settings.db_driver = os.getenv(
                    "DB_DRIVER", self._settings.db_driver
                )
                self._settings.db_trusted_connection = (
                    os.getenv("DB_TRUSTED_CONNECTION", "True").lower() == "true"
                )
                self._settings.db_port = int(os.getenv("DB_PORT", "1433"))
                self._settings.db_connection_timeout = int(
                    os.getenv("DB_CONNECTION_TIMEOUT", "30")
                )
                logger.info("Loaded settings from .env")
            except Exception as e:
                logger.warning(f"Could not load .env: {e}")

    def _load_keyring(self):
        """Load credentials from Windows Keyring."""
        if os.name == "nt":
            try:
                username = keyring.get_password(KEYRING_SERVICE, "db_username")
                password = keyring.get_password(KEYRING_SERVICE, "db_password")
                if username and password:
                    self._settings.db_username = username
                    self._settings.db_password = password
                    logger.info("Loaded credentials from Windows Keyring")
            except Exception as e:
                logger.debug(f"Keyring not available: {e}")

    def get(self) -> AppSettings:
        """Get current settings."""
        return self._settings

    def is_configured(self) -> bool:
        """Check if configuration is complete."""
        return self._is_configured

    def interactive_setup(self, force: bool = False) -> bool:
        """
        Run interactive setup to configure credentials.

        Args:
            force: Force setup even if already configured

        Returns:
            True if setup was successful
        """
        if not force and self.is_configured():
            print("\n✅ Configuration already exists.")
            choice = input("Do you want to reconfigure? (y/n): ").strip().lower()
            if choice != "y":
                return True

        print("\n" + "=" * 70)
        print("🔐 MyFactory Import Tool - Interactive Setup")
        print("=" * 70)
        print("\nThis will configure your database connection settings.")
        print("Credentials will be stored securely in Windows Credential Manager.\n")

        try:
            # Step 1: Database Server
            print("--- Database Connection ---")
            default_server = self._settings.db_server or "TCS135\\SQLEXPRESS"
            server = input(f"SQL Server instance [{default_server}]: ").strip()
            self._settings.db_server = server or default_server

            default_db = self._settings.db_database or "master"
            database = input(f"Database name [{default_db}]: ").strip()
            self._settings.db_database = database or default_db

            default_driver = self._settings.db_driver or "ODBC Driver 17 for SQL Server"
            driver = input(f"ODBC Driver [{default_driver}]: ").strip()
            self._settings.db_driver = driver or default_driver

            # Step 2: Authentication
            print("\n--- Authentication ---")
            print("  1. Windows Authentication (Trusted Connection)")
            print("  2. SQL Server Authentication (Username/Password)")
            auth_choice = (
                input("Choose authentication method (1/2) [1]: ").strip() or "1"
            )

            if auth_choice == "2":
                self._settings.db_trusted_connection = False
                self._settings.auth_method = "sql"

                username = input("Username: ").strip()
                while not username:
                    print("❌ Username is required.")
                    username = input("Username: ").strip()
                self._settings.db_username = username

                password = getpass.getpass("Password: ")
                while not password:
                    print("❌ Password is required.")
                    password = getpass.getpass("Password: ")
                self._settings.db_password = password
            else:
                self._settings.db_trusted_connection = True
                self._settings.auth_method = "windows"
                self._settings.db_username = ""
                self._settings.db_password = ""

            # Step 3: Import Settings
            print("\n--- Import Settings ---")
            default_products_table = (
                self._settings.default_products_table or "tdProducts"
            )
            table = input(f"Default product table [{default_products_table}]: ").strip()
            self._settings.default_products_table = table or default_products_table

            default_supplier = self._settings.default_supplier or "default"
            supplier = input(f"Default supplier name [{default_supplier}]: ").strip()
            self._settings.default_supplier = supplier or default_supplier

            default_batch = str(self._settings.default_batch_size)
            batch = input(f"Batch size (rows per batch) [{default_batch}]: ").strip()
            if batch:
                try:
                    self._settings.default_batch_size = int(batch)
                except ValueError:
                    print(f"⚠️ Invalid batch size, using {default_batch}")

            # Step 4: Test Connection
            print("\n--- Testing Connection ---")
            if self._test_connection():
                print("✅ Connection successful!")

                # Save configuration
                self._save_all()
                self._is_configured = True

                print("\n✅ Setup complete! Configuration saved.")
                print(f"📁 Config file: {self.config_path}")
                print(f"🔐 Credentials stored in: Windows Credential Manager")
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
            logger.error(f"Setup error: {e}", exc_info=True)
            return False

    def _test_connection(self) -> bool:
        """Test database connection."""
        try:
            import pyodbc

            conn_str = self._settings.get_connection_string()
            conn = pyodbc.connect(
                conn_str, timeout=self._settings.db_connection_timeout
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Connection error: {e}")
            logger.error(f"Connection test failed: {e}")
            return False

    def _save_all(self):
        """Save all configuration."""
        # Create config directory
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save config.json (non-sensitive)
        config_data = self._settings.to_dict()
        # Remove sensitive data from config.json
        config_data.pop("db_password", None)
        if not self._settings.db_trusted_connection:
            config_data.pop("db_username", None)

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        logger.info(f"Config saved to {self.config_path}")

        # Save credentials to Windows Keyring (Windows only)
        if os.name == "nt" and not self._settings.db_trusted_connection:
            try:
                keyring.set_password(
                    KEYRING_SERVICE, "db_username", self._settings.db_username
                )
                keyring.set_password(
                    KEYRING_SERVICE, "db_password", self._settings.db_password
                )
                logger.info("Credentials saved to Windows Keyring")
            except Exception as e:
                logger.warning(f"Could not save to Keyring: {e}")
                self._save_env_credentials()

        # Save .env fallback
        self._save_env_credentials()

    def _save_env_credentials(self):
        """Save credentials to .env file."""
        try:
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.write(f"DB_SERVER={self._settings.db_server}\n")
                f.write(f"DB_DATABASE={self._settings.db_database}\n")
                f.write(f"DB_DRIVER={self._settings.db_driver}\n")
                f.write(f"DB_PORT={self._settings.db_port}\n")
                f.write(
                    f"DB_CONNECTION_TIMEOUT={self._settings.db_connection_timeout}\n"
                )
                f.write(
                    f"DB_TRUSTED_CONNECTION={str(self._settings.db_trusted_connection)}\n"
                )
                if not self._settings.db_trusted_connection:
                    f.write(f"DB_USERNAME={self._settings.db_username}\n")
                    f.write(f"DB_PASSWORD={self._settings.db_password}\n")
            logger.info(f"Credentials saved to {self.env_path}")
        except Exception as e:
            logger.warning(f"Could not save .env: {e}")

    def get_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Get credentials (username, password)."""
        if self._settings.db_trusted_connection:
            return None, None
        return self._settings.db_username, self._settings.db_password

    def clear_credentials(self):
        """Clear stored credentials."""
        try:
            if os.name == "nt":
                keyring.delete_password(KEYRING_SERVICE, "db_username")
                keyring.delete_password(KEYRING_SERVICE, "db_password")
                logger.info("Credentials cleared from Keyring")
        except Exception as e:
            logger.debug(f"Keyring clear failed: {e}")

        if self.env_path.exists():
            try:
                self.env_path.unlink()
                logger.info("Credentials cleared from .env")
            except Exception as e:
                logger.warning(f"Could not delete .env: {e}")

        self._settings.db_username = ""
        self._settings.db_password = ""
        self._is_configured = False
        self._save_all()

    def set_setting(self, key: str, value: Any):
        """Update a setting and save."""
        if hasattr(self._settings, key):
            setattr(self._settings, key, value)
            self._save_all()
            logger.info(f"Updated setting: {key} = {value}")
        else:
            raise ValueError(f"Unknown setting: {key}")

    def get_config_summary(self) -> str:
        """Get a summary of the configuration."""
        s = self._settings
        lines = [
            "=" * 50,
            f"📋 Configuration Summary",
            "=" * 50,
            f"Server:        {s.db_server}",
            f"Database:      {s.db_database}",
            f"Driver:        {s.db_driver}",
            f"Auth Method:   {s.auth_method.upper()}",
            f"Table:         {s.default_products_table}",
            f"Supplier:      {s.default_supplier}",
            f"Batch Size:    {s.default_batch_size}",
            f"Log Level:     {s.log_level}",
            f"Data Directory: {s.app_data_dir}",
            "=" * 50,
        ]
        return "\n".join(lines)


# Global instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def ensure_configured() -> bool:
    """Ensure configuration exists, run setup if needed."""
    manager = get_config_manager()
    if not manager.is_configured():
        print("🔐 Database configuration not found. Starting setup...")
        return manager.interactive_setup()
    return True
