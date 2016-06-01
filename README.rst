volatildap
==========


.. image:: https://secure.travis-ci.org/rbarrois/volatildap.png?branch=master
    :target: http://travis-ci.org/rbarrois/volatildap/

.. image:: https://img.shields.io/pypi/v/volatildap.svg
    :target: https://pypi.python.org/pypi/volatildap/
    :alt: Latest Version

.. image:: https://img.shields.io/pypi/pyversions/volatildap.svg
    :target: https://pypi.python.org/pypi/volatildap/
    :alt: Supported Python versions

.. image:: https://img.shields.io/pypi/wheel/volatildap.svg
    :target: https://pypi.python.org/pypi/volatildap/
    :alt: Wheel status

.. image:: https://img.shields.io/pypi/l/volatildap.svg
    :target: https://pypi.python.org/pypi/volatildap/
    :alt: License

``volatildap`` provides simple helpers for testing code against a LDAP database.

Its main features include:

* **Simple configuration:** Don't provide anything the LDAP server will start with sane defaults
* **Built-in cleanup:** As soon as the test ends / the test process exits, the server is instantly removed
* **Cross-distribution setup:** Automatically discover system paths for OpenLDAP binaries, schemas, etc.


Usage
-----

.. code-block:: python

    import volatildap

    class MyTests(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            super(MyTests, cls).setUpClass()
            cls._slapd = volatildap.LdapServer(suffix='dc=example,dc=org')

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


The ``volatildap.LdapServer`` provides a few useful methods:

``start()``
    Start or restart the server.
    This will:

    * Clear all data, if any
    * Start the server if it's not yet running
    * Populate the initial data

``stop()``
    Stop the server.

    This will clean up all data and kill the proces.

``add(data)``
    Add some data, see the ``initial_data`` structure below.

``get(dn)``
    Retrieve an object by its distinguished name;

    Returns a dictionary mapping an attribute to the list of its values, as bytes.

    Raises ``KeyError`` if the distinguished name is unknown to the underlying database.


Configuration
-------------

The ``volatildap.LdapServer`` class accepts a few parameters:

``suffix``
    The suffix to use for the LDAP tree
    
    *Default:* ``dc=example,dc=org``

``rootdn``
    The administrator account for the LDAP server
    
    *Default:* ``cn=testadmin,dc=example,dc=org``

``rootpw``
    The administrator password.
    
    *Default:* A random value, available through ``LdapServer.rootpw``

``schemas``
    List of schemas to load; can be either a simple name (e.g ``cosine.schema``; looked up in openldap installation); or a path to a custom one.
    
    *Default:* ``['core.schema']``

``initial_data``
    Dict mapping a distinguished name to a dict of attribute/values:

    .. code-block:: python

        slapd(initial_data={
            'ou=people': {
                'objectClass': ['organizationalUnit'],
                'cn': ['People'],
            },
        })

    **Note:** When adding data, the suffix can be omitted on objects DNs.

    *Default:* ``{}``

``skip_missing_schemas``
    When loading schemas, this flag instructs ``volatildap`` to continue if some schemas
    can't be found.
    
    *Default:* ``False``

``port``
    The port to use.

    *Default:* An available TCP port on the system

``slapd_debug``
    The debug level for slapd; see ``slapd.conf``

    *Default:* ``0``

``max_server_startup_delay``
    The maximum delay allowed for server startup, in seconds.

    *Default:* ``30``
