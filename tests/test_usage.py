# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

import os
import time
import unittest

import psutil

import volatildap


class LdapServerTestCase(unittest.TestCase):
    def _launch_server(self, **kwargs):
        server = volatildap.LdapServer(**kwargs)
        server.start()
        context = {
            'dirname': server._tempdir.name,
            'pid': server._process.pid,
        }
        return server, context

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
        server, context = self._launch_server(initial_data=self.data)
        entry = server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'dn': [b'ou=test,dc=example,dc=org'],
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)

        server.stop()
        self.assertServerStopped(context)

    def test_post_start_add(self):
        server, context = self._launch_server()
        server.add(self.data)
        entry = server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'dn': [b'ou=test,dc=example,dc=org'],
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)

        server.stop()
        self.assertServerStopped(context)

    def test_get_missing_entry(self):
        server, context = self._launch_server()
        with self.assertRaises(KeyError):
            server.get('ou=test,dc=example,dc=org')

        server.stop()
        self.assertServerStopped(context)

    def test_clear_data(self):
        server, context = self._launch_server()
        server.add(self.data)
        self.assertIsNotNone(server.get('ou=test,dc=example,dc=org'))

        server.start()  # Actually a restart

        # Custom data has been removed
        with self.assertRaises(KeyError):
            server.get('ou=test,dc=example,dc=org')

        # Core data is still there
        self.assertIsNotNone(server.get('dc=example,dc=org'))

        server.stop()
        self.assertServerStopped(context)


class ResetTests(LdapServerTestCase):
    data = {
        'ou=test': {
            'objectClass': ['organizationalUnit'],
            'ou': ['test'],
        },
    }

    def test_cleanup(self):
        server, context = self._launch_server(initial_data=self.data)
        extra = {
            'ou=subarea,ou=test': {
                'objectClass': ['organizationalUnit'],
            },
        }
        server.add(extra)

        entry = server.get('ou=subarea,ou=test,dc=example,dc=org')
        server.reset()

        # Extra data should have been removed
        self.assertRaises(KeyError, server.get, 'ou=subarea,ou=test,dc=example,dc=org')

        # Initial data should still be here
        entry = server.get('ou=test,dc=example,dc=org')
        self.assertEqual({
            'dn': [b'ou=test,dc=example,dc=org'],
            'objectClass': [b'organizationalUnit'],
            'ou': [b'test'],
        }, entry)

        server.stop()
        self.assertServerStopped(context)


class AutoCleanupTests(LdapServerTestCase):

    def test_stop(self):
        """Deleting the LdapServer object causes its cleanup."""

        server, context = self._launch_server()

        server.stop()

        self.assertServerStopped(context)
