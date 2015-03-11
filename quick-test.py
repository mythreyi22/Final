#!/usr/bin/env python

import random
import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv)

from conf import my_builds, my_machine_name

if utils.run_make:
    errors = utils.buildall()
    if errors:
        print '\n\n' + errors
        sys.exit(1)

# note: remove lines of any sequences you do not have, feel free to add more
sequences = [
    'big_buck_bunny_360p24.y4m',
    'BasketballDrive_1920x1080_50.y4m',
    'KristenAndSara_1280x720_60.y4m',
    'ducks_take_off_444_720p50.y4m',
    'mobile_calendar_422_ntsc.y4m',
    'vtc1nw_422_ntsc.y4m',
    'washdc_422_ntsc.y4m',
    'DucksAndLegs_1920x1080_60_10bit_422.yuv',
    'CrowdRun_1920x1080_50_10bit_422.yuv',
    'CrowdRun_1920x1080_50_10bit_444.yuv',
    'NebutaFestival_2560x1600_60_10bit_crop.yuv',
]

configs = [
    ['--preset=superfast', '--hash=1'],
    ['--preset=medium', '--hash=2'],
    ['--preset=slower', '--hash=3'],
    ['--preset=medium', '--bitrate=1000', '--hash=2'],
]

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
    '--pools=+,-',
    '--pools=-,+',
)

rev = utils.hgversion()
lastgood = utils.findlastgood(rev)
print 'testing revision %s, validating against %s\n' % (rev, lastgood)

try:
    log = ''
    for x in xrange(20):
        seq = random.choice(sequences)
        cfg = random.choice(configs)
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
