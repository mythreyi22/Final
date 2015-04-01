#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import random
import sys

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'regression-tests.txt')

from conf import my_builds, my_sequences
from utils import logger

# do not use debug builds for long-running tests
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
for k in debugs:
    del my_builds[k]

utils.buildall()
if logger.errors:
    # send results to mail
    logger.email_results()
    sys.exit(1)

tests = utils.parsetestfile()

configs = [cmd for seq, cmd in tests if '--vbv' not in cmd]
sequences = list(set([seq for seq, cmd in tests]))

always = '--no-info --hash=1'
spotchecks = utils.spotchecks()

print 'Running 1000 test encodes, press CTRL+C to abort (maybe twice)\n'

# Never allow the long test script to save golden outputs, it will run the
# golden outputs folder out of disk space, filling it with outputs that are
# likely never re-used for validation. When save_results is False, every output
# bitstream is validated by the HM decoder
utils.save_results = False

try:

    logger.settestcount(1000)
    for x in xrange(1000):
        build = random.choice(my_builds.keys())
        logger.setbuild(build)

        seq = random.choice(sequences)
        cfg = random.choice(configs)
        extras = ['--psnr', '--ssim', random.choice(spotchecks)]
        utils.runtest(build, seq, cfg, always, extras)

    # send results to mail
    logger.email_results()

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
