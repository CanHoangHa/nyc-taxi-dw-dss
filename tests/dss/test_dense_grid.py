"""Sparse-to-dense demand-grid tests."""

from __future__ import annotations

import unittest

import pandas as pd

from dss.contracts import ContractError
from dss.dense_grid import build_dense_demand
from tests.dss.fixtures import coverage_months, eligible_zones, sparse_demand


class DenseDemandTests(unittest.TestCase):
    def test_zero_fills_only_eligible_zones_and_reconciles(self):
        dense = build_dense_demand(
            sparse_demand(),
            coverage_months(1),
            eligible_zones(),
        )
        self.assertEqual(len(dense), 31 * 24 * 2)
        self.assertEqual(dense["trip_count"].sum(), 12)
        self.assertEqual(set(dense["pickup_location_id"]), {1, 2})
        zero_cell = dense.loc[
            (dense["demand_date"] == pd.Timestamp("2024-01-01"))
            & (dense["demand_hour"] == 9)
            & (dense["pickup_location_id"] == 1),
            "trip_count",
        ]
        self.assertEqual(zero_cell.tolist(), [0])

    def test_requested_slice_has_exact_dense_shape(self):
        dense = build_dense_demand(
            sparse_demand(),
            coverage_months(1),
            eligible_zones(),
            start_date=pd.Timestamp("2024-01-01"),
            end_date=pd.Timestamp("2024-01-02"),
        )
        self.assertEqual(len(dense), 2 * 24 * 2)
        self.assertEqual(dense["trip_count"].sum(), 12)

    def test_does_not_fill_gap_between_covered_months(self):
        with self.assertRaisesRegex(ContractError, "uncovered"):
            build_dense_demand(
                sparse_demand(),
                coverage_months(1, 3),
                eligible_zones(),
                start_date=pd.Timestamp("2024-01-31"),
                end_date=pd.Timestamp("2024-03-01"),
            )

    def test_rejects_sparse_rows_outside_coverage_for_full_build(self):
        frame = sparse_demand()
        frame.loc[0, "demand_date"] = "2024-02-01"
        with self.assertRaisesRegex(ContractError, "outside reconciled coverage"):
            build_dense_demand(frame, coverage_months(1), eligible_zones())


if __name__ == "__main__":
    unittest.main()
