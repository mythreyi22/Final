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
    sys.exit(1)

sequences, configs = set(), set()
for line in open(utils.test_file).readlines():
    line = line.strip()
    if len(line) < 3 or line[0] == '#': continue
    seq, command = line.split(',', 1)
    if os.path.exists(os.path.join(my_sequences, seq)):
        sequences.add(seq)
    if '--vbv' not in command:
        configs.add(command)
# convert sets to lists for random.choice()
sequences = list(sequences)
configs = list(configs)

always = ' --no-info --hash=1' # must begin with a space
spotchecks = utils.spotchecks()

print 'Running 1000 test encodes, press CTRL+C to abort (maybe twice)\n'

try:
    for x in xrange(1000):
        seq = random.choice(sequences)
        cfg = random.choice(configs)
        extras = ['--psnr', '--ssim', random.choice(spotchecks)]
        build = random.choice(my_builds.keys())
        logger.setbuild(build)
        if ',' in cfg:
            utils.multipasstest(build, seq, cfg.split(','), always, extras)
        else:
            utils.runtest(build, seq, cfg + always, extras)
except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'
