import os
import shutil
import sys
from subprocess import call, Popen, PIPE
from distutils.spawn import find_executable

try:
    from conf import my_machine_name, my_machine_desc, my_x265_source
    from conf import my_sequences, my_goldens, option_strings, my_builds
    from conf import my_pastebin_key
except ImportError, e:
    print e
    print 'Copy conf.py.example to conf.py and edit the file as necessary'
    sys.exit(1)

# TODO:
#  error and warning handling

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

def pastebin(content):
    import urllib
    sizelimit = 500 * 1024

    if not my_pastebin_key:
        return 'Not using pastebin, no key configured. Contents:\n' + content
    elif len(content) >= sizelimit:
        content = content[:sizelimit - 30] + '\n\ntruncated to paste limit'

    pastebin_vars = {
        'api_option'     : 'paste',
        'api_dev_key'    : my_pastebin_key,
        'api_paste_code' : content
    }
    conn = urllib.urlopen('http://pastebin.com/api/api_post.php',
                          urllib.urlencode(pastebin_vars))
    return conn.read()

def hgversion():
    out, err = Popen(['hg', 'id', '-i'], stdout=PIPE, stderr=PIPE,
                     cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine source version: ' + err)
    # note, if the ID ends with '+' it means the user's repository has
    # uncommitted changes. We will never want to save golden outputs from these
    # repositories.
    return out[:-1] # strip line feed

def hgsummary():
    out, err = Popen(['hg', 'id', '-i'], stdout=PIPE, stderr=PIPE,
                     cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine repo summary: ' + err)
    return out

def hgrevisioninfo(rev):
    addstatus = False
    if rev.endswith('+'):
        rev = rev[:-1]
        addstatus = True
    out, err = Popen(['hg', 'log', '-r', rev], stdout=PIPE, stderr=PIPE,
                     cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine revision info: ' + err)
    if addstatus:
        out += 'Uncommitted changes in the working directory:\n'
        out += Popen(['hg', 'status'], stdout=PIPE,
                     cwd=my_x265_source).communicate()[0]
    return out

def hggetphase(rev):
    if rev.endswith('+'): rev = rev[:-1]
    out, err = Popen(['hg', 'log', '-r', rev, '--template', '{phase}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine revision phase: ' + err)
    return out

def allowNewGoldenOutputs():
    rev = hgversion()
    if rev.endswith('+'):
        # we do not store golden outputs if uncommitted changes
        print 'User repo has uncommitted changes'
        return False
    if hggetphase(rev) != 'public':
        # we do not store golden outputs until a revision is public (pushed)
        print 'User repo parent rev is not public'
        return False
    return True

def cmake(generator, buildfolder, cmakeopts, **opts):
    # buildfolder is the relative path to build folder

    if opts.get('rebuild') and os.path.exists(buildfolder):
        shutil.rmtree(buildfolder)
    if not os.path.exists(buildfolder):
        os.mkdir(buildfolder)
    else:
        generator = None

    cmds = ['cmake', os.path.abspath(my_x265_source)]

    if generator:
        cmds.append('-G')
        cmds.append(generator)
        if 'CFLAGS' in opts:
            cmds.append('-DCMAKE_C_COMPILER_ARG1=' + opts['CFLAGS'])
            cmds.append('-DCMAKE_CXX_COMPILER_ARG1=' + opts['CFLAGS'])

    cmds.extend(cmakeopts)

    env = os.environ.copy()
    if generator:
        if 'CC' in opts:
            env['CC'] = opts['CC']
        if 'CXX' in opts:
            env['CXX'] = opts['CXX']
    if 'mingw' in opts:
        env['PATH'] += os.pathsep + opts['mingw']

    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    stdout, stderr = proc.communicate()
    print stdout
    print stderr


def gmake(buildfolder, **opts):
    if 'mingw' in opts:
        env = os.environ.copy()
        env['PATH'] += os.pathsep + opts['mingw']
        call(['mingw32-make'], cwd=buildfolder, env=env)
    else:
        call(['make'], cwd=buildfolder)


vcvars = ('include', 'lib', 'mssdk', 'path', 'regkeypath', 'sdksetupdir',
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
            if k.lower() in vcvars:
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
    if '-DCMAKE_BUILD_TYPE=Debug' in cmakeopts:
        target += 'debug'
    elif '-DCMAKE_BUILD_TYPE=RelWithDebInfo' in cmakeopts:
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
    else:
        msbuild = find_executable('msbuild')
        if not msbuild:
            raise Exception('Unable to find msbuild.exe')

    call([msbuild, '/clp:disableconsolecolor', target, 'x265.sln'],
         cwd=buildfolder, env=env)

def validatetools():
    if not find_executable('hg'):
        raise Exception('Unable to find Mercurial executable (hg)')
    if not find_executable('cmake'):
        raise Exception('Unable to find cmake executable')

def setup(argv):
    validatetools()
    if not os.path.exists(os.path.join(my_x265_source, 'CMakeLists.txt')):
        raise Exception('my_x265_source does not point to x265 source/ folder')

def buildall():
    for key, value in my_builds.items():
        buildfolder, generator, co, opts = value

        cmakeopts = []
        for o in co.split():
            if o in option_strings:
                cmakeopts.append(option_strings[o])
            else:
                print 'Unknown cmake option', o

        cmake(generator, buildfolder, cmakeopts, **opts)

        if 'Makefiles' in generator:
            gmake(buildfolder, **opts)
        elif 'Visual Studio' in generator:
            msbuild(buildfolder, generator, cmakeopts)
        else:
            raise NotImplemented()
