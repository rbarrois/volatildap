# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

"""Compatibility layer for legacy Python (< 3.4 as of 2016)"""

import shutil
import sys
import tempfile

LEGACY_PY = sys.version_info[0] < 3


if LEGACY_PY:
    class TemporaryDirectory(object):
        def __init__(self):
            self.name = tempfile.mkdtemp()

        def cleanup(self):
            shutil.rmtree(self.name)

else:
    TemporaryDirectory = tempfile.TemporaryDirectory
