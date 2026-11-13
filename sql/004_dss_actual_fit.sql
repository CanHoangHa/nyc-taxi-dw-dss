\set ON_ERROR_STOP on

BEGIN;

-- Existing dates remain the immutable selection split. No historical rows change.
ALTER TABLE dss.model_run
    ADD COLUMN IF NOT EXISTS fit_kind text NOT NULL DEFAULT 'selection',
    ADD COLUMN IF NOT EXISTS fit_start_date date,
    ADD COLUMN IF NOT EXISTS fit_end_date date,
    ADD COLUMN IF NOT EXISTS fit_seconds double precision,
    ADD COLUMN IF NOT EXISTS artifact_sha256 text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'dss.model_run'::regclass
                     AND conname = 'model_run_actual_fit_check') THEN
        ALTER TABLE dss.model_run ADD CONSTRAINT model_run_actual_fit_check CHECK (
            (fit_kind = 'selection' AND
                ((fit_start_date IS NULL AND fit_end_date IS NULL) OR
                 (fit_start_date IS NOT NULL AND fit_end_date IS NOT NULL AND
                  fit_start_date = train_start_date AND fit_end_date = train_end_date)))
            OR
            (fit_kind = 'refit' AND fit_start_date IS NOT NULL AND fit_end_date IS NOT NULL
                AND fit_start_date = train_start_date AND fit_end_date >= validation_end_date
                AND NOT (metrics_json ? 'validation'))
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'dss.model_run'::regclass
                     AND conname = 'model_run_fit_seconds_check') THEN
        ALTER TABLE dss.model_run ADD CONSTRAINT model_run_fit_seconds_check CHECK (
            fit_seconds IS NULL OR (fit_seconds >= 0 AND fit_seconds < 'Infinity'::float8)
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'dss.model_run'::regclass
                     AND conname = 'model_run_artifact_sha256_check') THEN
        ALTER TABLE dss.model_run ADD CONSTRAINT model_run_artifact_sha256_check CHECK (
            artifact_sha256 IS NULL OR artifact_sha256 ~ '^[a-f0-9]{64}$'
        );
    END IF;
END $$;

COMMENT ON COLUMN dss.model_run.train_start_date IS 'Selection training start, not refit start';
COMMENT ON COLUMN dss.model_run.train_end_date IS 'Selection training end, not refit end';
COMMENT ON COLUMN dss.model_run.validation_start_date IS 'Original model selection validation start';
COMMENT ON COLUMN dss.model_run.validation_end_date IS 'Original model selection validation end';
COMMENT ON COLUMN dss.model_run.fit_start_date IS 'Actual estimator fit data start; NULL on legacy runs (selection train applies)';
COMMENT ON COLUMN dss.model_run.fit_end_date IS 'Actual estimator fit data end; forecast must follow this and selection validation end';
COMMENT ON COLUMN dss.model_run.fit_seconds IS 'Recorded original fit duration, never publication duration; NULL when unavailable';

CREATE INDEX IF NOT EXISTS model_run_artifact_sha256_idx
    ON dss.model_run (artifact_sha256) WHERE artifact_sha256 IS NOT NULL;

COMMIT;
