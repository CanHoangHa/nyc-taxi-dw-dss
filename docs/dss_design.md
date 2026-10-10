# DSS Design — Day-ahead Taxi Demand

## Forecast contract

- Horizon: all 24 hours of day D, issued after data through 23:59 on D−1.
- Grain: forecast date × local hour × eligible pickup taxi zone.
- Target: valid pickup `trip_count`.
- Gate B inputs: `mart.mart_demand_coverage`,
  `mart.mart_zone_hour_demand`, and eligible members from
  `dw.dim_taxi_zone`.
- Recommendation scope: TLC LocationIDs 1–263 only.
- Gate C outputs: `dss.model_run` and `dss.zone_hour_forecast`.

The mart is sparse. `src/dss/dense_grid.py` fills missing zone-hour cells with
zero only for dates proven complete by `mart.mart_demand_coverage`. A gap
between covered months remains unavailable and fails before feature creation.

## Leakage boundary and features

Each time series is grouped by stable `pickup_location_id × demand_hour`, so a
one-row shift represents the same zone-hour on the preceding calendar day.
Calendar-distance checks prevent a coverage gap from being treated as an
adjacent day.

The feature contract in `src/dss/features.py` includes:

- Calendar: hour, weekday, month, day of month, weekend flag.
- Exact lags: D−1, D−2, and D−7.
- Shifted rolling mean/std over seven preceding days.
- Shifted rolling median over 28 preceding days.
- Median of the preceding four matching weekdays.

Every rolling value is calculated after a one-day shift. Rows lacking the full
28-day history remain explicitly incomplete and are excluded from modeling.
Mutation tests change the target on forecast day D and verify that features
for D do not change.

## Split, baselines, and model selection

`configs/dss_q1.toml` defines the reproducible Q1 prototype:

| Split | Inclusive dates |
|---|---|
| Train | 2024-01-29 to 2024-02-29 |
| Validation | 2024-03-01 to 2024-03-15 |
| Test | 2024-03-16 to 2024-03-31 |

The January start supplies the 28-day warm-up. Q1 is a vertical-slice result,
not the final full-year experiment.

Two mandatory baselines are evaluated:

1. Seasonal naive: demand at the same zone-hour seven days earlier.
2. Same-weekday median: median of the preceding four matching weekdays.

The candidate is `HistGradientBoostingRegressor(loss="poisson")`; output is
clipped at zero. Training fits only the train split. `train` compares the
candidate and both baselines on validation WAPE and freezes the best approach.
`evaluate` is a separate command that opens the test split only after that
choice. MAE, RMSE, and WAPE are reported; WAPE is undefined rather than divided
by zero when actual demand totals zero.

## Demand level and recommendation

Historical p50/p75 thresholds are learned per zone-hour from train only. The
recommendation comparator is the fixed seasonal-naive value from D−7. It stays
independent of whichever approach wins validation; otherwise a winning
same-weekday-median forecast would be compared with itself, forcing every
ratio to 1.0 and making the High rule impossible to trigger.

```text
demand_ratio = prediction / max(historical baseline, 1)
High   = prediction >= p75 and ratio >= 1.15
Medium = prediction >= p50 or ratio >= 1.0
Low    = otherwise
```

The Gate C row includes prediction, the D−7 seasonal-naive baseline, both thresholds,
ratio, level, Vietnamese recommendation text, and an explanation of the rule
that fired. Non-actionable zones receive no dispatch recommendation.

The output supports prioritizing taxi availability. It does not optimize
routes, estimate a taxi relocation count, calculate unmet demand or profit, or
claim a causal effect.

## Modules and ownership

| Module | Responsibility |
|---|---|
| `contracts.py`, `repository.py` | Validate and read only the published Gate B interfaces |
| `dense_grid.py`, `features.py` | Covered zero-fill and leakage-safe features |
| `split.py`, `baseline.py`, `models.py`, `evaluation.py` | Experiment contract and comparison |
| `recommendation.py` | Deterministic decision rule and explanation |
| `persistence.py` | Atomic, versioned Gate C write and read API |
| `service.py` | Dashboard-facing use cases |
| `pipeline.py` | Independently runnable CLI orchestration |

Training artifacts are immutable Joblib files under the Git-ignored
`artifacts/models/` directory. Do not load artifacts from untrusted sources,
because Joblib uses Python pickle semantics.
