import os
import psutil
import time
import unittest

import templdap


class LdapServerTestCase(unittest.TestCase):
    def _launch_server(self, **kwargs):
        server = templdap.LdapServer(**kwargs)
        server.start()
        context = {
            'dirname': server._tempdir.name,
            'pid': server._process.pid,
        }
        return server, context

    def assertServerStopped(self, context):
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


class AutoCleanupTests(LdapServerTestCase):

    def test_stop(self):
        """Deleting the LdapServer object causes its cleanup."""

        server, context = self._launch_server()

        server.stop()

        self.assertServerStopped(context)

    def test_stops_on_del(self):
        """Deleting the LdapServer object causes its cleanup."""

        server, context = self._launch_server()

        del server

        # Allow some time for proper shutdown
        time.sleep(1)

        self.assertServerStopped(context)
