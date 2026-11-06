"""Apply packaged SQL migrations once, verifying previously applied checksums."""

import hashlib
from importlib.resources import files


def migrate(connection):
    directory = files('app').joinpath('db', 'migrations')
    scripts = sorted((path for path in directory.iterdir() if path.name.endswith('.sql')), key=lambda path: path.name)
    applied = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(742019231)")
        connection.execute('CREATE SCHEMA IF NOT EXISTS ingestion')
        connection.execute(
            'CREATE TABLE IF NOT EXISTS ingestion.schema_migrations ('
            'name text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())'
        )
        previous = dict(connection.execute('SELECT name,sha256 FROM ingestion.schema_migrations').fetchall())
        unknown = set(previous) - {script.name for script in scripts}
        if unknown:
            raise ValueError('Database contains migrations missing from this checkout')
        for script in scripts:
            content = script.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if script.name in previous:
                if previous[script.name] != digest:
                    raise ValueError(f'Applied migration changed: {script.name}')
                continue
            connection.execute(content.decode('utf-8'))
            connection.execute('INSERT INTO ingestion.schema_migrations(name,sha256) VALUES (%s,%s)', (script.name, digest))
            applied.append(script.name)
    return applied

