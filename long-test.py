#!/usr/bin/env python

import os
import random
import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv)

from conf import my_builds, my_machine_name, my_sequences

if utils.run_make:
    errors = utils.buildall()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

sequences, configs = {}, {} # use dictionaries to prune dups
for line in open('regression-tests.txt').readlines():
    if len(line) < 3 or line[0] == '#': continue
    seq, command = line.split(',')
    if os.path.exists(os.path.join(my_sequences, seq)):
        sequences[seq] = 1
    if '--vbv' not in command:
        configs[command] = 1

always = ['--no-info']

# these options can be added to any test and should not affect outputs
spotchecks = (
    '--no-asm',
    '--asm=SSE2',
    '--asm=SSE3',
    '--asm=SSSE3',
    '--asm=SSE4',
    '--asm=AVX',
    '--pme',
    '--recon=recon.yuv',
    '--recon=recon.y4m',
    '--csv=test.csv',
    '--log=frame',
    '--log=debug',
    '--log=full',
    '--pools=1', # pools=0 disables pool features
    '--pools=2',
)

rev = utils.hgversion()
lastgood = utils.findlastgood(rev)
print '\ntesting revision %s, validating against %s\n' % (rev, lastgood)

# do not use debug builds for long-running tests (they are only intended
# for smoke testing)
debugs = [key for key in my_builds if 'debug' in my_builds[key][3]]
if debugs:
    print 'Discarding debug builds <%s>\n' % ' '.join(debugs)
    for k in debugs:
        del my_builds[k]

print 'Running 1000 test encodes, press CTRL+C to abort (maybe twice)\n'

try:
    log = ''
    for x in xrange(1000):
        seq = random.choice(sequences.keys())
        cfg = random.choice(configs.keys()).split()
        cmdline = cfg[:] + always
        extras = ['--psnr', '--ssim', random.choice(spotchecks)]
        build = random.choice(my_builds.keys())
        desc = utils.describeEnvironment(build)
        log += utils.runtest(build, lastgood, rev, seq, cmdline, extras, desc)
        print
except KeyboardInterrupt:
    print 'Caught ctrl+c, exiting'

# summarize results (could be an email)
print '\n\n'
if log:
    print 'Revision under test:'
    print utils.hgsummary()
    print 'Last known good revision:'
    print utils.hgrevisioninfo(lastgood)
    print log
else:
    print 'All quick tests passed for %s against %s on %s' % \
           (rev, lastgood, my_machine_name)
