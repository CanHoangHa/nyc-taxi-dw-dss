"""Gate B contract validation tests."""

from __future__ import annotations

import unittest

import pandas as pd

from dss.contracts import (
    ContractError,
    require_covered_range,
    validate_coverage,
    validate_sparse_demand,
    validate_zones,
)
from tests.dss.fixtures import coverage_months, eligible_zones, sparse_demand


class DssContractTests(unittest.TestCase):
    def test_accepts_gate_b_fixtures(self):
        self.assertEqual(len(validate_sparse_demand(sparse_demand())), 3)
        self.assertEqual(len(validate_coverage(coverage_months(1, 3))), 2)
        self.assertEqual(len(validate_zones(eligible_zones())), 2)

    def test_rejects_duplicate_demand_grain(self):
        frame = sparse_demand()
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ContractError, "grain"):
            validate_sparse_demand(frame)

    def test_rejects_invalid_zone_eligibility(self):
        frame = sparse_demand()
        frame.loc[frame["pickup_location_id"] == 264, "is_recommendation_eligible"] = True
        with self.assertRaisesRegex(ContractError, "zones 1-263"):
            validate_sparse_demand(frame)

    def test_rejects_non_month_coverage_bounds(self):
        frame = coverage_months(1)
        frame.loc[0, "coverage_end_date"] = pd.Timestamp("2024-01-30")
        with self.assertRaisesRegex(ContractError, "last day"):
            validate_coverage(frame)

    def test_requested_range_must_be_fully_covered(self):
        coverage = coverage_months(1, 3)
        with self.assertRaisesRegex(ContractError, "uncovered"):
            require_covered_range(coverage, pd.Timestamp("2024-01-31"), pd.Timestamp("2024-03-01"))


if __name__ == "__main__":
    unittest.main()
