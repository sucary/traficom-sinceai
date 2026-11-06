"""Command entry points for preparing data, applying migrations and loading records."""

import argparse
import json
from pathlib import Path
import sys

from .config import PREPARED_DIRECTORY, PROJECT_ROOT, add_connection_arguments


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare', help='Extract inputs locally; no database connection')
    prepare_parser.add_argument('--root', type=Path, default=PROJECT_ROOT)
    prepare_parser.add_argument('--output', type=Path, default=PREPARED_DIRECTORY)
    prepare_parser.add_argument('--catalog-only', action='store_true')
    prepare_parser.add_argument('--only', action='append', help='Exact filename; repeat to select several')
    load_parser = commands.add_parser('load', help='Load records into an already migrated database')
    add_connection_arguments(load_parser)
    load_parser.add_argument('--prepared', type=Path, default=PREPARED_DIRECTORY)
    migrate_parser = commands.add_parser('migrate', help='Apply pending database migrations')
    add_connection_arguments(migrate_parser)
    args = parser.parse_args(argv)
    if args.command != 'prepare' and not args.ca.is_file():
        parser.error('CA certificate file does not exist')
    try:
        if args.command == 'prepare':
            from .ingestion.prepare import prepare
            manifest = prepare(args.root.resolve(), args.output.resolve(), args.catalog_only, args.only)
            print(f"Prepared {len(manifest['datasets'])} inputs; errors: {len(manifest['errors'])}")
            return 0 if manifest['complete'] else 1
        from .db.connection import connect
        with connect(args) as connection:
            if args.command == 'migrate':
                from .db.migrations import migrate
                applied = migrate(connection)
                print(json.dumps({'applied': applied, 'status': 'up_to_date'}))
            else:
                from .db.loader import load
                print(json.dumps(load(connection, args.prepared.resolve())))
    except Exception as error:
        # Connection exceptions can contain sensitive details.
        if args.command == 'prepare':
            print(f'Preparation failed ({type(error).__name__}): {error}', file=sys.stderr)
        else:
            print(f'{args.command.capitalize()} failed ({type(error).__name__}); transaction rolled back.', file=sys.stderr)
        return 1
    return 0

