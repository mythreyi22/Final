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

# do not use debug builds for long-running tests (they are only intended
# for smoke testing)
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
if debugs:
    print 'Discarding debug builds <%s>\n' % ' '.join(debugs)
    for k in debugs:
        del my_builds[k]

if utils.run_make:
    errors = utils.buildall()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

sequences, configs = set(), set()
for line in open(utils.test_file).readlines():
    if len(line) < 3 or line[0] == '#': continue
    seq, command = line.split(',', 1)
    if os.path.exists(os.path.join(my_sequences, seq)):
        sequences.add(seq)
    if '--vbv' not in command:
        configs.add(command)
# convert sets to lists for random.choice()
sequences = list(sequences)
configs = list(configs)

always = ['--no-info', '--hash=1']
spotchecks = utils.spotchecks()

print 'Running 1000 test encodes, press CTRL+C to abort (maybe twice)\n'

try:
    log = ''
    for x in xrange(1000):
        seq = random.choice(sequences)
        cfg = random.choice(configs)
        extras = ['--psnr', '--ssim', random.choice(spotchecks)]
        build = random.choice(my_builds.keys())
        desc = utils.describeEnvironment(build)
        if ',' in cfg:
            multipass = [cmd.split() + always for cmd in command.split(',')]
            log += utils.multipasstest(build, seq, multipass, extras, desc)
        else:
            cmdline = cfg[:] + always
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
    print 'All tests passed for %s on %s' % (utils.testrev, my_machine_name)
