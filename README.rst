templdap
========


Templdap provides simple helpers for testing code against a LDAP database.

Its main features include:

* **Simple configuration:** Don't provide anything the LDAP server will start with sane defaults
* **Built-in cleanup:** As soon as the test ends / the test process exits, the server is instantly removed
* **Cross-distribution setup:** Automatically discover system paths for OpenLDAP binaries, schemas, etc.


Usage
-----

.. code-block:: python

    import templdap

    class MyTests(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            super(MyTests, cls).setUpClass()
            cls._slapd = templdap.Slapd(suffix='dc=example,dc=org')

        def setUp(self):
            # Will start the server, or reset/restart it if already started from a previous test.
            self._slapd.start()

        def test_something(self):
            conn = ldap.connection(self._slapd.uri)
            # Do some tests

        def test_with_data(self):
            # Load some data
            self._slapd.add({'ou=people': {'cn': [b'Users']}})
            # Run the tests


Configuration
-------------

The ``templdap.Slapd`` class accepts a few parameters:

``suffix``
    The suffix to use for the LDAP tree; defaults to ``dc=example,dc=org``

``rootdn``
    The administrator account for the LDAP server; defaults to ``cn=testadmin,dc=example,dc=org``

``rootpw``
    The administrator password; defaults to a random value available through ``Slapd.rootpw``

``schemas``
    List of schemas to load; can be either a simple name (e.g ``cosine.schema``; looked up in openldap installation); or a path to a custom one.
    Defaults to ``['core.schema']``

``data``
    Dict mapping a distinguished name to a dict of attribute/values:

    .. code-block:: python

        slapd(data={
            'ou=people': {
                'objectClass': [b'organizationalUnit'],
                'cn': [b'People'],
            },
        })

    **Note:** When adding data, the suffix can be omitted on objects DNs.
