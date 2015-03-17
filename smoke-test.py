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

always = ['-f50', '--hash=1', '--no-info']
extras = ['--psnr', '--ssim']
missing = set()

try:
    for key in my_builds:
        logger.setbuild(key)

        for line in open(utils.test_file).readlines():
            if len(line) < 3 or line[0] == '#':
                continue

            seq, command = line.split(',', 1)

            if not os.path.exists(os.path.join(my_sequences, seq)):
                if seq not in missing:
                    logger.write('Ignoring missing sequence', seq)
                    missing.add(seq)
                continue

            if ',' in command:
                logger.write('Ignoring multipass test', command)
                continue

            cfg = command.split() + always
            utils.runtest(key, seq, cfg, extras)
except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
