import os
import shutil
import sys
from subprocess import call, Popen, PIPE
from distutils.spawn import find_executable

try:
    from conf import my_machine_name, my_machine_desc, my_x265_source
    from conf import my_sequences, my_goldens, option_strings, my_builds
    from conf import my_pastebin_key, my_progress
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
        return 'No pastebin key configured. Contents:\n' + content
    elif len(content) >= sizelimit:
        content = content[:sizelimit - 30] + '\n\ntruncated to paste limit'

    pastebin_vars = {
        'api_option'     : 'paste',
        'api_dev_key'    : my_pastebin_key,
        'api_paste_code' : content
    }
    conn = urllib.urlopen('http://pastebin.com/api/api_post.php',
                          urllib.urlencode(pastebin_vars))
    url = conn.read()
    if url.startswith('http://pastebin.com/'):
        return url
    else:
        return 'pastebin failed <%s> paste contents:\n%s' + (url, content)


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
    return proc.communicate()

if os.name == 'nt':

    # LOL Windows
    # Use two threads to poll stdout and stderr and write into queues
    # http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python

    def enqueue_output(fd, q):
        try: 
            while True:
                line = fd.readline()
                if line:
                    q.put(line)
                else:
                    return
        except:
            fd.close()

    def async_poll_process(proc):
        from Queue import Queue, Empty
        from threading import Thread
        qout = Queue()
        tout = Thread(target=enqueue_output, args=(proc.stdout, qout))
        tout.start()

        qerr = Queue()
        terr = Thread(target=enqueue_output, args=(proc.stderr, qerr))
        terr.start()

        out = []
        errors = ''
        while True:
            # note that this doesn't guaruntee we get the stdout and stderr
            # lines in the intended order, but they should be close
            try:
                while not qout.empty():
                    line = qout.get()
                    if my_progress: print line,
                    out.append(line)
            except Empty:
                pass

            if not qerr.empty():
                errors += ''.join(out[-3:])
                out = []

                try:
                    while not qerr.empty():
                        line = qerr.get()
                        if my_progress: print line,
                        errors += line
                except Empty:
                    pass

            if proc.poll() != None and qerr.empty() and qout.empty():
                break

        tout.join()
        terr.join()
        return errors

else:

    # POSIX systems have select()

    import select

    def async_poll_process(proc):
        out = []
        errors = ''

        # poll stdout and stderr file handles so we get errors in the context
        # of the stdout compile progress reports
        while True:
            fds = [proc.stdout.fileno(), proc.stderr.fileno()]
            ret = select.select(fds, [], [])

            for fd in ret[0]:
                if fd == p.stdout.fileno():
                    line = p.stdout.readline()
                    if line:
                        out.append(line)
                        if my_progress: print line,
                if fd == p.stderr.fileno():
                    line = p.stderr.readline()
                    if line:
                        if my_progress: print line,
                        if out:
                            errors += ''.join(out[-3:])
                            out = []
                        errors += line
            if p.poll() != None:
                break

        return errors


def gmake(buildfolder, **opts):
    origpath = os.environ['PATH']
    if 'mingw' in opts:
        os.environ['PATH'] += os.pathsep + opts['mingw']
        cmds = ['mingw32-make']
    else:
        cmds = ['make']
    if 'make-opts' in opts:
        cmds.extend(opts['make-opts'])

    p = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder)
    errors = async_poll_process(p)

    os.environ['PATH'] = origpath
    return errors

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
    return ''

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

        if my_progress: print 'building %s...'% key

        cmakeopts = []
        for o in co.split():
            if o in option_strings:
                cmakeopts.append(option_strings[o])
            else:
                print 'Unknown cmake option', o

        cout, cerr = cmake(generator, buildfolder, cmakeopts, **opts)
        if cerr:
            prefix = '** cmake errors reported for %s:: ' % key
            errors = cout + cerr
        elif 'Makefiles' in generator:
            errors = gmake(buildfolder, **opts)
            prefix = '** make warnings or errors reported for %s:: ' % key
        elif 'Visual Studio' in generator:
            errors = msbuild(buildfolder, generator, cmakeopts)
            prefix = '** msbuild warnings or errors reported for %s:: ' % key
        else:
            raise NotImplemented()

        if errors:
            # cmake output is always small, pastebin the whole thing
            desc  = 'system   : %s\n' % my_machine_name
            desc += 'hardware : %s\n' % my_machine_desc
            desc += 'generator: %s\n' % generator
            desc += 'options  : %s %s\n' % (co, str(opts))
            desc += 'version  : %s\n\n' % hgversion()
            return prefix + pastebin(desc + errors)

    return None
