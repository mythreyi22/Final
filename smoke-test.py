#!/usr/bin/env python

import sys
import shutil

import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv)

errors = utils.buildall()
if errors:
    print errors
    sys.exit(1)

errors = utils.testharness()
if errors:
    print errors
    sys.exit(1)

from conf import my_builds
encoders = my_builds.keys()

sequences = [
    'RaceHorses_416x240_30_10bit.yuv',
    'big_buck_bunny_360p24.y4m',
    'washdc_422_ntsc.y4m',
    'old_town_cross_444_720p50.y4m',
    'crowd_run_1080p50.y4m'
]

configs = [
    ['--preset=superfast', '-f50'],
    ['--preset=medium', '-f50'],
]

extras = ['--psnr', '--ssim']

for build in encoders:
    for seq in sequences:
        for cfg in configs:
            tmpdir, sum, errors = utils.encodeharness(build, seq, cfg, extras)
            if errors:
                print errors
            elif tmpdir:
                print sum
                shutil.rmtree(tmpdir)
