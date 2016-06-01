# -*- coding: utf-8 -*-

"""Compatibility layer for legacy Python (< 3.4 as of 2016)"""

import tempfile
import shutil
import sys

LEGACY_PY = sys.version_info[0] < 3


if LEGACY_PY:
    class TemporaryDirectory(object):
        def __init__(self):
            self.name = tempfile.mkdtemp()

        def cleanup(self):
            shutil.rmtree(self.name)

else:
    TemporaryDirectory = tempfile.TemporaryDirectory
