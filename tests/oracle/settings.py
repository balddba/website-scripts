"""Oracle integration-test connection settings."""

from __future__ import annotations

import os
from typing import Self

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr


class OracleTestSettings(BaseModel):
    """Validated Oracle connection settings for catalog integration tests.

    Attributes:
        user (str): Database username.
        password (SecretStr): Database password; unwrap only at connect time.
        connect (str): EZCONNECT string or TNS alias.
        schema_name (str): Disposable schema that owns fixture objects.
        allow_instance_ddl (bool): When True, tests may run instance-wide DDL.
    """

    model_config = ConfigDict(extra="forbid")

    user: str
    password: SecretStr
    connect: str
    schema_name: str
    allow_instance_ddl: bool = False

    @classmethod
    def from_env(cls) -> Self | None:
        """Load settings from ORACLE_TEST_* environment variables.

        Returns:
            OracleTestSettings | None: Settings when required fields are set; otherwise None.
        """
        load_dotenv()
        user = os.getenv("ORACLE_TEST_USER", "").strip()
        password = os.getenv("ORACLE_TEST_PASSWORD", "").strip()
        connect = os.getenv("ORACLE_TEST_CONNECT", "").strip()
        schema_name = os.getenv("ORACLE_TEST_SCHEMA", "").strip()
        if not user or not password or not connect or not schema_name:
            return None
        allow_raw = os.getenv("ORACLE_TEST_ALLOW_INSTANCE_DDL", "0").strip().lower()
        return cls(
            user=user,
            password=SecretStr(password),
            connect=connect,
            schema_name=schema_name,
            allow_instance_ddl=allow_raw in {"1", "true", "yes", "on"},
        )
