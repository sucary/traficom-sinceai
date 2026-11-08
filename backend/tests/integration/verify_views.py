from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg

from app.db.migrations import migrate
from support import local_connection


class RollbackChecks(Exception):
    pass


def main():
    with local_connection() as connection:
        before = connection.execute('SELECT count(*) FROM ingestion.source_rows').fetchone()[0]
        migrate(connection)
        assert migrate(connection) == []
        try:
            with connection.transaction():
                connection.execute("UPDATE ingestion.schema_migrations SET sha256=repeat('0',64) WHERE name='002_analysis.sql'")
                try:
                    migrate(connection)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Changed migration checksum was accepted')
                raise RollbackChecks()
        except RollbackChecks:
            pass
        assert migrate(connection) == []
        assert connection.execute('SELECT count(*) FROM ingestion.source_rows').fetchone()[0] == before
        expected = {
            'space_notices': 'notice', 'space_groups': 'grp', 'space_frequencies': 'freq',
            'space_assignments': 'assgn', 'space_emissions': 'emiss', 'space_geo_satellites': 'geo',
            'space_non_geo_satellites': 'non_geo', 'terrestrial_assignments': 'fxm_terra',
        }
        for view, table in expected.items():
            actual = connection.execute(f'SELECT count(*) FROM core.{view}').fetchone()[0]
            original = connection.execute('SELECT count(*) FROM ingestion.source_rows WHERE source_table=%s', (table,)).fetchone()[0]
            assert actual == original, (view, actual, original)
        record = connection.execute(
            "SELECT notice_id, publication_date FROM core.space_notices WHERE file_name='data/ific3074.mdb' ORDER BY source_row LIMIT 1"
        ).fetchone()
        assert record == (95500027, date(2026, 6, 23)), record
        frequency = connection.execute(
            "SELECT frequency_hz,frequency_min_hz,frequency_max_hz,bandwidth_hz "
            "FROM core.space_frequencies WHERE file_name='data/ific3074.mdb' ORDER BY source_row LIMIT 1"
        ).fetchone()
        assert frequency == (Decimal('6050000000'), Decimal('6011500000'), Decimal('6088500000'), Decimal('77000000')), frequency
        assert connection.execute(
            "SELECT core.try_bigint('bad'),core.try_bigint('999999999999999999999999'),"
            "core.try_numeric('NaN'),core.try_numeric('bad'),core.try_date('2026-02-31'),core.try_date('bad')"
        ).fetchone() == (None,) * 6
        assert connection.execute('SELECT count(*) FROM core.protected_stations').fetchone()[0] == 874
        assert connection.execute('SELECT count(*) FROM core.space_frequency_notices').fetchone()[0] == 271632
        assert connection.execute(
            "SELECT count(*) FROM core.space_frequency_notices WHERE notice_source_row IS NULL"
        ).fetchone()[0] == 0
        source = connection.execute(
            "SELECT dataset_id,source_table,source_row FROM ingestion.source_rows WHERE source_table='notice' LIMIT 1"
        ).fetchone()
        other = connection.execute(
            'SELECT dataset_id,source_table,source_row FROM ingestion.source_rows WHERE dataset_id<>%s LIMIT 1', (source[0],)
        ).fetchone()
        run_count = connection.execute('SELECT count(*) FROM analysis.runs').fetchone()[0]
        try:
            with connection.transaction():
                run_id = connection.execute(
                    "INSERT INTO analysis.runs(method,method_version) VALUES ('integration-test','1') RETURNING run_id"
                ).fetchone()[0]
                connection.execute("INSERT INTO analysis.run_datasets VALUES (%s,%s,'space')", (run_id, source[0]))
                finding_id = connection.execute(
                    "INSERT INTO analysis.findings(run_id,finding_key,kind,title,explanation) "
                    "VALUES (%s,'test','frequency_overlap','Test candidate','Test only') RETURNING finding_id", (run_id,)
                ).fetchone()[0]
                connection.execute('INSERT INTO analysis.finding_evidence VALUES (%s,%s,%s,%s,%s,%s)',
                                   (run_id, finding_id, *source, 'source_notice'))
                try:
                    with connection.transaction():
                        connection.execute('INSERT INTO analysis.finding_evidence VALUES (%s,%s,%s,%s,%s,%s)',
                                           (run_id, finding_id, *other, 'unselected_dataset'))
                except psycopg.errors.ForeignKeyViolation:
                    pass
                else:
                    raise AssertionError('Evidence from an unselected dataset was accepted')
                try:
                    with connection.transaction():
                        connection.execute(
                            "INSERT INTO analysis.findings(run_id,finding_key,kind,title,explanation,frequency_min_hz,frequency_max_hz) "
                            "VALUES (%s,'bad-band','frequency_overlap','Test','Test',200,100)", (run_id,)
                        )
                except psycopg.errors.CheckViolation:
                    pass
                else:
                    raise AssertionError('Inverted frequency range was accepted')
                raise RollbackChecks()
        except RollbackChecks:
            pass
        assert connection.execute('SELECT count(*) FROM analysis.runs').fetchone()[0] == run_count
        print(f'Passed: idempotent migration, {before:,} source rows unchanged, eight view counts, '
              'typed dates/IDs, Hz conversion, invalid-value handling, station count, '
              'evidence dataset isolation, frequency constraints, and rolled-back test findings.')


if __name__ == '__main__':
    main()
