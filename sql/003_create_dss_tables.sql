\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS dss;

COMMENT ON SCHEMA dss IS
    'Versioned decision-support model runs and zone-hour forecasts';

CREATE TABLE IF NOT EXISTS dss.model_run (
    run_id uuid PRIMARY KEY,
    model_name text NOT NULL,
    model_version text NOT NULL,
    feature_version text NOT NULL,
    recommendation_version text NOT NULL,
    train_start_date date NOT NULL,
    train_end_date date NOT NULL,
    validation_start_date date NOT NULL,
    validation_end_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_status text NOT NULL DEFAULT 'succeeded',
    metrics_json jsonb NOT NULL,
    git_commit_sha text NOT NULL,

    CONSTRAINT model_run_name_check CHECK (btrim(model_name) <> ''),
    CONSTRAINT model_run_version_check CHECK (btrim(model_version) <> ''),
    CONSTRAINT model_run_feature_version_check
        CHECK (btrim(feature_version) <> ''),
    CONSTRAINT model_run_recommendation_version_check
        CHECK (btrim(recommendation_version) <> ''),
    CONSTRAINT model_run_train_dates_check
        CHECK (train_start_date <= train_end_date),
    CONSTRAINT model_run_validation_dates_check
        CHECK (validation_start_date <= validation_end_date),
    CONSTRAINT model_run_split_order_check
        CHECK (train_end_date < validation_start_date),
    CONSTRAINT model_run_status_check
        CHECK (run_status IN ('succeeded')),
    CONSTRAINT model_run_git_sha_check CHECK (btrim(git_commit_sha) <> '')
);

CREATE TABLE IF NOT EXISTS dss.zone_hour_forecast (
    run_id uuid NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    forecast_date date NOT NULL,
    demand_hour smallint NOT NULL,
    pickup_zone_key text NOT NULL,
    pickup_location_id integer NOT NULL,
    borough text NOT NULL,
    zone_name text NOT NULL,
    predicted_trip_count double precision NOT NULL,
    baseline_trip_count double precision NOT NULL,
    historical_p50 double precision NOT NULL,
    historical_p75 double precision NOT NULL,
    demand_ratio double precision NOT NULL,
    demand_level text NOT NULL,
    recommendation text NOT NULL,
    recommendation_reason text NOT NULL,
    is_actionable boolean NOT NULL,

    CONSTRAINT zone_hour_forecast_pk PRIMARY KEY (
        run_id,
        forecast_date,
        demand_hour,
        pickup_zone_key
    ),
    CONSTRAINT zone_hour_forecast_run_fk FOREIGN KEY (run_id)
        REFERENCES dss.model_run (run_id) ON DELETE RESTRICT,
    CONSTRAINT zone_hour_forecast_hour_check CHECK (demand_hour BETWEEN 0 AND 23),
    CONSTRAINT zone_hour_forecast_zone_key_check
        CHECK (btrim(pickup_zone_key) <> ''),
    CONSTRAINT zone_hour_forecast_location_check
        CHECK (pickup_location_id > 0),
    CONSTRAINT zone_hour_forecast_borough_check CHECK (btrim(borough) <> ''),
    CONSTRAINT zone_hour_forecast_zone_name_check CHECK (btrim(zone_name) <> ''),
    CONSTRAINT zone_hour_forecast_prediction_check
        CHECK (predicted_trip_count >= 0),
    CONSTRAINT zone_hour_forecast_baseline_check
        CHECK (baseline_trip_count >= 0),
    CONSTRAINT zone_hour_forecast_p50_check CHECK (historical_p50 >= 0),
    CONSTRAINT zone_hour_forecast_p75_check
        CHECK (historical_p75 >= historical_p50),
    CONSTRAINT zone_hour_forecast_ratio_check CHECK (demand_ratio >= 0),
    CONSTRAINT zone_hour_forecast_level_check
        CHECK (demand_level IN ('Low', 'Medium', 'High', 'Not applicable')),
    CONSTRAINT zone_hour_forecast_recommendation_check
        CHECK (btrim(recommendation) <> ''),
    CONSTRAINT zone_hour_forecast_reason_check
        CHECK (btrim(recommendation_reason) <> ''),
    CONSTRAINT zone_hour_forecast_actionable_check
        CHECK (is_actionable = (pickup_location_id BETWEEN 1 AND 263))
);

CREATE INDEX IF NOT EXISTS zone_hour_forecast_date_rank_idx
    ON dss.zone_hour_forecast (
        forecast_date,
        is_actionable,
        demand_level,
        predicted_trip_count DESC
    );

CREATE INDEX IF NOT EXISTS model_run_created_at_idx
    ON dss.model_run (created_at DESC);

COMMIT;
