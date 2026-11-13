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
choice. Its config split must exactly match the artifact's saved split; other
settings such as output directory do not change the frozen experiment.
Forecast dates must be strictly after the saved validation end, covering both
model fitting and validation-based selection. History through D−1 may overlap
train/validation for lag and rolling features; it is not a new model fit.
Missing or invalid saved split metadata is rejected. MAE, RMSE, and WAPE are
reported; WAPE is undefined rather than divided by zero when actual demand
totals zero.

## Demand level and recommendation

Recommendation version **1.2.0** learns historical p50/p75 thresholds per
zone-hour from train only. Demand level measures the prediction relative to
that zone-hour's training history. Weekly growth is a separate signal: the
fixed D−7 comparator is used regardless of the validation-selected approach.

```text
demand_ratio = prediction / max(D−7 baseline, 1)
High   = prediction > 0 and prediction >= p75
Medium = prediction > 0 and prediction >= p50 (unless High)
Low    = otherwise
```

Version 1.1.0 required both p75 and ratio >= 1.15 for High, and allowed
ratio >= 1 for Medium. Seasonal-naive prediction equals D−7, so that rule
could never mark High even for exceptionally high demand. Version 1.2.0
separates demand magnitude from growth for every approach: stable or falling
high demand may be High, while growth from a small base does not by itself
raise the level. Zero prediction stays Low even when training quantiles are
zero. High is relative to each zone-hour, not an absolute comparison between
zones or a claim of unmet demand. No quantiles were tuned to force High counts;
this is an explicit semantic policy change, not evidence of model accuracy.
Previously persisted runs keep their saved levels and recommendation version.

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
