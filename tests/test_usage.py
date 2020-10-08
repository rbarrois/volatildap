# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

import os
import time
import unittest

import psutil

import volatildap


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



