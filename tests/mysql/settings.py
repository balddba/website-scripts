"""MySQL integration test connection settings."""

from __future__ import annotations

import os
from typing import Self

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr


class MySQLTestSettings(BaseModel):
    """Validated MySQL connection settings for catalog integration tests.

    Attributes:
        host (str): Database host address or IP.
        port (int): Database port number.
        user (str): Database username.
        password (SecretStr): Database password; unwrap only at connect time.
        database (str): Default database schema name.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 3306
    user: str
    password: SecretStr
    database: str = "mysql"

    @classmethod
    def from_env(cls) -> Self | None:
        """Load settings from MYSQL_TEST_* environment variables.

        Returns:
            MySQLTestSettings | None: Settings when required fields are set; otherwise None.
        """
        load_dotenv()
        user = os.getenv("MYSQL_TEST_USER", "").strip()
        password = os.getenv("MYSQL_TEST_PASSWORD", "").strip()
        if not user or not password:
            return None
        host = os.getenv("MYSQL_TEST_HOST", "127.0.0.1").strip()
        port_raw = os.getenv("MYSQL_TEST_PORT", "3306").strip()
        try:
            port = int(port_raw)
        except ValueError:
            port = 3306
        database = os.getenv("MYSQL_TEST_DATABASE", "mysql").strip()
        return cls(
            host=host,
            port=port,
            user=user,
            password=SecretStr(password),
            database=database,
        )
