import argparse
import json
from pathlib import Path
import sys

from .config import PREPARED_DIRECTORY, PROJECT_ROOT, add_connection_arguments


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run_parser = commands.add_parser(
        'run', help='Calculate one IFIC file (ificNNNN.mdb = space, brificNNNN.mdb = terrestrial)'
    )
    run_parser.add_argument('files', nargs='+', help='IFIC files in data/, e.g. ific3074.mdb brific3076.mdb')
    run_parser.add_argument('--output-root', type=Path, default=PROJECT_ROOT / 'output')
    run_parser.add_argument('--no-export', action='store_true', help='Do not refresh the app data afterwards')
    prepare_parser = commands.add_parser('prepare', help='Extract inputs locally; no database connection')
    prepare_parser.add_argument('--root', type=Path, default=PROJECT_ROOT)
    prepare_parser.add_argument('--output', type=Path, default=PREPARED_DIRECTORY)
    prepare_parser.add_argument('--catalog-only', action='store_true')
    prepare_parser.add_argument('--only', action='append', help='Exact filename; repeat to select several')
    match_parser = commands.add_parser('match-frequencies', help='Create satellite/Finnish frequency-overlap candidates')
    match_parser.add_argument('--prepared', type=Path, default=PREPARED_DIRECTORY)
    match_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/frequency-matches')
    match_parser.add_argument('--space-file', action='append', help='Exact MDB filename; repeat to select several')
    match_parser.add_argument(
        '--adjacent-channels', type=int, default=1,
        help='Also flag satellite bands within N protected bandwidths of a Finnish band (0 = co-frequency only)',
    )
    cases_parser = commands.add_parser('consolidate-frequency-matches', help='Group overlap rows into review cases')
    cases_parser.add_argument(
        '--input', type=Path, default=PROJECT_ROOT / 'output/frequency-matches/frequency_match_candidates.jsonl'
    )
    cases_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/frequency-cases')
    classify_parser = commands.add_parser('classify-frequency-cases', help='Classify review cases using public ITU codes')
    classify_parser.add_argument(
        '--input', type=Path, default=PROJECT_ROOT / 'output/frequency-cases/frequency_review_cases.jsonl'
    )
    classify_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/classified-cases')
    readiness_parser = commands.add_parser('check-calculation-readiness', help='Assemble and validate future PFD inputs')
    readiness_parser.add_argument('--prepared', type=Path, default=PREPARED_DIRECTORY)
    readiness_parser.add_argument(
        '--queue', type=Path, default=PROJECT_ROOT / 'output/classified-cases/future_calculation_queue.jsonl'
    )
    readiness_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/calculation-readiness')
    coverage_parser = commands.add_parser('criteria-coverage', help='Report which review cases have a pfd criterion')
    coverage_parser.add_argument(
        '--input', type=Path, default=PROJECT_ROOT / 'output/frequency-cases/frequency_review_cases.jsonl'
    )
    coverage_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/pfd-criteria')
    pfd_parser = commands.add_parser('calculate-pfd', help='Worst-case pfd and margins against RR Table 21-4')
    pfd_parser.add_argument('--readiness', type=Path, default=PROJECT_ROOT / 'output/calculation-readiness')
    pfd_parser.add_argument(
        '--cases', type=Path, default=PROJECT_ROOT / 'output/frequency-cases/frequency_review_cases.jsonl'
    )
    pfd_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/pfd-calculations')
    pfd_parser.add_argument('--near-margin-db', type=float, default=3.0,
                            help='Margins below this (but >= 0) are reported as near_limit')
    rebuild_parser = commands.add_parser(
        'rebuild-analysis', help='Rebuild, validate and publish every default analysis stage'
    )
    rebuild_parser.add_argument('--output-root', type=Path, default=PROJECT_ROOT / 'output')
    rebuild_parser.add_argument('--near-margin-db', type=float, default=3.0)
    rebuild_parser.add_argument('--ific', default='ific3074.mdb', help='Space IFIC MDB in data/ to evaluate (ificNNNN.mdb)')
    terrestrial_parser = commands.add_parser(
        'analyze-terrestrial',
        help='Compare consecutive terrestrial issues and calculate P.1546 land-mobile field strengths',
    )
    terrestrial_parser.add_argument('--prepared', type=Path, default=PROJECT_ROOT / 'output/terrestrial-prepared')
    terrestrial_parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'output/terrestrial-ific3076')
    terrestrial_parser.add_argument('--issue', type=int, default=3076)
    terrestrial_parser.add_argument('--near-margin-db', type=float, default=3.0)
    load_parser = commands.add_parser('load', help='Load records into an already migrated database')
    add_connection_arguments(load_parser)
    load_parser.add_argument('--prepared', type=Path, default=PREPARED_DIRECTORY)
    migrate_parser = commands.add_parser('migrate', help='Apply pending database migrations')
    add_connection_arguments(migrate_parser)
    args = parser.parse_args(argv)
    if args.command in {'load', 'migrate'} and not args.ca.is_file():
        parser.error('CA certificate file does not exist')
    try:
        if args.command == 'run':
            from .analysis.run_issues import run, run_many
            if len(args.files) == 1:
                results = [run(args.files[0], args.output_root)]
                print(json.dumps(results[0], indent=2))
            else:
                results = run_many(args.files, args.output_root)
                print(json.dumps(results, indent=2))
            if not args.no_export:
                import subprocess
                export = PROJECT_ROOT / 'backend' / 'scripts' / 'export_frontend_data.py'
                subprocess.run([sys.executable, str(export)], cwd=PROJECT_ROOT, check=True,
                               stdout=sys.stderr)
            return 1 if any(r.get('status') == 'failed' for r in results) else 0
        if args.command == 'prepare':
            from .ingestion.prepare import prepare
            manifest = prepare(args.root.resolve(), args.output.resolve(), args.catalog_only, args.only)
            print(f"Prepared {len(manifest['datasets'])} inputs; errors: {len(manifest['errors'])}")
            return 0 if manifest['complete'] else 1
        if args.command == 'match-frequencies':
            from .analysis.frequency_matching import run
            print(json.dumps(run(args.prepared, args.output, args.space_file, args.adjacent_channels)))
            return 0
        if args.command == 'consolidate-frequency-matches':
            from .analysis.case_consolidation import run
            print(json.dumps(run(args.input, args.output)))
            return 0
        if args.command == 'classify-frequency-cases':
            from .analysis.case_classification import run
            print(json.dumps(run(args.input, args.output)))
            return 0
        if args.command == 'check-calculation-readiness':
            from .analysis.calculation_readiness import run
            print(json.dumps(run(args.prepared, args.queue, args.output)))
            return 0
        if args.command == 'calculate-pfd':
            from .analysis.pfd_calculation import run
            print(json.dumps(run(args.readiness, args.cases, args.output, args.near_margin_db)))
            return 0
        if args.command == 'criteria-coverage':
            from .analysis.criteria_coverage import run
            print(json.dumps(run(args.input, args.output)))
            return 0
        if args.command == 'rebuild-analysis':
            from .analysis.pipeline import run
            print(json.dumps(run(args.output_root, args.near_margin_db, args.ific)))
            return 0
        if args.command == 'analyze-terrestrial':
            from .analysis.terrestrial_pipeline import run
            print(json.dumps(run(args.prepared.resolve(), args.output.resolve(), args.issue, args.near_margin_db)))
            return 0
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
        if args.command in {'prepare', 'rebuild-analysis', 'run'}:
            print(f'{args.command.capitalize()} failed ({type(error).__name__}): {error}', file=sys.stderr)
        else:
            print(f'{args.command.capitalize()} failed ({type(error).__name__}); transaction rolled back.', file=sys.stderr)
        return 1
    return 0

