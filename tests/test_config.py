"""Tests for environment-backed project configuration."""

import os
import unittest
from unittest.mock import patch

from taxi_dw.config import ConfigurationError, DatabaseSettings


class DatabaseSettingsTests(unittest.TestCase):
    def test_loads_dotenv_without_overriding_process_environment(self) -> None:
        process_environment = {
            "POSTGRES_DB": "process_database",
            "POSTGRES_USER": "process_user",
            "POSTGRES_PASSWORD": "process_password",
        }

        with (
            patch.dict(os.environ, process_environment, clear=True),
            patch("taxi_dw.config.load_dotenv") as load_dotenv_mock,
        ):
            settings = DatabaseSettings.from_environment()

        load_dotenv_mock.assert_called_once_with(override=False)
        self.assertEqual(settings.database, "process_database")
        self.assertEqual(settings.user, "process_user")

    def test_reads_valid_environment(self) -> None:
        settings = DatabaseSettings.from_environment(
            {
                "POSTGRES_DB": "nyc_taxi_dw",
                "POSTGRES_USER": "nyc_taxi",
                "POSTGRES_PASSWORD": "local-password",
                "POSTGRES_HOST": "database.internal",
                "POSTGRES_PORT": "55432",
                "POSTGRES_CONNECT_TIMEOUT": "7",
            }
        )

        self.assertEqual(settings.database, "nyc_taxi_dw")
        self.assertEqual(settings.user, "nyc_taxi")
        self.assertEqual(settings.host, "database.internal")
        self.assertEqual(settings.port, 55432)
        self.assertEqual(settings.connect_timeout, 7)

    def test_requires_password(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "POSTGRES_PASSWORD"):
            DatabaseSettings.from_environment(
                {
                    "POSTGRES_DB": "nyc_taxi_dw",
                    "POSTGRES_USER": "nyc_taxi",
                }
            )

    def test_rejects_invalid_port(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "POSTGRES_PORT"):
            DatabaseSettings.from_environment(
                {
                    "POSTGRES_DB": "nyc_taxi_dw",
                    "POSTGRES_USER": "nyc_taxi",
                    "POSTGRES_PASSWORD": "local-password",
                    "POSTGRES_PORT": "70000",
                }
            )


if __name__ == "__main__":
    unittest.main()
