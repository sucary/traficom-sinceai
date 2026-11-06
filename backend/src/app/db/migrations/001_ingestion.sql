CREATE SCHEMA IF NOT EXISTS ingestion;

CREATE TABLE IF NOT EXISTS ingestion.datasets (
    dataset_id text PRIMARY KEY CHECK (length(dataset_id) = 64),
    file_name text NOT NULL,
    issue integer,
    is_synthetic boolean NOT NULL,
    metadata jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion.source_rows (
    dataset_id text NOT NULL REFERENCES ingestion.datasets(dataset_id),
    source_table text NOT NULL,
    source_row integer NOT NULL CHECK (source_row > 0),
    payload jsonb NOT NULL,
    PRIMARY KEY (dataset_id, source_table, source_row)
);

CREATE TABLE IF NOT EXISTS ingestion.stations (
    dataset_id text NOT NULL REFERENCES ingestion.datasets(dataset_id),
    source_table text NOT NULL,
    source_row integer NOT NULL,
    station_number text NOT NULL,
    tx_frequency_hz bigint,
    rx_frequency_hz bigint,
    channel_bandwidth_hz bigint,
    longitude double precision,
    latitude double precision,
    quality_flags jsonb NOT NULL,
    normalized jsonb NOT NULL,
    PRIMARY KEY (dataset_id, source_row),
    FOREIGN KEY (dataset_id, source_table, source_row)
        REFERENCES ingestion.source_rows(dataset_id, source_table, source_row)
);

CREATE INDEX IF NOT EXISTS stations_rx_frequency_idx ON ingestion.stations(rx_frequency_hz);
CREATE INDEX IF NOT EXISTS source_rows_table_idx ON ingestion.source_rows(dataset_id, source_table);
