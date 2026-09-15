"""Tests for environment-backed project configuration."""

import unittest

from taxi_dw.config import ConfigurationError, DatabaseSettings


class DatabaseSettingsTests(unittest.TestCase):
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
