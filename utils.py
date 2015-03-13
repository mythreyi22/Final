import datetime
import filecmp
import md5
import os
import shutil
import sys
import tempfile
import time
import urllib
from subprocess import Popen, PIPE
from distutils.spawn import find_executable

try:
    from conf import my_machine_name, my_machine_desc, my_x265_source
    from conf import my_sequences, my_goldens, option_strings, my_hm_decoder
    from conf import my_pastebin_key, my_progress, my_tempfolder, my_builds

    # support ~/repos/x265 syntax
    my_x265_source = os.path.expanduser(my_x265_source)
    my_sequences = os.path.expanduser(my_sequences)
    my_goldens = os.path.expanduser(my_goldens)
    my_hm_decoder = os.path.expanduser(my_hm_decoder)
    my_tempfolder = os.path.expanduser(my_tempfolder)
except ImportError, e:
    print e
    print 'Copy conf.py.example to conf.py and edit the file as necessary'
    sys.exit(1)

run_make  = True
run_bench = True
rebuild   = False
save_results = True

def setup(argv):
    if not find_executable('hg'):
        raise Exception('Unable to find Mercurial executable (hg)')
    if not find_executable('cmake'):
        raise Exception('Unable to find cmake executable')
    if not find_executable(my_hm_decoder):
        raise Exception('Unable to find HM decoder')
    if not os.path.exists(os.path.join(my_x265_source, 'CMakeLists.txt')):
        raise Exception('my_x265_source does not point to x265 source/ folder')

    global run_make, run_bench, rebuild, save_results

    if my_tempfolder:
        tempfile.tempdir = my_tempfolder

    # do not write new golden outputs or write pass/fail files if revision
    # under test is not public
    save_results = allowNewGoldenOutputs()
    if not save_results:
        print 'NOTE: Revision under test is not public or has uncommited changes.'
        print 'No new golden outputs will be generated during this run, neither'
        print 'will it create pass/fail files.\n'

    import getopt
    longopts = ['builds=', 'help', 'no-make', 'no-bench', 'rebuild']
    optlist, args = getopt.getopt(argv[1:], 'hb:', longopts)
    for opt, val in optlist:
        # restrict the list of target builds to just those specified by -b
        # for example: ./smoke-test.py -b "gcc32 gcc10"
        if opt in ('-b', '--builds'):
            userbuilds = val.split()
            delkeys = [key for key in my_builds if not key in userbuilds]
            for key in delkeys:
                del my_builds[key]
        elif opt == '--no-make':
            run_make = False
        elif opt == '--no-bench':
            run_bench = False
        elif opt == '--rebuild':
            rebuild = True
        elif opt in ('-h', '--help'):
            print sys.argv[0], '[OPTIONS]\n'
            print '\t-h/--help            show this help'
            print '\t-b/--builds <string> space seperated list of build targets'
            print '\t   --no-make         do not compile sources'
            print '\t   --no-bench        do not run test benches'
            print '\t   --rebuild         remove old build folders and rebuild'
            sys.exit(0)

ignored_compiler_warnings = (
    'ld: warning: PIE disabled', # link warning on 32bit GCC builds on Mac
)

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

    def async_poll_process(proc, fulloutput):
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
        exiting = False
        output = ''
        while True:
            # note that this doesn't guaruntee we get the stdout and stderr
            # lines in the intended order, but they should be close
            try:
                while not qout.empty():
                    line = qout.get()
                    if fulloutput: output += line
                    if my_progress: print line,
                    out.append(line)
            except Empty:
                pass

            if not qerr.empty():
                try:
                    while not qerr.empty():
                        line = qerr.get()
                        if fulloutput: output += line
                        if my_progress: print line,
                        for i in ignored_compiler_warnings:
                            if line.startswith(i):
                                break
                        else:
                            errors += ''.join(out[-3:])
                            out = []
                            errors += line
                except Empty:
                    pass

            if proc.poll() != None and not exiting:
                tout.join()
                terr.join()
                exiting = True
            elif exiting and qerr.empty() and qout.empty():
                break

        if proc.returncode and not errors:
            errors = ''.join(out[-10:])
        if proc.returncode == -11:
            errors += 'SIGSEGV\n'
        elif proc.returncode == -4:
            errors += 'SIGILL\n'
        elif proc.returncode:
            errors += 'return code %d\n' % proc.returncode
        if fulloutput:
            return output, errors
        else:
            return errors

else:

    # POSIX systems have select()

    import select

    def async_poll_process(proc, fulloutput):
        out = []
        errors = ''
        output = ''
        exiting = False

        # poll stdout and stderr file handles so we get errors in the context
        # of the stdout compile progress reports
        while True:
            fds = [proc.stdout.fileno(), proc.stderr.fileno()]
            ret = select.select(fds, [], [])

            empty = True
            for fd in ret[0]:
                if fd == proc.stdout.fileno():
                    line = proc.stdout.readline()
                    if line:
                        empty = False
                        if fulloutput: output += line
                        if my_progress: print line,
                        out.append(line)
                if fd == proc.stderr.fileno():
                    line = proc.stderr.readline()
                    if line:
                        empty = False
                        if fulloutput: output += line
                        if my_progress: print line,
                        for i in ignored_compiler_warnings:
                            if line.startswith(i):
                                break
                        else:
                            errors += ''.join(out[-3:])
                            out = []
                            errors += line
            if proc.poll() != None and not exiting:
                exiting = True
            elif exiting and empty:
                break

        if proc.returncode and not errors:
            errors = ''.join(out[-10:])
        if proc.returncode == -11:
            errors += 'SIGSEGV\n'
        elif proc.returncode == -4:
            errors += 'SIGILL\n'
        elif proc.returncode:
            errors += 'return code %d\n' % proc.returncode
        if fulloutput:
            return output, errors
        else:
            return errors


def parseYuvFilename(fname):
    '''requires the format: foo_bar_WxH_FPS[_10bit][_CSP][_crop].yuv'''

    if not fname.lower().endswith('.yuv'):
        raise Exception('parseYuv only supports YUV files')

    # these steps can raise all manor of index exceptions, callers must
    # catch them in case the YUV filename does not match our scheme
    depth = 8
    csp = '420'
    words = fname[:-4].split('_')

    if words[-1] == 'crop':
        words.pop()

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
    out, err = Popen(['hg', 'summary'], stdout=PIPE, stderr=PIPE,
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


def hgrevisiondate(rev):
    if rev.endswith('+'): rev = rev[:-1]
    out, err = Popen(['hg', 'log', '-r', rev, '--template', '{isodate(date)}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine revision phase: ' + err)
    # isodate format is '2015-03-09 12:13 -0500', we want '15-03-09'
    return out[2:10]


def hggetbranch(rev):
    if rev.endswith('+'): rev = rev[:-1]
    out, err = Popen(['hg', 'log', '-r', rev, '--template', '{branch}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine revision phase: ' + err)
    return out


def allowNewGoldenOutputs():
    rev = hgversion()
    if rev.endswith('+'):
        # we do not store golden outputs if uncommitted changes
        return False
    if hggetphase(rev) != 'public':
        # we do not store golden outputs until a revision is public (pushed)
        return False
    return True


def cmake(generator, buildfolder, cmakeopts, **opts):
    # buildfolder is the relative path to build folder

    if rebuild and os.path.exists(buildfolder):
        shutil.rmtree(buildfolder)
        if os.name == 'nt': time.sleep(1)
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
    errors = async_poll_process(p, False)

    os.environ['PATH'] = origpath
    return errors


vcvars = ('include', 'lib', 'mssdk', 'path', 'regkeypath', 'sdksetupdir',
          'sdktools', 'targetos', 'vcinstalldir', 'vcroot', 'vsregkeypath')

def get_sdkenv(vcpath, arch):
    '''extract environment vars set by vcvarsall for compiler target'''

    vcvarsall = os.path.abspath(os.path.join(vcpath, 'vcvarsall.bat'))
    if not os.path.exists(vcvarsall):
        raise Exception(vcvarsall + ' not found')

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
    if os.name != 'nt':
        raise Exception('Visual Studio builds only supported on Windows')

    # Look for Visual Studio install location within the registry
    key = r'SOFTWARE\Wow6432Node\Microsoft\VisualStudio'
    if '12' in generator:
        key += r'\12.0'
    elif '11' in generator:
        key += r'\11.0'
    elif '10' in generator:
        key += r'\10.0'
    elif '9' in generator:
        key += r'\9.0'
    else:
        raise Exception('Unsupported VC version')

    import _winreg
    vcpath = ''
    win32key = 'SOFTWARE' + key[20:] # trim out Wow6432Node\
    for k in (key, win32key):
        try:
            hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, k)
            pfx = _winreg.QueryValueEx(hkey, 'InstallDir')[0]
            if pfx and os.path.exists(pfx):
                vcpath = os.path.abspath(pfx + r'\..\..\VC')
                break;
        except (WindowsError, EnvironmentError), e:
            pass

    if not vcpath:
        raise Exception(win32key + ' not found or is invalid')

    if 'Win64' in generator:
        arch = 'x86_amd64'
    else:
        arch = 'x86'

    sdkenv = get_sdkenv(vcpath, arch)
    env = os.environ.copy()
    env.update(sdkenv)

    target = '/p:Configuration='
    if '-DCMAKE_BUILD_TYPE=Debug' in cmakeopts:
        target += 'Debug'
    elif '-DCMAKE_BUILD_TYPE=RelWithDebInfo' in cmakeopts:
        target += 'RelWithDebInfo'
    else:
        target += 'Release'

    # use the newest MSBuild installed
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

    p = Popen([msbuild, '/clp:disableconsolecolor', target, 'x265.sln'],
              stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    return async_poll_process(p, False)


def describeEnvironment(key):
    _, _, generator, co, opts = my_builds[key]
    desc  = 'system   : %s\n' % my_machine_name
    desc += 'hardware : %s\n' % my_machine_desc
    desc += 'generator: %s\n' % generator
    desc += 'options  : %s %s\n' % (co, str(opts))
    desc += 'version  : %s\n\n' % hgversion()
    return desc


def buildall():
    for key in my_builds:
        print 'building %s...'% key

        buildfolder, _, generator, co, opts = my_builds[key]

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
            desc = describeEnvironment(key)
            return prefix + pastebin(desc + errors)

    return None


def testharness():
    for key in my_builds:
        buildfolder, _, generator, co, opts = my_builds[key]

        if 'tests' not in co.split():
            continue

        print 'Running testbench for %s...'% key

        if 'Visual Studio' in generator:
            if 'debug' in co.split():
                target = 'Debug'
            elif 'reldeb' in co.split():
                target = 'RelWithDebInfo'
            else:
                target = 'Release'
            bench = os.path.abspath(os.path.join(buildfolder, 'test', target, 'TestBench'))
        else:
            bench = os.path.abspath(os.path.join(buildfolder, 'test', 'TestBench'))
        if os.name == 'nt': bench += '.exe'

        if not os.path.isfile(bench):
            err = 'testbench <%s> not built' % bench
        else:
            origpath = os.environ['PATH']
            if 'mingw' in opts:
                os.environ['PATH'] += os.pathsep + opts['mingw']
            p = Popen([bench], stdout=PIPE, stderr=PIPE)
            err = async_poll_process(p, False)
            os.environ['PATH'] = origpath

        if err:
            desc = describeEnvironment(key)
            prefix = '** testbench failure reported for %s:: ' % key
            return prefix + pastebin(desc + err)
    return None


def testcasehash(sequence, commands):
    m = md5.new()
    m.update(sequence)
    m.update(' '.join(commands))
    return m.hexdigest()[:12]


def encodeharness(key, tmpfolder, sequence, commands, inextras, desc):
    '''
    Perform a single test encode within a tempfolder
     * key      is the shortname for the build to use, ex: 'gcc'
     * tmpfolder is a temporary folder in which the test will run
     * sequence is the YUV or Y4M filename with no path
     * commands is a list [] of params which influence outputs (hashed)
     * inextras is a list [] of params which do not influence outputs
     * desc     is a description of the test environment
    returns tuple of (logs, summary, error)
       logs    - stderr and stdout in paste-friendly format (encode log)
       summary - bitrate, psnr, ssim
       error   - full description of encoder warnings and errors and test env
    '''

    buildfolder, _, generator, cmakeopts, opts = my_builds[key]

    extras = inextras[:] # make copy so we can append locally
    if sequence.lower().endswith('.yuv'):
        (width, height, fps, depth, csp) = parseYuvFilename(sequence)
        extras += ['--input-res=%sx%s' % (width, height),
                   '--fps=%s' % fps,
                   '--input-depth=%s' % depth,
                   '--input-csp=i%s' % csp]

    print 'Running x265-%s %s %s' % (key, sequence, ' '.join(commands))

    seqfullpath = os.path.join(my_sequences, sequence)

    if 'Visual Studio' in generator:
        if 'debug' in cmakeopts.split():
            target = 'Debug'
        elif 'reldeb' in cmakeopts.split():
            target = 'RelWithDebInfo'
        else:
            target = 'Release'
        x265 = os.path.abspath(os.path.join(buildfolder, target, 'x265'))
    else:
        x265 = os.path.abspath(os.path.join(buildfolder, 'x265'))
    if os.name == 'nt': x265 += '.exe'

    cmds = [x265, seqfullpath, 'bitstream.hevc'] + commands + extras

    logs, errors, summary = '', '', ''
    if not os.path.isfile(x265):
        print 'x265 executable not found'
        errors = 'x265 <%s> cli not compiled\n\n' % x265
    elif not os.path.isfile(seqfullpath):
        print 'Sequence not found'
        errors = 'sequence <%s> not found\n\n' % seqfullpath
    else:
        origpath = os.environ['PATH']
        if 'mingw' in opts:
            os.environ['PATH'] += os.pathsep + opts['mingw']
        p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        os.environ['PATH'] = origpath

        logs = stderr + stdout
        logs = logs.replace('\r', '\n')

        summary, errors = parsex265(tmpfolder, stdout, stderr)
        if p.returncode == -11:
           errors += 'x265 encountered SIGSEGV\n\n'
        elif p.returncode == -4:
           errors += 'x265 encountered SIGILL (usually -ftrapv)\n\n'
        elif p.returncode:
           errors += 'x265 return code %d\n\n' % p.returncode

    if errors:
        prefix = '** encoder warning or error reported for %s:: ' % key
        errors = prefix + pastebin(desc + errors)
    return (logs, summary, errors)


ignored_warnings = (
    '--psnr used with psy on: results will be invalid!',
    '--ssim used with AQ off: results will be invalid!',
    '--psnr used with AQ on: results will be invalid!',
    '--tune psnr should be used if attempting to benchmark psnr!',
    'Assembly not supported in this binary',
    '!! HEVC Range Extension specifications are not finalized !!',
    '!! This output bitstream may not be compliant with the final spec !!',
    'Max TU size should be less than or equal to max CU size, setting max TU size = 16',
    'No thread pool allocated, --wpp disabled',
)

def parsex265(tmpfolder, stdout, stderr):
    errors = ''
    check = os.path.join(tmpfolder, 'x265_check_failures.txt')
    if os.path.exists(check):
        errors += '** check failures reported:\n' + open(check, 'r').read()
    leaks = os.path.join(tmpfolder, 'x265_leaks.txt')
    if os.path.exists(leaks):
        contents = open(leaks, 'r').read()
        if 'No memory leaks detected' not in contents:
            errors += '** leaks reported:\n' + contents + '\n'

    # parse summary from last line of stdout
    ssim, psnr, bitrate = 'N/A', 'N/A', 'N/A'
    if stdout:
        lines = stdout.splitlines()
        words = lines[-1].split()
        if 'fps),' in words:
            index = words.index('fps),')
            bitrate = words[index + 1]
        if 'SSIM' in words:
            ssim = words[-2]
            if ssim.startswith('('): ssim = ssim[1:]
        if 'PSNR:' in words:
            index = words.index('PSNR:')
            psnr = words[index + 1]
            if psnr.endswith(','): psnr = psnr[:-1]
    summary = 'bitrate: %s, SSIM: %s, PSNR: %s' % (bitrate, ssim, psnr)

    # check for warnings in x265 logs
    lastprog = ''
    for line in stderr.splitlines():
        if line.startswith(('yuv  [', 'y4m  [')):
            pass
        elif line.startswith('x265 ['):
            if line[6:13] == 'warning':
                warn = line[16:]
                if warn not in ignored_warnings:
                    print line
                    errors += lastprog + line + '\n'
                    lastprog = ''
            elif line[6:11] == 'error':
                errors += lastprog + line
                lastprog = ''
        elif line.startswith('[') and line.endswith('\r'):
            lastprog = line

    if errors:
        errors += '\n\nFull encoder log:\n' + stderr + stdout + '\n'

    return summary, errors


def findlastgood(testrev):
    '''
    output-changing-commits.txt must contain the hashes (12-bytes) of
    commits which change outputs. All commits which are ancestors of these
    commits should match outputs (unless they are also listed). New output
    changing commits must be added on top so they are found before any of
    their ancestor commits.

    Lines starting with a hash are considered comments, text after the 12 byte
    hash are ignored and can be used to describe the commit
    '''
    try:
        lines = open("output-changing-commits.txt").readlines()
    except EnvironmentError:
        return testrev

    if testrev.endswith('+'): testrev = testrev[:-1]
    for line in lines:
        if len(line) < 12 or line[0] == '#': continue
        rev = line[:12]
        cmds = ['hg', 'log', '-r', "%s::%s" % (rev, testrev),
                '--template', '"{short(node)}"']
        out = Popen(cmds, stdout=PIPE, cwd=my_x265_source).communicate()[0]
        if out:
            return rev

    return testrev


def checkoutputs(key, seq, cfg, lastfname, sum, tmpdir, desc):
    testhash = testcasehash(seq, cfg)
    testfolder = os.path.join(my_goldens, testhash, lastfname)
    if not os.path.isdir(testfolder):
        return None
    golden = os.path.join(testfolder, 'bitstream.hevc')
    test = os.path.join(tmpdir, 'bitstream.hevc')
    if not filecmp.cmp(golden, test):
        oldsum = open(os.path.join(testfolder, 'summary.txt'), 'r').read()
        res = '%s: %s output does not match last known good for group %s\n' % \
               (testhash, key, my_builds[key][1])
        res += desc
        res += 'PREV: %s\n' % oldsum
        res += ' NEW: %s\n\n' % sum
        return res
    return False


def newgoldenoutputs(seq, cfg, lastfname, testrev, desc, sum, logs, tmpdir):
    '''
    A test was run and the outputs are good (match the last known good or if
    no last known good is available, these new results are taken
    '''
    if not save_results:
        return

    testhash = testcasehash(seq, cfg)

    # create golden folder if necessary
    if not os.path.isdir(my_goldens):
        os.mkdir(my_goldens)

    # create a new test folder if necessary
    testfolder = os.path.join(my_goldens, testhash)
    if not os.path.isdir(testfolder):
        os.mkdir(testfolder)
        fp = open(os.path.join(testfolder, 'hashed-command-line.txt'), 'w')
        fp.write('%s %s\n' % (seq, ' '.join(cfg)))
        fp.close()

    # create a new golden output folder if necessary
    lastgoodfolder = os.path.join(testfolder, lastfname)
    if not os.path.isdir(lastgoodfolder):
        os.mkdir(lastgoodfolder)
        shutil.copy(os.path.join(tmpdir, 'bitstream.hevc'), lastgoodfolder)
        open(os.path.join(lastgoodfolder, 'summary.txt'), 'w').write(sum)

    addpass(testhash, lastfname, testrev, desc, logs)
    print 'new golden outputs stored'


def addpass(testhash, lastfname, testrev, desc, logs):
    if not save_results:
        return
    folder = os.path.join(my_goldens, testhash, lastfname, 'passed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    open(os.path.join(folder, fname), 'w').write(desc + logs + '\n')


def addfail(testhash, lastfname, testrev, desc, logs, errors):
    if not save_results:
        return
    folder = os.path.join(my_goldens, testhash, lastfname, 'failed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    open(os.path.join(folder, fname), 'w').write(desc + errors + logs + '\n')


def checkdecoder(tmpdir):
    cmds = [my_hm_decoder, '-b', 'bitstream.hevc']
    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=tmpdir)
    stdout, errors = async_poll_process(proc, True)
    hashErrors = [l for l in stdout.splitlines() if '***ERROR***' in l]
    if hashErrors or errors:
        # Any stream which causes decode errors is saved into
        # goldens/bad-streams under an MD5 hash of its contents
        badbitstreamfolder = os.path.join(my_goldens, 'bad-streams')
        if not os.path.exists(badbitstreamfolder):
            os.mkdir(badbitstreamfolder)
        badfn = os.path.join(tmpdir, 'bitstream.hevc')
        m = md5.new()
        m.update(open(badfn, 'rb').read())
        hashname = m.hexdigest()
        hashfname = os.path.join(badbitstreamfolder, hashname + '.hevc')
        shutil.copy(badfn, hashfname)
        return 'Validation failed with %s\n\n' % my_hm_decoder + \
               '\n'.join(hashErrors) + '\n' + errors + '\n' + \
               'This bitstream was saved to %s\n' % hashfname
    else:
        return ''


def _test(build, tmpfolder, lastgood, testrev, seq, cfg, extras, desc):
    '''
    Run a test encode within the specified temp folder
    Check to see if golden outputs exist:
        If they exist, verify bit-exactness or report divergence
        If not, validate new bitstream with decoder then save
    '''
    fulldesc = desc
    fulldesc += 'command: %s %s\n' % (seq, ' '.join(cfg))
    fulldesc += ' extras: ' + ' '.join(extras) + '\n\n'

    # run the encoder, abort early if any errors encountered
    logs, sum, errors = encodeharness(build, tmpfolder, seq, cfg, extras, fulldesc)
    if errors:
        print 'Encoder warnings or errors detected'
        return errors

    group = my_builds[build][1]
    revdate = hgrevisiondate(lastgood)
    lastfname = '%s-%s-%s' % (revdate, group, lastgood)
    testhash = testcasehash(seq, cfg)

    # check against last known good outputs
    errors = checkoutputs(build, seq, cfg, lastfname, sum, tmpfolder, fulldesc)
    if errors is None:
        print 'No golden outputs for this test case, validating with decoder'
        errors = checkdecoder(tmpfolder)
        if errors:
            print 'Decoder validation failed'
            return fulldesc + errors
        else:
            print 'Decoder validation ok:', sum
            newgoldenoutputs(seq, cfg, lastfname, testrev, fulldesc, sum, logs, tmpfolder)
            return ''
    elif errors:
        fname = os.path.join(my_goldens, testhash, lastfname, 'summary.txt')
        lastsum = open(fname, 'r').read()

        decodeerr = checkdecoder(tmpfolder)
        addfail(testhash, lastfname, testrev, fulldesc, logs, errors + decodeerr)
        if decodeerr:
            print 'OUTPUT CHANGE WITH DECODE ERRORS'
            return errors
        elif '--vbv-bufsize' in cfg:
            # VBV encodes are non-deterministic, check that golden output
            # bitrate is within 1% of new bitrate. Extract bitrate from summary
            # example summary: bitrate: 121.95, SSIM: 20.747, PSNR: 53.359
            lastbitrate = float(lastsum.split(',')[0].split(' ')[1])
            newbitrate = float(sum.split(',')[0].split(' ')[1])
            diff = abs(lastbitrate - newbitrate) / lastbitrate
            print 'VBV OUTPUT CHANGED BY %.2f%%' % (diff * 100)
            if diff > 0.01:
                errors += 'VBV bitrate changed by %.2f%%\n' % (diff * 100)
                return errors
            else:
                # this is considered a passing test
                return ''
        else:
            print 'OUTPUT CHANGE: <%s> to <%s>' % (lastsum, sum)
            return errors + decodeerr
    else:
        addpass(testhash, lastfname, testrev, fulldesc, logs)
        print 'PASS'
        return ''

def runtest(build, lastgood, testrev, seq, cfg, extras, desc):
    tmpfolder = tempfile.mkdtemp(prefix='x265-temp')
    try:
        return _test(build, tmpfolder, lastgood, testrev, seq, cfg, extras, desc)
    finally:
        shutil.rmtree(tmpfolder)

def multipasstest(build, lastgood, testrev, seq, multipass, extras, desc):
    # multipass is an array of command lines, each encode command line is run
    # in series (each given the same input sequence and 'extras' options and
    # within the same temp folder so multi-pass stats files and analysis load /
    # save files will be left unharmed between calls
    tmpfolder = tempfile.mkdtemp(prefix='x265-temp')
    try:
        log = ''
        for cfg in multipass:
            log += _test(build, tmpfolder, lastgood, testrev, seq, cfg, extras, desc)
        return log
    finally:
        shutil.rmtree(tmpfolder)
