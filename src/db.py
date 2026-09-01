"""Database engine, session management, and connection handling."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config_manager import get_config_manager
from src.logger import get_logger

logger = get_logger(__name__)

# App data directory (for local SQLite DB)
LOCAL_DB_DIR = Path("data")
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
            logger.info(f"Local database directory: {LOCAL_DB_DIR}")

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

            logger.info(f"Local database initialized at: {LOCAL_DB_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize local database: {e}")
            raise

    def _get_myfactory_engine(self) -> "Engine":
        """Get or create Myfactory database engine."""
        if self._myfactory_engine is None:
            config = get_config_manager()
            settings = config.get()

            if not config.is_configured():
                logger.warning("Myfactory database not configured. Run setup first.")
                return None

            try:
                connection_string = settings.get_sqlalchemy_url()
                logger.info(f"Creating Myfactory engine for: {settings.db_server}")

                self._myfactory_engine = create_engine(
                    connection_string,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30,
                    echo=False,
                )
            except Exception as e:
                logger.error(f"Failed to create Myfactory engine: {e}")
                raise

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
        engine = self._get_myfactory_engine()
        if engine is None:
            return None

        if self._myfactory_session_factory is None:
            self._myfactory_session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
            )

        return self._myfactory_session_factory()

    @contextmanager
    def myfactory_session(self) -> Generator[Session, None, None]:
        """Context manager for Myfactory database session."""
        session = self.get_myfactory_session()
        if session is None:
            raise RuntimeError("Myfactory database not configured. Please run setup.")

        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Myfactory session error: {e}")
            raise
        finally:
            session.close()

    def get_myfactory_engine(self) -> Optional["Engine"]:
        """Get the Myfactory database engine."""
        return self._get_myfactory_engine()

    # ========== Utility Methods ==========

    def test_myfactory_connection(self) -> bool:
        """Test the Myfactory database connection."""
        try:
            engine = self._get_myfactory_engine()
            if engine is None:
                return False

            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
                logger.info("✅ Myfactory connection successful")
                return True
        except Exception as e:
            logger.error(f"❌ Myfactory connection failed: {e}")
            return False

    def get_table_columns(
        self, table_name: str = "tdProducts", use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table from Myfactory database.
        If cache exists, return from SQLite with target_field_id.
        Otherwise, fetch from MSSQL, insert into SQLite, and return with IDs.
        """

        # ✅ Step 1: Check cache first
        if use_cache:
            cached = self._get_cached_columns(table_name)
            if cached:
                logger.info(
                    f"Returning {len(cached)} cached columns from SQLite for {table_name}"
                )
                return cached

        # ✅ Step 2: Fetch from MSSQL
        engine = self._get_myfactory_engine()
        if engine is None:
            return []

        try:
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name)

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

            # ✅ Step 3: Insert into SQLite (this will generate target_field_id)
            self._cache_columns(table_name, result)

            # ✅ Step 4: Fetch back from SQLite with IDs
            cached_with_ids = self._get_cached_columns(table_name)
            if cached_with_ids:
                logger.info(
                    f"✅ Inserted and retrieved {len(cached_with_ids)} columns from SQLite with IDs"
                )
                return cached_with_ids

            # ✅ Fallback: return without IDs if SQLite fetch fails
            logger.warning(
                "SQLite cache fetch failed, returning MSSQL data without IDs"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to get columns from {table_name}: {e}")
            return self._get_fallback_columns()

    def _get_cached_columns(self, table_name: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached columns from local database."""
        try:
            from src.models import TargetField

            with self.local_session() as session:
                columns = (
                    session.query(TargetField)
                    .filter(TargetField.table_name == table_name)
                    .all()
                )

                if columns:
                    return [
                        {
                            "target_field_id": c.id,
                            "name": c.field_name,
                            "type": c.data_type,
                            "nullable": c.is_nullable,
                            "identity": c.is_identity,
                        }
                        for c in columns
                    ]
        except Exception as e:
            logger.debug(f"Could not get cached columns: {e}")

        return None

    def _cache_columns(self, table_name: str, columns: List[Dict[str, Any]]) -> None:
        """Cache column information in local SQLite database."""

        try:
            from src.models import TargetField

            with self.local_session() as session:
                # Clear existing cache for this table
                session.query(TargetField).filter(
                    TargetField.table_name == table_name
                ).delete()

                # Add new cache entries (SQLite will auto-generate target_field_id)
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
            logger.warning(f"Failed to cache columns: {e}")

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
        engine = self._get_myfactory_engine()
        if engine is None:
            return False

        try:
            inspector = inspect(engine)
            return table_name in inspector.get_table_names()
        except Exception as e:
            logger.error(f"Failed to check table existence: {e}")
            return False

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_one: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a raw query on Myfactory database."""
        engine = self._get_myfactory_engine()
        if engine is None:
            raise RuntimeError("Myfactory database not configured")

        try:
            with engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                if fetch_one:
                    row = result.fetchone()
                    return [dict(row._mapping)] if row else []
                return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def close(self) -> None:
        """Close all database connections."""
        if self._local_engine:
            self._local_engine.dispose()
            self._local_engine = None

        if self._myfactory_engine:
            self._myfactory_engine.dispose()
            self._myfactory_engine = None

        self._local_session_factory = None
        self._myfactory_session_factory = None
        logger.info("Database connections closed")


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
