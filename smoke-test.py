#!/usr/bin/env python

# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys
import shutil
from subprocess import Popen, PIPE
import utils

# setup will call sys.exit() if it determines the tests are unable to continue
utils.setup(sys.argv, 'smoke-tests.txt')
from conf import my_builds, my_sequences, my_x265_source
from utils import logger

try:
    from conf import my_upload
except ImportError, e:
    print 'failed to import my_upload'
    my_upload = False

try:
    from conf import csv_feature
except ImportError, e:
    print 'failed to import csv_feature'
    csv_feature = False

try:
    from conf import my_patchlocation, my_ftp_location
except ImportError, e:
    print 'failed to import  my_patchlocation, my_ftp_location'
my_patchrevision = ''

try:
    from conf import encoder_binary_name
except ImportError, e:
    print 'failed to import encoder_binary_name'
    encoder_binary_name = 'x265'

try:
    from conf import my_email_to
    from conf import my_receiver_mailid
except ImportError, e:
    print 'failed to import my_receiver_mailid'
    my_receiver_mailid = my_email_to

utils.buildall()
if logger.errors:
    # send results to mail
    logger.email_results()
    sys.exit(1)
# run testbenches
utils.testharness()
if encoder_binary_name == 'x265':
    always = '-f50 --hash=1 --no-info'
else:
    always = '-f100 --hash=1 --no-info'
extras = ['--psnr', '--ssim']
try:

    tests = utils.parsetestfile()
    logger.settestcount(len(my_builds.keys()) * len(tests))

    for key in my_builds:
        logger.setbuild(key)
        for (seq, command) in tests:
            utils.runtest(key, seq, command, always, extras)

    # send results to mail
    logger.email_results()


    # rebuild without debug options and upload binaries on egnyte
    logs = open(os.path.join(utils.encoder_binary_name, logger.logfname),'r')
    fatalerror = False
    for line in logs:
         if 'encoder error reported' in line or 'DECODE ERRORS' in line  or 'Validation failed' in line or 'encoder warning reported' in line:
             fatalerror = True

    if fatalerror == False and my_upload:
        utils.setup(sys.argv, 'smoke-tests.txt')
        from utils import logger
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
        logger.email_results(my_receiver_mailid, 'Regular binaries upload')

        # here it applies specific patch and shares libraries
        if csv_feature == True:
            out, err = Popen(['hg', 'import', my_patchlocation], cwd=my_x265_source, stdout=PIPE, stderr=PIPE).communicate()
            utils.setup(sys.argv, 'smoke-tests.txt')
            from utils import logger
            my_patchrevision = utils.hgversion(my_x265_source)
            testedbranch = utils.hggetbranch(my_patchrevision)
            if err:
                logger.writeerr('\nfailed to import patch\n' + err)
                p = Popen("hg up -C", cwd=my_x265_source, stdout=PIPE, stderr=PIPE)
            else:
                utils.buildall(None, my_upload)
                extras = ['--psnr', '--ssim', '--csv-log-level=3', '--csv=test.csv']
                for build in my_upload:
                    logger.setbuild(build)
                    for seq, command in tests:
                        utils.runtest(build, seq, command, always, extras)
                logs = open(os.path.join(utils.encoder_binary_name, logger.logfname),'r')
                fatalerror = False
                for line in logs:
                    if 'encoder error reported' in line or 'DECODE ERRORS' in line  or 'Validation failed' in line or 'encoder warning reported' in line:
                        fatalerror = True
                if fatalerror == False:
                    utils.upload_binaries(my_ftp_location)
                out, err = Popen(['hg', 'strip', my_patchrevision], cwd=my_x265_source, stdout=PIPE, stderr=PIPE).communicate()
                if err:
                    logger.writeerr('\nfailed to strip local csv patch\n' + err)
            logger.email_results(my_receiver_mailid, 'Amazon binaries upload', testedbranch)

except KeyboardInterrupt:
    print 'Caught CTRL+C, exiting'

finally:
    if csv_feature == True:
        out, err = Popen(['hg', 'strip', my_patchrevision], cwd=my_x265_source, stdout=PIPE, stderr=PIPE).communicate()
        if err:
            print '\nfailed to strip local csv patch ' + err
        p = Popen("hg up -C", cwd=my_x265_source, stdout=PIPE, stderr=PIPE)
