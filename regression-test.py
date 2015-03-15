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

if utils.run_make:
    errors = utils.buildall()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

always = ['--no-info', '--hash=1']

spotchecks = utils.spotchecks()

# do not use debug builds for long-running tests (they are only intended
# for smoke testing)
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
if debugs:
    print 'Discarding debug builds <%s>\n' % ' '.join(debugs)
    for k in debugs:
        del my_builds[k]

try:
    log = ''
    missing = set()
    for build in my_builds:
        desc = utils.describeEnvironment(build)
        for line in open(utils.test_file).readlines():
            if len(line) < 3 or line[0] == '#': continue
            seq, command = line.split(',', 1)
            if not os.path.exists(os.path.join(my_sequences, seq)):
                if seq not in missing:
                    print 'Ignoring missing sequence', seq
                    missing.add(seq)
                continue
            extras = ['--psnr', '--ssim', random.choice(spotchecks)]
            if ',' in command:
                multipass = [cmd.split() + always for cmd in command.split(',')]
                log += utils.multipasstest(build, seq, multipass, extras, desc)
            else:
                cmdline = command.split() + always
                log += utils.runtest(build, seq, cmdline, extras, desc)
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
    print 'All quick tests passed for %s against %s on %s' % \
           (utils.testrev, utils.lastgood, my_machine_name)
