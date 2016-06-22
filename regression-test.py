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

try:
    from conf import my_upload
except ImportError, e:
    print 'failed to import my_upload'

try:
    from conf import encoder_binary_name
except ImportError, e:
    print 'failed to import encoder_binary_name'	
    encoder_binary_name = 'x265'
	
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
            if encoder_binary_name == 'x265':
                extras = ['--psnr', '--ssim', utils.getspotcheck(command)]
            else:
                extras = ['--psnr', '--ssim']
            utils.runtest(build, seq, command, always, extras)

    # send results to mail
    logger.email_results()
    # rebuild without debug options and upload binaries on egnyte
    logs = open(os.path.join(utils.encoder_binary_name, logger.logfname),'r')
    fatalerror = False
    for line in logs:
         if 'encoder error reported' in line or 'DECODE ERRORS' in line  or 'Validation failed' in line or 'encoder warning reported' in line:
             fatalerror = True

    if fatalerror == False and my_upload:
        for key, v in my_upload.iteritems():
            buildoption = []
            buildoption.append(v[0])
            buildoption.append(v[1])
            buildoption.append(v[2])
            buildoption.append(v[3].replace('debug', '').replace('checked', '').replace('tests', '').replace('warn', '').replace('reldeb', '').replace('noasm','').replace('static',''))
            buildoption.append(v[4])
            my_upload[key] = tuple(buildoption)
        utils.buildall(None, my_upload)
        utils.upload_binaries()

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'

