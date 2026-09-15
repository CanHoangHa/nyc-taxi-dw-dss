"""Environment-backed application configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable {name} is not set")
    return value


def _bounded_integer(
    environment: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = environment.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error

    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}, got {value}"
        )
    return value


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated settings required to connect to the project database."""

    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int = 5

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> DatabaseSettings:
        """Build settings from a mapping, defaulting to the process environment."""

        values = os.environ if environment is None else environment
        return cls(
            host=values.get("POSTGRES_HOST", "localhost").strip() or "localhost",
            port=_bounded_integer(
                values,
                "POSTGRES_PORT",
                default=5432,
                minimum=1,
                maximum=65535,
            ),
            database=_required(values, "POSTGRES_DB"),
            user=_required(values, "POSTGRES_USER"),
            password=_required(values, "POSTGRES_PASSWORD"),
            connect_timeout=_bounded_integer(
                values,
                "POSTGRES_CONNECT_TIMEOUT",
                default=5,
                minimum=1,
                maximum=60,
            ),
        )

    def as_connection_kwargs(self) -> dict[str, str | int]:
        """Return keyword arguments accepted by ``psycopg.connect``."""

        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": self.connect_timeout,
        }
