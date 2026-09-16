BEGIN;

CREATE TABLE IF NOT EXISTS audit.etl_batch (
    batch_id uuid PRIMARY KEY,
    dataset_name text NOT NULL,
    source_year smallint NOT NULL,
    source_month smallint NOT NULL,
    source_file text NOT NULL,
    source_file_sha256 char(64) NOT NULL,
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamptz,
    source_row_count bigint,
    loaded_row_count bigint,
    valid_count bigint,
    quarantined_count bigint,
    rejected_count bigint,
    status text NOT NULL,
    error_message text,

    CONSTRAINT etl_batch_dataset_check
        CHECK (dataset_name = 'yellow_taxi'),
    CONSTRAINT etl_batch_year_check
        CHECK (source_year = 2024),
    CONSTRAINT etl_batch_month_check
        CHECK (source_month BETWEEN 1 AND 12),
    CONSTRAINT etl_batch_source_file_check
        CHECK (btrim(source_file) <> ''),
    CONSTRAINT etl_batch_sha256_check
        CHECK (source_file_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT etl_batch_status_check
        CHECK (status IN ('started', 'succeeded', 'failed', 'skipped')),
    CONSTRAINT etl_batch_finished_at_check
        CHECK (
            (status = 'started' AND finished_at IS NULL)
            OR
            (status <> 'started' AND finished_at IS NOT NULL)
        ),
    CONSTRAINT etl_batch_time_order_check
        CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT etl_batch_error_message_check
        CHECK (
            (status = 'failed' AND nullif(btrim(error_message), '') IS NOT NULL)
            OR
            (status <> 'failed' AND error_message IS NULL)
        ),
    CONSTRAINT etl_batch_source_row_count_check
        CHECK (source_row_count IS NULL OR source_row_count >= 0),
    CONSTRAINT etl_batch_loaded_row_count_check
        CHECK (loaded_row_count IS NULL OR loaded_row_count >= 0),
    CONSTRAINT etl_batch_valid_count_check
        CHECK (valid_count IS NULL OR valid_count >= 0),
    CONSTRAINT etl_batch_quarantined_count_check
        CHECK (quarantined_count IS NULL OR quarantined_count >= 0),
    CONSTRAINT etl_batch_rejected_count_check
        CHECK (rejected_count IS NULL OR rejected_count >= 0),
    CONSTRAINT etl_batch_success_counts_check
        CHECK (
            status <> 'succeeded'
            OR (
                source_row_count IS NOT NULL
                AND loaded_row_count IS NOT NULL
                AND source_row_count = loaded_row_count
            )
        ),
    CONSTRAINT etl_batch_classification_counts_check
        CHECK (
            (
                valid_count IS NULL
                AND quarantined_count IS NULL
                AND rejected_count IS NULL
            )
            OR (
                valid_count IS NOT NULL
                AND quarantined_count IS NOT NULL
                AND rejected_count IS NOT NULL
                AND loaded_row_count IS NOT NULL
                AND valid_count + quarantined_count + rejected_count
                    = loaded_row_count
            )
        )
);

CREATE INDEX IF NOT EXISTS etl_batch_month_status_idx
    ON audit.etl_batch (
        dataset_name,
        source_year,
        source_month,
        status,
        started_at DESC
    );

CREATE TABLE IF NOT EXISTS raw.yellow_trip (
    "VendorID" integer,
    "tpep_pickup_datetime" timestamp without time zone,
    "tpep_dropoff_datetime" timestamp without time zone,
    "passenger_count" bigint,
    "trip_distance" double precision,
    "RatecodeID" bigint,
    "store_and_fwd_flag" text,
    "PULocationID" integer,
    "DOLocationID" integer,
    "payment_type" bigint,
    "fare_amount" double precision,
    "extra" double precision,
    "mta_tax" double precision,
    "tip_amount" double precision,
    "tolls_amount" double precision,
    "improvement_surcharge" double precision,
    "total_amount" double precision,
    "congestion_surcharge" double precision,
    "Airport_fee" double precision,

    batch_id uuid NOT NULL,
    source_dataset text NOT NULL,
    source_year smallint NOT NULL,
    source_month smallint NOT NULL,
    source_file text NOT NULL,
    source_file_sha256 char(64) NOT NULL,
    source_row_number bigint NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT yellow_trip_source_identity_pk
        PRIMARY KEY (
            source_dataset,
            source_year,
            source_month,
            source_row_number
        ),
    CONSTRAINT yellow_trip_batch_fk
        FOREIGN KEY (batch_id)
        REFERENCES audit.etl_batch (batch_id),
    CONSTRAINT yellow_trip_dataset_check
        CHECK (source_dataset = 'yellow_taxi'),
    CONSTRAINT yellow_trip_year_check
        CHECK (source_year = 2024),
    CONSTRAINT yellow_trip_month_check
        CHECK (source_month BETWEEN 1 AND 12),
    CONSTRAINT yellow_trip_source_file_check
        CHECK (btrim(source_file) <> ''),
    CONSTRAINT yellow_trip_sha256_check
        CHECK (source_file_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT yellow_trip_row_number_check
        CHECK (source_row_number >= 0)
);

CREATE INDEX IF NOT EXISTS yellow_trip_batch_id_idx
    ON raw.yellow_trip (batch_id);

COMMIT;
