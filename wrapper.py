#!/usr/bin/env python

# Copyright (C) 2016 Mahesh Pittala <mahesh@multicorewareinc.com>,
# Aasai Priya <aasai@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys
import utils
import shlex
def arrangecli(seq, command, always, extras, ffmpegpath, build):
    if 'ffmpeg' in command:
        pipe = '-|'
        ffmpeg = 'ffmpeg'
        ffmpegformat = command.split('-i ')[1].split('-|')[0]
        options = command.split('-|')[1]
        final_command = [ffmpegpath]
        final_command.append('-i')
        final_command.append(seq)
        final_command.extend(shlex.split(ffmpegformat))
        final_command.append(pipe)
        final_command.append(build)
        final_command.extend(shlex.split(options))
        final_command.extend(extras)
        final_command.append('-o')
        return final_command

    cmd_string = str(command)
    f = cmd_string.split('[')[0]
    cmd = cmd_string.split('[')[1].split(']')[0]
    commandslist = []

    bitrates, vbvmaxrates, vbvbufsizes = [], [], []

    if '--bitrate ' in cmd:
        list = cmd.split('--bitrate ')[1].split(' ')[0]
        for l in list.split (','):
            bitrates.append(l)
        cmd_string = cmd_string.replace('--bitrate', '')
        cmd_string = cmd_string.replace(list, '')
    if '--vbv-bufsize ' in cmd:
        list = cmd.split('--vbv-bufsize ')[1].split(' ')[0]
        for l in list.split (','):
            vbvbufsizes.append(l)
        cmd_string = cmd_string.replace('--vbv-bufsize', '')
        cmd_string = cmd_string.replace(list, '')
    if '--vbv-maxrate ' in cmd:
        list = cmd.split('--vbv-maxrate ')[1].split(' ')[0]
        for l in list.split (','):
            vbvmaxrates.append(l)
        cmd_string = cmd_string.replace('--vbv-maxrate', '')
        cmd_string = cmd_string.replace(list, '')
    for i in range(len(bitrates)):
        command = '--bitrate '
        command += str(bitrates[i])
        if vbvbufsizes and vbvbufsizes[i]:
            command +=  ' --vbv-bufsize '
            command +=  str(vbvbufsizes[i])
        if vbvmaxrates and vbvmaxrates[i]:
            command +=  ' --vbv-maxrate '
            command +=  str(vbvmaxrates[i])
        command += ' '
        command += cmd_string.strip(';').strip('[').strip(']')
        command += ' '
        command += always
        commandslist.append(command)
        testhash = utils.testcasehash(seq, command)
        utils.testhashlist.append(testhash)

    final_command = f
    final_command += ' '
    final_command += cmd.replace(';', '').strip('[').strip(']')
    final_command += ' '
    final_command += always
    final_command += ' -o '
    final_command += '.hevc,'.join(utils.testhashlist)
    final_command += '.hevc'
    if '--csv=test.csv' in extras:
        csv_filenames = ''
        for i in utils.testhashlist:
            csv_filenames += i
            csv_filenames += '.csv,'
        csv_filenames = csv_filenames[:-1]
        final_command += ' --csv '
        final_command += csv_filenames
    elif '--recon=recon.y4m' in extras:
        recon_filenames = ''
        for i in utils.testhashlist:
            recon_filenames += i
            recon_filenames += '.y4m,'
        recon_filenames = recon_filenames[:-1]
        final_command += ' --recon='
        final_command += recon_filenames
    elif '--recon=recon.yuv' in extras:
        recon_filenames = ''
        for i in utils.testhashlist:
            recon_filenames += i
            recon_filenames += '.yuv,'
        recon_filenames = recon_filenames[:-1]
        final_command += ' --recon='
        final_command += recon_filenames
    return final_command