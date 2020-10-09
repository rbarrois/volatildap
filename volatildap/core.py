# This software is distributed under the two-clause BSD license.

"""Core components for volatildap: base types, RFC implementations, etc."""

import base64
import collections
import re


class LdapError(Exception):
    """Exceptions for volatildap"""


class PathError(LdapError):
    """Exception for missing paths"""


class TimeoutExpired(LdapError):
    def __init__(self, message, timeout=None):
        super().__init__(message)
        self.timeout = timeout


TLSConfig = collections.namedtuple('TLSConfig', ['root', 'chain', 'certificate', 'key'])


class BaseServer:
    rootdn: str
    rootpw: str
    suffix: str
    host: str
    port: int
    tls_config: TLSConfig

    def start(self):
        """Start the server if not started. Reset it otherwise."""
        raise NotImplementedError()

    def wait(self, timeout=None):
        """Wait for the server process to stop.

        The timeout is optional, and counted in seconds.

        If the server hasn't stopped before the timeout, the code will raise a
        volatildap.TimeoutExpired exception.
        """
        raise NotImplementedError()

    def reset(self):
        """Reset the directory to the contents provided at instantiation."""
        raise NotImplementedError()

    def stop(self):
        """Stop the server process."""
        raise NotImplementedError()

    def add(self, data):
        """Add items to the directory.

        Args:
            data: {dn => {attribute => [values]}}, map a distinguised name to
                  a map of attribute / values.

        Items will be inserted by increasing dn length; this ensures that an
        object is inserted after its containing entity.
        """
        raise NotImplementedError()

    def add_ldif(self, lines):
        """Add items to the directory, from a LDIF file lines.

        Args:
            lines: bytes, the LDIF content as a suite of bytes.

        Items will be inserted by increasing dn length; this ensures that an
        object is inserted after its containing entity.
        """
        self.add(ldif_to_entries(lines))

    def get(self, dn):
        """Fetch an item based on its DistinguisedName.

        The suffix may be omitted, and will be added dynamically.

        Returns:
            dict(attribute => [values]), with attribute names as strings and
            values as bytes.
        """
        raise NotImplementedError()

    def get_ldif(self, dn):
        """Fetch an item based on its DistinguisedName.

        The suffix may be omitted, and will be added dynamically.

        Returns:
            str: a LDIF file content.
        """
        entry = self.get(dn)
        lines = self._data_as_ldif({dn: entry})
        return '\n'.join(lines)

    def _normalize_dn(self, dn):
        if not dn.endswith(self.suffix):
            return '%s,%s' % (dn, self.suffix)
        else:
            return dn

    def _data_as_ldif(self, data):
        return entries_to_ldif({
            self._normalize_dn(dn): attributes
            for dn, attributes in data.items()
        })

    @property
    def uri(self):
        if self.tls_config:
            # localhost.volatildap.org is guaranteed to point to ::1 / 127.0.0.1.
            # It matches the default included TLSConfig.
            host = 'localhost.volatildap.org' if self.host == 'localhost' else self.host
            return 'ldaps://%s:%d' % (host, self.port)
        else:
            return 'ldap://%s:%d' % (self.host, self.port)


# Valid characters for a non-base64-encoded LDIF value
_BASE_LDIF_ASCII_CODES = [
    i for i in range(20, 128)
    if chr(i) not in [' ', '<', ':']
]

_BASE_LDIF = [chr(i) for i in _BASE_LDIF_ASCII_CODES]


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
        if all(c in _BASE_LDIF_ASCII_CODES for c in value):
            return '%s: %s' % (attr, value.decode('ascii'))
        else:
            return '%s:: %s' % (attr, base64.b64encode(value).decode('ascii'))
    elif any(c not in _BASE_LDIF for c in value):
        return '%s:: %s' % (attr, base64.b64encode(value.encode('utf-8')).decode('ascii'))
    else:
        return '%s: %s' % (attr, value)


def ldif_to_entries(ldif_lines):
    """Convert a LDIF file to a dict of dn => attributes.

    Args:
        ldif_lines: ASCII-encoded LDIF string

    Returns:
        dict(dn => dict(attribute => list(values))), where:
        - `dn` is a string;
        - `attribute` is a string;
        - `value` is bytes.

    Note: the object's DN is not included in the attributes.
    """
    entries = {}
    for entry in ldif_lines.decode('ascii').split('\n\n'):
        if not entry.strip():
            continue
        if entry.startswith('version:'):
            if re.match('^version: +1$', entry.strip()):
                continue
            else:
                raise ValueError("Invalid LDIF file - missing 'version: 1' header")

        attributes = {}
        for line in entry.split('\n'):
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
        dns = attributes.pop('dn', [b''])
        assert len(dns) == 1
        entries[dns[0].decode('utf-8')] = attributes
    return entries


def entries_to_ldif(entries):
    """Convert a dict of dn => attributes to a LDIF file.

    Args:
        entries: dict(dn => dict(attribute => list(value))), where:
            - `dn` is a string;
            - `attribute` is a string;
            - `value` is bytes.

    Yields:
        str: lines of the file
    """
    yield 'version: 1'
    yield ''
    # Sort by dn length, thus adding parents first.
    for dn, attributes in sorted(entries.items(), key=lambda e: (len(e[0]), e)):
        yield ldif_encode('dn', dn)
        for attribute, values in sorted(attributes.items()):
            for value in values:
                yield ldif_encode(attribute, value)
        yield ''
