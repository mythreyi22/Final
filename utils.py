#!/usr/bin/env python

import os
import shutil
import sys
from subprocess import call, Popen, PIPE

# TODO:
#  error and warning handling
#  MSBuild support
#  MSYS support
#  findExe() for cmake and hg

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
        if 'CFLAGS' in opts:
            cmds.append('-DCMAKE_C_COMPILER_ARG1=' + opts['CFLAGS'])
            cmds.append('-DCMAKE_CXX_COMPILER_ARG1=' + opts['CFLAGS'])

    for opt in cmakeopts:
        if opt in option_strings:
            cmds.append(option_strings[opt])
        else:
            print 'Unknown cmake option', opt

    if generator:
        if 'CC' in opts:
            os.environ['CC'] = opts['CC']
        if 'CXX' in opts:
            os.environ['CXX'] = opts['CXX']

    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder)
    stdout, stderr = proc.communicate()


def gmake(buildfolder, **opts):
    if 'mingw' in opts:
        call(['mingw32-make'], cwd=buildfolder)
    else:
        call(['make'], cwd=buildfolder)


sdkenv_vars = ('include', 'lib', 'mssdk', 'path', 'regkeypath', 'sdksetupdir',
               'sdktools', 'targetos', 'vcinstalldir', 'vcroot', 'vsregkeypath')

def get_sdkenv(sdkpath, arch):
    '''extract environment vars set by vcvarsall for compiler target'''
    vcvarsall = os.path.abspath(sdkpath + r'..\VC\vcvarsall.bat')
    p = Popen(r'cmd /e:on /v:on /c call "%s" %s && set' % (vcvarsall, arch),
              shell=False, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    newenv = {}
    for line in out.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k.lower() in sdkenv_vars:
                newenv[k.upper()] = v
    return newenv


def msbuild(buildfolder, generator, cmakeopts):
    '''Build visual studio solution using specified compiler'''
    if '12' in generator:
        envvar = 'VSSDK120Install'
    elif '11' in generator:
        envvar = 'VSSDK110Install'
    elif '10' in generator:
        envvar = 'VSSDK100Install'
    else:
        raise Exception('Unsupported VC version')
    if 'Win64' in generator:
        arch = 'x86_amd64'
    else:
        arch = 'x86'

    if envvar not in os.environ:
        raise Exception(envvar + ' not found in system environment')

    sdkpath = os.environ[envvar]
    sdkenv = get_sdkenv(sdkpath, arch)
    env = os.environ.copy()
    env.update(sdkenv)

    target = '/p:Configuration='
    if 'debug' in cmakeopts:
        target += 'debug'
    elif 'reldeb' in cmakeopts:
        target += 'RelWithDebInfo'
    else:
        target += 'Release'

    msbuild = 'msbuild'
    for f in (r'C:\Program Files (x86)\MSBuild\12.0\Bin\MSBuild.exe',
              r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe',
              r'C:\Windows\Microsoft.NET\Framework\v3.5\MSBuild.exe'):
        if os.path.exists(f):
            msbuild = f
            break
    #TODO: check for msbuild in PATH, this is not robust enough

    call([msbuild, '/clp:disableconsolecolor', target, 'x265.sln'],
         cwd=buildfolder, env=env)


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
    'nocolor' : '-DCMAKE_COLOR_MAKEFILE=OFF',
    'crt'     : '-DSTATIC_LINK_CRT=ON',
}

my_x265_source = r'C:\mcw\x265\source'

my_builds = {
    # Examples
    #'gcc'   : ('default/', 'Unix Makefiles',   'static checked', {}),
    #'gcc32' : ('gcc32/',   'Unix Makefiles',   'static',    {'CFLAGS':'-m32'}),
    #'gcc10' : ('gcc10/',   'Unix Makefiles',   '16bpp',     {}),
    #'llvm'  : ('llvm/',    'Unix Makefiles',   'checked',   {'CC':'clang', 'CXX':'clang++'}),
    #'vc11'  : ('vc11/',    'Visual Studio 11 Win64', 'checked',   {}),
    #'vc11D' : ('vc11D/',   'Visual Studio 11 Win64', 'debug static noasm ppa', {}),
    #'win32' : ('vc11x86/', 'Visual Studio 11', 'static ppa', {}),

    'mingw'  : ('mingw/',
                'MinGW Makefiles',
                'tests',
                {'mingw':r'C:\mcw\msys\mingw64\bin'}),

    'vc12'   : ('vc12/',                         # build folder
                'Visual Studio 12 Win64',        # cmake generator
                'tests checked static nocolor',  # cmake options
                {}),                             # env overrides

    'vc11'   : ('vc11/',                         # build folder
                'Visual Studio 11 Win64',        # cmake generator
                'tests checked crt reldeb',      # cmake options
                {}),                             # env overrides

    # note: these regression scripts can only build and run msys targets
    # if they are invoked from within an msys shell, so it will generally need
    # to be handled in a seperate configuration from VC builds.
    #'msys'   : ('msys/', 'MSYS Makefiles', 'tests', {})
}

# build all requested versions of x265
for key, value in my_builds.items():
    buildfolder, generator, cmakeopts, opts = value
    #opts['rebuild'] = True
    if 'mingw' in opts:
        # insert mingw compiler path into system search path
        path = os.environ['PATH'].split(os.pathsep)
        path.append(opts['mingw'])
        os.environ['PATH'] = os.pathsep.join(path)
    cmake(my_x265_source, generator, buildfolder, *cmakeopts.split(), **opts)
    if 'Makefiles' in generator:
        gmake(buildfolder, **opts)
    elif 'Visual Studio' in generator:
        msbuild(buildfolder, generator, cmakeopts)
    else:
        raise NotImplemented()
