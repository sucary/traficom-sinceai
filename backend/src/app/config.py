"""Shared local paths and connection arguments. No dotenv files are read."""

from pathlib import Path


def project_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'backend/pyproject.toml').is_file():
            return parent
    return Path.cwd()


PROJECT_ROOT = project_root()
PREPARED_DIRECTORY = PROJECT_ROOT / 'output/prepared'


def add_connection_arguments(parser):
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--database', default='defaultdb')
    parser.add_argument('--user', default='avnadmin')
    parser.add_argument('--ca', type=Path, required=True)

