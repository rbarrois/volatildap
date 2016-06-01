#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This software is distributed under the two-clause BSD license.

import codecs
import os
import re
import sys

from setuptools import find_packages, setup

root_dir = os.path.abspath(os.path.dirname(__file__))


def get_version(package_name):
    version_re = re.compile(r"^VERSION = [\"']([\w_.-]+)[\"']$")
    package_components = package_name.split('.')
    init_path = os.path.join(root_dir, *(package_components + ['version.py']))
    with codecs.open(init_path, 'r', 'utf-8') as f:
        for line in f:
            match = version_re.match(line[:-1])
            if match:
                return match.groups()[0]
    return '0.1.0'


PACKAGE = 'volatildap'


setup(
    name=PACKAGE,
    version=get_version(PACKAGE),
    description="Temporary slapd launcher for testing purposes",
    long_description=''.join(codecs.open('README.rst', 'r', 'utf-8').readlines()),
    author="Raphaël Barrois",
    author_email="raphael.barrois+%s@polytechnique.org" % PACKAGE,
    license="BSD",
    keywords=['ldap', 'test', 'openldap', 'slapd'],
    url="https://github.com/rbarrois/%s/" % PACKAGE,
    download_url="https://pypi.python.org/pypi/%s/" % PACKAGE,
    packages=find_packages(exclude=['tests*']),
    platforms=["OS Independent"],
    install_requires=[
    ],
    setup_requires=[
        'setuptools>=0.8',
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: Unix",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python",
        "Topic :: Software Development",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP",
    ],
    test_suite='tests',
)
