#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'regression-tests.txt')

from conf import my_builds, my_machine_name, my_sequences
from utils import logger, find_executable

# do not use debug builds for long-running tests
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
for k in debugs:
    del my_builds[k]

utils.buildall()
if logger.errors:
    # send results to mail
    logger.email_results()
    sys.exit(1)

always = '--no-info --hash=1'
hasffplay = find_executable('ffplay')

try:

    tests = utils.parsetestfile()
    logger.settestcount(len(my_builds.keys()) * len(tests))

    for build in my_builds:
        logger.setbuild(build)
        for seq, command in tests:
            if 'ffplay' in command and not hasffplay:
                continue
            extras = ['--psnr', '--ssim', utils.getspotcheck(command)]
            utils.runtest(build, seq, command, always, extras)

    # send results to mail
    logger.email_results()

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'

