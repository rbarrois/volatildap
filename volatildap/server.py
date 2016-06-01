# -*- coding: utf-8 -*-

"""Temporary LDAP server based on OpenLdap for tests."""

from __future__ import unicode_literals


import base64
import logging
import os
import re
import random
import socket
import subprocess
import tempfile
import time
import sys


logger = logging.getLogger(__name__.split('.')[0])


DEFAULT_SUFFIX = 'dc=example,dc=org'
DEFAULT_ROOTDN = 'cn=testadmin,%s' % DEFAULT_SUFFIX
DEFAULT_SCHEMAS = (
    'core.schema',
)
DEFAULT_STARTUP_DELAY = 30
DEFAULT_SLAPD_DEBUG = 0


class LdapError(Exception):
    """Exceptions for volatildap"""


class PathError(LdapError):
    """Exception for missing paths"""


class OpenLdapPaths(object):
    """Collection of Openldap-related paths, distribution dependend."""

    def __init__(self):
        self.schemas = os.path.dirname(self._find_file('core.schema', self._SCHEMA_DIRS))

        self.slapd = self._find_file('slapd', self._BINARY_DIRS)
        self.ldapadd = self._find_file('ldapadd', self._BINARY_DIRS)
        self.ldapsearch = self._find_file('ldapsearch', self._BINARY_DIRS)
        self.slaptest = self._find_file('slaptest', self._BINARY_DIRS)

    def _find_file(self, needle, candidates):
        """Find the first directory containing a given candidate file."""
        for candidate in candidates:
            fullpath = os.path.join(candidate, needle)
            if os.path.isfile(fullpath):
                return fullpath
        raise PathError("Unable to locate file %s; tried %s" % (needle, candidates))

    _SCHEMA_DIRS = [
        '/etc/openldap/schema',
        '/usr/local/openldap/schema',
    ]
    _BINARY_DIRS = [
        '/usr/sbin',
        '/usr/bin',
        '/usr/lib/openldap',
        '/usr/local/sbin',
        '/usr/local/bin',
    ] + os.environ.get('PATH', '').split(':')


class LdapServer(object):
    _DATASUBDIR = 'ldif-data'

    def __init__(self,
                 suffix=DEFAULT_SUFFIX,
                 rootdn=DEFAULT_ROOTDN,
                 rootpw='',
                 schemas=DEFAULT_SCHEMAS,
                 initial_data=None,
                 skip_missing_schemas=False,
                 max_server_startup_delay=DEFAULT_STARTUP_DELAY,
                 port=None,
                 slapd_debug=DEFAULT_SLAPD_DEBUG,
                 ):

        self.paths = OpenLdapPaths()
        self.suffix = suffix
        self.rootdn = rootdn
        self.rootpw = rootpw or self._generate_password()
        self.schemas = list(self._locate_schemas(schemas, skip_missing_schemas))
        self.initial_data = initial_data or {}
        self.max_server_startup_delay = max_server_startup_delay
        self.port = port or find_available_port()
        self.slapd_debug = slapd_debug

        self._tempdir = None
        self._process = None

    def _generate_password(self):
        chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return ''.join(
            random.choice(chars)
            for _i in range(20)
        )

    def _locate_schemas(self, schemas, skip_missing_schemas):
        """Locate all schemas (look in openldap store).

        If skip_missing_schemas is True, ignore missing schemas;
        otherwise, raise.
        """
        for schema in schemas:
            if schema == os.path.abspath(schema):
                schema_file = schema
            else:
                schema_file = os.path.join(self.paths.schemas, schema)

            if os.path.isfile(schema_file):
                # Absolute path: use it.
                yield schema_file
            elif skip_missing_schemas:
                logger.warning("Unable to locate schema %s at %s", schema, schema_file)
            else:
                raise PathError("Unable to locate schema %s at %s" % (schema, schema_file))

    def _configuration_lines(self):
        def quote(base, *args):
            return base % tuple("%s" % arg.replace('\\', '\\\\').replace('"', '\\"') for arg in args)
        for schema in self.schemas:
            yield quote('include %s', schema)
        yield quote('database ldif')
        yield quote('directory %s', self._datadir)
        yield quote('suffix %s', self.suffix)
        yield quote('rootdn %s', self.rootdn)
        yield quote('rootpw %s', self.rootpw)

    def _normalize_dn(self, dn):
        if not dn.endswith(self.suffix):
            return '%s,%s' % (dn, self.suffix)
        else:
            return dn

    def start(self):
        try:
            if self._process is None:
                self._setup()
                self._start()
            else:
                self._clear()
            self._populate()
        except Exception as e:
            logger.exception("Error starting LDAP server: %s", e)
            self._shutdown()
            raise

    def stop(self):
        self._shutdown()

    def add(self, data):
        lines = '\n'.join(self._data_as_ldif(data))
        ldif = lines.encode('utf-8')

        logger.info("Adding data %r", ldif)
        sp = subprocess.Popen(
            [
                self.paths.ldapadd,
                '-x',
                '-D', self.rootdn,
                '-w', self.rootpw,
                '-H', self.uri,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        stdout, _stderr = sp.communicate(ldif)
        if sp.wait() != 0:
            raise RuntimeError("ldapadd failed: %s" % stdout)

    def get(self, dn):
        dn = self._normalize_dn(dn)
        logger.info("Fetching data at %s", dn)
        sp = subprocess.Popen(
            [
                self.paths.ldapsearch,
                '-x',
                '-D', self.rootdn,
                '-w', self.rootpw,
                '-H', self.uri,
                '-LLL',  # As LDIF
                '-b', dn,  # Fetch this specific DN
                '-s', 'base',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = sp.communicate()
        retcode = sp.wait()
        if retcode == 32:
            # Not found
            raise KeyError("Entry %s not found: %r" % (dn, stderr))
        if retcode != 0:
            raise RuntimeError("ldapsearch failed with code %d: %r" % (retcode, stderr))

        return ldif_to_dict(stdout)

    def _data_as_ldif(self, data):
        for dn, attributes in data.items():
            yield ldif_encode('dn', self._normalize_dn(dn))
            for attribute, values in sorted(attributes.items()):
                for value in values:
                    yield ldif_encode(attribute, value)
            yield ''

    @property
    def uri(self):
        return 'ldap://localhost:%d' % self.port

    @property
    def _datadir(self):
        return os.path.join(self._tempdir.name, self._DATASUBDIR)

    @property
    def _slapd_conf(self):
        return os.path.join(self._tempdir.name, 'slapd.conf')

    @property
    def _core_data(self):
        return {
            self.suffix: {
                'objectClass': ['dcObject', 'organization'],
                'dc': [self.suffix.split(',')[0][len('dc='):]],
                'o': [self.suffix],
            },
        }

    def _setup(self):
        self._tempdir = tempfile.TemporaryDirectory()
        logger.info("Setting up openldap server in %s", self._tempdir.name)

        # Create datadir
        os.mkdir(self._datadir)

        # Write configuration
        with open(self._slapd_conf, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self._configuration_lines()))

        slaptest = subprocess.Popen([
            self.paths.slaptest,
            '-f', self._slapd_conf,
        ])
        if slaptest.wait() != 0:
            raise RuntimeError("Testing configuration failed.")

    def _start(self):
        """Start the server."""
        assert self._tempdir is not None
        assert self._process is None
        self._process = subprocess.Popen(
            [
                self.paths.slapd,
                '-f', self._slapd_conf,
                '-h', self.uri,
                '-d', str(self.slapd_debug),
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        self._poll_slapd(timeout=self.max_server_startup_delay)

    def _populate(self):
        """Populate a *running* server with initial data."""
        self.add(self._core_data)
        if self.initial_data:
            self.add(self.initial_data)

    def _clear(self):
        for root, dirs, files in os.walk(self._datadir, topdown=False):
            for name in files:
                os.unlink()
            for name in dirs:
                os.rmdir(os.path.join(root, name))

        # We must not delete the ldif datastore.
        assert os.path.exists(self._datadir)

    def _poll_slapd(self, timeout=DEFAULT_STARTUP_DELAY):
        """Poll slapd port until available."""

        s = socket.socket()
        begin = time.time()
        while time.time() < begin + timeout:
            if self._process.poll() is not None:
                raise RuntimeError("LDAP server has exited before starting listen.")

            try:
                s.connect(('localhost', self.port))
            except socket.error:
                # Not ready yet, sleep
                time.sleep(0.5)
            else:
                s.close()
                return

        raise RuntimeError("LDAP server not responding within %s seconds." % timeout)

    def _shutdown(self):
        if self._process is not None:
            self._process.terminate()
            self._process.wait()
            self._process = None
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __del__(self):
        self.stop()

    def __repr__(self):
        if self._process:
            state = 'running:%s' % self._process.pid
        else:
            state = 'stopped'
        return '<%s at %s [%s]>' % (self.__class__.__name__, self.uri, state)


def find_available_port():
    """Find an available port.

    Simple trick: open a socket to localhost, see what port was allocated.

    Could fail in highly concurrent setups, though.
    """
    s = socket.socket()
    s.bind(('localhost', 0))
    _address, port = s.getsockname()
    s.close()
    return port


# Valid characters for a non-base64-encoded LDIF value
_BASE_LDIF = [
    chr(i) for i in range(20, 128)
    if chr(i) not in [' ', '<', ':']
]


def ldif_encode(attr, value):
    """Encode a attribute: value pair for the LDIF format.

    See RFC2849 for details.

    Rules are:
    - Text containing only chars <= 127 except control, ' ', '<', ':'
      is passed as-is
    - Other text is encoded through UTF-8 and base64-encoded
    - Binary data is simply base64-encoded

    Returns:
        A 'key: value' or 'key:: b64value' text line.
    """
    if isinstance(value, bytes):
        return '%s:: %s' % (attr, base64.b64encode(value).decode('ascii'))
    elif any(c not in _BASE_LDIF for c in value):
        return '%s:: %s' % (attr, base64.b64encode(value.encode('utf-8')).decode('ascii'))
    else:
        return '%s: %s' % (attr, value)


def ldif_to_dict(ldif_lines):
    attributes = {}
    for line in ldif_lines.decode('ascii').split('\n'):
        if not line.strip():
            continue
        m = re.match(r'(\w+)(:?): (.*)', line.strip())
        if m is None:
            raise ValueError("Invalid line in ldif output: %r" % line)

        field, is_extended, value = m.groups()
        if is_extended:
            value = base64.b64decode(value.encode('ascii'))
        else:
            value = value.encode('ascii')
        attributes.setdefault(field, []).append(value)
    return attributes
