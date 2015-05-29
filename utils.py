# Copyright (C) 2015 Steve Borho <steve@borho.org>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version. See COPYING

import atexit
import datetime
import filecmp
import md5
import os
import platform
import random
import shutil
import shlex
import sys
import tempfile
import time
import urllib
from subprocess import Popen, PIPE
from distutils.spawn import find_executable

run_make  = True     # run cmake and make/msbuild
run_bench = True     # run test benches
rebuild   = False    # delete build folders prior to build
save_results = True  # allow new golden outputs or pass/fail files
save_changed = False # save output bitstreams with valid changes
only_string = None   # filter tests - only those matching this string
skip_string = None   # filter tests - all except those matching this string
test_file = None     # filename or full path of file containing test cases
testrev = None       # revision under test
changers = None      # list of all output changing commits which are ancestors
                     # of the revision under test
changefilter = {}
vbv_tolerance = .015 # fraction of bitrate difference allowed (1.5%)
logger = None
buildObj = {}
spot_checks = []
encoder_binary_name = 'x265'

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

    # backward compatibility check
    for key in my_builds:
        opts = my_builds[key][4]
        if 'mingw' in opts:
            print '** `mingw` keyword for MinGW path is deprecated, use PATH'
            opts['PATH'] = opts['mingw']
except ImportError, e:
    print e
    print 'Copy conf.py.example to conf.py and edit the file as necessary'
    sys.exit(1)

try:
    from conf import my_make_flags
except ImportError, e:
    print '** `my_make_flags` not defined in conf.py, defaulting to []'
    my_make_flags = []

try:
    from conf import my_email_from, my_email_to, my_smtp_pwd, my_smtp_host
    from conf import my_smtp_port
except ImportError, e:
    print '** `my_email_*` not defined in conf.py, defaulting to None'
    my_email_from, my_email_to, my_smtp_pwd = None, None, None

try:
    from conf import my_save_changed
    save_changed = my_save_changed
except ImportError, e:
    pass

try:
    from conf import my_coredumppath
    my_coredumppath = os.path.expanduser(my_coredumppath)
except ImportError, e:
    print '** `my_coredumppath` not defined in conf.py, defaulting to none'
    my_coredumppath = None

try:
    from conf import my_ftp_url, my_ftp_user, my_ftp_pass, my_ftp_folder
    from conf import my_binaries_upload
except ImportError, e:
    my_ftp_url, my_ftp_user, my_ftp_pass = None, None, None
    my_binaries_upload = []

try:
    from conf import my_local_changers
except ImportError, e:
    my_local_changers = False

try:
    from conf import my_libpairs
except ImportError, e:
    my_libpairs = []

osname = platform.system()
if osname == 'Windows':
    exe_ext = '.exe'
    dll_ext = '.dll'
elif osname == 'Darwin':
    exe_ext = ''
    dll_ext = '.dylib'
elif osname == 'Linux':
    exe_ext = ''
    dll_ext = '.so'

class Build():
    def __init__(self, *args):
        self.folder, self.group, self.gen, self.cmakeopts, self.opts = args
        co = self.cmakeopts.split()
        for p in ('main', 'main10', 'main12'):
            if p in co:
                self.profile = p
                break
        else:
            self.profile = 'main'

        if 'Visual Studio' in self.gen:
            if 'debug' in co:
                self.target = 'Debug'
            elif 'reldeb' in co:
                self.target = 'RelWithDebInfo'
            else:
                self.target = 'Release'
            self.exe = os.path.join(self.folder, self.target, encoder_binary_name + exe_ext)
            self.dll = os.path.join(self.folder, self.target, 'libx265' + dll_ext)
            self.testbench = os.path.join(self.folder, 'test', self.target, 'TestBench' + exe_ext)
        else:
            self.exe = os.path.join(self.folder, encoder_binary_name + exe_ext)
            self.dll = os.path.join(self.folder, 'libx265' + dll_ext)
            self.testbench = os.path.join(self.folder, 'test', 'TestBench' + exe_ext)

class Logger():
    def __init__(self, testfile):
        testharnesspath = os.path.dirname(os.path.abspath(__file__))
        nowdate = datetime.datetime.now().strftime('log-%y%m%d%H%M')
        self.testname = os.path.splitext(os.path.basename(testfile))[0]
        self.logfname = '%s-%s.txt' % (nowdate, self.testname)
        print 'Logging test results to %s\n' % self.logfname
        self.start_time = datetime.datetime.now()
        self.errors = 0
        self.testcount = 0
        self.totaltests = 0
        self.newoutputs = {}
        self.logfp = open(self.logfname, 'wb')
        self.header  = 'system:      %s\n' % my_machine_name
        self.header += 'hardware:    %s\n' % my_machine_desc
        self.header += 'testharness: %s\n' % hgversion(testharnesspath)
        self.header += '%s\n' % hgrevisioninfo(hgversion(my_x265_source))
        self.logfp.write(self.header + '\n')
        self.logfp.write('Running %s\n\n' % testfile)
        self.logfp.flush()

    def setbuild(self, key):
        '''configure current build info'''
        b = buildObj[key]
        self.build  = 'cur build: %s group=%s\n' % (key, b.group)
        self.build += 'generator: %s\n' % b.gen
        self.build += 'options  : %s %s\n' % (b.cmakeopts, str(b.opts))
        self.logfp.write(self.build + '\n')
        self.logfp.flush()

    def logrevs(self, lastchange):
        '''configure current revision info'''
        self.write('Revision under test:')
        self.write(hgrevisioninfo(testrev))
        #self.write('Most recent output changing commit:')
        #self.write(hgrevisioninfo(lastchange))

    def read(self):
        return open(self.logfname, 'r').read()

    def write(self, *args):
        '''print text to stdout and maybe write to file'''
        print ' '.join(args)

    def newgolden(self, commit):
        self.write('new golden outputs stored, credited to %s' % commit)
        self.logfp.write(self.test)
        self.logfp.write('new outputs credited to <%s>\n\n' % commit)
        self.logfp.flush()
        if commit in self.newoutputs:
            self.newoutputs[commit] += 1
        else:
            self.newoutputs[commit] = 1

    def writeerr(self, message):
        '''cmake, make, or testbench errors'''
        # TODO: wrapper for pastebin
        if os.linesep == '\r\n':
            message = message.replace(os.linesep, '\n')
        self.logfp.write(message + '\n')
        self.logfp.flush()
        self.errors += 1

    def settest(self, seq, command, extras, hash):
        '''configure current test case'''
        self.test  = 'command: %s %s\n' % (seq, command)
        self.test += '   hash: %s\n' % hash
        self.test += ' extras: ' + ' '.join(extras) + '\n\n'
        nofn = '[%d/%d]' % (self.testcount, self.totaltests)
        self.settitle(' '.join([nofn, seq, command]))
        print nofn,

    def settestcount(self, count):
        self.totaltests = count

    def settitle(self, str):
        '''set console title'''
        title = '%s: %s' % (platform.node(), str)
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleA(title)
                return
            except ImportError:
                pass
            try:
                import win32console
                win32console.SetConsoleTitle(title)
                return
            except ImportError:
                pass
        elif 'xterm' in os.getenv('TERM', ''):
            sys.stdout.write("\x1b]2;%s\x07" % title)

    def testfail(self, prefix, errors, logs):
        '''encoder test failures'''
        if my_pastebin_key:
            url = pastebin('\n'.join([self.header, self.build, self.test,
                                      prefix, errors, logs]))
            self.write(' '.join([prefix, url]))
            self.logfp.write('\n'.join(['**', self.test, prefix, url, '']))
        else:
            message = '\n'.join([prefix, errors, logs])
            if os.linesep == '\r\n':
                message = message.replace(os.linesep, '\n')
            self.write(prefix)
            self.logfp.write('**\n\n' + self.test)
            self.logfp.write(message + '\n')
        self.logfp.flush()
        self.errors += 1

    def close(self):
        for co, count in self.newoutputs.iteritems():
            msg = '%d test case output changes credited to %s\n' % (count, co)
            print msg
            self.logfp.write(msg)
        if self.errors:
            print 'Errors written to %s' % self.logfname
        else:
            msg = '\nAll tests passed for %s on %s' % (testrev, my_machine_name)
            print msg
            self.logfp.write(msg)
        self.logfp.close()
        self.settitle(os.path.basename(test_file) + ' complete')

    def email_results(self):
        if not (my_email_from and my_email_to and my_smtp_pwd):
            return

        import smtplib
        from email.mime.text import MIMEText

        duration = str(datetime.datetime.now() - self.start_time).split('.')[0]
        msg = MIMEText("Test Duration(H:M:S) = " + duration + "\n\n" + open(self.logfname, 'r').read())
        msg['To'] = my_email_to
        msg['From'] = my_email_from
        testname = self.testname.split('-')
        status = self.errors and 'failures' or 'successful'
        branch = hggetbranch(testrev)
        data = [platform.system(), '-'] + testname + [status, '-', branch]
        msg['Subject'] = ' '.join(data)

        session = smtplib.SMTP(my_smtp_host, my_smtp_port)
        try:
            session.ehlo()
            session.starttls()
            session.ehlo()
            session.login(my_email_from, my_smtp_pwd)
            session.sendmail(my_email_from, my_email_to, msg.as_string())
        except smtplib.SMTPException, e:
            print 'Unable to send email', e
        finally:
            session.quit()


def setup(argv, preferredlist):
    if not find_executable('hg'):
        raise Exception('Unable to find Mercurial executable (hg)')
    if not find_executable('cmake'):
        raise Exception('Unable to find cmake executable')
    if not find_executable(my_hm_decoder):
        raise Exception('Unable to find HM decoder')
    if not os.path.exists(os.path.join(my_x265_source, 'CMakeLists.txt')):
        raise Exception('my_x265_source does not point to x265 source/ folder')

    global run_make, run_bench, rebuild, save_results, test_file, skip_string
    global only_string, save_changed

    if my_tempfolder:
        tempfile.tempdir = my_tempfolder

    test_file = preferredlist

    import getopt
    longopts = ['builds=', 'help', 'no-make', 'no-bench', 'only=', 'rebuild',
                'save-changed', 'skip=', 'tests=']
    optlist, args = getopt.getopt(argv[1:], 'hb:t:', longopts)
    for opt, val in optlist:
        # restrict the list of target builds to just those specified by -b
        # for example: ./smoke-test.py -b "gcc32 gcc10"
        if opt in ('-b', '--builds'):
            userbuilds = val.split()
            delkeys = [key for key in my_builds if not key in userbuilds]
            for key in delkeys:
                del my_builds[key]
        elif opt == '--skip':
            skip_string = val
        elif opt == '--only':
            only_string = val
        elif opt in ('-t', '--tests'):
            test_file = val
        elif opt == '--save-changed':
            save_changed = True
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
            print '\t-t/--tests <fname>   location of text file with test cases'
            print '\t   --skip <string>   skip test cases matching string'
            print '\t   --only <string>   only test cases matching string'
            print '\t   --save-changed    save bitstreams with changed outputs'
            print '\t   --no-make         do not compile sources'
            print '\t   --no-bench        do not run test benches'
            print '\t   --rebuild         remove old build folders and rebuild'
            sys.exit(0)

    listInRepo = os.path.join(my_x265_source, 'test', test_file)
    if os.sep not in test_file and os.path.exists(listInRepo):
        test_file = listInRepo
    elif not os.path.exists(test_file):
        raise Exception('Unable to find test list file ' + test_file)

    global buildObj
    for key in my_builds:
        buildObj[key] = Build(*my_builds[key])

    global logger, testrev, changers
    logger = Logger(test_file)

    def closelog():
        logger.close()
    atexit.register(closelog)

    testrev = hgversion(my_x265_source)
    if testrev.endswith('+'):
        # we do not store golden outputs if uncommitted changes
        save_results = False
        testrev = testrev[:-1]
    elif hggetphase(testrev) != 'public':
        # we do not store golden outputs until a revision is public (pushed)
        save_results = False
    else:
        save_results = True

    if not save_results:
        logger.write('NOTE: Revision under test is not public or has uncommited changes.')
        logger.write('No new golden outputs will be generated during this run, neither')
        logger.write('will it create pass/fail files.\n')

    changers = findchangeancestors()
    logger.logrevs(changers[0])
    initspotchecks()


ignored_x265_warnings = (
    '--psnr used with psy on: results will be invalid!',
    '--ssim used with AQ off: results will be invalid!',
    '--psnr used with AQ on: results will be invalid!',
    '--tune psnr should be used if attempting to benchmark psnr!',
    '--tune ssim should be used if attempting to benchmark ssim!',
    'Assembly not supported in this binary',
    '!! HEVC Range Extension specifications are not finalized !!',
    '!! This output bitstream may not be compliant with the final spec !!',
    'Max TU size should be less than or equal to max CU size, setting max TU size = 16',
    'QGSize should be less than or equal to maxCUSize, setting QGSize = 16',
    'QGSize should be less than or equal to maxCUSize, setting QGSize = 32',
    'No thread pool allocated, --wpp disabled',
    'No thread pool allocated, --pme disabled',
    'Support for interlaced video is experimental',
    'y4m: down-shifting reconstructed pixels to 8 bits',
    'level 5 detected, but NumPocTotalCurr (total references) is non-compliant',
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
                        if 'PIE' not in line:
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
        elif proc.returncode == -6:
            errors += 'SIGABRT\n'
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
                        if 'PIE' not in line:
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
        elif proc.returncode == -6:
            errors += 'SIGABRT\n'
        elif proc.returncode == -4:
            errors += 'SIGILL\n'
        elif proc.returncode:
            errors += 'return code %d\n' % proc.returncode
        if fulloutput:
            return output, errors
        else:
            return errors

# ftp upload x265 binaries
def upload_binaries():
    if not (my_ftp_url and my_ftp_user and my_ftp_pass):
        return

    import ftplib
    from collections import defaultdict

    debugopts = set(['reldeb', 'ftrapv', 'noasm', 'ppa', 'debug', 'stats', 'static'])

    for key in my_binaries_upload:
        build = buildObj[key]
        buildopts = set(build.co.split())
        if buildopts & debugopts:
            print 'debug option(s) %s detected, skipping build %s' % (buildopts & debugopts, key)
            continue
        if not os.path.exists(build.folder):
            print '%s buildfolder does not exist' % build.folder
            continue

        branch = hggetbranch(testrev)
        tagdistance = hggettagdistance(testrev)

        folder = 'Development' # default
        if branch == 'stable':
            if tagdistance.endswith('+0'):
                folder = 'Release'
                tagdistance = tagdistance[:-2]
            else:
                folder = 'Stable'

        ftp_path = '/'.join([my_ftp_folder, osname, folder, build.profile])

        # open x265 binary & library files and give appropriate names for them to upload
        # ex: Darwin - x265-1.5+365-887ac5e457e0, libx265-1.5+365-887ac5e457e0.dylib
        exe_name = '-'.join(['x265', tagdistance, testrev]) + exe_ext
        dll_name = '-'.join(['libx265', tagdistance, testrev]) + dll_ext
        try:
            x265 = open(build.exe, 'rb')
            dll = open(build.dll, 'rb')
            if osname == 'Linux':
                compilertype = 'gcc'
                if build.opts.get('CXX') == 'icpc':
                    compilertype = 'intel'
                ftp_path = '/'.join([my_ftp_folder, osname, compilertype, folder, build.profile])
        except EnvironmentError, e:
            print("failed to open x265binary or library file", e)
            return

        try:
            ftp = ftplib.FTP(my_ftp_url)
            ftp.login(my_ftp_user, my_ftp_pass)
            ftp.cwd(ftp_path)

            # list the files from ftp location ex:
            # x265-1.5+365-887ac5e457e0, libx265-1.5+365-887ac5e457e0.dylib...
            list_allfiles = ftp.nlst()

            # if files is already exist, delete and re-upload
            for file in (exe_name, dll_name):
                if file in list_allfiles:
                    ftp.delete(file)

            # upload x265 binary and corresponding libraries
            ftp.storbinary('STOR ' + exe_name, x265)
            ftp.storbinary('STOR ' + dll_name, dll)
            list_allfiles = ftp.nlst()
        except ftplib.all_errors, e:
            print "ftp failed", e
            return

        if folder == 'Release': # never delete tagged builds
            continue
        tagrevs = defaultdict(set)
        for file in list_allfiles:
            name, tagdist, hash = file.split('-', 2)
            tag, dist = tagdist.split('+', 1)
            tagrevs[tag].add(int(dist)) # { '1.6' : (100, 110, 112) }

        # Keep M last build versions for most recent N tags, and last stable
        # build on each tag. Note that this is relying on string sorting of
        # version numbers - '1.10' would be less than '1.9' - so it is relying
        # on the policy to bump to version '2.0' following '1.9'

        M = 8
        N = folder == 'Stable' and 2 or 1
        keeprevs = []
        for tags_count, tag in enumerate(sorted(tagrevs.keys(), reverse=True)):
            revs = ['+'.join([tag, str(rev)]) for rev in sorted(tagrevs[tag], reverse=True)]
            if tags_count < N:
                keeprevs.extend(revs[:M])
            elif folder == 'Stable':
                keeprevs.append(revs[0])
            else:
                break

        for file in list_allfiles:
            name, tagdist, hash = file.split('-', 2)
            if tagdist not in keeprevs:
                ftp.delete(file)

# save binaries, core dump and required files to debug
def save_coredump(tmpfolder, binary):
    if not my_coredumppath or not os.path.exists(my_coredumppath):
        return 'core dump saving not enabled\n'
    try:
        dest_dir = os.path.join(my_coredumppath, time.strftime("%d-%m-%Y_%H-%M-%S"))
        os.mkdir(dest_dir)
        if binary:
            shutil.copy(binary, dest_dir)
        for filename in os.listdir(my_coredumppath):
            if not os.path.isdir(os.path.join(my_coredumppath, filename)):
                shutil.move(os.path.join(my_coredumppath, filename), dest_dir)
        for filename in os.listdir(tmpfolder):
            if not os.path.isdir(os.path.join(tmpfolder, filename)):
                shutil.copy(os.path.join(tmpfolder,filename), dest_dir)
        return 'core dump file stored in %s\n\n' % dest_dir
    except EnvironmentError, e:
        return 'unable to save coredump, ' + str(e) + '\n'

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


def parsetestfile():
    global test_file, vbv_tolerance
    missing = set()
    tests = []
    for line in open(test_file).readlines():
        line = line.strip()
        if line.startswith('# vbv-tolerance ='):
            vbv_tolerance = float(line.split('=')[1])
            print 'using vbv tolerance', vbv_tolerance
        if len(line) < 3 or line[0] == '#':
            continue

        seq, command = line.split(',', 1)
        seq = seq.strip()
        command = command.strip()

        if not os.path.exists(os.path.join(my_sequences, seq)):
            if seq not in missing:
                logger.write('Ignoring missing sequence', seq)
                missing.add(seq)
            continue
        tests.append((seq, command))
    return tests


def testcasehash(sequence, command):
    m = md5.new()
    m.update(sequence)
    m.update(command)
    return m.hexdigest()[:12]


def initspotchecks():
    # these options can be added to any test and should not affect outputs
    sc = [
        '--no-asm',
        '--asm=SSE2',
        '--asm=SSE3',
        '--asm=SSSE3',
        '--asm=SSE4',
        '--asm=AVX',
        '--pme',
        '--recon=recon.yuv',
        '--recon=recon.y4m',
        '--csv=test.csv',
        '--no-progress',
        '--log=debug',
        '--log=full',
    ]
    # stats: introduce X265_LOG_FRAME for file level CSV logging without console logs
    if isancestor('a5af4cf20660'):
        sc.append('--log=frame')
    # check if the revision under test is after the NUMA pools commit
    if isancestor('62b8fe990df5'):
        sc.append('--pools=3')
    else:
        sc.append('--threads=3')

    global spot_checks
    spot_checks = sc


def getspotcheck(cmd):
    '''pick a random spot check, but don't allow some combinations'''
    forbiddens = {
        '--log=none': ['vbv'],
        '--pools=3' : ['veryslow', 'placebo'],
        '--threads=3' : ['veryslow', 'placebo'],
        '--no-asm'  : ['veryslow', 'placebo'],
    }
    global spot_checks
    while True:
        sc = random.choice(spot_checks)
        f = forbiddens.get(sc, [])
        if [match for match in f if match in cmd]:
            # pick another spot-check
            continue
        return sc


def pastebin(content):
    sizelimit = 500 * 1024

    if len(content) >= sizelimit:
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
        return 'pastebin failed <%s> paste contents:\n%s' % (url, content)


def hgversion(reporoot):
    out, err = Popen(['hg', 'id', '-i'], stdout=PIPE, stderr=PIPE,
                     cwd=reporoot).communicate()
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

def hggettagdistance(rev):
    if rev.endswith('+'): rev = rev[:-1]
    out, err = Popen(['hg', 'log', '-r', rev, '--template', '{latesttag}+{latesttagdistance}'],
                     stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err:
        raise Exception('Unable to determine tag distance: ' + err)
    return out

def isancestor(ancestor):
    # hg log -r "descendants(1bed2e325efc) and 5ebd5d7c0a76"
    cmds = ['hg', 'log', '-r', 'ancestors(%s) and %s' % (testrev, ancestor),
            '--template', '"{node}"']
    out, err = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=my_x265_source).communicate()
    if err and 'unknown revision' not in err:
        raise Exception('Unable to determine ancestry: ' + err)
    return bool(out)


def getcommits():
    fname = 'output-changing-commits.txt'

    out = Popen(['hg', 'status', fname], stdout=PIPE).communicate()[0]
    if 'M' in out:
        if my_local_changers:
            print 'local %s is modified, disabling download' % fname
            return open(fname).readlines()
        else:
            print 'changes in %s ignored, my_local_changers is false' % fname

    try:
        print 'Downloading most recent list of output changing commits...',
        l = urllib.urlopen('https://bitbucket.org/sborho/test-harness/raw/tip/' + \
                          fname).readlines()
        print 'done\n'
        return l
    except EnvironmentError:
        print 'failed\nWARNING: using local copy of', fname
        print '         it may not be up to date\n'
        return open(fname).readlines()


def findchangeancestors():
    '''
    output-changing-commits.txt must contain the hashes (12-bytes) of
    commits which change outputs. All commits which are ancestors of these
    commits should match outputs (unless they are also listed). New output
    changing commits must be added on top so they are found before any of
    their ancestor commits.

    Lines starting with a hash are considered comments, text after the 12 byte
    hash are ignored and can be used to describe the commit

    Returns a list of all output changing commits which are ancestors of the
    current revision under test.
    '''
    lines = getcommits()

    global changefilter
    ancestors = []
    for line in lines:
        if len(line) < 12 or line[0] == '#': continue
        rev = line[:12]
        if isancestor(rev):
            ancestors.append(rev)
            comment = line[13:]
            if comment.startswith('[') and ']' in comment:
                contents = comment[1:].split(']', 1)[0]
                changefilter[rev] = contents.split(',')

    return ancestors or [testrev]


def cmake(generator, buildfolder, cmakeopts, **opts):
    # buildfolder is the relative path to build folder
    logger.settitle('cmake ' + buildfolder)

    if rebuild and os.path.exists(buildfolder):
        shutil.rmtree(buildfolder)
        if os.name == 'nt': time.sleep(1)
    if not os.path.exists(buildfolder):
        os.mkdir(buildfolder)
    else:
        generator = None

    cmds = ['cmake', '-Wno-dev', os.path.abspath(my_x265_source)]

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

    # note that it is not enough to insert the path into the subprocess
    # environment; it must be in the system PATH in case the compiler
    # spawns subprocesses of its own that take the system PATH (cough, mingw)
    origpath = os.environ['PATH']
    if 'PATH' in opts:
        os.environ['PATH'] += os.pathsep + opts['PATH']
        env['PATH'] += os.pathsep + opts['PATH']

    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    out, err = proc.communicate()
    os.environ['PATH'] = origpath

    return out, err


def gmake(buildfolder, generator, **opts):
    logger.settitle('make ' + buildfolder)
    if 'MinGW' in generator:
        cmds = ['mingw32-make']
    else:
        cmds = ['make']
    if my_make_flags:
        cmds.extend(my_make_flags)

    origpath = os.environ['PATH']
    if 'PATH' in opts:
        os.environ['PATH'] += os.pathsep + opts['PATH']

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


def msbuild(buildkey, buildfolder, generator, cmakeopts):
    '''Build visual studio solution using specified compiler'''
    logger.settitle('msbuild ' + buildfolder)
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

    build = buildObj[buildkey]
    target = ''.join(['/p:Configuration=', build.target])

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

    p = Popen([msbuild, '/clp:disableconsolecolor', target, encoder_binary_name + '.sln'],
              stdout=PIPE, stderr=PIPE, cwd=buildfolder, env=env)
    out, err = async_poll_process(p, True)
    if not err:
        warnings = []
        for line in out.splitlines(True):
            if 'MSBUILD : warning MSB' in line: # vc9 is a mess
                continue
            if 'warning' in line:
                warnings.append(line.strip())
                logger.write(line.strip())
        if warnings:
            err = '\n'.join(warnings)
    return err


def buildall(prof=None):
    if not run_make:
        return
    for key in buildObj:
        logger.write('building %s...'% key)
        build = buildObj[key]

        cmakeopts = []
        for o in build.cmakeopts.split():
            if o in option_strings:
                cmakeopts.append(option_strings[o])
            else:
                logger.write('Unknown cmake option', o)

        if not isancestor('65d004d54895'): # cmake: introduce fprofile options
            pass
        elif 'Makefiles' not in build.gen:
            pass # our cmake script does not support PGO for MSVC yet
        elif prof is 'generate':
            cmakeopts.append('-DFPROFILE_GENERATE=ON')
            cmakeopts.append('-DFPROFILE_USE=OFF')
        elif prof is 'use':
            cmakeopts.append('-DFPROFILE_GENERATE=OFF')
            cmakeopts.append('-DFPROFILE_USE=ON')
        else:
            cmakeopts.append('-DFPROFILE_GENERATE=OFF')
            cmakeopts.append('-DFPROFILE_USE=OFF')

        # force the default of release build if not already specified
        if '-DCMAKE_BUILD_TYPE=' not in ' '.join(cmakeopts):
            cmakeopts.append('-DCMAKE_BUILD_TYPE=Release')

        cout, cerr = cmake(build.gen, build.folder, cmakeopts, **build.opts)
        if cerr:
            prefix = 'cmake errors reported for %s:: ' % key
            errors = cout + cerr
        elif 'Makefiles' in build.gen:
            errors = gmake(build.folder, build.gen, **build.opts)
            prefix = 'make warnings or errors reported for %s:: ' % key
        elif 'Visual Studio' in build.gen:
            errors = msbuild(key, build.folder, build.gen, cmakeopts)
            prefix = 'msbuild warnings or errors reported for %s:: ' % key
        else:
            raise NotImplemented()

        if errors:
            logger.writeerr(prefix + '\n' + errors + '\n')

    # output depth support: to bind libx265_main for 8bit encoder, libx265_main10 for 10bit encoder
    for tup in my_libpairs:
        if len(tup) != 2:
            print("`my_libpairs` variable format is wrong", my_libpairs)
            return
        if tup[0] not in buildObj or tup[1] not in buildObj:
            print("`my_libpairs` variable format is wrong", my_libpairs)
            return

        build1 = buildObj[tup[0]]
        build2 = buildObj[tup[1]]
        if 'static' in build1.cmakeopts.split() or \
           'static' in build2.cmakeopts.split():
            print "%s or %s not generating shared libs" % tup
            return

        b1  = (build1.dll).replace('libx265.', 'libx265_' + build2.profile + '.')
        b2  = (build2.dll).replace('libx265.', 'libx265_' + build1.profile + '.')
        try:
            if os.path.lexists(b1):
                os.unlink(b1)
            if os.path.lexists(b2):
                os.unlink(b2)
            if osname == 'Windows':
                shutil.copy(build1.dll, b2)
                shutil.copy(build2.dll, b1)
            else:
                os.symlink(os.path.abspath(build1.dll), b2)
                os.symlink(os.path.abspath(build2.dll), b1)
        except IOError:
            print("failed to setup library pair", tup)


def testharness():
    if not run_bench:
        return

    for key in buildObj:
        build = buildObj[key]
        bench = build.testbench

        if 'tests' not in build.cmakeopts.split():
            continue
        logger.settitle('testbench ' + key)
        logger.write('Running testbench for %s...'% key)

        if not os.path.isfile(bench):
            err = 'testbench <%s> not built' % bench
        else:
            origpath = os.environ['PATH']
            if 'PATH' in build.opts:
                os.environ['PATH'] += os.pathsep + build.opts['PATH']
            p = Popen([bench], stdout=PIPE, stderr=PIPE)
            err = async_poll_process(p, False)
            os.environ['PATH'] = origpath

        if err:
            prefix = '** testbench failure reported for %s::\n' % key
            logger.writeerr(prefix + err)


def encodeharness(key, tmpfolder, sequence, command, inextras):
    '''
    Perform a single test encode within a tempfolder
     * key      is the shortname for the build to use, ex: 'gcc'
     * tmpfolder is a temporary folder in which the test will run
     * sequence is the YUV or Y4M filename with no path
     * command is a string of params which influence outputs (hashed)
     * inextras is a list [] of params which do not influence outputs
    returns tuple of (logs, summary, error)
       logs    - stderr and stdout in paste-friendly format (encode log)
       summary - bitrate, psnr, ssim
       error   - full description of encoder warnings and errors
    '''

    extras = inextras[:] # make copy so we can append locally
    if sequence.lower().endswith('.yuv'):
        (width, height, fps, depth, csp) = parseYuvFilename(sequence)
        extras += ['--input-res=%sx%s' % (width, height),
                   '--fps=%s' % fps,
                   '--input-depth=%s' % depth,
                   '--input-csp=i%s' % csp]

    seqfullpath = os.path.join(my_sequences, sequence)

    build = buildObj[key]
    x265 = build.exe
    cmds = [x265]
    if '--command-file' in command:
        cmds.append(command)
    else:
        cmds.extend([seqfullpath, 'bitstream.hevc'])
        cmds.extend(shlex.split(command))
        cmds.extend(extras)

    logs, errors, summary = '', '', ''
    if not os.path.isfile(x265):
        logger.write('x265 executable not found')
        errors = 'x265 <%s> cli not compiled\n\n' % x265
    elif not os.path.isfile(seqfullpath):
        logger.write('Sequence not found')
        errors = 'sequence <%s> not found\n\n' % seqfullpath
    else:
        def prefn():
            import resource # enable core dumps
            resource.setrlimit(resource.RLIMIT_CORE, (-1, -1))

        origpath = os.environ['PATH']
        if 'PATH' in build.opts:
            os.environ['PATH'] += os.pathsep + build.opts['PATH']
        if os.name == 'nt':
            p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE)
        else:
            p = Popen(cmds, cwd=tmpfolder, stdout=PIPE, stderr=PIPE, preexec_fn=prefn)
        stdout, stderr = p.communicate()
        os.environ['PATH'] = origpath

        # prune progress reports
        el = [l for l in stderr.splitlines(True) if not l.endswith('\r')]
        # prune debug and full level log messages
        el = [l for l in el if not l.startswith(('x265 [debug]:', 'x265 [full]:'))]
        logs = 'Full encoder logs without progress reports or debug/full logs:\n'
        logs += ''.join(el) + stdout

        summary, errors = parsex265(tmpfolder, stdout, stderr)
        if p.returncode == -11:
            errors += 'x265 encountered SIGSEGV\n\n'
        elif p.returncode == -6:
            errors += 'x265 encountered SIGABRT (usually check failure)\n\n'
        elif p.returncode == -4:
            errors += 'x265 encountered SIGILL (usually -ftrapv)\n\n'
        elif p.returncode == 1:
            errors += 'unable to parse command line (ret 1)\n\n'
        elif p.returncode == 2:
            errors += 'unable open encoder (ret 2)\n\n'
        elif p.returncode == 3:
            errors += 'unable open generate stream headers (ret 3)\n\n'
        elif p.returncode == 4:
            errors += 'encoder abort (ret 4)\n\n'
        elif p.returncode:
            errors += 'x265 return code %d\n\n' % p.returncode

        if p.returncode:
            errors += save_coredump(tmpfolder, x265)

    return (logs, summary, errors)


def parsex265(tmpfolder, stdout, stderr):
    '''parse warnings and errors from stderr, summary from stdout, and look
       for leak and check failure files in the temp folder'''

    errors = ''
    check = os.path.join(tmpfolder, 'x265_check_failures.txt')
    if os.path.exists(check):
        errors += '** check failures reported:\n' + open(check, 'r').read()

    leaks = os.path.join(tmpfolder, 'x265_leaks.txt')
    if os.path.exists(leaks):
        contents = open(leaks, 'r').read()
        if contents and 'No memory leaks detected' not in contents:
            errors += '** leaks reported:\n' + contents + '\n'

    def scansummary(output):
        ssim, psnr, bitrate = 'N/A', 'N/A', 'N/A'
        for line in output.splitlines():
            if not line.startswith('encoded '):
                continue
            words = line.split()
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
            if bitrate:
                return bitrate, ssim, psnr
        return None

    # parse summary from last line of stdout
    sum = scansummary(stdout)
    if sum is None:
        sum = scansummary(stderr)
    if sum:
        summary = 'bitrate: %s, SSIM: %s, PSNR: %s' % sum
    else:
        summary = 'bitrate: N/A, SSIM: N/A, PSNR: N/A'

    # check for warnings and errors in x265 logs, report together with most
    # recent progress report if there was any
    lastprog = None
    ls = len(os.linesep) # 2 on Windows, 1 on POSIX
    for line in stderr.splitlines(True):
        if line.endswith('\r'):
            lastprog = line
        elif line.startswith(('x265 [debug]:', 'x265 [full]:')):
            lastprog = line
        elif line.startswith('x265 [error]:') or \
             (line.startswith('x265 [warning]:') and \
              line[16:-ls] not in ignored_x265_warnings):
            if lastprog:
                errors += lastprog.replace('\r', os.linesep)
                lastprog = None
            errors += line
            logger.write(line[:-1])

    return summary, errors


def checkoutputs(key, seq, command, sum, tmpdir):
    group = my_builds[key][1]
    testhash = testcasehash(seq, command)

    opencommits = [] # changing commits without 'no-change' or testfolder

    # walk list of ancestor commits which changed outputs until we find the
    # most recent output bitstream we are expected to match
    for commit in changers:
        nc = 'no-change-%s-%s.txt' % (group, commit)
        nochange = os.path.join(my_goldens, testhash, nc)
        if os.path.exists(nochange):
            # this commit claims to match outputs of a previous commit
            commit = open(nochange, 'r').read()
            revdate = hgrevisiondate(commit)
            lastfname = '%s-%s-%s' % (revdate, group, commit)
            testfolder = os.path.join(my_goldens, testhash, lastfname)
            break

        revdate = hgrevisiondate(commit)
        lastfname = '%s-%s-%s' % (revdate, group, commit)
        testfolder = os.path.join(my_goldens, testhash, lastfname)
        if os.path.isdir(testfolder):
            # this commit has known-good outputs
            break

        opencommits.append(commit)
    else:
        # no previously saved known good
        commit = changers[0]
        revdate = hgrevisiondate(commit)
        lastfname = '%s-%s-%s' % (revdate, group, commit)
        # caller will create a new testfolder with this name if the current
        # encode outputs pass validations
        print 'no golden outputs for this test case,',
        return lastfname, None

    golden = os.path.join(testfolder, 'bitstream.hevc')
    test = os.path.join(tmpdir, 'bitstream.hevc')

    if filecmp.cmp(golden, test):
        # outputs matched last-known good, record no-change status for all
        # output changing commits which were not previously accounted for
        for oc in opencommits:
            nc = 'no-change-%s-%s.txt' % (group, oc)
            nochange = os.path.join(my_goldens, testhash, nc)
            open(nochange, 'w').write(commit)
            print 'not changed by %s,' % oc,

        # if the test run which created the golden outputs used a --log=none
        # spot-check or something similar, the summary will have some unknowns
        # in it. Replace it with the current summary if it is complete
        fname = os.path.join(my_goldens, testhash, lastfname, 'summary.txt')
        lastsum = open(fname, 'r').read()
        if 'N/A' in lastsum and 'N/A' not in sum:
            print 'correcting golden output summary,',
            open(fname, 'w').write(sum)
        return lastfname, False

    if '--vbv-bufsize' in command:
        # outputs did not match but this is a VBV test case.
        # an open commmit with the 'vbv' keyword may take credit for the change
        for oc in opencommits:
            if 'vbv' in changefilter.get(oc, ''):
                lastfname = '%s-%s-%s' % (hgrevisiondate(oc), group, oc)
                return lastfname, None
        return lastfname, 'VBV output change'

    # outputs do not match last good, check for a changing commit that might
    # take credit for this test case being changed
    unfiltered = None
    for oc in opencommits:
        if oc in changefilter:
            if [True for m in changefilter[oc] if m in command]:
                print 'commit %s takes credit for this change' % oc
                revdate = hgrevisiondate(oc)
                lastfname = '%s-%s-%s' % (revdate, group, oc)
                return lastfname, None
        elif not unfiltered:
            unfiltered = oc
    if unfiltered:
        print 'unfiltered commit %s takes credit for this change' % unfiltered
        revdate = hgrevisiondate(unfiltered)
        lastfname = '%s-%s-%s' % (revdate, group, unfiltered)
        return lastfname, None

    # outputs did not match, and were expected to match, considered an error
    oldsum = open(os.path.join(testfolder, 'summary.txt'), 'r').read()
    res = '%s output does not match last good for group %s\n\n' % (key, group)
    res += 'Previous last known good revision\n'
    res += hgrevisioninfo(commit).replace(os.linesep, '\n') + '\n'
    res += 'PREV: %s\n' % oldsum
    res += ' NEW: %s\n\n' % sum
    return lastfname, res



def newgoldenoutputs(seq, command, lastfname, sum, logs, tmpdir):
    '''
    A test was run and the outputs are good (match the last known good or if
    no last known good is available, these new results are taken
    '''
    commit = lastfname.split('-')[-1]
    if not save_results:
        # only save results if the testrev is a keyword change commit
        strings = changefilter.get(commit)
        if commit != testrev:
            return
        elif strings and [True for s in strings if s in command]:
            print 'allowing new golden outputs because of change keyword filter'
        else:
            return

    testhash = testcasehash(seq, command)

    # create golden folder if necessary
    if not os.path.isdir(my_goldens):
        os.mkdir(my_goldens)

    # create a new test folder if necessary
    testfolder = os.path.join(my_goldens, testhash)
    if not os.path.isdir(testfolder):
        os.mkdir(testfolder)
        fp = open(os.path.join(testfolder, 'hashed-command-line.txt'), 'w')
        fp.write('%s %s\n' % (seq, command))
        fp.close()

    # create a new golden output folder if necessary
    lastgoodfolder = os.path.join(testfolder, lastfname)
    if not os.path.isdir(lastgoodfolder):
        os.mkdir(lastgoodfolder)
        shutil.copy(os.path.join(tmpdir, 'bitstream.hevc'), lastgoodfolder)
        open(os.path.join(lastgoodfolder, 'summary.txt'), 'w').write(sum)

    addpass(testhash, lastfname, logs)
    logger.newgolden(commit)


def addpass(testhash, lastfname, logs):
    if not save_results:
        return

    folder = os.path.join(my_goldens, testhash, lastfname, 'passed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    message = logger.header + logger.build + logger.test + logs
    if os.linesep == '\r\n':
        message = message.replace(os.linesep, '\n')
    open(os.path.join(folder, fname), 'wb').write(message)


def addfail(testhash, lastfname, logs, errors):
    if not save_results:
        return

    folder = os.path.join(my_goldens, testhash, lastfname, 'failed')
    if not os.path.isdir(folder):
        os.mkdir(folder)
    nowdate = str(datetime.date.fromtimestamp(time.time()))[2:]
    fname = '%s-%s-%s.txt' % (nowdate, testrev, my_machine_name)
    message = logger.header + logger.build + logger.test + errors + logs
    if os.linesep == '\r\n':
        message = message.replace(os.linesep, '\n')
    open(os.path.join(folder, fname), 'wb').write(message)


def hashbitstream(badfn):
    m = md5.new()
    m.update(open(badfn, 'rb').read())
    return m.hexdigest()


def savebadstream(tmpdir):
    badbitstreamfolder = os.path.join(my_goldens, 'bad-streams')
    if not os.path.exists(badbitstreamfolder):
        os.mkdir(badbitstreamfolder)

    badfn = os.path.join(tmpdir, 'bitstream.hevc')
    hashname = hashbitstream(badfn)
    hashfname = os.path.join(badbitstreamfolder, hashname + '.hevc')
    shutil.copy(badfn, hashfname)
    return hashfname


def checkdecoder(tmpdir):
    cmds = [my_hm_decoder, '-b', 'bitstream.hevc']
    proc = Popen(cmds, stdout=PIPE, stderr=PIPE, cwd=tmpdir)
    stdout, errors = async_poll_process(proc, True)
    hashErrors = [l for l in stdout.splitlines() if '***ERROR***' in l]
    if hashErrors or errors:
        return 'Validation failed with %s\n\n' % my_hm_decoder + \
               '\n'.join(hashErrors + ['', errors])
    else:
        return ''


def _test(build, tmpfolder, seq, command, extras):
    '''
    Run a test encode within the specified temp folder
    Check to see if golden outputs exist:
        If they exist, verify bit-exactness or report divergence
        If not, validate new bitstream with decoder then save
    '''
    testhash = testcasehash(seq, command)

    # run the encoder, abort early if any errors encountered
    logs, sum, errors = encodeharness(build, tmpfolder, seq, command, extras)
    if errors:
        logger.testfail('encoder warning or error reported', errors, logs)
        return

    # check against last known good outputs - lastfname is the folder
    # containing the last known good outputs (or for the new ones to be
    # created)
    lastfname, errors = checkoutputs(build, seq, command, sum, tmpfolder)
    if errors is None:
        # no golden outputs for this test yet
        logger.write('validating with decoder')
        decodeerr = checkdecoder(tmpfolder)
        if decodeerr:
            hashfname = savebadstream(tmpfolder)
            decodeerr += '\nThis bitstream was saved to %s' % hashfname
            logger.testfail('Decoder validation failed', decodeerr, logs)
        else:
            logger.write('Decoder validation ok:', sum)
            newgoldenoutputs(seq, command, lastfname, sum, logs, tmpfolder)
    elif errors:
        # outputs did not match golden outputs
        fname = os.path.join(my_goldens, testhash, lastfname, 'summary.txt')
        lastsum = open(fname, 'r').read()

        decodeerr = checkdecoder(tmpfolder)
        if decodeerr:
            prefix = 'OUTPUT CHANGE WITH DECODE ERRORS'
            hashfname = savebadstream(tmpfolder)
            prefix += '\nThis bitstream was saved to %s' % hashfname
            logger.testfail(prefix, errors + decodeerr, logs)
        elif '--vbv-bufsize' in command:
            # golden outputs might have used --log=none, recover from this
            if 'N/A' in lastsum and 'N/A' not in sum:
                logger.write('saving new outputs with valid summary:', sum)
                newgoldenoutputs(seq, command, lastfname, sum, logs, tmpfolder)
                return

            # VBV encodes are non-deterministic, check that golden output
            # bitrate is within 1% of new bitrate. Example summary:
            # 'bitrate: 121.95, SSIM: 20.747, PSNR: 53.359'
            try:
                lastbitrate = float(lastsum.split(',')[0].split(' ')[1])
                newbitrate = float(sum.split(',')[0].split(' ')[1])
                diff = abs(lastbitrate - newbitrate) / lastbitrate
                diffmsg = 'VBV OUTPUT CHANGED BY %.2f%%' % (diff * 100)
            except (IndexError, ValueError), e:
                diffmsg = 'Unable to parse bitrates for %s:\n<%s>\n<%s>' % \
                           (testhash, lastsum, sum)
                diff = vbv_tolerance + 1
            if diff > vbv_tolerance:
                addfail(testhash, lastfname, logs, diffmsg)
                logger.testfail(diffmsg, '', '')
            else:
                logger.write(diffmsg)
        else:
            logger.write('FAIL')
            prefix = 'OUTPUT CHANGE: <%s> to <%s>' % (lastsum, sum)
            if save_changed:
                hashfname = savebadstream(tmpfolder)
                prefix += '\nThis bitstream was saved to %s' % hashfname
            else:
                badfn = os.path.join(tmpfolder, 'bitstream.hevc')
                prefix += '\nbitstream hash was %s' % hashbitstream(badfn)
            addfail(testhash, lastfname, logs, errors)
            logger.testfail(prefix, errors, logs)
    else:
        # outputs matched golden outputs
        addpass(testhash, lastfname, logs)
        logger.write('PASS')


def runtest(key, seq, commands, always, extras):
    '''
    Execute one complete test case (one line in a testcase file):
       key      - build keyname
       seq      - sequence basename
       commands - comma seperated list of command lines (multipass)
       always   - output-changing arguments which must always be present (hashed)
       extras   - non-output changing arguments

    Creates a temp-folder, runs the test(s), verifies, then removes the temp-
    folder.
    '''

    def skip(*matchers):
        if skip_string:
            if [True for f in matchers if skip_string in f]:
                logger.write('Skipping test', f)
                return True
        if only_string:
            if not [True for f in matchers if only_string in f]:
                return True
        return False

    logger.testcount += 1
    cmds = []
    for command in commands.split(','):
        command = command.strip()
        if always:
            command = command + ' ' + always
        testhash = testcasehash(seq, command)
        if skip(seq, command, testhash):
            return
        cmds.append((command, testhash))

    tmpfolder = tempfile.mkdtemp(prefix='x265-temp')
    try:

        for command, testhash in cmds:
            logger.settest(seq, command, extras, testhash)
            logger.write('testing x265-%s %s %s' % (key, seq, command))
            print 'extras: %s ...' % ' '.join(extras),
            sys.stdout.flush()

            _test(key, tmpfolder, seq, command, extras)

        logger.write('')

    finally:
        shutil.rmtree(tmpfolder)
