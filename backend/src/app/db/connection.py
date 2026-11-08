from getpass import getpass

import psycopg


def connect(args):
    if not args.ca.is_file():
        raise ValueError('CA certificate file does not exist')
    return psycopg.connect(
        host=args.host, port=args.port, dbname=args.database, user=args.user,
        password=getpass('Database password (hidden): '),
        sslmode='verify-full', sslrootcert=str(args.ca.resolve()),
        connect_timeout=15, autocommit=True,
    )

