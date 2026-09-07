"""Database engine, session management, and connection handling."""

from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config_manager import get_config_manager
from src.logger import get_logger
from src.paths import BASE_DIR

logger = get_logger(__name__)

# App data directory (for local SQLite DB)
LOCAL_DB_DIR = BASE_DIR / "data"
LOCAL_DB_PATH = LOCAL_DB_DIR / "mappings.db"
LOCAL_DB_URL = f"sqlite:///{LOCAL_DB_PATH}"


class DatabaseManager:
    """
    Singleton database manager for handling both local and remote connections.
    """

    _instance: Optional["DatabaseManager"] = None
    _local_engine = None
    _myfactory_engine = None
    _local_session_factory = None
    _myfactory_session_factory = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._init_local_db()

    def _init_local_db(self) -> None:
        """Initialize local SQLite database."""
        try:
            LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Local database directory: {LOCAL_DB_DIR}")
            logger.info(f"📁 Local database path: {LOCAL_DB_PATH}")

            # Create engine
            self._local_engine = create_engine(
                LOCAL_DB_URL,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
                echo=False,
            )

            # Create session factory
            self._local_session_factory = sessionmaker(
                bind=self._local_engine,
                autoflush=False,
                autocommit=False,
            )

            # Create tables
            from src.models import Base

            Base.metadata.create_all(self._local_engine)

            logger.info(f"✅ Local database initialized at: {LOCAL_DB_PATH}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize local database: {e}")
            raise

    def _get_myfactory_engine(self) -> "Engine":
        """Get or create Myfactory database engine."""
        logger.info("🔍 _get_myfactory_engine called")

        if self._myfactory_engine is None:
            logger.info("🔍 Myfactory engine is None, creating new engine...")
            config = get_config_manager()

            # ✅ Debug: Log config status
            logger.info(f"🔍 Config is_configured: {config.is_configured()}")

            settings = config.get()

            # ✅ Debug: Log settings values (mask password)
            logger.info(f"🔍 DB Server: {settings.db_server}")
            logger.info(f"🔍 DB Database: {settings.db_database}")
            logger.info(f"🔍 DB Driver: {settings.db_driver}")
            logger.info(f"🔍 DB Port: {settings.db_port}")
            logger.info(f"🔍 Trusted Connection: {settings.db_trusted_connection}")
            logger.info(
                f"🔍 Username: {settings.db_username if settings.db_username else '(not set)'}"
            )
            logger.info(
                f"🔍 Password: {'***' if settings.db_password else '(not set)'}"
            )

            if not config.is_configured():
                logger.warning("⚠️ Myfactory database not configured. Run setup first.")
                return None

            try:
                # ✅ Log connection string (masked)
                connection_string = settings.get_sqlalchemy_url()
                masked_conn_str = connection_string
                if settings.db_password:
                    masked_conn_str = connection_string.replace(
                        settings.db_password, "***"
                    )
                logger.info(f"🔍 Connection string (masked): {masked_conn_str}")

                logger.info(f"🔍 Creating Myfactory engine for: {settings.db_server}")

                self._myfactory_engine = create_engine(
                    connection_string,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30,
                    echo=False,
                )
                logger.info(
                    f"✅ Myfactory engine created successfully for: {settings.db_server}"
                )

            except Exception as e:
                logger.error(f"❌ Failed to create Myfactory engine: {e}")
                logger.error(
                    f"❌ Connection string (masked): {masked_conn_str if 'masked_conn_str' in locals() else 'N/A'}"
                )
                raise

        else:
            logger.info("🔍 Reusing existing Myfactory engine")

        return self._myfactory_engine

    # ========== Local Database Methods ==========

    def get_local_session(self) -> Session:
        """Get a session for the local database."""
        if self._local_session_factory is None:
            self._init_local_db()
        return self._local_session_factory()

    def get_local_engine(self) -> "Engine":
        """Get the local database engine."""
        if self._local_engine is None:
            self._init_local_db()
        return self._local_engine

    @contextmanager
    def local_session(self) -> Generator[Session, None, None]:
        """Context manager for local database session."""
        session = self.get_local_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Local session error: {e}")
            raise
        finally:
            session.close()

    # ========== Myfactory Database Methods ==========

    def get_myfactory_session(self) -> Optional[Session]:
        """Get a session for the Myfactory database."""
        logger.info("🔍 get_myfactory_session called")
        engine = self._get_myfactory_engine()
        if engine is None:
            logger.warning("⚠️ Engine is None, returning None")
            return None

        if self._myfactory_session_factory is None:
            logger.info("🔍 Creating Myfactory session factory...")
            self._myfactory_session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )
            logger.info("✅ Myfactory session factory created")

        return self._myfactory_session_factory()

    @contextmanager
    def myfactory_session(self) -> Generator[Session, None, None]:
        """Context manager for Myfactory database session."""
        logger.info("🔍 myfactory_session context manager called")
        session = self.get_myfactory_session()
        if session is None:
            logger.error("❌ Session is None - database not configured")
            raise RuntimeError("Myfactory database not configured. Please run setup.")

        try:
            logger.info("🔍 Yielding session...")
            yield session
            logger.info("🔍 Committing session...")
            session.commit()
            logger.info("✅ Session committed successfully")
        except Exception as e:
            logger.error(f"❌ Myfactory session error: {e}")
            session.rollback()
            logger.info("🔍 Session rolled back")
            raise
        finally:
            logger.info("🔍 Closing session...")
            session.close()
            logger.info("✅ Session closed")

    def get_myfactory_engine(self) -> Optional["Engine"]:
        """Get the Myfactory database engine."""
        logger.info("🔍 get_myfactory_engine called")
        return self._get_myfactory_engine()

    # ========== Utility Methods ==========

    def test_myfactory_connection(self) -> bool:
        """Test the Myfactory database connection."""
        logger.info("🔍 Testing Myfactory connection...")

        try:
            engine = self._get_myfactory_engine()
            if engine is None:
                logger.warning("⚠️ Engine is None, returning False")
                return False

            logger.info("🔍 Attempting to connect...")
            with engine.connect() as conn:
                logger.info("🔍 Executing SELECT 1...")
                result = conn.execute(text("SELECT 1"))
                row = result.fetchone()
                logger.info(f"✅ Connection successful! Result: {row}")
                return True
        except Exception as e:
            logger.error(f"❌ Myfactory connection failed: {e}")
            return False

    def get_table_columns(
        self, table_name: str = "tdProducts", use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table from Myfactory database.
        """

        logger.info(
            f"🔍 get_table_columns called: table={table_name}, use_cache={use_cache}"
        )

        # ✅ Step 1: Check cache first
        if use_cache:
            logger.info("🔍 Checking cache...")
            cached = self._get_cached_columns(table_name)
            if cached:
                logger.info(
                    f"✅ Returning {len(cached)} cached columns from SQLite for {table_name}"
                )
                return cached
            logger.info("🔍 No cached columns found")

        # ✅ Step 2: Fetch from MSSQL
        logger.info("🔍 Fetching columns from Myfactory database...")
        engine = self._get_myfactory_engine()
        if engine is None:
            logger.warning("⚠️ Engine is None, returning []")
            return []

        try:
            logger.info("🔍 Inspecting table...")
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name)
            logger.info(f"🔍 Found {len(columns)} columns in {table_name}")

            result = []
            for col in columns:
                result.append(
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "default": (
                            str(col.get("default")) if col.get("default") else None
                        ),
                        "autoincrement": col.get("autoincrement", False),
                    }
                )

            # ✅ Step 3: Insert into SQLite
            logger.info(f"🔍 Caching {len(result)} columns to SQLite...")
            self._cache_columns(table_name, result)

            # ✅ Step 4: Fetch back from SQLite with IDs
            logger.info("🔍 Fetching cached columns with IDs...")
            cached_with_ids = self._get_cached_columns(table_name)
            if cached_with_ids:
                logger.info(
                    f"✅ Inserted and retrieved {len(cached_with_ids)} columns from SQLite with IDs"
                )
                return cached_with_ids

            # ✅ Fallback
            logger.warning(
                "⚠️ SQLite cache fetch failed, returning MSSQL data without IDs"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Failed to get columns from {table_name}: {e}")
            return self._get_fallback_columns()

    def _get_cached_columns(self, table_name: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached columns from local database."""
        logger.info(f"🔍 _get_cached_columns called: table={table_name}")

        try:
            from src.models import TargetField

            with self.local_session() as session:
                logger.info("🔍 Querying TargetField table...")
                columns = (
                    session.query(TargetField)
                    .filter(TargetField.table_name == table_name)
                    .all()
                )
                logger.info(f"🔍 Query returned {len(columns)} rows")

                if columns:
                    result = [
                        {
                            "target_field_id": c.id,
                            "name": c.field_name,
                            "type": c.data_type,
                            "nullable": c.is_nullable,
                            "identity": c.is_identity,
                        }
                        for c in columns
                    ]
                    logger.info(f"✅ Returning {len(result)} cached columns")
                    return result
                else:
                    logger.info("ℹ️ No cached columns found")
        except Exception as e:
            logger.error(f"❌ Could not get cached columns: {e}")

        return None

    def _cache_columns(self, table_name: str, columns: List[Dict[str, Any]]) -> None:
        """Cache column information in local SQLite database."""
        logger.info(
            f"🔍 _cache_columns called: table={table_name}, columns={len(columns)}"
        )

        try:
            from src.models import TargetField

            with self.local_session() as session:
                logger.info(f"🔍 Deleting existing cache for {table_name}...")
                deleted = (
                    session.query(TargetField)
                    .filter(TargetField.table_name == table_name)
                    .delete()
                )
                logger.info(f"🔍 Deleted {deleted} existing entries")

                logger.info(f"🔍 Inserting {len(columns)} new entries...")
                for col in columns:
                    product_col = TargetField(
                        table_name=table_name,
                        field_name=col["name"],
                        data_type=col["type"],
                        is_nullable=col.get("nullable", True),
                        is_identity=col.get("autoincrement", False),
                        default_value=col.get("default"),
                    )
                    session.add(product_col)

                session.commit()
                logger.info(
                    f"✅ Cached {len(columns)} columns for {table_name} in SQLite"
                )

        except Exception as e:
            logger.error(f"❌ Failed to cache columns: {e}")

    def get_myfactory_connection_string(self) -> Optional[str]:
        """Get the current Myfactory connection string (without password)."""
        config = get_config_manager()
        if not config.is_configured():
            return None
        return config.get().get_connection_string()

    def get_myfactory_server(self) -> Optional[str]:
        """Get the Myfactory server name."""
        config = get_config_manager()
        if not config.is_configured():
            return None
        return config.get().db_server

    def get_myfactory_database(self) -> Optional[str]:
        """Get the Myfactory database name."""
        config = get_config_manager()
        if not config.is_configured():
            return None
        return config.get().db_database

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in Myfactory database."""
        logger.info(f"🔍 table_exists called: {table_name}")

        engine = self._get_myfactory_engine()
        if engine is None:
            logger.warning("⚠️ Engine is None, returning False")
            return False

        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            exists = table_name in tables
            logger.info(f"✅ Table {table_name} exists: {exists}")
            return exists
        except Exception as e:
            logger.error(f"❌ Failed to check table existence: {e}")
            return False

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_one: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a raw query on Myfactory database."""
        logger.info(f"🔍 execute_query called: {query[:100]}...")

        engine = self._get_myfactory_engine()
        if engine is None:
            logger.error("❌ Myfactory database not configured")
            raise RuntimeError("Myfactory database not configured")

        try:
            with engine.connect() as conn:
                logger.info("🔍 Executing query...")
                result = conn.execute(text(query), params or {})
                if fetch_one:
                    row = result.fetchone()
                    if row:
                        logger.info("✅ Query returned 1 row")
                        return [dict(row._mapping)]
                    logger.info("ℹ️ Query returned 0 rows")
                    return []
                rows = [dict(row._mapping) for row in result]
                logger.info(f"✅ Query returned {len(rows)} rows")
                return rows
        except Exception as e:
            logger.error(f"❌ Query execution failed: {e}")
            raise

    def close(self) -> None:
        """Close all database connections."""
        logger.info("🔍 Closing all database connections...")

        if self._local_engine:
            self._local_engine.dispose()
            self._local_engine = None
            logger.info("✅ Local engine disposed")

        if self._myfactory_engine:
            self._myfactory_engine.dispose()
            self._myfactory_engine = None
            logger.info("✅ Myfactory engine disposed")

        self._local_session_factory = None
        self._myfactory_session_factory = None
        logger.info("✅ Database connections closed")


# ========== Singleton Accessor ==========

_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get the singleton database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


# ========== Convenience Functions ==========


def get_local_session() -> Session:
    """Get a session for the local database."""
    return get_db_manager().get_local_session()


def get_myfactory_session() -> Session:
    """Get a session for the Myfactory database."""
    return get_db_manager().get_myfactory_session()


@contextmanager
def local_session() -> Generator[Session, None, None]:
    """Context manager for local database session."""
    with get_db_manager().local_session() as session:
        yield session


@contextmanager
def myfactory_session() -> Generator[Session, None, None]:
    """Context manager for Myfactory database session."""
    with get_db_manager().myfactory_session() as session:
        yield session


def test_connection() -> bool:
    """Test the Myfactory database connection."""
    return get_db_manager().test_myfactory_connection()


def get_table_columns(
    table_name: str = "tdProducts", use_cache: bool = True
) -> List[Dict[str, Any]]:
    """Get columns for a table in Myfactory database."""
    return get_db_manager().get_table_columns(table_name, use_cache)
