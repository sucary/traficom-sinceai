"""Connection options restricted to disposable local PostgreSQL instances."""

import argparse

import psycopg


def local_connection():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=55439)
    args = parser.parse_args()
    return psycopg.connect(host='127.0.0.1', port=args.port, user='pipeline_test', dbname='postgres',
                           autocommit=True, connect_timeout=5)
