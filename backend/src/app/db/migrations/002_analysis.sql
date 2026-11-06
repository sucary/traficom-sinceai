CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analysis;

CREATE OR REPLACE FUNCTION core.try_bigint(value text) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    RETURN value::bigint;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION core.try_numeric(value text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
BEGIN
    IF value !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' THEN
        RETURN NULL;
    END IF;
    RETURN value::numeric;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION core.try_date(value text) RETURNS date
LANGUAGE plpgsql STABLE STRICT AS $$
BEGIN
    IF value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}($| )' THEN
        RETURN NULL;
    END IF;
    RETURN left(value, 10)::date;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE VIEW core.source_records AS
SELECT r.dataset_id, r.source_table, r.source_row, d.file_name,
       d.issue AS dataset_issue, d.is_synthetic, r.payload
FROM ingestion.source_rows r
JOIN ingestion.datasets d USING (dataset_id);

CREATE OR REPLACE VIEW core.space_notices AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'ntc_id') AS notice_id,
       payload->>'adm' AS administration,
       core.try_bigint(payload->>'wic_no') AS publication_issue,
       core.try_date(payload->>'d_wic') AS publication_date,
       core.try_date(payload->>'d_rcv') AS received_date,
       payload->>'ntc_type' AS notice_type,
       payload->>'prov' AS provision,
       payload->>'act_code' AS action_code,
       payload->>'wic_part' AS publication_part,
       payload->>'st_cur' AS status_code
FROM core.source_records WHERE source_table = 'notice';

CREATE OR REPLACE VIEW core.space_groups AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'grp_id') AS group_id,
       core.try_bigint(payload->>'ntc_id') AS notice_id,
       payload->>'emi_rcp' AS emission_reception_code,
       payload->>'beam_name' AS beam_name,
       core.try_bigint(payload->>'wic_no') AS publication_issue,
       core.try_numeric(payload->>'freq_min') AS frequency_min_mhz,
       core.try_numeric(payload->>'freq_max') AS frequency_max_mhz,
       core.try_numeric(payload->>'bdwdth') AS bandwidth_khz
FROM core.source_records WHERE source_table = 'grp';

-- ITU SNS Preface, May 2026, freq: frequencies in MHz, bandwidth in kHz.
CREATE OR REPLACE VIEW core.space_frequencies AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'ntc_id') AS notice_id,
       core.try_bigint(payload->>'grp_id') AS group_id,
       core.try_bigint(payload->>'seq_no') AS sequence_number,
       core.try_numeric(payload->>'freq_mhz') AS frequency_mhz,
       core.try_numeric(payload->>'freq_mhz') * 1000000 AS frequency_hz,
       core.try_numeric(payload->>'freq_min') * 1000000 AS frequency_min_hz,
       core.try_numeric(payload->>'freq_max') * 1000000 AS frequency_max_hz,
       core.try_numeric(payload->>'bdwdth') * 1000 AS bandwidth_hz,
       payload->>'emi_rcp' AS emission_reception_code,
       payload->>'beam_name' AS beam_name,
       core.try_bigint(payload->>'wic_no') AS publication_issue
FROM core.source_records WHERE source_table = 'freq';

CREATE OR REPLACE VIEW core.space_frequency_notices AS
SELECT f.*, n.source_row AS notice_source_row, n.administration,
       n.notice_type, n.provision, n.publication_date AS notice_publication_date,
       n.publication_issue AS notice_publication_issue
FROM core.space_frequencies f
LEFT JOIN core.space_notices n
  ON n.dataset_id = f.dataset_id AND n.notice_id = f.notice_id;

CREATE OR REPLACE VIEW core.space_assignments AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'grp_id') AS group_id,
       core.try_bigint(payload->>'seq_no') AS sequence_number,
       core.try_numeric(payload->>'freq_mhz') * 1000000 AS frequency_hz,
       core.try_numeric(payload->>'freq_assgn') AS assigned_frequency_source,
       payload->>'freq_sym' AS source_frequency_unit_code
FROM core.source_records WHERE source_table = 'assgn';

CREATE OR REPLACE VIEW core.space_emissions AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'grp_id') AS group_id,
       core.try_bigint(payload->>'seq_no') AS sequence_number,
       payload->>'design_emi' AS emission_designator,
       core.try_numeric(payload->>'pep_max') AS peak_power_source,
       core.try_numeric(payload->>'pwr_ds_max') AS power_density_source
FROM core.source_records WHERE source_table = 'emiss';

CREATE OR REPLACE VIEW core.space_geo_satellites AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'ntc_id') AS notice_id,
       payload->>'sat_name' AS satellite_name,
       core.try_numeric(payload->>'long_nom') AS nominal_longitude_deg
FROM core.source_records WHERE source_table = 'geo';

CREATE OR REPLACE VIEW core.space_non_geo_satellites AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'ntc_id') AS notice_id,
       payload->>'sat_name' AS satellite_name,
       core.try_bigint(payload->>'nbr_plane') AS orbital_plane_count,
       payload->>'ref_body' AS reference_body_code
FROM core.source_records WHERE source_table = 'non_geo';

-- TerRaSys units and station classifications remain source values pending validation.
CREATE OR REPLACE VIEW core.terrestrial_assignments AS
SELECT dataset_id, source_table, source_row, file_name, dataset_issue,
       core.try_bigint(payload->>'terrakey') AS terra_key,
       payload->>'assgn_id' AS assignment_id,
       payload->>'adm' AS administration,
       payload->>'stn_cls' AS station_class_code,
       payload->>'stn_type' AS station_type_code,
       payload->>'notice_typ' AS notice_type_code,
       payload->>'stage' AS stage_code,
       payload->>'intent' AS intent_code,
       payload->>'is_notice' AS is_notice_source,
       core.try_numeric(payload->>'freq_assgn') AS assigned_frequency_source,
       core.try_numeric(payload->>'freq_min') AS frequency_min_source,
       core.try_numeric(payload->>'freq_max') AS frequency_max_source,
       core.try_numeric(payload->>'bdwdth') AS bandwidth_source,
       core.try_date(payload->>'d_rcv') AS received_date
FROM core.source_records WHERE source_table = 'fxm_terra';

CREATE OR REPLACE VIEW core.protected_stations AS
SELECT s.*, d.file_name, d.issue AS dataset_issue, d.is_synthetic
FROM ingestion.stations s JOIN ingestion.datasets d USING (dataset_id);

CREATE TABLE IF NOT EXISTS analysis.runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    method text NOT NULL CHECK (length(btrim(method)) > 0),
    method_version text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    parameters jsonb NOT NULL DEFAULT '{}',
    assumptions jsonb NOT NULL DEFAULT '[]',
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_summary text,
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK (status NOT IN ('completed', 'failed') OR finished_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS analysis.run_datasets (
    run_id bigint NOT NULL REFERENCES analysis.runs(run_id),
    dataset_id text NOT NULL REFERENCES ingestion.datasets(dataset_id),
    role text NOT NULL CHECK (role IN ('space', 'terrestrial', 'protected_usage', 'regulation', 'reference')),
    PRIMARY KEY (run_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS analysis.findings (
    finding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES analysis.runs(run_id),
    finding_key text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('frequency_overlap', 'protection_criterion', 'data_quality', 'other')),
    title text NOT NULL,
    explanation text NOT NULL,
    review_status text NOT NULL DEFAULT 'unreviewed'
        CHECK (review_status IN ('unreviewed', 'needs_information', 'accepted_for_follow_up', 'dismissed')),
    frequency_min_hz numeric CHECK (frequency_min_hz >= 0),
    frequency_max_hz numeric CHECK (frequency_max_hz >= 0),
    calculation jsonb NOT NULL DEFAULT '{}',
    missing_inputs jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, finding_key),
    UNIQUE (run_id, finding_id),
    CHECK ((frequency_min_hz IS NULL) = (frequency_max_hz IS NULL)),
    CHECK (frequency_min_hz <= frequency_max_hz)
);

CREATE TABLE IF NOT EXISTS analysis.finding_evidence (
    run_id bigint NOT NULL,
    finding_id bigint NOT NULL,
    dataset_id text NOT NULL,
    source_table text NOT NULL,
    source_row integer NOT NULL,
    evidence_role text NOT NULL,
    PRIMARY KEY (finding_id, dataset_id, source_table, source_row, evidence_role),
    FOREIGN KEY (run_id, finding_id) REFERENCES analysis.findings(run_id, finding_id),
    FOREIGN KEY (run_id, dataset_id) REFERENCES analysis.run_datasets(run_id, dataset_id),
    FOREIGN KEY (dataset_id, source_table, source_row)
        REFERENCES ingestion.source_rows(dataset_id, source_table, source_row)
);

COMMENT ON SCHEMA core IS 'Typed projections of source records. Every join must include dataset_id.';
COMMENT ON SCHEMA analysis IS 'Reproducible analysis runs and expert-review candidates; overlap is not proof of interference.';
COMMENT ON COLUMN core.space_notices.dataset_issue IS 'Snapshot file issue; differs from a notice publication_issue.';
COMMENT ON COLUMN core.space_frequencies.emission_reception_code IS 'ITU E=emission, R=reception; preserve source code.';
COMMENT ON COLUMN core.space_emissions.peak_power_source IS 'Original pep_max value; no ERP/EIRP or unit conversion applied.';
