# This software is distributed under the two-clause BSD license.

import http.server
import json
import subprocess
import sys
import threading
import time
from urllib.parse import urljoin

import requests

from . import core

if sys.version_info < (3, 7):
    HTTPServer = http.server.HTTPServer
else:
    HTTPServer = http.server.ThreadingHTTPServer


class ControlServer(HTTPServer):
    """The HTTP control server.

    Launched in a background thread; keeps a reference to the actual
    server.LdapServer instance.
    """
    def __init__(self, server_address, ldap_server):
        super().__init__(server_address, RequestHandler)
        self.ldap_server = ldap_server
        self._thread = None

    def start(self):
        if self._thread is not None:
            # Already started
            return
        self._thread = threading.Thread(
            target=self.serve_forever,
            name='control-server',
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return
        self.shutdown()
        self.server_close()
        self._thread.join()
        self._thread = None


class RequestHandler(http.server.BaseHTTPRequestHandler):
    @property
    def ldap(self):
        return self.server.ldap_server

    def _send_empty(self, status_code, message=None):
        """Send an empty HTTP response, with a specific status code."""
        self.send_response(status_code, message=message)
        self.end_headers()

    def do_POST(self):
        if self.path.strip('/') == 'control/reset':
            self.ldap.reset()
            self._send_empty(204)
        elif self.path.strip('/') == 'control/stop':
            self.ldap.stop()
            self._send_empty(204)
        elif self.path.strip('/') == 'control/start':
            self.ldap.start()
            self._send_empty(204)
        elif self.path.strip('/') == 'entry':
            self.post_entries()
        else:
            self._send_empty(404)

    def do_GET(self):
        if self.path.startswith('/entry/'):
            self.get_entry(self.path[len('/entry/'):])
        elif self.path.strip('/') == 'config':
            self.get_config()
        elif self.path.strip('/') == 'control/wait':
            self.get_wait()
        else:
            self._send_empty(404)

    def post_entries(self):
        length = int(self.headers['Content-Length'])
        data = self.rfile.read(length)
        self.ldap.add_ldif(data)
        self._send_empty(201)

    def get_config(self):
        tls_config = self.ldap.tls_config
        data = dict(
            suffix=self.ldap.suffix,
            rootdn=self.ldap.rootdn,
            rootpw=self.ldap.rootpw,
            port=self.ldap.port,
            host=self.ldap.host,
            tls_root=tls_config.root if tls_config else None
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def get_entry(self, dn):
        try:
            entry = self.ldap.get_ldif(dn)
        except KeyError as e:
            self._send_empty(404, str(e))
        except RuntimeError as e:
            self._send_empty(500, str(e))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/ldif")
            self.end_headers()
            self.wfile.write(entry.encode('utf-8'))

    def get_wait(self):
        try:
            self.ldap.wait(5)
        except subprocess.TimeoutExpired as e:
            self._send_empty(504, str(e))
        else:
            self._send_empty(204)


class ProxyServer(core.BaseServer):
    """A proxy to an LDAP server, based on its control API."""
    def __init__(self, url):
        self.base_url = url
        config = self._get_config()
        self.rootdn = config['rootdn']
        self.rootpw = config['rootpw']
        self.suffix = config['suffix']
        self.port = config['port']
        self.host = config['host']
        if config['tls_root']:
            self.tls_config = core.TLSConfig(
                root=config['tls_root'],
                chain=None,
                certificate=None,
                key=None,
            )
        else:
            self.tls_config = None

    def _path(self, path):
        return urljoin(self.base_url, path)

    def _get_config(self):
        response = requests.get(self._path('config/'))
        response.raise_for_status()
        return response.json()

    def reset(self):
        response = requests.post(self._path('control/reset/'))
        response.raise_for_status()

    def get(self, dn):
        response = requests.get(self._path('entry/') + dn)
        if response.status_code == 404:
            raise KeyError(dn)
        response.raise_for_status()
        entries = core.ldif_to_entries(response.content)
        assert len(entries) == 1
        return list(entries.values())[0]

    def add(self, data):
        lines = '\n'.join(core.entries_to_ldif(data))
        response = requests.post(self._path('entry/'), data=lines.encode('ascii'))
        response.raise_for_status()

    def start(self):
        response = requests.post(self._path('control/start/'))
        response.raise_for_status()

    def wait(self, timeout=None):
        since = time.time()
        while timeout is None or time.time() - since < timeout:
            response = requests.get(self._path('control/wait/'))
            if response.status_code == 504:
                continue
            else:
                response.raise_for_status()
                return
        raise core.TimeoutExpired('', timeout=timeout)

    def stop(self):
        response = requests.post(self._path('control/stop/'))
        response.raise_for_status()
