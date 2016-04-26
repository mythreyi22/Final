#!/usr/bin/env python

# Copyright (C) 2016 Mahesh Pittala <mahesh@multicorewareinc.com>,
# Aasai Priya <aasai@multicorewareinc.com>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import os
import sys
import utils


def arrangecli(seq, command, always):
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
    utils.testhashlist = []
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
    return final_command