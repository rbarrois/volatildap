# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

import unittest

from volatildap import core

# A valid LDIF.
# Note that entries are sorted by increasing DN length, then by alphabetical
# DN order.
# Attributes are sorted in alphabetical order.
VALID_LDIF = b"""version: 1

dn: ou=groups,dc=example,dc=org
objectClass: organizationalUnit
ou: groups

dn: ou=people,dc=example,dc=org
objectClass: organizationalUnit
ou: people

dn: ou=admins,ou=people,dc=example,dc=org
objectClass: organizationalUnit
ou: admins
"""

VALID_ENTRIES = {
    'ou=people,dc=example,dc=org': {
        'ou': [b'people'],
        'objectClass': [b'organizationalUnit'],
    },
    'ou=groups,dc=example,dc=org': {
        'ou': [b'groups'],
        'objectClass': [b'organizationalUnit'],
    },
    'ou=admins,ou=people,dc=example,dc=org': {
        'ou': [b'admins'],
        'objectClass': [b'organizationalUnit'],
    },
}


class CoreTests(unittest.TestCase):
    def test_ldif_to_entries(self):
        entries = core.ldif_to_entries(VALID_LDIF)
        self.assertEqual(VALID_ENTRIES, entries)

    def test_entries_to_ldif(self):
        ldif = '\n'.join(core.entries_to_ldif(VALID_ENTRIES))
        self.assertEqual(VALID_LDIF.decode('ascii'), ldif)

    def test_loop_from_ldif(self):
        ldif = '\n'.join(core.entries_to_ldif(core.ldif_to_entries(VALID_LDIF)))
        self.assertEqual(VALID_LDIF, ldif.encode('ascii'))

    def test_loop_from_entries(self):
        entries = core.ldif_to_entries(
            '\n'.join(core.entries_to_ldif(VALID_ENTRIES)).encode('ascii')
        )
        self.assertEqual(VALID_ENTRIES, entries)
