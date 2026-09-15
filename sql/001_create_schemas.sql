\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS mart;

COMMENT ON SCHEMA audit IS 'Pipeline metadata, batch status, and reconciliation';
COMMENT ON SCHEMA raw IS 'Source-aligned ingested records with lineage metadata';
COMMENT ON SCHEMA staging IS 'Canonical records and data-quality classification';
COMMENT ON SCHEMA dw IS 'Dimensional warehouse facts and dimensions';
COMMENT ON SCHEMA mart IS 'Analytics and decision-support marts';
