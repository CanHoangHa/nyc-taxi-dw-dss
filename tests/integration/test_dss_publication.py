"""Real PostgreSQL migration, idempotent publication and same-date selection."""
from dataclasses import replace
from datetime import date
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg

from dss.contracts import ContractError
from dss.persistence import ForecastRepository, ModelRunMetadata
from taxi_dw.db import open_connection
from tests.dss.test_persistence import forecast_rows


def metadata(**changes):
    return replace(ModelRunMetadata(
        model_name="random_forest", model_version="test", feature_version="test",
        recommendation_version="test", train_start_date=date(2024, 1, 29),
        train_end_date=date(2024, 2, 29), validation_start_date=date(2024, 3, 1),
        validation_end_date=date(2024, 3, 15), metrics={"selection_validation": {"wape": 0.17}},
        git_commit_sha="test", fit_kind="refit", fit_start_date=date(2024, 1, 29),
        fit_end_date=date(2024, 3, 31), fit_seconds=337.5229522), **changes)


def sql_source(name, schema):
    text = Path("sql", name).read_text()
    text = "\n".join(line for line in text.splitlines()
                     if not line.startswith("\\") and line not in ("BEGIN;", "COMMIT;"))
    return (text.replace("dss.", schema + ".")
            .replace("SCHEMA IF NOT EXISTS dss", "SCHEMA IF NOT EXISTS " + schema)
            .replace("SCHEMA dss", "SCHEMA " + schema))


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "set RUN_DB_TESTS=1")
class DssPublicationIntegrationTests(unittest.TestCase):
    def test_upgrade_twice_preserves_legacy_metadata_and_constraints(self):
        schema = "test_dss_" + uuid4().hex
        with open_connection() as connection, connection.transaction(force_rollback=True):
            connection.execute(sql_source("003_create_dss_tables.sql", schema))
            connection.execute(f"INSERT INTO {schema}.model_run "
                               "(run_id,model_name,model_version,feature_version,recommendation_version,"
                               "train_start_date,train_end_date,validation_start_date,validation_end_date,"
                               "metrics_json,git_commit_sha) VALUES "
                               "(%s,'legacy','1','1','1','2024-01-29','2024-02-29',"
                               "'2024-03-01','2024-03-15','{}','old')", (uuid4(),))
            before = connection.execute(f"SELECT row_to_json(r) FROM {schema}.model_run r").fetchone()[0]
            for _ in range(2):
                connection.execute(sql_source("004_dss_actual_fit.sql", schema))
            after = connection.execute(f"SELECT row_to_json(r) FROM {schema}.model_run r").fetchone()[0]
            self.assertEqual({key: after[key] for key in before}, before)
            self.assertEqual(after["fit_kind"], "selection")
            self.assertIsNone(after["fit_end_date"])
            for assignment in ("train_end_date='2024-03-01'", "fit_kind='refit'",
                               "fit_seconds='NaN'", "fit_seconds='Infinity'",
                               "artifact_sha256='invalid'"):
                with self.subTest(assignment=assignment), self.assertRaises(psycopg.errors.CheckViolation):
                    with connection.transaction():
                        connection.execute(f"UPDATE {schema}.model_run SET " + assignment)

    def test_publication_reuses_only_matching_artifact_date_and_latest_run_is_deterministic(self):
        digest = uuid4().hex * 2
        with open_connection() as connection, connection.transaction(force_rollback=True):
            repository = ForecastRepository(connection)
            meta = metadata(artifact_sha256=digest)
            first = repository.save_run(meta, forecast_rows())
            second = repository.save_run(meta, forecast_rows())
            self.assertEqual(first, second)
            self.assertEqual(connection.execute("SELECT count(*) FROM dss.model_run WHERE artifact_sha256=%s",
                                                (digest,)).fetchone()[0], 1)
            self.assertEqual(repository.latest_run(date(2024, 4, 1))["run_id"], first)
            self.assertEqual(repository.latest_run(date(2024, 4, 1))["fit_end_date"], date(2024, 3, 31))
            changed = forecast_rows()
            changed["predicted_trip_count"] += 1
            with self.assertRaisesRegex(ContractError, "differs"):
                repository.save_run(meta, changed)
            with self.assertRaisesRegex(ContractError, "differs"):
                repository.save_run(replace(meta, fit_seconds=12), forecast_rows())
            # Same-date legacy run can be newer, but the timestamp and UUID tie-break is explicit.
            legacy = replace(meta, fit_kind="selection", fit_start_date=None, fit_end_date=None,
                             fit_seconds=None, artifact_sha256=None, metrics={"validation": {"wape": 0.2}})
            third = repository.save_run(legacy, forecast_rows())
            selected = repository.latest_run(date(2024, 4, 1))["run_id"]
            self.assertEqual(selected, max(first, third))  # same transaction -> same created_at
            self.assertEqual(len(repository.read_forecasts(first)), 24)
            self.assertEqual(len(repository.read_forecasts(third)), 24)
