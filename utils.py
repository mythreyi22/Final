#!/usr/bin/env python

import os
import shutil
import sys
from subprocess import call, Popen, PIPE

def parseYuvFilename(fname):
    '''requires the format: foo_bar_WxH_FPS[_10bit][_CSP].yuv'''

    if not fname.lower().endswith('.yuv'):
        raise Exception('parseYuv only supports YUV files')

    # these steps can raise all manor of index exceptions, callers must
    # catch them in case the YUV filename does not match our scheme
    depth = 8
    csp = '420'
    words = fname[:-4].split('_')

    if words[-1] in ('422','444'):
        csp = words.pop()

    if words[-1] == '10bit':
        depth = 10
        words.pop()

    fps = words.pop()
    width, height = words.pop().lower().split('x')

    return (width, height, fps, depth, csp)


def parseY4MHeader(fname):
    '''read important file details from the Y4M header'''
    header = open(fname, "r").readline() # read up to first newline
    if not header.startswith('YUV4MPEG2'):
        raise Exception('parseY4MHeader() did not find YUV4MPEG2 signature')

    # example: C420jpeg W854 H480 F24:1 Ip A1:1
    words = header.split()[1:]
    csp = 420
    depth = 8
    for word in words:
        if word[0] == 'C':
            csp = word[1:4]
            if word.endswith('p10'):
                depth = 10
        elif word[0] == 'W':
            width = word[1:]
        elif word[0] == 'H':
            height = word[1:]
        elif word[0] == 'F':
            fps = word[1:].replace(':', '/')
        elif word[0] in ('A', 'I'):
            pass # ignored, libx265 will parse if needed
        else:
            print 'unknown Y4M header word'

    return (width, height, fps, depth, csp)

def cmake(srcrelpath, generator, buildfolder, *cmakeopts, **opts):
    # srcrelpath points to repo source/ folder containing CMakeLists.txt
    # buildfolder is the relative path to build folder

    if opts.get('rebuild') and os.path.exists(buildfolder):
        shutil.rmtree(buildfolder)
    if not os.path.exists(buildfolder):
        os.mkdir(buildfolder)
    else:
        generator = None

    cmds = ['cmake', os.path.abspath(srcrelpath)]

    if generator:
        cmds.append('-G')
        cmds.append(generator)
        if 'cflags' in opts:
            cmds.append('-DCMAKE_C_COMPILER_ARG1=' + opts['cflags'])
            cmds.append('-DCMAKE_CXX_COMPILER_ARG1=' + opts['cflags'])

    option_strings = {
        'checked' : '-DCHECKED_BUILD=ON',
        '16bpp'   : '-DHIGH_BIT_DEPTH=ON',
        'debug'   : '-DCMAKE_BUILD_TYPE=Debug',
        'reldeb'  : '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        'tests'   : '-DENABLE_TESTS=ON',
        'ppa'     : '-DENABLE_PPA=ON',
        'stats'   : '-DDETAILED_CU_STATS=ON',
        'static'  : '-DENABLE_SHARED=OFF',
        'noasm'   : '-DENABLE_ASSEMBLY=OFF',
    }

    for opt in cmakeopts:
        if opt in option_strings:
            cmds.append(option_strings[opt])
        else:
            print 'Unknown cmake option', opt

    pwd = os.getcwd()
    try:
        os.chdir(buildfolder)
        if generator:
            if 'CC' in opts:
                os.environment['CC'] = opts['CC']
            if 'CXX' in opts:
                os.environment['CXX'] = opts['CXX']

        proc = Popen(cmds, stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()
        # TODO error and warning handling
    finally:
        os.chdir(pwd)


def gmake(buildfolder):
    pwd = os.getcwd()
    try:
        os.chdir(buildfolder)
        call(['make', '-j4'])
        # TODO error and warning handling
    finally:
        os.chdir(pwd)


# parse command line arguments
#x265source, generator, buildfolder = sys.argv[1:4]
#cmakeopts = sys.argv[4:]
#cmake(x265source, generator, buildfolder, *cmakeopts, rebuild=True)
#gmake(buildfolder)

# TODO:
#  error and warning handling
#  MSBuild support
#  MSYS support
#  findExe() for cmake and hg

# CMake generator strings
# make    'Unix Makefiles',
# vc9-32  'Visual Studio 9 2008',
# vc9     'Visual Studio 9 2008 Win64',
# vc10-32 'Visual Studio 10',
# vc10    'Visual Studio 10 Win64',
# vc11-32 'Visual Studio 11',
# vc11    'Visual Studio 11 Win64',
# vc12-32 'Visual Studio 12',
# vc12    'Visual Studio 12 Win64',

my_builds = {
    # label    buildfolder, generator, cmake-options, flags
    'gcc'   : ('default/', 'Unix Makefiles',   'static checked', {}),
    'gcc32' : ('gcc32/',   'Unix Makefiles',   'static',    {'cflags':'-m32'}),
    'gcc10' : ('gcc10/',   'Unix Makefiles',   '16bpp',     {}),
    'llvm'  : ('llvm/',    'Unix Makefiles',   'checked',   {'CC':'clang', 'CXX':'clang++'}),
    'vc11'  : ('vc11/',    'Visual Studio 11 Win64', 'checked',   {}),
    'vc11D' : ('vc11D/',   'Visual Studio 11 Win64', 'debug static noasm ppa', {}),
    'win32' : ('vc11x86/', 'Visual Studio 11', 'static ppa', {}),
}
