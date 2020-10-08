# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

import os
import socket
import time
import unittest

import psutil

import volatildap


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


class LdapServerTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = None
        self.context = None

    def _launch_server(self, **kwargs):
        self.server = volatildap.LdapServer(**kwargs)
        self.server.start()
        self.context = {
            'dirname': self.server._tempdir.name,
            'pid': self.server._process.pid,
        }

    def tearDown(self):
        if self.server is not None:
            self.server.stop()
            self.assertServerStopped(self.context)
        super().tearDown()

    def assertServerStopped(self, context, max_delay=5):
        now = time.time()
        # Allow some time for proper shutdown
        while time.time() < now + max_delay and os.path.exists(context['dirname']):
            time.sleep(0.2)

        self.assertFalse(os.path.exists(context['dirname']))

        # Check that the process is no longer running.
        # We cannot rely solely on "the pid is no longer running", as it may
        # have been reused by the operating system.
        # If a process by that pid still exists, we'll check that we aren't its parent.
        try:
            stats = psutil.Process(context['pid'])
            ppid = stats.ppid()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process has died / is not in our context: all is fine.
            return

        self.assertNotEqual(ppid, os.getpid())


class ReadWriteTests(LdapServerTestCase):
    data = {
        'ou=test': {
            'objectClass': ['organizationalUnit'],
            'ou': ['test'],
        },
    }

    def test_initial_data(self):
        self._launch_server(initial_data=self.data)
        entry = self.server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)

    def test_post_start_add(self):
        self._launch_server()
        self.server.add(self.data)
        entry = self.server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)

    def test_get_missing_entry(self):
        self._launch_server()
        with self.assertRaises(KeyError):
            self.server.get('ou=test,dc=example,dc=org')

    def test_clear_data(self):
        self._launch_server()
        self.server.add(self.data)
        self.assertIsNotNone(self.server.get('ou=test,dc=example,dc=org'))

        self.server.start()  # Actually a restart

        # Custom data has been removed
        with self.assertRaises(KeyError):
            self.server.get('ou=test,dc=example,dc=org')

        # Core data is still there
        self.assertIsNotNone(self.server.get('dc=example,dc=org'))


class ResetTests(LdapServerTestCase):
    data = {
        'ou=test': {
            'objectClass': ['organizationalUnit'],
            'ou': ['test'],
        },
    }

    def test_cleanup(self):
        self._launch_server(initial_data=self.data)
        extra = {
            'ou=subarea,ou=test': {
                'objectClass': ['organizationalUnit'],
            },
        }
        self.server.add(extra)

        entry = self.server.get('ou=subarea,ou=test,dc=example,dc=org')
        self.server.reset()

        # Extra data should have been removed
        self.assertRaises(KeyError, self.server.get, 'ou=subarea,ou=test,dc=example,dc=org')

        # Initial data should still be here
        entry = self.server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)


class TLSTests(LdapServerTestCase):
    def test_connection(self):
        self._launch_server(tls_config=volatildap.LOCALHOST_TLS_CONFIG)
        self.assertEqual(self.server.uri[:8], 'ldaps://')
        entry = self.server.get('dc=example,dc=org')
        self.assertEqual([b'example'], entry['dc'])


class AutoCleanupTests(LdapServerTestCase):

    def test_stop(self):
        """Deleting the LdapServer object causes its cleanup."""

        self._launch_server()


class ControlTests(LdapServerTestCase):
    def setUp(self):
        super().setUp()
        self.proxy = None

    def tearDown(self):
        if self.proxy:
            self.proxy.stop()
        super().tearDown()

    def _launch_server(self, **kwargs):
        control_port = find_available_port()
        super()._launch_server(
            control_address=('localhost', control_port),
            **kwargs,
        )
        self.proxy = volatildap.ProxyServer('http://localhost:%d/' % control_port)

    def test_launch_control(self):
        self._launch_server()
        self.assertEqual(
            self.server.uri,
            self.proxy.uri,
        )
        self.assertEqual('dc=example,dc=org', self.proxy.suffix)
        self.assertEqual(self.server.rootdn, self.proxy.rootdn)
        self.assertEqual(self.server.rootpw, self.proxy.rootpw)

    def test_tls(self):
        """The server CA should be available through the proxy."""
        self._launch_server(tls_config=volatildap.LOCALHOST_TLS_CONFIG)
        self.assertEqual(self.proxy.uri[:8], 'ldaps://')
        self.assertIsNotNone(self.proxy.tls_config)
        self.assertIsNotNone(self.proxy.tls_config.root)

    def test_get(self):
        initial = {'ou=people': {
            'objectClass': ['organizationalUnit'],
            'ou': ['people'],
        }}
        self._launch_server(
            initial_data=initial,
        )

        entry = self.proxy.get('ou=people')
        self.assertEqual(
            {
                'objectClass': [b'organizationalUnit'],
                'ou': [b'people'],
            },
            entry,
        )

    def test_add(self):
        self._launch_server()
        data = {'ou=people': {
            'objectClass': ['organizationalUnit'],
            'ou': ['people'],
        }}
        self.proxy.add(data)
        entry = self.proxy.get('ou=people')
        self.assertEqual(
            {
                'objectClass': [b'organizationalUnit'],
                'ou': [b'people'],
            },
            entry,
        )

    def test_reset(self):
        self._launch_server()
        data = {'ou=people': {
            'objectClass': ['organizationalUnit'],
            'ou': ['people'],
        }}
        self.proxy.add(data)
        # Ensure the data is visible
        self.proxy.get('ou=people')
        self.proxy.reset()

        with self.assertRaises(KeyError):
            self.proxy.get('ou=people')
