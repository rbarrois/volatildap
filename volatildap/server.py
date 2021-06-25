# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

"""Temporary LDAP server based on OpenLdap for tests."""

from __future__ import unicode_literals

import codecs
import logging
import os
import random
import socket
import subprocess
import sys
import tempfile
import time

from . import control
from . import core

logger = logging.getLogger(__name__.split('.')[0])


DEFAULT_SUFFIX = 'dc=example,dc=org'
DEFAULT_ROOTDN = 'cn=testadmin,%s' % DEFAULT_SUFFIX
DEFAULT_SCHEMAS = (
    'core.schema',
)
DEFAULT_STARTUP_DELAY = 15
DEFAULT_SLAPD_DEBUG = 0


class OpenLdapPaths(object):
    """Collection of Openldap-related paths, distribution dependend."""

    def __init__(self):
        self.schemas = os.path.dirname(self._find_file('core.schema', self._SCHEMA_DIRS))

        self.slapd = self._find_file('slapd', self._BINARY_DIRS)
        self.ldapadd = self._find_file('ldapadd', self._BINARY_DIRS)
        self.ldapdelete = self._find_file('ldapdelete', self._BINARY_DIRS)
        self.ldapsearch = self._find_file('ldapsearch', self._BINARY_DIRS)
        self.slaptest = self._find_file('slaptest', self._BINARY_DIRS)

    def _find_file(self, needle, candidates):
        """Find the first directory containing a given candidate file."""
        for candidate in candidates:
            fullpath = os.path.join(candidate, needle)
            if os.path.isfile(fullpath):
                return fullpath
        raise core.PathError("Unable to locate file %s; tried %s" % (needle, candidates))

    _SCHEMA_DIRS = [
        '/etc/ldap/schema',  # Debian
        '/etc/openldap/schema',  # Gentoo
        '/usr/local/openldap/schema',  # Manual install
    ]
    _BINARY_DIRS = [
        '/usr/sbin',
        '/usr/bin',
        '/usr/lib/openldap',
        '/usr/lib64/openldap',
        '/usr/local/sbin',
        '/usr/local/bin',
    ] + os.environ.get('PATH', '').split(':')


class LdapServer(core.BaseServer):
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
                 host='localhost',
                 slapd_debug=DEFAULT_SLAPD_DEBUG,
                 tls_config=None,
                 control_address=(),
                 ):

        self.paths = OpenLdapPaths()
        self.suffix = suffix
        self.rootdn = rootdn
        self.rootpw = rootpw or self._generate_password()
        self.schemas = list(self._locate_schemas(schemas, skip_missing_schemas))
        self.initial_data = initial_data or {}
        self.max_server_startup_delay = max_server_startup_delay
        self.port = port or find_available_port()
        self.host = host
        self.slapd_debug = slapd_debug
        self.tls_config = tls_config
        self.control = None

        self._tempdir = None
        self._process = None

        if control_address:
            self.control = control.ControlServer(
                server_address=control_address,
                ldap_server=self,
            )

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
                raise core.PathError("Unable to locate schema %s at %s" % (schema, schema_file))

    def _configuration_lines(self):
        def quote(base, *args):
            return base % tuple("%s" % arg.replace('\\', '\\\\').replace('"', '\\"') for arg in args)

        for schema in self.schemas:
            yield quote('include %s', schema)

        if self.tls_config:
            yield quote('TLSCACertificateFile %s', self._tls_chain_path)
            yield quote('TLSCertificateFile %s', self._tls_certificate_path)
            yield quote('TLSCertificateKeyFile %s', self._tls_key_path)

        yield quote('moduleload back_mdb')
        yield quote('database mdb')
        yield quote('directory %s', self._datadir)
        yield quote('suffix %s', self.suffix)
        yield quote('rootdn %s', self.rootdn)
        yield quote('rootpw %s', self.rootpw)

    def start(self):
        logger.info("Starting LDAP server")
        try:
            if self.control is not None:
                logger.info("Starting control server")
                self.control.start()
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

    def wait(self, timeout=None):
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise core.TimeoutExpired(str(e), timeout) from e

    def stop(self):
        logger.info("Shutting down LDAP server")
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
            stderr=subprocess.PIPE,
            env=self._subprocess_env
        )
        stdout, stderr = sp.communicate(ldif)
        retcode = sp.wait()
        if retcode != 0:
            raise RuntimeError("ldapadd failed with code %d: %s %s" % (retcode, stdout, stderr))

    def add_ldif(self, lines):
        self.add(core.ldif_to_entries(lines))

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
            env=self._subprocess_env
        )
        stdout, stderr = sp.communicate()
        retcode = sp.wait()
        if retcode == 32:
            # Not found
            raise KeyError("Entry %s not found: %r" % (dn, stderr))
        if retcode != 0:
            raise RuntimeError("ldapsearch failed with code %d: %r" % (retcode, stderr))

        entries = core.ldif_to_entries(stdout)
        return entries[dn]

    def get_ldif(self, dn):
        entry = self.get(dn)
        lines = self._data_as_ldif({dn: entry})
        return '\n'.join(lines)

    def reset(self):
        """Reset all entries except inital ones."""
        logger.info("Resetting the LDAP server to its initial data")
        self._clear()
        self._populate()

    @property
    def _datadir(self):
        return os.path.join(self._tempdir.name, self._DATASUBDIR)

    @property
    def _slapd_conf(self):
        return os.path.join(self._tempdir.name, 'slapd.conf')

    @property
    def _tls_ca_bundle_path(self):
        return os.path.join(self._tempdir.name, 'ca-bundle.pem')

    @property
    def _tls_chain_path(self):
        return os.path.join(self._tempdir.name, 'chain.pem')

    @property
    def _tls_certificate_path(self):
        return os.path.join(self._tempdir.name, 'server.crt')

    @property
    def _tls_key_path(self):
        return os.path.join(self._tempdir.name, 'server.key')

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

        # Manage TLS
        if self.tls_config:
            chain = [cert.strip() for cert in self.tls_config.chain]

            with codecs.open(self._tls_ca_bundle_path, 'w', encoding='utf-8') as f:
                f.write(self.tls_config.root)
            with codecs.open(self._tls_chain_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(chain))
            with codecs.open(self._tls_certificate_path, 'w', encoding='utf-8') as f:
                f.write(self.tls_config.certificate)
            with codecs.open(self._tls_key_path, 'w', encoding='utf-8') as f:
                f.write(self.tls_config.key)

        # Write configuration
        with codecs.open(self._slapd_conf, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self._configuration_lines()))

        slaptest = subprocess.Popen([
            self.paths.slaptest,
            '-f', self._slapd_conf,
            '-u',  # only test the config file
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
        logger.info("Preparing to clear all data")
        sp = subprocess.Popen(
            [
                self.paths.ldapsearch,
                '-x',
                '-D', self.rootdn,
                '-w', self.rootpw,
                '-H', self.uri,
                '-LLL',  # As LDIF
                '-b', self.suffix,  # The whole tree
                '-s', 'sub',  # All children
                'dn',  # Fetch only the 'dn' field
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._subprocess_env
        )
        stdout, stderr = sp.communicate()
        retcode = sp.wait()
        if retcode != 0:
            raise RuntimeError("ldapsearch failed with code %d: %r" % (retcode, stderr))

        data = core.ldif_to_entries(stdout)
        dns = data.keys()
        # Remove the furthest first
        dns = sorted(dns, key=lambda dn: (len(dn), dn), reverse=True)

        logger.info("Deleting entries %s", dns)
        sp = subprocess.Popen(
            [
                self.paths.ldapdelete,
                '-x',
                '-D', self.rootdn,
                '-w', self.rootpw,
                '-H', self.uri,
            ] + dns,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._subprocess_env
        )
        _stdout, stderr = sp.communicate()
        retcode = sp.wait()
        if retcode != 0:
            raise RuntimeError("ldapdelete failed with code %d: %r" % (retcode, stderr))

    def _poll_slapd(self, timeout=DEFAULT_STARTUP_DELAY):
        """Poll slapd port until available."""

        begin = time.time()
        time.sleep(0.5)
        while time.time() < begin + timeout:
            if self._process.poll() is not None:
                raise RuntimeError("LDAP server has exited before starting listen.")

            s = socket.socket()
            try:
                s.connect((self.host, self.port))
            except socket.error:
                # Not ready yet, sleep
                time.sleep(0.5)
            else:
                return
            finally:
                s.close()

        raise RuntimeError("LDAP server not responding within %s seconds." % timeout)

    def _shutdown(self):
        if self._process is not None:
            self._process.terminate()
            self._process.wait()
            self._process = None
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    @property
    def _subprocess_env(self):
        """Prepare the environment for a subprocess file."""
        env = dict(os.environ)
        env.update(
            LDAPTLS_CACERT=self._tls_ca_bundle_path,
            LDAPTLS_REQCERT='hard',
        )
        return env

    def __del__(self):
        if self._process is not None:
            logger.warning("Server %s removed from memory before being stopped!", self)

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
