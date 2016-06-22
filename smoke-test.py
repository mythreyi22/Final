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

try:
    from conf import encoder_binary_name
except ImportError, e:
    print 'failed to import encoder_binary_name'
    encoder_binary_name = 'x265'

utils.buildall()
if logger.errors:
    # send results to mail
    logger.email_results()
    sys.exit(1)
# run testbenches
utils.testharness()
if encoder_binary_name == 'x265':
    always = '-f50 --hash=1 --no-info'
else:
    always = '-f100 --hash=1 --no-info'
extras = ['--psnr', '--ssim']
try:

    tests = utils.parsetestfile()
    logger.settestcount(len(my_builds.keys()) * len(tests))

    for key in my_builds:
        logger.setbuild(key)
        for (seq, command) in tests:
            utils.runtest(key, seq, command, always, extras)

    # send results to mail
    logger.email_results()

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
