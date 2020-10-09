# This software is distributed under the two-clause BSD license.

import argparse
import logging
import sys

from . import LOCALHOST_TLS_CONFIG
from . import core
from . import server


def launch(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--port', default='',
        help="Port to listen on; empty for a dynamic port",
    )
    parser.add_argument(
        '--host', default='localhost',
        help="Host to listen on; defaults to localhost",
    )
    parser.add_argument(
        '--suffix', default=server.DEFAULT_SUFFIX,
        help="LDAP suffix",
    )
    parser.add_argument(
        '--rootdn', default=server.DEFAULT_ROOTDN,
        help="Distinguished Name of LDAP admin user",
    )
    parser.add_argument(
        '--rootpw', default='',
        help="Password of LDAP admin user",
    )
    parser.add_argument(
        '--debug', default=server.DEFAULT_SLAPD_DEBUG, type=int,
        help="slapd debug level",
    )
    parser.add_argument(
        '--control',
        help="Start the HTTP control server on this address",
    )
    parser.add_argument(
        '--initial', type=argparse.FileType('rb'),
        help="Load initial objects from the provided LDIF file",
    )
    parser.add_argument(
        '--schemas', nargs='*', default=server.DEFAULT_SCHEMAS,
        help="Schemas to load (multi-valued)",
    )
    parser.add_argument(
        '--tls', action='store_true',
        help="Enable TLS, using a built-in stack",
    )

    args = parser.parse_args(argv)
    if args.initial:
        lines = b''.join(args.initial)
        initial = core.ldif_to_entries(lines)
    else:
        initial = {}
    if args.tls:
        tls_config = LOCALHOST_TLS_CONFIG
    else:
        tls_config = None

    if args.control:
        address, port = args.control.rsplit(':', 1)
        control_address = (address, int(port))
    else:
        control_address = ()

    instance = server.LdapServer(
        suffix=args.suffix,
        rootdn=args.rootdn,
        rootpw=args.rootpw,
        schemas=args.schemas,
        port=int(args.port) if args.port else None,
        host=args.host,
        slapd_debug=args.debug,
        initial_data=initial,
        tls_config=tls_config,
        control_address=control_address,
    )
    instance.start()
    sys.stdout.write("LDAP server listening on %s\n" % instance.uri)
    sys.stdout.write("Credentials: %s / %s\n" % (instance.rootdn, instance.rootpw))
    if control_address:
        sys.stdout.write("Control server listening on %s\n" % (instance.control.server_address,))

    try:
        instance.wait()
    finally:
        instance.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    launch(sys.argv[1:])
