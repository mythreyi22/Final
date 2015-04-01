#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'fprofile-tests.txt')

from conf import my_builds, my_sequences
from utils import logger

# prune checking and debugging options
for key in my_builds.keys():
    buildfolder, group, generator, co, opts = my_builds[key]
    words = co.split()
    for opt in ('checked', 'reldeb', 'ftrapv', 'noasm', 'ppa', 'tests'):
        while opt in words:
            print 'dropping %s option from %s build' % (opt, key)
            words.remove(opt)
    # when generating usage data, GCC generally needs a static linked executable
    # with optimizations disabled
    if 'static' not in words:
        words.append('static')
    if 'debug' not in words:
        words.append('debug')
    my_builds[key] = (buildfolder, group, generator, ' '.join(words), opts)

tests = utils.parsetestfile()
utils.save_results = False

utils.rebuild = True # delete build folders prior to build
utils.buildall(prof='generate')
if logger.errors:
    sys.exit(1)

logger.settestcount(len(my_builds.keys()) * len(tests))
for key in my_builds:
    logger.setbuild(key)
    for (seq, command) in tests:
        utils.runtest(key, seq, command, '', [])

# build shared lib, add native arch compile option
for key in my_builds.keys():
    buildfolder, group, generator, co, opts = my_builds[key]
    words = co.split()
    if 'static' in words:
        words.remove('static')
    if 'debug' in words:
        words.remove('debug')
    if 'native' not in words:
        words.append('native')
    my_builds[key] = (buildfolder, group, generator, ' '.join(words), opts)

utils.rebuild = False
utils.buildall(prof='use')
if logger.errors:
    sys.exit(1)
