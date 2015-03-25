#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import random
import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'regression-tests.txt')

from conf import my_builds, my_machine_name, my_sequences
from utils import logger

# do not use debug builds for long-running tests
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
for k in debugs:
    del my_builds[k]

utils.buildall()
if logger.errors:
    sys.exit(1)

always = ' --no-info --hash=1' # must begin with a space
spotchecks = utils.spotchecks()

tests = utils.parsetestfile()

try:
    logger.settestcount(len(my_builds.keys()) * len(tests))

    for build in my_builds:
        logger.setbuild(build)
        for seq, command in tests:
            extras = ['--psnr', '--ssim', random.choice(spotchecks)]
            if ',' in command:
                utils.multipasstest(build, seq, command.split(','), always, extras)
            else:
                utils.runtest(build, seq, command + always, extras)

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
