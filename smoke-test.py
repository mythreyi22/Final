#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'smoke-tests.txt')

from conf import my_builds, my_machine_name

if utils.run_make:
    errors = utils.buildall()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

if utils.run_bench:
    errors = utils.testharness()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

always = ['-f50', '--hash=1', '--no-info']
extras = ['--psnr', '--ssim']

try:
    log = ''
    for key in my_builds:
        desc = utils.describeEnvironment(key)
        for line in open(utils.test_file).readlines():
            if len(line) < 3 or line[0] == '#': continue
            seq, command = line.split(',', 1)
            if ',' in command: continue # skip multipass tests
            cfg = command.split() + always
            log += utils.runtest(key, seq, cfg, extras, desc)
            print
except KeyboardInterrupt:
    print 'Caught ctrl+c, exiting'

# summarize results (could be an email)
print '\n\n'
if log:
    print 'Revision under test:'
    print utils.hgsummary()
    print log
else:
    print 'All tests passed for %s on %s' % (utils.testrev, my_machine_name)
