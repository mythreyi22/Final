#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'smoke-tests.txt')

from conf import my_builds, my_sequences
from utils import logger

utils.buildall()
if logger.errors:
    sys.exit(1)

utils.testharness()
if logger.errors:
    sys.exit(1)

always = ' -f50 --hash=1 --no-info' # must begin with a space
extras = ['--psnr', '--ssim']

tests = utils.parsetestfile()

try:
    logger.settestcount(len(my_builds.keys()) * len(tests))
    for key in my_builds:
        logger.setbuild(key)

        for (seq, command) in tests:
            if ',' in command:
                logger.write('Ignoring multipass test', command)
                continue
            utils.runtest(key, seq, command + always, extras)

    # send results to mail
    logger.email_results()

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
