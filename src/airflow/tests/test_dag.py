"""Run with the Airflow image's Python, rather than the project's venv."""

import copy
import runpy
import unittest

from airflow.exceptions import ParamValidationError


class IngestionDagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dag = runpy.run_path("/opt/airflow/dags/yellow_taxi_ingestion.py")["dag"]

    def test_audit_write_back_is_gated_by_staging_tests(self) -> None:
        order = ["ingest_raw", "seed_lookup", "build_staging", "test_staging", "record_dq_counts"]
        self.assertEqual(set(self.dag.task_ids), set(order))
        for earlier, later in zip(order, order[1:]):
            self.assertEqual(self.dag.get_task(later).upstream_task_ids, {earlier})
        self.assertEqual(self.dag.max_active_runs, 1)
        self.assertEqual(self.dag.max_active_tasks, 1)

    def test_invalid_year_and_month_are_rejected(self) -> None:
        for key, value in (("year", 2025), ("start_month", 0), ("end_month", 13)):
            with self.subTest(key=key, value=value):
                parameters = copy.deepcopy(self.dag.params)
                with self.assertRaises(ParamValidationError):
                    parameters[key] = value

    def test_month_values_are_passed_as_quoted_environment_arguments(self) -> None:
        ingest = self.dag.get_task("ingest_raw")
        self.assertIn('"$START_MONTH"', ingest.bash_command)
        self.assertIn('"$END_MONTH"', ingest.bash_command)
        self.assertTrue(ingest.append_env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
