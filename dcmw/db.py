import configparser
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, MutableMapping

import toml
from sqlalchemy import create_engine, exc, text
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.engine.base import Engine

from dcmw.models import *
from dcmw.paths import CONFIG_DIR
from dcmw.utils.utils_io import get_logger

logger = get_logger()


class DatabaseManager:
    """
    Database Manager Class
    Note: Do not store an engine into self.engine for example. Engine objects can't be pickled for multiprocessing.

    Attributes:
        - db_name (str): Name of the database.
        - config_file (str): Name of the file containing database info.
    """

    def __init__(self, db_name: str, config_file: str = "database.ini") -> None:
        self.db_name = db_name
        self.config = self.load_config(self.db_name, config_file)
        self.database_url = self._construct_database_url()

    @abstractmethod
    def _construct_database_url(self) -> str:
        """Construct the database URL based on the loaded configuration."""
        pass

    @abstractmethod
    def create_database_if_not_exists(self) -> None:
        """Create database."""
        pass

    def _create_db_tables(self) -> None:
        """Create tables in the database using the provided URL."""
        WarehouseBase.metadata.create_all(bind=self._create_engine())

    def _create_engine(self) -> Engine:
        """Create a database engine using the constructed URL."""
        engine = create_engine(self.database_url)
        return engine

    def create_session(self) -> Session:
        """Create and return a new session."""
        return sessionmaker(bind=self._create_engine())()

    @classmethod
    def load_config(cls, db_name: str, config_file: str = "database.ini") -> Dict[str, str]:
        parser = configparser.ConfigParser()
        parser.read(os.path.join(CONFIG_DIR, config_file))

        if db_name not in parser:
            logger.error(f"'{db_name}' not found in {config_file}")
            raise ValueError(f"Configuration for '{db_name}' not found")

        return dict(parser[db_name])


class SQLite(DatabaseManager):
    # TODO: should this actually have their own init function?
    # specific methods or attributes for SQLite

    # # TODO: need to look at this.
    # def create_session_wal_mode(self) -> Session:
    #     """Create and return a new session with WAL mode for multiprocessing in a sqlite db."""
    #     # TODO: IDK if we want/need to continue with WAL mode?
    #     with self.engine.connect() as connection:
    #         connection.execute(text("PRAGMA journal_mode=WAL;"))
    #     return sessionmaker(bind=self.engine)()

    def _construct_database_url(self) -> str:
        database_url = self.config.get("database_url")
        if not database_url:
            error_message = "database_url is missing in the configuration"
            logger.error(error_message)
            raise ValueError(error_message)

        return database_url.format(**self.config)

    def create_database_if_not_exists(self) -> None:
        """SQLite database is automatically made if it does not exist."""
        logger.info(f"No need to explicitly create an SQLite database. Path: {self.database_url}")
        self._create_db_tables()


class PostgreSQL(DatabaseManager):
    # specific methods or attributes for PostgreSQL

    def _construct_database_url(self) -> str:
        """Construct the database URL based on the loaded configuration."""
        return f"postgresql://{self.config.get('user')}:{self.config.get('password')}@{self.config.get('host')}:{self.config.get('port')}/{self.config.get('database_name')}"

    def create_database_if_not_exists(self) -> None:
        """Create a new PostgreSQL database if it doesn't exist."""

        logger.info(f"Checking and potentially creating PostgreSQL database: {self.db_name}")
        # Connect to the PostgreSQL server using the default "postgres" database
        standard_database_url = self.database_url.replace(self.db_name, "postgres")
        engine = create_engine(standard_database_url)
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")

        existing_databases = conn.execute(text("SELECT datname FROM pg_database;")).fetchall()
        if self.db_name not in [d[0] for d in existing_databases]:
            try:
                # Create a new database
                conn.execute(text(f"CREATE DATABASE {self.db_name}"))
                # Create tables
                self._create_db_tables()
                logger.info(f"Database '{self.db_name}' created successfully!")
            except exc.SQLAlchemyError as e:
                logger.error(f"Error: {e}")
        conn.close()


def get_database_manager(db_name: str, config_file: str = "database.ini") -> DatabaseManager:
    config = DatabaseManager.load_config(db_name, config_file)
    db_type = config.get("database_type")

    if db_type == "sqlite":
        return SQLite(db_name, config_file)
    elif db_type == "postgres":
        return PostgreSQL(db_name, config_file)
    else:
        error_msg = f"Database type {db_type} not supported"
        logger.error(error_msg)
        raise ValueError(error_msg)
