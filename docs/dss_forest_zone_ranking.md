# Random Forest and zone interval ranking

This document preserves the original Q1 experiment. For the subsequent fixed
Q1 refit and April check, see [the protocol](dss_april_protocol.md) and
[the April report](dss_april_evaluation.md). Statements below about April not
yet being loaded describe the state at the original Q1 experiment.

For publication of the existing Q1-refitted RF into PostgreSQL/dashboard (without
training again), see [the publication runbook](dss_refit_publication_runbook.md).

Base: origin/develop `3b339197a75a2a16307b2f2d6efd6a36f449615a`.
Implementation branch: `feature/dss-poisson-zone-ranking`.
The branch name is historical; the active fourth method is Random Forest.

## Methods and selection

Keep D−7, same-weekday median over four weeks, and
HistGradientBoostingRegressor(loss="poisson"). Remove the experimental GLM
from training, selection, UI labels and active-model tests. The boosting model
with Poisson loss remains a separate, supported method.

Fixed RF configuration (declared before Q1 training): 64 estimators,
max_depth=16, min_samples_leaf=10, max_features=0.7, n_jobs=2, random_state=42.
No grid search. One-hot encode pickup_location_id, with unknown categories
ignored. Pass the remaining existing numeric/calendar/history features through;
trees do not require scaling. The encoder is fitted only on train. Bounds on
trees, depth, leaf support and workers limit resource use, not statistical risk.

Use identical feature availability, target, dates and rows for all four methods.
Train is January 29–February 29, validation March 1–15. Select minimum validation
WAPE. Record MAE/RMSE/WAPE on train and validation, plus actual model fit times.
Baselines have no fitted estimator (fit time recorded as zero). Equal WAPE
retains insertion order: boosting, D−7, median, RF. Do not force RF to win.
Keep forecast-after-validation, split-matching and recommendation policy 1.2.0.

Artifacts store named/versioned methods, RF settings, sklearn version, train
bounds/counts, metrics, timing, and source provenance. Source provenance records
HEAD, an explicit dirty flag and SHA256 hashes for an allowlist of DSS/dashboard
code, script, config and requirements. The comparison script also saves those
exact source files in an immutable sibling .source directory. No secrets/data
are copied. Code hashes describe the experiment source; HEAD alone does not
identify a dirty working tree. Documentation/tests outside this allowlist are
not part of that source snapshot. Paths use unique IDs; old outputs are not
replaced. Small floating-point differences may occur in threaded RF predictions.

## Archived experimental artifacts and runs

The two pre-GLM artifacts remain supported, including forecasting and three-method
evaluation:

- dss-3fd1705a-61ab-40f5-926b-173cdeb19aa8.joblib
- dss-8a9bb0d4-4535-4c61-b368-11e5d1f8eed7.joblib

The archived GLM experiment remains on disk:
`artifacts/models/dss-poisson-b58ece6a-3aca-489a-89d4-dbb37a10d27f.joblib`.
Its validation MAE/RMSE/WAPE was 16.2902 / 70.4949 / 89.4181%; median was selected.
Its forecast run `91221df7-d59a-4379-9326-a6f3bbdb7f02` is preserved.
The earlier runs eb5b167d-5ec1-4dfd-89b6-bc3ea3d31c7e and
 a7d505b6-828c-4bfe-8dea-64e3872d82d5 are also preserved.

Loading an experimental GLM TrainingArtifact now raises ContractError explicitly,
even when it selected a baseline; it is never silently treated as a new RF or
legacy artifact. Direct GLM model loading/prediction is rejected too. Old DB
runs/metrics remain readable by service/dashboard (unknown historical method
names render as their stored name). This support limit applies only to the
experimental pickle, not to saved DB results. Do not modify/archive-delete these
outputs to conceal a previous experiment. Trusted-local-joblib and compatible
Python/sklearn requirements still apply.

## Ranking bug and fix (ranking policy 1.1.0)

Previously candidates were inferred only from surviving forecast rows. Losing
all rows for zone 2 made zone 2 disappear from the completeness check, so an
explicit (1,2) request silently returned zone 1.

Resolve candidates before testing hour coverage. Production service/dashboard
supply the full taxi-zone dimension using one bulk reference query, including
borough and operational eligibility. No query per zone. Select the borough's
eligible LocationIDs 1–263 and optional explicit zone IDs from that reference.
Reject unknown IDs, wrong-borough IDs and ineligible IDs with distinct errors.
Then reject missing whole candidate zones, missing hours, duplicate hours,
forecast/reference disagreement, nonfinite or negative measures. Do not fill
missing forecasts with zero. Dropdowns also use reference zones, so absent zones
remain visible and cannot quietly disappear from the selection UI.

A complete zone_reference is required even for direct standalone calls. An absent
zone cannot be discovered from forecast rows alone, so the API no longer permits
that ambiguous fallback. The dimension's non-operational unknown member has no
LocationID; the bulk reference query excludes only that null-ID sentinel. It
retains identified ineligible zones for explicit eligibility error messages.
An empty reference borough returns no rows. A known run missing every forecast
cell in a nonempty candidate set raises an incomplete-data error.

Intervals remain [start,end), 0–24: 06:00–10:00 includes 6,7,8,9;
23:00–24:00 includes 23. Split overnight intervals by date. Legacy hourly
ranked_recommendations/zone_hour_detail APIs retain inclusive endpoints.
Each zone has one total predicted pickup row plus matching D−7 total and hour
support. Rank predicted totals descending, with competition ranks 1,1,3.
Zone ID only stabilizes tie display. Preserve hourly labels/reasons. Zero total
explicitly means no recommendation to add taxis. There is no AHP, vehicle
shortage/count estimate, confidence score or error penalty.

## Ranking evaluation

Freeze A=Top K predicted totals and B=Top K D−7 totals for the same date,
borough, interval, candidate zones and K. Cut ties for both lists by ascending
zone ID and select exactly K; this is a deterministic convention, not higher
business priority among tied zones. Only then align complete actual cells.
Report selected-zone actual pickups and their share of all candidate pickups,
with K, IDs and support. Zero denominator gives None, not a zero share.
K is declared before looking at actuals; do not optimize it on test.

Q1 March 16–31 has been viewed before. Every subsequent use is explicitly
retrospective/exploratory. The script retains a fixed illustrative March 16,
Manhattan, [6,10), K=10 case. It is one slice, not a general ranking assessment.
Pickup concentration does not establish dispatch effectiveness, profit or
waiting-time reduction. No historical confidence/error display was added.
April has not been loaded or used for selection. Freeze the model/ranking policy
before the next separately authorized April check.

## Reproduction and local output policy

Run from repo root:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$env:OMP_NUM_THREADS='2'
.\.venv\Scripts\python.exe scripts/compare_dss_q1.py --persist-forecast
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

The script uses existing Q1 marts without ingestion or DW rebuild. It generates
a new RF artifact, source snapshot, report and optionally a new forecast run.
The snapshot is verified against hashes before saving the artifact.

.gitignore excludes all generated artifacts/, tmp/ and the exact local
`docs/INGESTION_SELF_IMPLEMENTATION_GUIDE.md`. No broad *.json or scripts/ rule.
No generated file was tracked, so none was untracked. Source, reproducibility
scripts, tests and this handoff remain visible to Git. No output was deleted.

## Current run and verification

RF artifact: `artifacts/models/dss-rf-9a687651-d038-4f06-8ec2-1bbaa5946f3a.joblib`.
Train has 201,984 rows, validation 94,680 rows, each identical across methods.

| Method | Train MAE | Train RMSE | Train WAPE | Validation MAE | Validation RMSE | Validation WAPE |
|---|---:|---:|---:|---:|---:|---:|
| D−7 | 3.5088 | 12.4154 | 21.90% | 3.9553 | 13.9744 | 21.71% |
| Weekday median | 2.9361 | 10.6079 | 18.32% | 3.4296 | 12.2634 | 18.83% |
| Gradient boosting (Poisson loss) | 2.5712 | 8.6196 | 16.05% | 3.4708 | 12.6303 | 19.05% |
| Random Forest (selected) | 2.2507 | 7.6240 | 14.05% | 3.2281 | 11.4841 | 17.72% |

RF fit: 117.9517 seconds, including preprocessing; boosting fit: 2.2789 seconds.
The first run saved the model and source snapshot, then failed at ranking because
the dimension's null-ID sentinel was initially rejected. The model was not
refitted or overwritten. Use --artifact to resume with the unchanged fixed
model. A separate evaluation source hash/snapshot records the sentinel and
candidate-reference fixes. On resumed scoring total_training_seconds is null;
original per-model fit_seconds remain in the artifact and report.

RF's train-to-validation WAPE gap is about 3.67 percentage points. This is a
useful diagnostic, not proof against overfitting or of future performance.
Only one RF configuration was evaluated; no test or April tuning was done.
The ranking reference is the current warehouse dimension, not a historical
versioned eligibility snapshot. Future changes to eligibility need a separate
policy decision for comparisons across saved runs.

Default final suite: 122 tests, 104 passed and 18 DB tests skipped. Targeted
PostgreSQL persistence passed independently. Related model/ranking/AppTest
checks passed, including the missing-entire-zone regression, borough vs
eligibility errors, interval boundaries, duplicates, missing hours, zero totals,
negative/nonfinite measures, train-only encoding, round trips and compatibility.
AppTest also verifies that a missing whole zone stops the dashboard ranking.
No full unrelated ingestion DB suite was rerun in this turn. Browser visual
inspection has not been performed.

The experiment ran before commit/push, with source dirty relative to HEAD; the
report and snapshot identify this explicitly. Subsequent commits do not change
that experiment provenance. Existing artifacts/run data are retained.


New forecast run: `3f421939-8822-4d2c-a2cb-a6c8cdda6a90`, 2024-03-16, 6,312 cells.
Independent SQL sums match both predicted and D−7 zone totals in the service.
Report: `artifacts/models/dss-rf-9a687651-d038-4f06-8ec2-1bbaa5946f3a-report-3f8d7e32-1c1c-4de2-8542-57bd3273ab5c.json`.

The report separates original training source/snapshot from final evaluation
source/snapshot; both have working_tree_dirty=true. The archived original
training source includes the earlier ranking code, before the null-ID handling
and mandatory-reference fix. No model refitting occurred during resumed scoring.
To repeat scoring without training, pass --artifact with this joblib path;
--persist-forecast creates another run, so omit it for read-only scoring.

Retrospective/exploratory forecast Top 10: 3032 actual pickups, 41.7458% of 7263 candidate pickups across 69 Manhattan zones, March 16 [6,10).

Retrospective/exploratory d_minus_7 Top 10: 2856 actual pickups, 39.3226% of 7263 candidate pickups across 69 Manhattan zones, March 16 [6,10).


Final live DB AppTest passed after explicitly selecting the new run's March 16
forecast date (the default was an existing April 1 forecast, not April actuals).
It verified the Random Forest label, 69 Manhattan ranking rows, 276 [6,10)
hourly detail rows and 69 [23,24) detail rows, with no app errors/warnings.
All three pre-existing runs remain readable with 6,312 rows each. A simulation
on real persisted RF forecasts rejects missing whole zones with and without
explicit IDs. Training/evaluation snapshot files verified against their hashes.
All three old artifact SHA256 hashes match the audit before this turn's changes.

Verified using git check-ignore -v: artifacts/q1-poisson-comparison.log,
artifacts/q1-rf-comparison.log, artifacts/rf-full-tests-final.log and the new RF
joblib match artifacts/; tmp/ZONE_RANKING_FINDINGS_2026_10_27.md matches tmp/;
docs/INGESTION_SELF_IMPLEMENTATION_GUIDE.md matches the exact local guide rule.
Source scripts/compare_dss_q1.py, src/dss/ranking.py, new tests and this handoff
were checked separately and are not ignored. No tracked generated file existed
under artifacts/, tmp/ or the local guide path; no git untrack operation occurred.
