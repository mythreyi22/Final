#!/usr/bin/env python

import sys

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv[1:])

errors = utils.buildall()
if errors:
    print errors
    sys.exit(1)

errors = utils.testharness()
if errors:
    print errors
    sys.exit(1)
